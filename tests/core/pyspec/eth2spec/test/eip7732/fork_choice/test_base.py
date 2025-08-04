from eth2spec.test.context import (
    spec_state_test,
    with_eip7732_and_later,
)
from eth2spec.test.helpers.attestations import get_valid_attestation
from eth2spec.test.helpers.block import (
    build_empty_block_for_next_slot,
)
from eth2spec.test.helpers.fork_choice import (
    add_block,
    check_head_against_root,
    get_anchor_root,
    get_genesis_forkchoice_store_and_block,
    output_head_check,
    tick_and_add_block,
    get_ptc_indices,
    create_payload_attestation_message,
)
from eth2spec.test.helpers.state import (
    payload_state_transition,
    state_transition_and_sign_block,
)


@with_eip7732_and_later
@spec_state_test
def test_genesis(spec, state):
    """Test genesis initialization with EIP7732 fork choice modifications"""
    test_steps = []
    # Initialization
    store, anchor_block = get_genesis_forkchoice_store_and_block(spec, state)
    yield "anchor_state", state
    yield "anchor_block", anchor_block

    anchor_root = get_anchor_root(spec, state)
    check_head_against_root(spec, store, anchor_root)

    # EIP7732-specific assertions
    assert hasattr(store, 'execution_payload_states'), "Store should have execution_payload_states field"
    assert hasattr(store, 'ptc_vote'), "Store should have ptc_vote field"
    assert anchor_root in store.execution_payload_states, "Anchor block should be in execution_payload_states"
    assert anchor_root in store.ptc_vote, "Anchor block should have ptc_vote entry"
    
    # Check PTC vote initialization
    ptc_vote = store.ptc_vote[anchor_root]
    assert len(ptc_vote) == spec.PTC_SIZE, f"PTC vote should have {spec.PTC_SIZE} entries"
    assert all(vote == False for vote in ptc_vote), "All PTC votes should be False initially"

    # Verify get_head returns ForkChoiceNode
    head = spec.get_head(store)
    assert isinstance(head, spec.ForkChoiceNode), "get_head should return ForkChoiceNode in EIP7732"

    output_head_check(spec, store, test_steps)

    yield "steps", test_steps


@with_eip7732_and_later
@spec_state_test
def test_chain_no_attestations(spec, state):
    """Test chain building without attestations (like phase0 test_chain_no_attestations)"""
    test_steps = []
    # Initialization
    store, anchor_block = get_genesis_forkchoice_store_and_block(spec, state)
    yield "anchor_state", state
    yield "anchor_block", anchor_block

    anchor_root = get_anchor_root(spec, state)
    check_head_against_root(spec, store, anchor_root)
    output_head_check(spec, store, test_steps)

    # On receiving a block of `GENESIS_SLOT + 1` slot
    block_1 = build_empty_block_for_next_slot(spec, state)
    signed_block_1 = state_transition_and_sign_block(spec, state, block_1)
    yield from tick_and_add_block(spec, store, signed_block_1, test_steps)
    payload_state_transition(spec, store, signed_block_1.message)

    # On receiving a block of next epoch
    block_2 = build_empty_block_for_next_slot(spec, state)
    signed_block_2 = state_transition_and_sign_block(spec, state, block_2)
    yield from tick_and_add_block(spec, store, signed_block_2, test_steps)
    check_head_against_root(spec, store, spec.hash_tree_root(block_2))
    payload_state_transition(spec, store, signed_block_2.message)
    output_head_check(spec, store, test_steps)

    yield "steps", test_steps


@with_eip7732_and_later
@spec_state_test
def test_simple_ptc_voting(spec, state):
    """Test basic PTC voting functionality specific to EIP7732"""
    test_steps = []
    # Initialization
    store, anchor_block = get_genesis_forkchoice_store_and_block(spec, state)
    yield "anchor_state", state
    yield "anchor_block", anchor_block

    anchor_root = get_anchor_root(spec, state)
    check_head_against_root(spec, store, anchor_root)
    output_head_check(spec, store, test_steps)

    # Get PTC committee for current slot
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


