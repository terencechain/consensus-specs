<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [ePBS -- Honest Builder](#epbs----honest-builder)
  - [Introduction](#introduction)
  - [Becoming a builder](#becoming-a-builder)
    - [Initialization](#initialization)
    - [Deposit amount](#deposit-amount)
        - [Builder withdrawal credential](#builder-withdrawal-credential)
    - [Submit deposit](#submit-deposit)
    - [Process deposit](#process-deposit)
    - [Activation](#activation)
  - [Beacon chain responsibilities](#beacon-chain-responsibilities)
    - [Signed execution payload header envelope proposal](#signed-execution-payload-header-envelope-proposal)
      - [Constructing the `SignedExecutionPayloadHeaderEnvelope`](#constructing-the-signedexecutionpayloadheaderenvelope)
      - [Broadcast execution payload header envelope](#broadcast-execution-payload-header-envelope)
    - [Signed execution payload envelope construction](#signed-execution-payload-envelope-construction)
      - [Determine if it is safe to reveal](#determine-if-it-is-safe-to-reveal)
      - [Constructing the `SignedExecutionPayloadEnvelope`](#constructing-the-signedexecutionpayloadenvelope)
      - [Broadcast execution payload envelope](#broadcast-execution-payload-envelope)
      - [Broadcast blob sidecars](#broadcast-blob-sidecars)
  - [Design Decision Rationale](#design-decision-rationale)
    - [What are the changes with regard to blob sidecars?](#what-are-the-changes-with-regard-to-blob-sidecars)
    - [How does builder to proposer payment work?](#how-does-builder-to-proposer-payment-work)
    - [Should the builder worry about same slot unbundling?](#should-the-builder-worry-about-same-slot-unbundling)
    - [What if builder sees proposer equivocate?](#what-if-builder-sees-proposer-equivocate)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# ePBS -- Honest Builder

**Notice**: This document is a work-in-progress for researchers and implementers.


## Introduction

This document represents the expected behavior of an "honest builder" with respect to ePBS of the Ethereum proof-of-stake protocol. 
This document does not distinguish between a "node" (i.e. the functionality of following and reading the beacon chain) and a "builder" (i.e. the functionality of actively participating in consensus).
The separation of concerns between these (potentially) two pieces of software is left as a design decision that is out of scope.

A builder is an entity that participates in the block building of the Ethereum proof-of-stake protocol. This is an optional role for users in which they can post ETH as collateral and build blocks to see financial returns in exchange for building the protocol.
In this design, builder is an extension of validator using a different withdrawal prefix `0x0b`. The protocol onboards builder by upgrading validators into builders if minimal staked balance is reached.

## Becoming a builder

### Initialization

A builder must initialize many parameters locally before submitting a deposit and joining the builder registry.

Refer key general from the phase 0 validator spec.

### Deposit amount

The initial deposit amount is the amount of ETH that the builder is willing to stake in order to become a builder. 
The builder must keep a minimal balance of `BUILDER_MIN_BALANCE` to remain a builder for block building duty.

##### Builder withdrawal credential

Builder Withdrawal credentials with the builder withdrawal prefix specify
a 20-byte Eth1 address `eth1_withdrawal_address` as the recipient for all withdrawals.
The `eth1_withdrawal_address` can be the address of either an externally owned account or of a contract.

The `withdrawal_credentials` field must be such that:

* `withdrawal_credentials[:1] == BUILDER_WITHDRAWAL_PREFIX` [New in ePBS]
* `withdrawal_credentials[1:12] == b'\x00' * 11`
* `withdrawal_credentials[12:] == eth1_withdrawal_address`

### Submit deposit

No change from phase 0 validator spec.

### Process deposit

No change from phase 0 validator spec.

### Activation

No change from phase 0 validator spec.


## Beacon chain responsibilities


### Signed execution payload header envelope proposal

#### Constructing the `SignedExecutionPayloadHeaderEnvelope`

<<<<<<< Updated upstream
First, the builder needs to obtain an execution payload. The builder building on top of block on top of `state` must take the following actions through execution layer

=======
First, the builder needs to obtain an execution payload. The builder building on top of block on top of `s
>>>>>>> Stashed changes
1. Set `payload_id = prepare_execution_payload(state, pow_chain, safe_block_hash, finalized_block_hash, suggested_fee_recipient, execution_engine)`, where:
  * `state` is the state object after applying `process_slots(state, slot)` transition to the resulting state of the parent block processing
  * `safe_block_hash` is the return value of the `get_safe_execution_payload_hash(store: Store)` function call
  * `finalized_block_hash` is the hash of the latest finalized execution payload (`Hash32()` if none yet finalized)
  * `suggested_fee_recipient` is the value suggested to be used for the `fee_recipient` field of the builder


```python
def prepare_execution_payload(state: BeaconState,
                              safe_block_hash: Hash32,
                              finalized_block_hash: Hash32,
                              suggested_fee_recipient: ExecutionAddress,
                              execution_engine: ExecutionEngine) -> Optional[PayloadId]:
    # Set the forkchoice head and initiate the payload build process
    payload_attributes = PayloadAttributes(
        timestamp=compute_timestamp_at_slot(state, state.slot),
        prev_randao=get_randao_mix(state, get_current_epoch(state)),
        suggested_fee_recipient=suggested_fee_recipient,
    )
    return execution_engine.notify_forkchoice_updated(
        head_block_hash=parent_hash,
        safe_block_hash=safe_block_hash,
        finalized_block_hash=finalized_block_hash,
        payload_attributes=payload_attributes,
    )
```

2. Set `ExecutionPayload`, where:

```python
def get_execution_payload(payload_id: Optional[PayloadId], execution_engine: ExecutionEngine) -> ExecutionPayload:
        return execution_engine.get_payload(payload_id).execution_payload
```

3. Builder should cache the `ExecutionPayload` and `BlobsBundle` for later use.

4. Convert the `ExecutionPayload` to `ExecutionPayloadHeader` by calling `convert_payload_to_header(payload)`

```python
def convert_payload_to_header(payload: ExecutionPayload) -> ExecutionPayloadHeader:
    return ExecutionPayloadHeader(
        parent_hash=payload.parent_hash,
        fee_recipient=payload.fee_recipient,
        state_root=payload.state_root,
        receipts_root=payload.receipts_root,
        logs_bloom=payload.logs_bloom,
        prev_randao=payload.prev_randao,
        block_number=payload.block_number,
        gas_limit=payload.gas_limit,
        gas_used=payload.gas_used,
        timestamp=payload.timestamp,
        extra_data=payload.extra_data,
        base_fee_per_gas=payload.base_fee_per_gas,
        block_hash=payload.block_hash,
        transactions_root=hash_tree_root(payload.transactions),
        withdrawals_root=hash_tree_root(payload.withdrawals),
        blob_gas_used=payload.blob_gas_used,
        excess_blob_gas=payload.excess_blob_gas,
        inclusion_list_summary_root=hash_tree_root(payload.inclusion_list_summary),
        inclusion_list_exclutions_root=hash_tree_root(payload.inclusion_list_exclutions),
    )
```
5. Build `ExecutionPayloadHeaderEnvelope`
- Set `header` to the `ExecutionPayloadHeader` from step 3
- Set `builder_index` to the index of the builder in the beacon state
- Set `value` to the bid value (ie. how much Gwei builder is willing to pay the proposer if the block is included)

6. Sign the `ExecutionPayloadHeaderEnvelope` with the builder's private key

```python
def get_execution_payload_header_envelope(state: BeaconState, header: ExecutionPayloadHeaderEnvelope, privkey: int) -> BLSSignature:
    domain = get_domain(state, DOMAIN_BEACON_BUILDER, compute_epoch_at_slot(state.slot))
    signing_root = compute_signing_root(header, domain)
    return bls.Sign(privkey, signing_root)
```

7. Build `SignedExecutionPayloadHeaderEnvelope`
- Set `header` to the `ExecutionPayloadHeaderEnvelope` from step 4
- Set `signature` to the `BLSSignature` from step 5

#### Broadcast execution payload header envelope

Finally, the validator broadcasts `signed_execution_payload_header_envelope` to the `execution_payload_header_envelope` pubsub topic.

### Signed execution payload envelope construction 

#### Determine if it is safe to reveal

The builder should reveal if it observes the following conditions:
- The block containing the payload header is valid

#### Constructing the `SignedExecutionPayloadEnvelope`

1. Build `ExecutionPayloadEnvelope`
- Set `payload`  to the saved `execution_payload` from constructing the header.
- Set `builder_index` to the index of the builder.
- Set `beacon_block_root` to the block root of the block containing the payload header.
- Set `blob_kzg_commitments` to the kzg commitments from the saved blobs bundle `blobs_bundle.kzg_commitments`.
- Set `state_root` to the state root after processing head block.

2. Sign the `ExecutionPayloadEnvelope` with the builder's private key

```python
def get_execution_payload_envelope(state: BeaconState, payload: ExecutionPayloadEnvelope, privkey: int) -> BLSSignature:
    domain = get_domain(state, DOMAIN_BEACON_BUILDER, compute_epoch_at_slot(state.slot))
    signing_root = compute_signing_root(payload, domain)
    return bls.Sign(privkey, signing_root)
```

3. Build `SignedExecutionPayloadEnvelope`
- Set `message` to the `ExecutionPayloadEnvelope` from step 1
- Set `signature` to the `BLSSignature` from step 2

#### Broadcast execution payload envelope

Finally, the builder broadcasts `signed_execution_payload_envelope` to the global `execution_payload_envelope` pubsub topic.

#### Broadcast blob sidecars

`SignedBlobSidecars`s constructions remain the same as in the deneb spec. The builder will broadcast `SignedBlobSidecars` to the global `blob_sidecars` pubsub topic the same time as `SignedExecutionPayloadEnvelope` is broadcasted.
Builder may broadcast `SignedBlobSidecars` before `SignedExecutionPayloadEnvelope` if it is safe to reveal. (ie. the head block contains the payload header)

## Design Decision Rationale

### What are the changes with regard to blob sidecars?
- Builder does not have to commit KZG commitments at the header phase. Given transaction contains versioned hashes, it's committed implicitly there given the transaction root.
- This means KZG will only be known at the payload phase, and the commitments are moved from block body to the execution payload envelope.
- Builder will gossip blob sidecars at the same time as the execution payload envelope. This is to ensure that the blob sidecars are available to the proposer when the proposer is building the block.
- Builder may gossip the blob sidecars earlier than the execution payload.

### How does builder to proposer payment work?

- Builder to proposer payment is unconditional after processing the signed execution payload header and the block remains head and canonical throughout. The builder will not lose the bid if the block is reorged.

### Should the builder worry about same slot unbundling?

- There are cases to consider for same slot unbundling. the common case is proposer equivocate and broadcast the equivocated block to the network after builder has revealed the payload. In this case, the next slot proposer will also have to collude and build on the equivocated block.
- Besides the above, a vast majority of the committee attesters would also have voted for the previous head.

### What if builder sees proposer equivocate?

- At the time of reveal, the builder has counted attestations for the beacon block, even if there are or not equivocations. Before the reveal deadline, proposer can not unbundle because builder has not revealed payload.
- If the original beacon block to which the builder committed is included, then the builder doesn't lose anything, that was the original intent. So if the original block is the overwhelming winner at the time of reveal, the builder can simply reveal and be safe that if there are any equivocations anyway his block was included.
- If the builder reveals, he knows that he can never be unbundled unless the current and next committee have a majority of malicious validators. Where attestations vote empty block before a block that is revealed after the reveal deadline.
- Since the builder cannot be unbundled, then he either doesn't pay if the block is not included, or pays and if it is included.
- The splitting grief, that is, the proposer's block has about 50% of the vote at reveal deadline is still an open problem.
