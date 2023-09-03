<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [ePBS -- Honest Validator](#epbs----honest-validator)
  - [Introduction](#introduction)
  - [Prerequisites](#prerequisites)
  - [Beacon chain responsibilities](#beacon-chain-responsibilities)
  - [Validator assignment](#validator-assignment)
    - [Lookahead](#lookahead)
    - [Block proposal](#block-proposal)
      - [Constructing the new `signed_execution_payload_header_envelope` field in  `BeaconBlockBody`](#constructing-the-new-signed_execution_payload_header_envelope-field-in--beaconblockbody)
      - [Constructing the new `payload_attestations` field in  `BeaconBlockBody`](#constructing-the-new-payload_attestations-field-in--beaconblockbody)
    - [Consensus attesting remains unchanged](#consensus-attesting-remains-unchanged)
    - [Consensus attestation aggregation reminds unchanged](#consensus-attestation-aggregation-reminds-unchanged)
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

## Beacon chain responsibilities

All validator responsibilities remain unchanged other than those noted below. Namely, proposer normal block production switched to a new `BeaconBlockBody`.
Proposer with additional duty to broadcast `InclusionList`.
Attester with chance with an additional duty to submit `PayloadAttestationMessage`.

## Validator assignment

### Lookahead

The beacon chain shufflings are designed to provide a minimum of 1 epoch lookahead
on the validator's upcoming payload attestation committee assignments for attesting dictated by the shuffling and slot.

`get_ptc` should be called at the start of each epoch
to get the assignment for the next epoch (`current_epoch + 1`).
A validator should plan for future assignments by noting their assigned attestation

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

### Consensus attesting remains unchanged

### Consensus attestation aggregation reminds unchanged

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
def get_payload_attestation_signature(state: BeaconState, attestation: PayloadAttestationMessage, privkey: int) -> BLSSignature:
    domain = get_domain(state, DOMAIN_PAYLOAD_TIMELINESS_COMMITTEE, compute_epoch_at_slot(attestation.slot))
    signing_root = compute_signing_root(attestation, domain)
    return bls.Sign(privkey, signing_root)
```

#### Broadcast payload attestation

Finally, the validator broadcasts `payload_attestation_message` to the global `payload_attestation_message` pubsub topic.
