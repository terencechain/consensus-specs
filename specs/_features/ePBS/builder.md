# ePBS -- Honest Builder

**Notice**: This document is a work-in-progress for researchers and implementers.


## Introduction

This document represents the changes to be made in the code of an "honest builder" to implement ePBS.

## Becoming a builder

### Initialization

A builder must initialize many parameters locally before submitting a deposit and joining the builder registry.

Refer BLS public key and Withdrawal credentials to phase 0 validator spec.

### Submit deposit

TODO:


## Beacon chain responsibilities


### Signed builder bid proposal

At slot `N`, builder constructs `SignedBuilderBid` and broadcasts to `builder_bid` gossip topic for slot `N+1` block proposal.
Builder may submit multiple `SignedBuilderBid` for different chain tips, but builder should only submit one bid per chain tip.


### Signed builder bid reveal

At slot `N+1`, builder observes proposer at `N+1` proposed a block using the bid constructed at `N`. If the proposer used the builder bid, the builder has to make a note for the following duty.

At `SECONDS_PER_SLOT * 2 / INTERVALS_PER_SLOT` seconds, if the builder did not observe equivocation for the block, builder will reveal the payload by broadcasting it to the `execution_payload` gossip topic. By monitoring equivocation, this prevents same-slot unbundling.


### Signed builder bid reveal (conservative mode)

Builder monitors all the beacon attestation subnets and observe all the attestations. Builder should not reveal payload if only few attestations for current slot and many attestations for parent slot and bid is not large enough. This prevents next-slot re-orging