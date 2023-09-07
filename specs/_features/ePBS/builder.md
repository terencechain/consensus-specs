<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [ePBS -- Honest Builder](#epbs----honest-builder)
  - [Introduction](#introduction)
  - [Becoming a builder](#becoming-a-builder)
    - [Initialization](#initialization)
        - [Builder withdrawal credential](#builder-withdrawal-credential)
    - [Submit deposit](#submit-deposit)
    - [Process deposit](#process-deposit)
    - [Activation](#activation)
  - [Beacon chain responsibilities](#beacon-chain-responsibilities)
    - [Signed execution payload header envelope proposal](#signed-execution-payload-header-envelope-proposal)
      - [Constructing the `SignedExecutionPayloadHeaderEnvelope`](#constructing-the-signedexecutionpayloadheaderenvelope)
      - [Broadcast execution payload header envelope](#broadcast-execution-payload-header-envelope)
    - [Signed execution payload envelope construction](#signed-execution-payload-envelope-construction)
  - [Design Decision Rationale](#design-decision-rationale)
    - [How does builder to proposer payment work?](#how-does-builder-to-proposer-payment-work)
    - [How does same slot unbundling happen? (common case)](#how-does-same-slot-unbundling-happen-common-case)
    - [What if builder sees  proposer equivocate?](#what-if-builder-sees--proposer-equivocate)

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

First, the builder need obtain an execution payload. The builder building on top of block on top of `state` must ake the following actions through execution layer

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

2. Set `execution_payload`, where:

```python
def get_execution_payload(payload_id: Optional[PayloadId], execution_engine: ExecutionEngine) -> ExecutionPayload:
        return execution_engine.get_payload(payload_id).execution_payload
```

3. Convert the `ExecutionPayload` to `ExecutionPayloadHeader` by calling `convert_payload_to_header(payload)`

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
4. Build `ExecutionPayloadHeaderEnvelope`
- Set `header` to the `ExecutionPayloadHeader` from step 3
- Set `builder_index` to the index of the builder in the beacon state
- Set `value` to the bid value (ie. how much Gwei builder is willing to pay the proposer if the block is included)

5. Sign the `ExecutionPayloadHeaderEnvelope` with the builder's private key

```python
def get_execution_payload_header_envelope(state: BeaconState, header: ExecutionPayloadHeaderEnvelope, privkey: int) -> BLSSignature:
    domain = get_domain(state, DOMAIN_BEACON_BUILDER, compute_epoch_at_slot(state.slot))
    signing_root = compute_signing_root(header, domain)
    return bls.Sign(privkey, signing_root)
```

6. Build `SignedExecutionPayloadHeaderEnvelope`
- Set `header` to the `ExecutionPayloadHeaderEnvelope` from step 4
- Set `signature` to the `BLSSignature` from step 5

#### Broadcast execution payload header envelope

Finally, the validator broadcasts `execution_payload_header_envelope` to the global `execution_payload_header_envelope` pubsub topic.

### Signed execution payload envelope construction 

TBD


## Design Decision Rationale

### How does builder to proposer payment work?

- Builder to proposer payment is unconditional after processing the signed execution payload header and the block remains head and canonical throughout. The builder will not lose the bid if the block is reorged.

### How does same slot unbundling happen? (common case)

- There are cases to consider for same slot unbundling. the common case is proposer equivocate and broadcast the equivocated block to the network after builder has revealed the payload. In this case, the next slot proposer will also have to collude and build on the equivocated block.

### What if builder sees  proposer equivocate?

- At the time of reveal, the builder has counted attestations for the beacon block, even if there are or not equivocations. Before the reveal deadline, proposer can not unbundle because builder has not revealed payload.
- If the original beacon block to which the builder committed is included, then the builder doesn't lose anything, that was the original intent. So if the original block is the overwhelming winner at the time of reveal, the builder can simply reveal and be safe that if there are any equivocations anyway his block was included.
- If the builder reveals, he knows that he can never be unbundled unless the current and next committee have a majority of malicious validators. Where attestations vote empty block before a block that is revealed after the reveal deadline.
- Since the builder cannot be unbundled, then he either doesn't pay if the block is not included, or pays and if it is included.
- The splitting grief, that is, the proposer's block has about 50% of the vote at reveal deadline is still an open problem.