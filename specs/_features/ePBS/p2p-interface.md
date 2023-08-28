# ePBS -- Networking


This document contains the consensus-layer networking specification for ePBS.

The specification of these changes continues in the same format as the network specifications of previous upgrades, and assumes them as pre-requisite.

## Table of contents

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

##### ExecutionPayloadByHash v1

**Protocol ID:** `/eth2/beacon_chain/req/execution_payload_by_hash/1/`

The `<context-bytes>` field is calculated as `context = compute_fork_digest(fork_version, genesis_validators_root)`:

[1]: # (eth2spec: skip)

| `fork_version`           | Chunk SSZ type                |
|--------------------------|-------------------------------|
| `EPBS_FORK_VERSION`     | `epbs.EXECUTION_PAYLOAD`           |

Request Content:

```
(
  List[HASH, MAX_REQUEST_PAYLOAD]
)
```

Response Content:

```
(
  List[EXECUTION_PAYLOAD, MAX_REQUEST_PAYLOAD]
)
```


## Design decision rationale

TODO: Add