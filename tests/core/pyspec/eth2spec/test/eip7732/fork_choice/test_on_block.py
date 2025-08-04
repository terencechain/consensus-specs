from eth2spec.test.context import (
    spec_state_test,
    with_eip7732_and_later,
)
from eth2spec.test.helpers.block import (
    build_empty_block_for_next_slot,
)
from eth2spec.test.helpers.fork_choice import (
    check_head_against_root,
    get_anchor_root,
    get_genesis_forkchoice_store_and_block,
    get_ptc_indices,
    create_payload_attestation_message,
    on_tick_and_append_step,
    output_head_check,
    tick_and_add_block,
)
from eth2spec.test.helpers.state import (
    payload_state_transition,
    state_transition_and_sign_block,
)


@with_eip7732_and_later
@spec_state_test
def test_basic_ptc_voting(spec, state):
    """Test basic PTC voting functionality specific to EIP7732"""
    test_steps = []
    # Initialization
    store, anchor_block = get_genesis_forkchoice_store_and_block(spec, state)
    yield "anchor_state", state
    yield "anchor_block", anchor_block
    current_time = state.slot * spec.config.SECONDS_PER_SLOT + store.genesis_time
    on_tick_and_append_step(spec, store, current_time, test_steps)
    assert store.time == current_time

    anchor_root = get_anchor_root(spec, state)
    check_head_against_root(spec, store, anchor_root)

    # EIP7732-specific: Test PTC voting
    ptc_indices = get_ptc_indices(spec, state, state.slot)
    assert len(ptc_indices) == spec.PTC_SIZE, f"PTC should have {spec.PTC_SIZE} members"
    
    # Create and process payload attestation
    validator_index = ptc_indices[0]
    message = create_payload_attestation_message(
        spec, validator_index, anchor_root, state.slot, payload_present=True
    )
    
    # Process the payload attestation (from block)
    spec.on_payload_attestation_message(store, message, is_from_block=True)
    
    # Verify PTC vote was updated
    ptc_vote = store.ptc_vote[anchor_root]
    ptc_index = ptc_indices.index(validator_index)
    assert ptc_vote[ptc_index] == True, "PTC vote should be updated"
    
    # Record test step
    test_steps.append({
        "payload_attestation": {
            "validator_index": int(validator_index),
            "beacon_block_root": anchor_root.hex(),
            "slot": int(state.slot),
            "payload_present": True,
        }
    })

    output_head_check(spec, store, test_steps)

    yield "steps", test_steps


@with_eip7732_and_later
@spec_state_test
def test_on_block_with_ptc_initialization(spec, state):
    """Test that on_block properly initializes PTC votes for new blocks"""
    test_steps = []
    # Initialization
    store, anchor_block = get_genesis_forkchoice_store_and_block(spec, state)
    yield "anchor_state", state
    yield "anchor_block", anchor_block
    current_time = state.slot * spec.config.SECONDS_PER_SLOT + store.genesis_time
    on_tick_and_append_step(spec, store, current_time, test_steps)
    assert store.time == current_time

    # On receiving a block of `GENESIS_SLOT + 1` slot
    block = build_empty_block_for_next_slot(spec, state)
    signed_block = state_transition_and_sign_block(spec, state, block)
    yield from tick_and_add_block(spec, store, signed_block, test_steps)
    
    # EIP7732-specific: Verify PTC vote initialization
    block_root = signed_block.message.hash_tree_root()
    assert block_root in store.ptc_vote, "New block should have PTC vote entry"
    
    ptc_vote = store.ptc_vote[block_root]
    assert len(ptc_vote) == spec.PTC_SIZE, "New block should have full PTC vote array"
    assert all(vote == False for vote in ptc_vote), "All PTC votes should be False initially"
    
    check_head_against_root(spec, store, signed_block.message.hash_tree_root())
    payload_state_transition(spec, store, signed_block.message)

    yield "steps", test_steps