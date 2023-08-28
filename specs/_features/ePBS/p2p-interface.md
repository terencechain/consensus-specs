<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [ePBS -- Networking](#epbs----networking)
  - [Table of contents](#table-of-contents)
    - [Containers](#containers)
      - [`SignedNetworkBlock`](#signednetworkblock)
    - [The gossip domain: gossipsub](#the-gossip-domain-gossipsub)
      - [Topics and messages](#topics-and-messages)
        - [Global topics](#global-topics)
          - [`beacon_block`](#beacon_block)
          - [`execution_payload`](#execution_payload)
          - [`payload_attestation`](#payload_attestation)
          - [`execution_payload_header`](#execution_payload_header)
          - [`inclusion_list`](#inclusion_list)
      - [Transitioning the gossip](#transitioning-the-gossip)
    - [The Req/Resp domain](#the-reqresp-domain)
      - [Messages](#messages)
        - [](#)
        - [ExecutionPayloadEnvelopeByRoot v1](#executionpayloadenvelopebyroot-v1)
        - [NetworkBlockByRange v1](#networkblockbyrange-v1)
        - [NetworkBlockByRoot v1](#networkblockbyroot-v1)
  - [Design decision rationale](#design-decision-rationale)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# ePBS -- Networking


This document contains the consensus-layer networking specification for ePBS.

The specification of these changes continues in the same format as the network specifications of previous upgrades, and assumes them as pre-requisite.

## Table of contents

### Containers

#### `SignedNetworkBlock`

*[New in ePBS]*

```python
class SignedNetworkBlock(Container):
    block: SignedBeaconBlock
    payload: ExecutionPayload // Can be empty
```

### The gossip domain: gossipsub

Some gossip meshes are upgraded in the fork of ePBS to support upgraded types.

#### Topics and messages

Topics follow the same specification as in prior upgrades.

The `beacon_block` topic is modified to also support block with signed execution header and new topics are added per table below.

The derivation of the `message-id` remains stable.

The new topics along with the type of the `data` field of a gossipsub message are given in this table:

| Name                       | Message Type                                   |
|----------------------------|------------------------------------------------|
| `execution_payload_header` | `SignedExecutionPayloadHeader` [New in ePBS]   |
| `execution_payload`        | `SignedExecutionPayloadEnvelope` [New in ePBS] |
| `payload_attestation`      | `PayloadAttestation` [New in ePBS]             |
| `inclusion_list`           | `InclusionList` [New in ePBS]                  |

##### Global topics

ePBS introduces new global topics for execution header, execution payload, payload attestation and inclusion list.

###### `beacon_block`

The *type* of the payload of this topic changes to the (modified) `SignedBeaconBlock` found in ePBS spec. Specifically, this type changes with the replacement of `signed_execution_payload_header`.

In addition to the gossip validations for this topic from prior specifications, the following validations MUST pass before forwarding the `signed_beacon_block` on the network. Alias `block = signed_beacon_block.message`, `signed_header = block.body.execution_payload_header`, `header = signed_header.message`.


New validation:

- _[REJECT]_ The block's execution header timestamp is correct with respect to the slot -- i.e. `header.timestamp == compute_timestamp_at_slot(state, block.slot)`.
- _[REJECT]_ The header's builder index is a valid builder in state. 
- _[REJECT]_ The builder has sufficient balances to pay for the bid. i.e. `BUILDER_MIN_BALANCE + header.value < state.builder_balances[header.builder_index]`.
- _[REJECT]_ The builder signature, `signed_header.signature`, is valid with respect to the builder's public key.

###### `execution_payload`

This topic is used to propagate execution payload envelope `SignedExecutionPayloadEnvelope`.

The following validations MUST pass before forwarding the `signed_execution_payload_envelope` on the network, assuming the alias `payload_envelope = signed_execution_payload_envelope.message`, `payload = payload_envelope.message.payload`:

- _[IGNORE]_ The envelope's block root `payload_envelope.block_root` has been seen (via both gossip and non-gossip sources) (a client MAY queue payload for processing once the block is retrieved).
- _[IGNORE]_ The hash tree root of the payload matches the hash tree root of a payload header received previously on the `beacon_block` topic.
- _[REJECT]_ The builder signature, `signed_execution_payload_envelope.signature`, is valid with respect to the builder's public key.

###### `payload_attestation`

This topic is used to propagate signed execution attestation.

The following validations MUST pass before forwarding the `payload_attestation` on the network, assuming the alias `data = payload_attestation.data`:

- _[IGNORE]_ The attestation's `data.block_root` has been seen (via both gossip and non-gossip sources) (a client MAY queue attestation for processing once the block is retrieved. Note a client might want to request payload after).
- _[REJECT]_ The validator index is within the execution committee in `get_payload_timeliness_committee(state, slot)`
- _[REJECT]_ The signature of `payload_attestation` is valid with respect to the validator index.

###### `execution_payload_header`

This topic is used to propagate signed execution payload header.

The following validations MUST pass before forwarding the `signed_execution_payload_header` on the network, assuming the alias `header = signed_execution_payload_header.message`:

- _[REJECT]_ The signed builder bid pubkey, `header.builder_index` is a valid and non-slashed builder index in state.
- _[IGNORE]_ The signed builder bid value, `header.value`, is less than the builder minimum balance in state.  i.e. `MIN_BUILDER_BALANCE + header.value < state.builder_balances[header.builder_index]`.
- _[IGNORE]_ The signed builder header timestamp is correct with respect to next slot -- i.e. `header.timestamp == compute_timestamp_at_slot(state, current_slot + 1)`.
- _[IGNORE]_ The signed builder header parent block matches one of the chain tip(s) in the fork choice store. Builder may submit multiple bids corresponding to various forks.
- _[REJECT]_ The builder signature, `signed_bid.signature`, is valid with respect to the `header.builder_index`.

###### `inclusion_list`

This topic is used to propagate inclusion list.

The following validations MUST pass before forwarding the `inclusion_list` on the network, assuming the alias `signed_summary = inclusion_list.summary`, `summary = signed_summary.message`:

- _[REJECT]_ The inclusion list transactions `inclusion_list.transactions` length is within upperbound `MAX_TRANSACTIONS_PER_INCLUSION_LIST`.
- _[REJECT]_ The inclusion list summery has the same length of transactions `len(summary.summary) == len(inclusion_list.transactions)`.
- _[REJECT]_ The summary signature, `signed_summary.signature`, is valid with respect to the `proposer_index` pubkey.
- _[REJECT]_ The summary is proposed by the expected proposer_index for the summary's slot in the context of the current shuffling (defined by parent_root/slot). If the proposer_index cannot immediately be verified against the expected shuffling, the inclusion list MAY be queued for later processing while proposers for the summary's branch are calculated -- in such a case do not REJECT, instead IGNORE this message.

#### Transitioning the gossip

See gossip transition details found in the [Altair document](../altair/p2p-interface.md#transitioning-the-gossip) for
details on how to handle transitioning gossip topics for this upgrade.

### The Req/Resp domain

#### Messages

##### 

##### ExecutionPayloadEnvelopeByRoot v1

**Protocol ID:** `/eth2/beacon_chain/req/execution_payload_envelope_by_root/1/`

The `<context-bytes>` field is calculated as `context = compute_fork_digest(fork_version, genesis_validators_root)`:

[1]: # (eth2spec: skip)

| `fork_version`      | Chunk SSZ type                        |
|---------------------|---------------------------------------|
| `EPBS_FORK_VERSION` | `epbs.SignedExecutionPayloadEnvelope` |

Request Content:

```
(
  List[Root, MAX_REQUEST_PAYLOAD]
)
```

Response Content:

```
(
  List[SignedExecutionPayloadEnvelope, MAX_REQUEST_PAYLOAD]
)
```
Requests execution payload envelope by `signed_execution_payload_envelope.message.block_root`. The response is a list of SignedExecutionPayloadEnvelope whose length is less than or equal to the number of requested execution payload envelopes. It may be less in the case that the responding peer is missing payload envelopes.

No more than MAX_REQUEST_PAYLOAD may be requested at a time.

ExecutionPayloadEnvelopeByRoot is primarily used to recover recent execution payload envelope (e.g. when receiving a payload attestation with revealed status as true but never received a payload).

The request MUST be encoded as an SSZ-field.

The response MUST consist of zero or more response_chunk. Each successful response_chunk MUST contain a single SignedExecutionPayloadEnvelope payload.

Clients MUST support requesting payload envelopes since the latest finalized epoch.

Clients MUST respond with at least one payload envelope, if they have it. Clients MAY limit the number of payload envelopes in the response.

##### NetworkBlockByRange v1

**Protocol ID:** `/eth2/beacon_chain/req/network_block_by_range/1/`

This replaces `BeaconBlockByRange` from prior specifications starting at ePBS fork.

/eth2/beacon_chain/req/beacon_blocks_by_range/2/ is deprecated. Clients MAY respond with an empty list during the deprecation transition period.

The `<context-bytes>` field is calculated as `context = compute_fork_digest(fork_version, genesis_validators_root)`:

[1]: # (eth2spec: skip)

| `fork_version`      | Chunk SSZ type            |
|---------------------|---------------------------|
| `EPBS_FORK_VERSION` | `epbs.SignedNetworkBlock` |

Request Content:

```
(
  start_slot: Slot
  count: uint64
  step: uint64 # Deprecated, must be set to 1
)
```

Response Content:

```
(
  List[SignedNetworkBlock, MAX_REQUEST_BLOCK]
)
```

NetworkBlockByRange is primarily used to sync historical blocks and payloads.

Clients must respond execution payloads alongside the blocks if available.

Clients must respond null execution payload if not available.

##### NetworkBlockByRoot v1

**Protocol ID:** `/eth2/beacon_chain/req/network_block_by_root/1/`

This replaces `BeaconBlockByRoot` from prior specifications starting at ePBS fork.

/eth2/beacon_chain/req/beacon_blocks_by_root/2/ is deprecated. Clients MAY respond with an empty list during the deprecation transition period.

The `<context-bytes>` field is calculated as `context = compute_fork_digest(fork_version, genesis_validators_root)`:

[1]: # (eth2spec: skip)

| `fork_version`      | Chunk SSZ type            |
|---------------------|---------------------------|
| `EPBS_FORK_VERSION` | `epbs.SignedNetworkBlock` |

Request Content:

```
(
  List[Root, MAX_REQUEST_BLOCKS]
)
```

Response Content:

```
(
  List[SignedNetworkBlock, MAX_REQUEST_BLOCK]
)
```

NetworkBlockByRoot is primarily used to recover recent blocks and payloads (e.g. when receiving a block or attestation whose parent is unknown).

Clients must respond execution payloads alongside the blocks if available.

Clients must respond null execution payload if not available.

## Design decision rationale

TODO: Add