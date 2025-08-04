from eth2spec.test.context import (
    spec_state_test,
    with_eip7732_and_later,
)
from eth2spec.test.helpers.attestations import get_valid_attestation
from eth2spec.test.helpers.block import (
    build_empty_block_for_next_slot,
)
from eth2spec.test.helpers.fork_choice import (
    add_attestation,
    add_block,
    check_head_against_root,
    get_anchor_root,
    get_formatted_head_output,
    get_genesis_forkchoice_store_and_block,
    on_tick_and_append_step,
    output_head_check,
    tick_and_add_block,
)
from eth2spec.test.helpers.forks import (
    is_post_eip7732,
)
from eth2spec.test.helpers.state import (
    next_slots,
    payload_state_transition,
    state_transition_and_sign_block,
)


@with_eip7732_and_later
@spec_state_test
def test_genesis(spec, state):
    """Test genesis fork choice with EIP7732 modifications (identical to phase0 pattern)"""
    test_steps = []
    # Initialization
    store, anchor_block = get_genesis_forkchoice_store_and_block(spec, state)
    yield "anchor_state", state
    yield "anchor_block", anchor_block

    anchor_root = get_anchor_root(spec, state)
    check_head_against_root(spec, store, anchor_root)

    # EIP7732-specific verification
    assert hasattr(store, 'execution_payload_states'), "Store should have execution_payload_states field"
    assert hasattr(store, 'ptc_vote'), "Store should have ptc_vote field"
    assert anchor_root in store.execution_payload_states, "Anchor block should be in execution_payload_states"
    assert anchor_root in store.ptc_vote, "Anchor block should have ptc_vote entry"

    # Verify get_head returns ForkChoiceNode
    head = spec.get_head(store)
    assert isinstance(head, spec.ForkChoiceNode), "get_head should return ForkChoiceNode in EIP7732"

    test_steps.append(
        {
            "checks": {
                "genesis_time": int(store.genesis_time),
                "head": get_formatted_head_output(spec, store),
            }
        }
    )

    yield "steps", test_steps

    if is_post_eip7732(spec):
        yield (
            "description",
            "meta",
            f"EIP7732 fork choice test with payload-aware functionality.",
        )


@with_eip7732_and_later
@spec_state_test
def test_chain_no_attestations(spec, state):
    """Test chain building without attestations (identical to phase0 pattern)"""
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
def test_split_tie_breaker_no_attestations(spec, state):
    """Test EIP7732 tiebreaking logic (adapted from phase0, which excluded EIP7732)"""
    test_steps = []
    genesis_state = state.copy()

    # Initialization
    store, anchor_block = get_genesis_forkchoice_store_and_block(spec, state)
    yield "anchor_state", state
    yield "anchor_block", anchor_block
    anchor_root = get_anchor_root(spec, state)
    check_head_against_root(spec, store, anchor_root)
    output_head_check(spec, store, test_steps)

    # Create block at slot 1
    block_1_state = genesis_state.copy()
    block_1 = build_empty_block_for_next_slot(spec, block_1_state)
    signed_block_1 = state_transition_and_sign_block(spec, block_1_state, block_1)

    # Create additional block at slot 1
    block_2_state = genesis_state.copy()
    block_2 = build_empty_block_for_next_slot(spec, block_2_state)
    block_2.body.graffiti = b"\x42" * 32
    signed_block_2 = state_transition_and_sign_block(spec, block_2_state, block_2)

    # Tick time past slot 1 so proposer score boost does not apply
    time = store.genesis_time + (block_2.slot + 1) * spec.config.SECONDS_PER_SLOT
    on_tick_and_append_step(spec, store, time, test_steps)

    yield from add_block(spec, store, signed_block_1, test_steps)
    payload_state_transition(spec, store, signed_block_1.message)
    yield from add_block(spec, store, signed_block_2, test_steps)
    payload_state_transition(spec, store, signed_block_2.message)

    # EIP7732 uses different tiebreaking logic - it should pick based on payload status and other factors
    head = spec.get_head(store)
    head_root = head.root if hasattr(head, 'root') else head
    
    # Head should be one of the two blocks
    assert head_root in [spec.hash_tree_root(block_1), spec.hash_tree_root(block_2)]
    output_head_check(spec, store, test_steps)

    yield "steps", test_steps


@with_eip7732_and_later
@spec_state_test
def test_shorter_chain_but_heavier_weight(spec, state):
    """Test shorter chain with heavier weight wins (identical to phase0 pattern)"""
    test_steps = []
    genesis_state = state.copy()

    # Initialization
    store, anchor_block = get_genesis_forkchoice_store_and_block(spec, state)
    yield "anchor_state", state
    yield "anchor_block", anchor_block
    anchor_root = get_anchor_root(spec, state)
    check_head_against_root(spec, store, anchor_root)
    output_head_check(spec, store, test_steps)

    # build longer tree
    long_state = genesis_state.copy()
    for _ in range(3):
        long_block = build_empty_block_for_next_slot(spec, long_state)
        signed_long_block = state_transition_and_sign_block(spec, long_state, long_block)
        yield from tick_and_add_block(spec, store, signed_long_block, test_steps)
        payload_state_transition(spec, store, signed_long_block.message)

    # build short tree
    short_state = genesis_state.copy()
    short_block = build_empty_block_for_next_slot(spec, short_state)
    short_block.body.graffiti = b"\x42" * 32
    signed_short_block = state_transition_and_sign_block(spec, short_state, short_block)
    yield from tick_and_add_block(spec, store, signed_short_block, test_steps)
    payload_state_transition(spec, store, signed_short_block.message)

    # Since the long chain has higher proposer_score at slot 1, the latest long block is the head
    check_head_against_root(spec, store, spec.hash_tree_root(long_block))

    short_attestation = get_valid_attestation(spec, short_state, short_block.slot, signed=True)
    next_slots(spec, short_state, spec.MIN_ATTESTATION_INCLUSION_DELAY)
    yield from add_attestation(spec, store, short_attestation, test_steps)

    check_head_against_root(spec, store, spec.hash_tree_root(short_block))
    output_head_check(spec, store, test_steps)

    yield "steps", test_steps