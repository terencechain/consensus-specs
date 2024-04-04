# ePBS -- Honest Builder

This is an accompanying document which describes the expected actions of a "builder" participating in the Ethereum proof-of-stake protocol.

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->


<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## Introduction

With the ePBS Fork, the protocol includes new staked participants of the protocol called *Builders*. While Builders are a subset of the validator set, they have extra attributions that are optional. Validators may opt to not be builders and as such we collect the set of guidelines for those validators that want to act as builders in this document. 

## Builders attributions

Builders can submit bids to produce execution payloads. They can broadcast these bids in the form of `SignedExecutionPayloadHeader` objects, these objects encode a commitment to to reveal a full execution payload in exchange for a payment. When their bids are chosen by the corresponding proposer, builders are expected to broadcast an accompanying `SignedExecutionPayloadEnvelope` object honoring the commitment. 

Thus, builders tasks are divided in two, submitting bids, and submitting payloads. 

### Constructing the payload bid

Builders can broadcast a payload bid for the current or the next slot's proposer to include. They produce a `SignedExecutionPayloadHeader` as follows. 

1. Set `header.parent_block_hash` to the current head of the execution chain (this can be obtained from the beacon state as `state.last_block_hash`). 
2. Construct an execution payload. This can be performed with an external execution engine with a call to Set `header.block_hash` for t
