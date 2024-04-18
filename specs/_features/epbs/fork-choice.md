# ePBS -- Fork Choice

## Table of contents
<!-- TOC -->
<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Introduction](#introduction)
- [Constant](#constant)
- [Containers](#containers)
  - [New `ChildNode`](#new-childnode)
- [Helpers](#helpers)
  - [Modified `LatestMessage`](#modified-latestmessage)
  - [Modified `update_latest_messages`](#modified-update_latest_messages)
  - [Modified `Store`](#modified-store)
  - [`verify_inclusion_list`](#verify_inclusion_list)
  - [`blocks_for_slot`](#blocks_for_slot)
  - [`block_for_inclusion_list`](#block_for_inclusion_list)
  - [`on_inclusion_list`](#on_inclusion_list)
  - [`notify_ptc_messages`](#notify_ptc_messages)
  - [`is_payload_present`](#is_payload_present)
  - [`is_parent_node_full`](#is_parent_node_full)
  - [Modified `get_ancestor`](#modified-get_ancestor)
  - [Modified `get_checkpoint_block`](#modified-get_checkpoint_block)
  - [`is_supporting_vote`](#is_supporting_vote)
  - [New `compute_proposer_boost`](#new-compute_proposer_boost)
  - [New `compute_withhold_boost` `](#new-compute_withhold_boost-)
  - [New `compute_reveal_boost` `](#new-compute_reveal_boost-)
  - [Modified `get_weight`](#modified-get_weight)
  - [New `get_head_no_il`](#new-get_head_no_il)
  - [Modified `get_head`](#modified-get_head)
- [Engine APIs](#engine-apis)
  - [New `NewInclusionListRequest`](#new-newinclusionlistrequest)
  - [New `notify_new_inclusion_list`](#new-notify_new_inclusion_list)
- [Updated fork-choice handlers](#updated-fork-choice-handlers)
  - [`on_block`](#on_block)
- [New fork-choice handlers](#new-fork-choice-handlers)
  - [`on_execution_payload`](#on_execution_payload)
  - [`seconds_into_slot`](#seconds_into_slot)
  - [Modified `on_tick_per_slot`](#modified-on_tick_per_slot)
  - [`on_payload_attestation_message`](#on_payload_attestation_message)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->
<!-- /TOC -->

## Introduction

This is the modification of the fork choice accompanying the ePBS upgrade.

## Constant

| Name                 | Value       |
| -------------------- | ----------- |
| `PAYLOAD_TIMELY_THRESHOLD` | `PTC_SIZE/2` (=`uint64(256)`) | 
| `PROPOSER_SCORE_BOOST` | `20` (modified in ePBS]) | 
| `PAYLOAD_WITHHOLD_BOOST` | `40` | 
| `PAYLOAD_REVEAL_BOOST` | `40` | 

## Containers

### New `ChildNode` 
Auxiliary class to consider `(block, slot, bool)` LMD voting

```python
class ChildNode(Container):
    root: Root
    slot: Slot
    is_payload_present: bool
```

## Helpers

### Modified `LatestMessage`
**Note:** The class is modified to keep track of the slot instead of the epoch

```python
@dataclass(eq=True, frozen=True)
class LatestMessage(object):
    slot: Slot
    root: Root
```

### Modified `update_latest_messages`
**Note:** the function `update_latest_messages` is updated to use the attestation slot instead of target. Notice that this function is only called on validated attestations and validators cannot attest twice in the same epoch without equivocating. Notice also that target epoch number and slot number are validated on `validate_on_attestation`. 

```python
def update_latest_messages(store: Store, attesting_indices: Sequence[ValidatorIndex], attestation: Attestation) -> None:
    slot = attestation.data.slot
    beacon_block_root = attestation.data.beacon_block_root
    non_equivocating_attesting_indices = [i for i in attesting_indices if i not in store.equivocating_indices]
    for i in non_equivocating_attesting_indices:
        if i not in store.latest_messages or slot > store.latest_messages[i].slot:
            store.latest_messages[i] = LatestMessage(slot=slot, root=beacon_block_root)
```

### Modified `Store` 
**Note:** `Store` is modified to track the intermediate states of "empty" consensus blocks, that is, those consensus blocks for which the corresponding execution payload has not been revealed or has not been included on chain. 

```python
@dataclass
class Store(object):
    time: uint64
    genesis_time: uint64
    justified_checkpoint: Checkpoint
    finalized_checkpoint: Checkpoint
    unrealized_justified_checkpoint: Checkpoint
    unrealized_finalized_checkpoint: Checkpoint
    proposer_boost_root: Root
    equivocating_indices: Set[ValidatorIndex]
    blocks: Dict[Root, BeaconBlock] = field(default_factory=dict)
    block_states: Dict[Root, BeaconState] = field(default_factory=dict)
    checkpoint_states: Dict[Checkpoint, BeaconState] = field(default_factory=dict)
    latest_messages: Dict[ValidatorIndex, LatestMessage] = field(default_factory=dict)
    unrealized_justifications: Dict[Root, Checkpoint] = field(default_factory=dict)
    execution_payload_states: Dict[Root, BeaconState] = field(default_factory=dict) # [New in ePBS]
    inclusion_list_available: Dict[Root, bool] = field(default_factory=dict) # [New in ePBS]
    ptc_vote: Dict[Root, Vector[uint8, PTC_SIZE]] = field(default_factory=dict) # [New in ePBS]
    payload_withhold_boost_root: Root # [New in ePBS]
    payload_withhold_boost_full: bool # [New in ePBS]
    payload_reveal_boost_root: Root # [New in ePBS]
```

### `verify_inclusion_list`
*[New in ePBS]*

```python
def verify_inclusion_list(state: BeaconState, block: BeaconBlock, inclusion_list: InclusionList, execution_engine: ExecutionEngine) -> bool:
    """
    Returns true if the inclusion list is valid. 
    """
    # Check that the inclusion list corresponds to the block proposer
    signed_summary = inclusion_list.summary
    proposer_index = signed_summary.message.proposer_index
    assert block.proposer_index == proposer_index

    # Check that the signature is correct
    assert verify_inclusion_list_summary_signature(state, signed_summary)
 
    # TODO: These checks will also be performed by the EL surely so we can probably remove them from here.
    # Check the summary and transaction list lengths
    summary = signed_summary.message.summary
    assert len(summary) <= MAX_TRANSACTIONS_PER_INCLUSION_LIST
    assert len(inclusion_list.transactions) == len(summary)

    # Check that the inclusion list is valid
    return execution_engine.notify_new_inclusion_list(NewInclusionListRequest(
            inclusion_list=inclusion_list.transactions, 
            summary=summary,
            parent_block_hash = state.latest_block_hash))
```

### `blocks_for_slot`
*[New in ePBS]*

The function `blocks_for_slot` returns all the beacon blocks found in the store for the given slot. This implementation here is only for specification purposes and clients may choose to optimize this by using an internal map or similar caching structures. 

```python
def blocks_for_slot(store: Store, slot: Slot) -> Set[BeaconBlock]:
    return [block for root, block in store.blocks.items() if block.slot == slot]
```

### `block_for_inclusion_list`
*[New in ePBS]*
The function `block_for_inclusion_list` returns a known beacon block in store that is compatible with the given inclusion list.

```python
def block_for_inclusion_list(store: Store, inclusion_list: InclusionList) -> Optional[BeaconBlock]:
    summary = inclusion_list.signed_summary.message
    parent_hash = inclusion_list.parent_block_hash
    
    blocks = blocks_for_slot(store, summary.slot)
    for block in blocks:
        if block.proposer_index == summary.proposer_index and block.signed_execution_payload_header.message.parent_block_hash == parent_hash:
            return block
    return None
```

### `on_inclusion_list`
*[New in ePBS]*

The function `on_inclusion_list` is called every time an `InclusionList` is seen by the node that passes pubsub validation. This specification requires that there is already a beacon block in the store that is compatible with this inclusion list. Client developers may (and should) instead validate the inclusion list against the head state in case it arrives earlier than the beacon block and cache this result. 

```python
def on_inclusion_list(store: Store, inclusion_list: InclusionList) -> None:
    """
    Validates an incoming inclusion list and records the result in the corresponding forkchoice node.
    """
    # Require we have one block compatible with the inclusion list
    block = block_for_inclusion_list(store, inclusion_list)
    assert block is not None
    root = hash_tree_root(block)
    assert root in store.block_states
    state = store.block_states[root]
    assert block.parent_root in store.blocks
    parent_block = store.blocks[block.parent_root]

    # Ignore the list if the parent consensus block did not contain a payload
    header = block.body.signed_execution_payload_header.message
    parent_header = parent_block.body.signed_execution_payload_header.message
    if header.parent_block_hash != parent_header.block_hash:
        assert header.parent_block_hash == parent_header.parent_block_hash
        return

    # verify the inclusion list
    assert verify_inclusion_list(state, block, inclusion_list, EXECUTION_ENGINE)
    store.inclusion_list_available[root]=True
```
    
### `notify_ptc_messages`

```python
def notify_ptc_messages(store: Store, state: BeaconState, payload_attestations: Sequence[PayloadAttestation]) -> None:
    """
    Extracts a list of ``PayloadAttestationMessage`` from ``payload_attestations`` and updates the store with them
    These Payload attestations are assumed to be in the beacon block hence signature verification is not needed
    """
    if state.slot == 0:
        return
    for payload_attestation in payload_attestations:
        indexed_payload_attestation = get_indexed_payload_attestation(state, state.slot - 1, payload_attestation)
        for idx in indexed_payload_attestation.attesting_indices:
            store.on_payload_attestation_message(PayloadAttestationMessage(validator_index=idx,
                    data=payload_attestation.data, signature= BLSSignature(), is_from_block=true))
```

### `is_payload_present`

```python
def is_payload_present(store: Store, beacon_block_root: Root) -> bool:
    """
    Return whether the execution payload for the beacon block with root ``beacon_block_root`` was voted as present 
    by the PTC
    """
    # The beacon block root must be known
    assert beacon_block_root in store.ptc_vote
    return store.ptc_vote[beacon_block_root].count(PAYLOAD_PRESENT) > PAYLOAD_TIMELY_THRESHOLD
```

### `is_parent_node_full`

```python
def is_parent_node_full(store: Store, block: BeaconBlock) -> bool:
    parent = store.blocks[block.parent_root]
    return block.body.signed_execution_payload_header.message.parent_block_hash == parent.body.signed_execution_payload_header.message.block_hash
```

### Modified `get_ancestor` 
**Note:** `get_ancestor` is modified to return whether the chain is based on an *empty* or *full* block. 

```python
def get_ancestor(store: Store, root: Root, slot: Slot) -> ChildNode:
    """
    Returns the beacon block root, the slot and the payload status of the ancestor of the beacon block 
    with ``root`` at ``slot``. If the beacon block with ``root`` is already at ``slot`` or we are 
    requesting an ancestor "in the future" it returns its PTC status instead of the actual payload content. 
    """
    block = store.blocks[root]
    if block.slot <= slot:
        return ChildNode(root=root, slot=slot, is_payload_present=is_payload_present(store, root))

    parent = store.blocks[block.parent_root]
    if parent.slot > slot:
        return get_ancestor(store, block.parent_root, slot)
    return ChildNode(root=block.parent_root, slot=parent.slot, is_payload_present=is_parent_node_full(block))
```

### Modified `get_checkpoint_block`
**Note:** `get_checkpoint_block` is modified to use the new `get_ancestor`

```python
def get_checkpoint_block(store: Store, root: Root, epoch: Epoch) -> Root:
    """
    Compute the checkpoint block for epoch ``epoch`` in the chain of block ``root``
    """
    epoch_first_slot = compute_start_slot_at_epoch(epoch)
    return get_ancestor(store, root, epoch_first_slot).root
```


### `is_supporting_vote`

```python
def is_supporting_vote(store: Store, node: ChildNode, message: LatestMessage) -> bool:
    """
    Returns whether a vote for ``message.root`` supports the chain containing the beacon block ``node.root`` with the
    payload contents indicated by ``node.is_payload_present`` as head during slot ``node.slot``.
    """
    if node.root == message.root:
        # an attestation for a given root always counts for that root regardless if full or empty
        # as long as the attestation happened after the requested slot. 
        return node.slot <= message.slot
    message_block = store.blocks[message.root]
    if node.slot >= message_block.slot:
        return False
    ancestor =  get_ancestor(store, message.root, node.slot)
    return (node.root == ancestor.root) and (node.is_payload_present == ancestor.is_payload_present)
```

### New `compute_proposer_boost`
This is a helper to compute the proposer boost. It applies the proposer boost to any ancestor of the proposer boost root taking into account the payload presence. There is one exception: if the requested node has the same root and slot as the block with the proposer boost root, then the proposer boost is applied to both empty and full versions of the node. 
```python
def compute_proposer_boost(store: Store, state: State, node: ChildNode) -> Gwei:
    if store.proposer_boost_root == Root():
        return Gwei(0)
    ancestor = get_ancestor(store, store.proposer_boost_root, node.slot)
    if ancestor.root != node.root:
        return Gwei(0)
    proposer_boost_slot = store.blocks[store.proposer_boost_root].slot
    # Proposer boost is not applied after skipped slots
    if node.slot > proposer_boost_slot:
        return Gwei(0)
    if (node.slot < proposer_boost_slot) and (ancestor.is_payload_present != node.is_payload_present):
        return Gwei(0)
    committee_weight = get_total_active_balance(state) // SLOTS_PER_EPOCH
    return  (committee_weight * PROPOSER_SCORE_BOOST) // 100
```

### New `compute_withhold_boost` `
This is a similar helper that applies for the withhold boost. In this case this always takes into account the reveal status.

```python
def compute_withhold_boost(store: Store, state: State, node: ChildNode) -> Gwei:
    if store.payload_withhold_boost_root == Root():
        return Gwei(0)
    ancestor = get_ancestor(store, store.payload_withold_boost_root, node.slot)
    if ancestor.root != node.root:
        return Gwei(0)
    if node.slot >= store.blocks[store.payload_withhold_boost_root].slot:
        ancestor.is_payload_present = store.payload_withhold_boost_full
    if ancestor.is_payload_present != node.is_payload_present:
        return Gwei(0)

    committee_weight = get_total_active_balance(state) // SLOTS_PER_EPOCH
    return  (committee_weight * PAYLOAD_WITHHOLD_BOOST) // 100
```

### New `compute_reveal_boost` `
This is a similar helper to the last two, the only difference is that the reveal boost is only applied to the full version of the node when querying for the same slot as the revealed payload. 

```python
def compute_reveal_boost(store: Store, state: State, node: ChildNode) -> Gwei:
    if store.payload_reveal_boost_root == Root():
        return Gwei(0)
    ancestor = get_ancestor(store, store.payload_reveal_boost_root, node.slot)
    if ancestor.root != node.root:
        return Gwei(0)
    if node.slot >= store.blocks[store.payload_reveal_boost_root].slot:
        ancestor.is_payload_present = True
    if is_ancestor_full != node.is_payload_present:
        return Gwei(0)
    committee_weight = get_total_active_balance(state) // SLOTS_PER_EPOCH
    return  (committee_weight * PAYLOAD_REVEAL_BOOST) // 100
```

### Modified `get_weight`

**Note:** `get_weight` is modified to only count votes for descending chains that support the status of a triple `Root, Slot, bool`, where the `bool` indicates if the block was full or not. `Slot` is needed for a correct implementation of `(Block, Slot)` voting. 

```python
def get_weight(store: Store, node: ChildNode) -> Gwei:
    state = store.checkpoint_states[store.justified_checkpoint]
    unslashed_and_active_indices = [
        i for i in get_active_validator_indices(state, get_current_epoch(state))
        if not is_slashed_attester(state.validators[i])
    ]
    attestation_score = Gwei(sum(
        state.validators[i].effective_balance for i in unslashed_and_active_indices
        if (i in store.latest_messages
            and i not in store.equivocating_indices
            and is_supporting_vote(store, node, store.latest_messages[i]))
    ))

    # Compute boosts
    proposer_score = compute_boost(store, state, node)
    builder_reveal_score = compute_reveal_boost(store, state, node)
    builder_withhold_score = compute_withhold_boost(store, state, node)

    return attestation_score + proposer_score + builder_reveal_score + builder_withhold_score
```

### New `get_head_no_il` 

**Note:** `get_head_no_il` is a modified version of `get_head` to use the new `get_weight` function. It returns the Beacon block root of the head block and whether its payload is considered present or not. It disregards IL availability. 

```python
def get_head_no_il(store: Store) -> tuple[Root, bool]:
    # Get filtered block tree that only includes viable branches
    blocks = get_filtered_block_tree(store)
    # Execute the LMD-GHOST fork choice
    head_root = store.justified_checkpoint.root
    head_block = store.blocks[head_root]
    head_slot = head_block.slot
    head_full = is_payload_present(store, head_root)
    while True:
        children = [
            ChildNode(root=root, slot=block.slot, is_payload_present=present) for (root, block) in blocks.items()
            if block.parent_root == head_root and is_parent_node_full(store, block) == head_full 
            for present in (True, False) if root in store.execution_payload_states or present == False
        ]
        if len(children) == 0:
            return (head_root, head_full)
        # if we have children we consider the current head advanced as a possible head 
        children += [ChildNode(root=head_root, slot=head_slot + 1, head_full)]
        # Sort by latest attesting balance with ties broken lexicographically
        # Ties broken by favoring full blocks according to the PTC vote
        # Ties are then broken by favoring full blocks
        # Ties broken then by favoring higher slot numbers
        # Ties then broken by favoring block with lexicographically higher root
        best_child = max(children, key=lambda child: (get_weight(store, child), is_payload_present(store, child.root), child.is_payload_present, child.slot, child.root))
        if best_child.root == head_root:
            return (best_child.root, best_child.is_payload_present)
        head_root = best_child.root
        head_full = best_child.is_payload_present
```

### Modified `get_head` 
`get_head` is modified to use the new weight system by `(block, slot, payload_present)` voting and to not consider nodes without an available inclusion list

```python
def get_head(store: Store) -> tuple[Root, bool]:
    head_root, _ = get_head_no_il(store)
    while not store.inclusion_list_available(head_root):
        head_block = store.blocks[head_root]
        head_root = head_block.parent_root
    return head_root, store.is_payload_present(head_root)
```

## Engine APIs

### New `NewInclusionListRequest`

```python
@dataclass
class NewInclusionListRequest(object):
    inclusion_list: List[Transaction, MAX_TRANSACTIONS_PER_INCLUSION_LIST]
    summary: List[ExecutionAddress, MAX_TRANSACTIONS_PER_INCLUSION_LIST]
    parent_block_hash: Hash32
```
  

### New `notify_new_inclusion_list`

```python
def notify_new_inclusion_list(self: ExecutionEngine,
                              inclusion_list_request: NewInclusionListRequest) -> bool:
    """
    Return ``True`` if and only if the transactions in the inclusion list can be succesfully executed
    starting from the execution state corresponding to the `parent_block_hash` in the inclusion list 
    summary. The execution engine also checks that the total gas limit is less or equal that
    ```MAX_GAS_PER_INCLUSION_LIST``, and the transactions in the list of transactions correspond to the signed summary
    """
    ...
```
 
## Updated fork-choice handlers

### `on_block`

*Note*: The handler `on_block` is modified to consider the pre `state` of the given consensus beacon block depending not only on the parent block root, but also on the parent blockhash. In addition we delay the checking of blob data availability until the processing of the execution payload. 

```python
def on_block(store: Store, signed_block: SignedBeaconBlock) -> None:
    """
    Run ``on_block`` upon receiving a new block.
    """
    block = signed_block.message
    # Parent block must be known
    assert block.parent_root in store.block_states

    # Check if this blocks builds on empty or full parent block
    parent_block = store.blocks[block.parent_root]
    header = block.body.signed_execution_payload_header.message
    parent_header = parent_block.body.signed_execution_payload_header.message
    parent_payload_hash = parent_header.block_hash
    current_payload_parent_hash = header.parent_block_hash
    # Make a copy of the state to avoid mutability issues
    if current_payload_parent_hash == parent_payload_hash:
        assert block.parent_root in store.execution_payload_states
        state = copy(store.execution_payload_states[block.parent_root])
    else:
        assert current_payload_parent_hash == parent_header.parent_block_hash
        state = copy(store.block_states[block.parent_root])

    # Blocks cannot be in the future. If they are, their consideration must be delayed until they are in the past.
    current_slot = get_current_slot(store)
    assert current_slot >= block.slot

    # Check that block is later than the finalized epoch slot (optimization to reduce calls to get_ancestor)
    finalized_slot = compute_start_slot_at_epoch(store.finalized_checkpoint.epoch)
    assert block.slot > finalized_slot
    # Check block is a descendant of the finalized block at the checkpoint finalized slot
    finalized_checkpoint_block = get_checkpoint_block(
        store,
        block.parent_root,
        store.finalized_checkpoint.epoch,
    )
    assert store.finalized_checkpoint.root == finalized_checkpoint_block

    # Check the block is valid and compute the post-state
    block_root = hash_tree_root(block)
    state_transition(state, signed_block, True)

    # Add new block to the store
    store.blocks[block_root] = block
    # Add new state for this block to the store
    store.block_states[block_root] = state
    # Add a new PTC voting for this block to the store
    store.ptc_vote[block_root] = [PAYLOAD_ABSENT]*PTC_SIZE
    # if the parent block is empty record that the inclusion list for this block has been satisfied
    if current_payload_parent_hash == parent_header.parent_block_hash:
        store.inclusion_list_available = True

    # Notify the store about the payload_attestations in the block
    store.notify_ptc_messages(state, block.body.payload_attestations)
    # Add proposer score boost if the block is timely
    time_into_slot = (store.time - store.genesis_time) % SECONDS_PER_SLOT
    is_before_attesting_interval = time_into_slot < SECONDS_PER_SLOT // INTERVALS_PER_SLOT
    if get_current_slot(store) == block.slot and is_before_attesting_interval:
        store.proposer_boost_root = hash_tree_root(block)

    # Update checkpoints in store if necessary
    update_checkpoints(store, state.current_justified_checkpoint, state.finalized_checkpoint)

    # Eagerly compute unrealized justification and finality.
    compute_pulled_up_tip(store, block_root)
```

## New fork-choice handlers

### `on_execution_payload`

```python
def on_execution_payload(store: Store, signed_envelope: SignedExecutionPayloadEnvelope) -> None:
    """
    Run ``on_execution_payload`` upon receiving a new execution payload.
    """
    envelope = signed_envelope.message 
    # The corresponding beacon block root needs to be known
    assert envelope.beacon_block_root in store.block_states

    # Check if blob data is available
    # If not, this payload MAY be queued and subsequently considered when blob data becomes available
    assert is_data_available(envelope.beacon_block_root, envelope.blob_kzg_commitments)

    # Make a copy of the state to avoid mutability issues
    state = copy(store.block_states[envelope.beacon_block_root])

    # Process the execution payload
    process_execution_payload(state, signed_envelope, EXECUTION_ENGINE)

    # Add new state for this payload to the store
    store.execution_payload_states[envelope.beacon_block_root] = state
```   

### `seconds_into_slot`

```python
def seconds_into_slot(store: Store) -> uint64:
    return (store.time - store.genesis_time) % SECONDS_PER_SLOT
```

### Modified `on_tick_per_slot`

Modified to reset the payload boost roots

```python
def on_tick_per_slot(store: Store, time: uint64) -> None:
    previous_slot = get_current_slot(store)

    # Update store time
    store.time = time

    current_slot = get_current_slot(store)

    # If this is a new slot, reset store.proposer_boost_root
    if current_slot > previous_slot:
        store.proposer_boost_root = Root()
    else: 
        # Reset the payload boost if this is the attestation time
        if seconds_into_slot(store) >= SECONDS_PER_SLOT // INTERVALS_PER_SLOT:
            store.payload_withhold_boost_root = Root()
            store.payload_withhold_boost_full = False
            store.payload_reveal_boost_root = Root()

    # If a new epoch, pull-up justification and finalization from previous epoch
    if current_slot > previous_slot and compute_slots_since_epoch_start(current_slot) == 0:
        update_checkpoints(store, store.unrealized_justified_checkpoint, store.unrealized_finalized_checkpoint)
```

### `on_payload_attestation_message`

```python
def on_payload_attestation_message(store: Store, 
    ptc_message: PayloadAttestationMessage, is_from_block: bool=False) -> None:
    """
    Run ``on_payload_attestation_message`` upon receiving a new ``ptc_message`` directly on the wire.
    """
    # The beacon block root must be known
    data = ptc_message.data
    # PTC attestation must be for a known block. If block is unknown, delay consideration until the block is found
    state = store.block_states[data.beacon_block_root]
    ptc = get_ptc(state, data.slot)
    # PTC votes can only change the vote for their assigned beacon block, return early otherwise
    if data.slot != state.slot:
        return
    # Check that the attester is from the PTC
    assert ptc_message.validator_index in ptc

    # Verify the signature and check that its for the current slot if it is coming from the wire
    if not is_from_block:
        # Check that the attestation is for the current slot
        assert data.slot == get_current_slot(store)
        # Verify the signature
        assert is_valid_indexed_payload_attestation(state, 
            IndexedPayloadAttestation(attesting_indices = [ptc_message.validator_index], data = data,
                                      signature = ptc_message.signature))
    # Update the ptc vote for the block
    ptc_index = ptc.index(ptc_message.validator_index)
    ptc_vote = store.ptc_vote[data.beacon_block_root]
    ptc_vote[ptc_index] = data.payload_status
    
    # Only update payload boosts with attestations from a block if the block is for the current slot and it's early
    if is_from_block && data.slot + 1 != get_current_slot(store):
        return
    time_into_slot = (store.time - store.genesis_time) % SECONDS_PER_SLOT
    if time_into_slot >= SECONDS_PER_SLOT // INTERVALS_PER_SLOT:
        return

    # Update the payload boosts if threshold has been achieved
    if ptc_vote.count(PAYLOAD_PRESENT) > PAYLOAD_TIMELY_THRESHOLD:
        store.payload_reveal_boost_root = data.beacon_block_root
    if ptc_vote.count(PAYLOAD_WITHHELD) > PAYLOAD_TIMELY_THRESHOLD:
        block = store.blocks[data.beacon_block_root]
        store.payload_withhold_boost_root = block.parent_root
        store.payload_withhold_boost_full = is_parent_node_full(block)
```