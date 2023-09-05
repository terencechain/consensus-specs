<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [ePBS -- Honest Validator](#epbs----honest-validator)
  - [Introduction](#introduction)
  - [Prerequisites](#prerequisites)
  - [Protocols](#protocols)
    - [`ExecutionEngine`](#executionengine)
      - [`get_inclusion_list`](#get_inclusion_list)
  - [Beacon chain responsibilities](#beacon-chain-responsibilities)
  - [Validator assignment](#validator-assignment)
    - [Lookahead](#lookahead)
    - [Inclusion list proposal](#inclusion-list-proposal)
      - [Constructing the `InclusionList`](#constructing-the-inclusionlist)
      - [Broadcast inclusion list](#broadcast-inclusion-list)
    - [Block proposal](#block-proposal)
      - [Constructing the new `signed_execution_payload_header_envelope` field in  `BeaconBlockBody`](#constructing-the-new-signed_execution_payload_header_envelope-field-in--beaconblockbody)
      - [Constructing the new `payload_attestations` field in  `BeaconBlockBody`](#constructing-the-new-payload_attestations-field-in--beaconblockbody)
    - [Attesting remains unchanged](#attesting-remains-unchanged)
    - [Attestation aggregation](#attestation-aggregation)
      - [Aggregation selection](#aggregation-selection)
    - [Payload timeliness attestation](#payload-timeliness-attestation)
      - [Constructing payload attestation](#constructing-payload-attestation)
        - [Prepare payload attestation message](#prepare-payload-attestation-message)
      - [Broadcast payload attestation](#broadcast-payload-attestation)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# ePBS -- Honest Validator

**Notice**: This document is a work-in-progress for researchers and implementers.

## Introduction

This document represents the changes to be made in the code of an "honest validator" to implement ePBS.

## Prerequisites

This document is an extension of the Deneb -- Honest Validator guide.
All behaviors and definitions defined in this document, and documents it extends, carry over unless explicitly noted or overridden.

All terminology, constants, functions, and protocol mechanics defined in the updated Beacon Chain doc of ePBS. are requisite for this document and used throughout.
Please see related Beacon Chain doc before continuing and use them as a reference throughout.

## Protocols

### `ExecutionEngine`

*Note*: `get_inclusion_list` function is added to the `ExecutionEngine` protocol for use as a validator.

The body of this function is implementation dependent.
The Engine API may be used to implement it with an external execution engine.

#### `get_inclusion_list`

Given the `payload_id`, `get_payload` returns `GetInclusionListResponse` with the most recent version of
the execution payload that has been built since the corresponding call to `notify_forkchoice_updated` method.

```python
def get_inclusion_list(self: ExecutionEngine, payload_id: PayloadId) -> GetInclusionListResponse:
    """
    Return ``GetInclusionListResponse`` object.
    """
    ...
```

## Beacon chain responsibilities

All validator responsibilities remain unchanged other than those noted below. Namely, proposer normal block production switched to a new `BeaconBlockBody`.
Proposer with additional duty to construct and broadcast `InclusionList` alongside `SignedBeaconBlock`.
Attester by chance with an additional duty to be part of PTC committee and broadcast `PayloadAttestationMessage`.

## Validator assignment

A validator can get PTC committee assignments for a given epoch using the following helper via `get_ptc_committee_assignment(state, epoch, validator_index)` where `epoch <= next_epoch`.

A validator can use the following function to see if they are supposed to submit payload attestation message during a slot. 
This function can only be run with a `state` of the slot in question. PTC committee selection is only stable within the context of the current and next epoch.

```python
def get_ptc_committee_assignment(state: BeaconState,
                             epoch: Epoch,
                             validator_index: ValidatorIndex
                             ) -> Optional[Tuple[Sequence[ValidatorIndex], Slot]]:
    """
    Return the ptc committee assignment in the ``epoch`` for ``validator_index``.
    ``assignment`` returned is a tuple of the following form:
        * ``assignment[0]`` is the list of validators in the committee
        * ``assignment[1]`` is the slot at which the committee is assigned
    Return None if no assignment.
    """
    next_epoch = Epoch(get_current_epoch(state) + 1)
    assert epoch <= next_epoch

    start_slot = compute_start_slot_at_epoch(epoch)
    committee_count_per_slot = get_committee_count_per_slot(state, epoch)
    for slot in range(start_slot, start_slot + SLOTS_PER_EPOCH):
        for index in range(committee_count_per_slot):
            committee = get_ptc_committee(state, Slot(slot))
            if validator_index in committee:
                return committee, Slot(slot)
    return None
```

### Lookahead

The beacon chain shufflings are designed to provide a minimum of 1 epoch lookahead
on the validator's upcoming committee assignments for attesting dictated by the shuffling and slot.
Note that this lookahead does not apply to proposing, which must be checked during the epoch in question.

`get_ptc_committee_assignment` should be called at the start of each epoch
to get the assignment for the next epoch (`current_epoch + 1`).
A validator should plan for future assignments by noting their assigned ptc committee
slot and planning to participate in the ptc committee subnet.

Specifically a validator should:
* Find peers of the pubsub topic `beacon_attestation_{subnet_id}`.
    * If the validator is assigned to be an aggregator for the slot (see `is_aggregator()`) [New in MaxEB], then subscribe to the topic.

### Inclusion list proposal

ePBS introduces forward inclusion list. The detail design is described in this [post](https://ethresear.ch/t/no-free-lunch-a-new-inclusion-list-design/16389)
Proposer is introduced to construct and broadcast `InclusionList` alongside `SignedBeaconBlock`.
- Proposer for slot `N` submits `SignedBeaconBlock` and in parallel submits `InclusionList` to be included at the beginning of slot `N+1`.
- Within `InclusionList`, `Transactions` are list of transactions that the proposer wants to include at the beginning of slot `N+1`.
- Within `inclusionList`, `Summaries` are lists consisting on addresses sending those transactions and their gas limits. The summaries are signed by the proposer.
- Proposer is allowed to send many of these pairs that aren't committed to its beacon block so no double proposing slashing is involved.

#### Constructing the `InclusionList`

To obtain an inclusion, a block proposer building a block on top of a `state` must take the following actions:

1. Retrieve inclusion list by calling `get_inclusion_list`.

```python
def get_inclusion_list(payload_id: Optional[PayloadId], execution_engine: ExecutionEngine) -> InclusionListResponse:
        return execution_engine.get_payload(payload_id).inclusion_list
```

2. Build `InclusionListSummary`
 - Set `summary` to the `inclusion_list_response.summary`
 - Set `proposer_index` to the proposer's index

3. Get `signature` by signing `InclusionListSummary` with its private key.

```python
def get_inclusion_list_summary_signature(state: BeaconState, inclusion_list_summary: InclusionListSummary, block_slot: Slot, privkey: int) -> BLSSignature:
    domain = get_domain(state, DOMAIN_INCLUSION_LIST, compute_epoch_at_slot(block_slot))
    signing_root = compute_signing_root(inclusion_list_summary, domain)
    return bls.Sign(privkey, signing_root)
```

4. Build `SignedInclusionListSummary`
 - set `signed_inclusion_list_summary.summary` to `InclusionListSummary`
 - set `signed_inclusion_list_summary.signature` to `signature

5. Build `InclusionList
- set `inclusion_list.summaries` to `SignedInclusionListSummary`
- set `inclusion_list.transactions` to `inclusion_list_response.transactions`

#### Broadcast inclusion list

Finally, the validator broadcasts inclusion to the inclusion list subnet, the `inclusion_list` pubsub topic.

### Block proposal

#### Constructing the new `signed_execution_payload_header_envelope` field in  `BeaconBlockBody`

To obtain `signed_execution_payload_header_envelope`, a block proposer building a block on top of a `state` must take the following actions:
* Listen to the `execution_payload_header` gossip subnet
* Filter out the bids where `signed_execution_payload_header_envelope.message.header.parent_hash` matches `state.latest_execution_payload_header.block_hash`
* The `signed_execution_payload_header_envelope` must satisfy the verification conditions found in `process_execution_payload_header`.
* Select the best bid and set `body.signed_execution_payload_header_envelope = signed_execution_payload_header_envelope`

#### Constructing the new `payload_attestations` field in  `BeaconBlockBody`

Up to `MAX_PAYLOAD_ATTESTATIONS`, aggregate payload attestations can be included in the block. 
The payload attestations added must satisfy the verification conditions found in payload attestation processing. 
To maximize profit, the validator should attempt to gather aggregate payload attestations that include singular attestations from the largest number of validators whose signatures from the same epoch have not previously been added on chain.

### Attesting remains unchanged

### Attestation aggregation

Some validators are selected to locally aggregate attestations with a similar `attestation_data` to their constructed `attestation` for the assigned `slot`.

#### Aggregation selection

A validator is selected to aggregate based upon the return value of `is_aggregator()`. [New in MaxEB]. Taken from [PR](https://github.com/michaelneuder/consensus-specs/pull/3)

```python
def is_aggregator(state: BeaconState, slot: Slot, index: CommitteeIndex, validator_index: ValidatorIndex, slot_signature: BLSSignature) -> bool:
    validator = state.validators[validator_index]
    committee = get_beacon_committee(state, slot, index)
    min_balance_increments = validator.effective_balance // MIN_ACTIVATION_BALANCE
    committee_balance_increments = get_total_balance(state, set(committee)) // MIN_ACTIVATION_BALANCE
    denominator = committee_balance_increments ** min_balance_increments
    numerator = denominator - (committee_balance_increments -  TARGET_AGGREGATORS_PER_COMMITTEE) ** min_balance_increments
    modulo = denominator // numerator
    return bytes_to_uint64(hash(slot_signature)[0:8]) % modulo == 0
```

Rest of the aggregation process remains unchanged.

### Payload timeliness attestation

Some validators are selected to submit payload timeliness attestation. The `committee`, assigned `index`, and assigned `slot` for which the validator performs this role during an epoch are defined by `get_execution_committee(state, slot)`.

A validator should create and broadcast the `execution_attestation` to the global execution attestation subnet at `SECONDS_PER_SLOT * 3 / INTERVALS_PER_SLOT` seconds after the start of `slot`

#### Constructing payload attestation

##### Prepare payload attestation message
If a validator is in the payload attestation committee (i.e. `is_assigned_to_payload_committee()` above returns True), 
then the validator should prepare a `PayloadAttestationMessage` for the current slot,
according to the logic in `get_payload_attestation_message` at `SECONDS_PER_SLOT * 3 / INTERVALS_PER_SLOT` interval.

```python
def is_assigned_to_payload_committee(state: BeaconState,
                                  slot: Slot,
                                  validator_index: ValidatorIndex) -> bool:
                                                     
    committe = get_ptc(state, slot)
    return validator_index in committee
```

Next, the validator creates `payload_attestation_message` as follows:
* Set `payload_attestation_data.slot = slot` where `slot` is the assigned slot.
* Set `payload_attestation_data.beacon_block_root = block_root` where `block_root` is the block hash seen from the block builder reveal at `SECONDS_PER_SLOT * 2 / INTERVALS_PER_SLOT`. If the `SignedExecutionPayloadEnvelope`
* Set `payload_attestation_message.validator_index = validator_index` where `validator_index` is the validator chosen to submit. The private key mapping to `state.validators[validator_index].pubkey` is used to sign the payload timeliness attestation.
* Set `payload_attestation_message = PayloadAttestationMessage(data=payload_attestation_data, signature=payload_attestation_signature)`, where `payload_attestation_signature` is obtained from:

```python
def get_payload_attestation_message_signature(state: BeaconState, attestation: PayloadAttestationMessage, privkey: int) -> BLSSignature:
    domain = get_domain(state, DOMAIN_PAYLOAD_TIMELINESS_COMMITTEE, compute_epoch_at_slot(attestation.slot))
    signing_root = compute_signing_root(attestation, domain)
    return bls.Sign(privkey, signing_root)
```

#### Broadcast payload attestation

Finally, the validator broadcasts `payload_attestation_message` to the global `payload_attestation_message` pubsub topic.
