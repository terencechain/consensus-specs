# ePBS -- Networking Design Notes

## Gossip validation considerations

### Signed builder bid (aka. execution payload header with builder attribution and value)

The signed builder bid arrives at slot `N` for the inclusion of `N+1`. When a node receives the builder's bid, the node will make one of the three decisions. `ACCEPT`, `IGNORE`, or `REJECT`. These are gossip sub lingo which I won't get too much into. `ACCEPT` forwards to its peers. `IGNORE` and `REJECT` both drop the object, the only difference is `REJECT` penalizes the forwarding peer. The builder bid validations consist of four components with the corresponding validation questions.
- Time
    - Did the builder's bid arrive at the right time?
- Value
    - Did the builder have enough to pay for the bid?
- Chain extension
    - Did the builder's bid extend a valid chain tip from the chain's perspective?
- Attribution
    - Did the bid come from a builder on the chain?
- Signature
    - Did the bid's signature validate for the builder?

Let's first tackle the `time` check. A node must drop a late bid (ie `< N+1`), and can drop a future bid (ie `> N+1`), although It's not clear to me why a builder wants to send an early bid. In both cases, I think `IGNORE` makes more sense than `REJECT`, typically in gossip validations, time-bound checks all used `IGNORE`. A node could be syncing to the tip of the chain.

For the `value` check. A node must drop a bid if the builder does not have enough balance to pay for the bid plus maintain a self-min balance. I think `REJECT` makes more sense here. A node should not gossip about this because it's no use.

For the `chain_extension` check. Suppose a chain has multiple tips. Builders maintain the same view. Competitive builders will be building simultaneously on all the tips. One paradigm shift is builder bid cancellation is no longer viable. This differs from the current mev-boost model. A node should `IGNORE` builder bids that are not top-of-the-chain tips. Worrying about DOS, a node can accept multiple bids of the same builder on the same tip, but the value has to be incremental. We need to think about this more.

Finally, for the `signature` check, similar to other beacon objects, a bid with an invalid signature gets a `REJECT`. Simple to reason.

### Signed beacon block

The signed beacon block now contains `ExecutionPayloadHeader` instead of `ExecutionPayload`. It also contains a new `InclusionListTransition` field. From the gossip perspective, we could add the same `time`, `value`, `chain_extention`, and `signature` checks above to for header in the block body before forwarding to the peers. As p2p spec is constructed, it never checks the objects in the block, so do we open the case here? I'm leaning towards it's not worth it as the block will fail state transition shortly after.

### Beacon attestation

Nothing changes here

### Aggregated attestation

Nothing changes here

### Execution attestation (aka. PTC attestation)

The newly signed execution attestation contains a validator index, signature, block root, and a simple boolean for revealed and not revealed. As for validations
* Block
    * Did the block process?
        * Suppose a node has not received a block. It could request the block by root, then execution_payload by root. Given there are two requests, the attestation will be late. Can we do better here?
* Attribution
    * Did the attestation come from a validator in the execution committee?
* Signature
    * Did the attestation's signature validate for the validator?

## Request / respond RPC considerations

With the new notion of full block slots and blind block slots, we have to adjust the block by range and block by root RPCs. In addition, we might need an execution payload by root RPC. The natural change will be the following
- Change `block_by_range` to blind block format
- Change `block_by_root` to blind block format
- Add `execution_payload_by_range`
- Add `execution_payload_by_root`

When syncing using `by_range`, a node will request `block_by_range` and, in parallel, request `execution_payload_by_range`. It's not clear to me what behavior to enforce. Assuming a node is sync'ed to the head but missing execution payload for corresponding blocks and head. What limitation do we enforce? On this particular handicapped node?
- A node can not continue syncing if it hasn't received the payload
- A node is optimistic if it hasn't received the payload
- A node can validate if it hasn't received the payload

Another option is to change `block_by_root` and `block_by_range` responses to union of the block between `SignedBeaconBlock` or `SignedFullBeaconBlock`. The complexity here is a brand new type for syncing but trading off the handshake needed above.


