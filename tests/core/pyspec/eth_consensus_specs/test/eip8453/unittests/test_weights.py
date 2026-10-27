from importlib import import_module

import pytest

from eth_consensus_specs.test import context


@pytest.fixture
def spec(preset):
    # EIP-8453 is not yet registered in the shared fork test runner.
    return import_module(f"eth_consensus_specs.eip8453.{context.DEFAULT_TEST_PRESET}")


def make_state(spec, balances, scores=None):
    return spec.BeaconState(
        validators=spec.Validators(
            data=[
                spec.Validator(
                    effective_balance=balance * spec.EFFECTIVE_BALANCE_INCREMENT,
                    activation_epoch=spec.GENESIS_EPOCH,
                    exit_epoch=spec.FAR_FUTURE_EPOCH,
                )
                for balance in balances
            ]
        ),
        inactivity_scores=spec.InactivityScores(
            data=[spec.Uint64(score) for score in scores or [0] * len(balances)]
        ),
    )


def participation(spec, flags):
    return spec.HeightParticipation(data=[spec.Boolean(flag) for flag in flags])


@pytest.mark.parametrize(
    ("flags", "expected"), [([True, True, False], False), ([False, False, True], True)]
)
def test_quorum_uses_balance_not_validator_count(spec, flags, expected):
    state = make_state(spec, [32, 32, 128])
    assert spec.has_quorum(state, participation(spec, flags)) == expected


@pytest.mark.parametrize(("supporting_balance", "expected"), [(63, False), (64, True), (65, True)])
def test_two_thirds_boundary(spec, supporting_balance, expected):
    state = make_state(spec, [supporting_balance, 96 - supporting_balance])
    assert spec.has_quorum(state, participation(spec, [True, False])) == expected


@pytest.mark.parametrize("inactive", [False, True])
def test_consolidation_preserves_weight_and_quorum(spec, inactive):
    score = int(spec.EJECTION_INACTIVITY_SCORE) // 2 if inactive else 0
    split = make_state(spec, [32] * 64 + [1024], [score] * 65)
    consolidated = make_state(spec, [2048, 1024], [score] * 2)
    split_votes = participation(spec, [True] * 64 + [False])
    consolidated_votes = participation(spec, [True, False])

    assert spec.get_total_weight(split, set(range(65))) == spec.get_total_weight(
        consolidated, {0, 1}
    )
    assert spec.get_participating_weight(split, split_votes) == spec.get_participating_weight(
        consolidated, consolidated_votes
    )
    assert spec.has_quorum(split, split_votes)
    assert spec.has_quorum(consolidated, consolidated_votes)


def test_inactivity_reduces_balance_weight(spec):
    limit = int(spec.EJECTION_INACTIVITY_SCORE)
    state = make_state(spec, [32, 128, 128, 128, 128], [0, 0, limit // 2, limit, limit + 1])
    assert spec.get_validator_weight(state, 1) == 4 * spec.get_validator_weight(state, 0)
    assert 4 * spec.get_validator_weight(state, 2) == 3 * spec.get_validator_weight(state, 1)
    assert spec.get_validator_weight(state, 3) == 0
    assert spec.get_validator_weight(state, 4) == 0


def test_slashed_weight_stays_in_denominator(spec):
    state = make_state(spec, [64, 32])
    state.validators[0].slashed = True
    votes = participation(spec, [True, True])
    assert spec.get_participating_weight(state, votes) == spec.get_validator_weight(state, 1)
    assert spec.get_total_weight(state, {0, 1}) == 3 * spec.get_validator_weight(state, 1)
    assert not spec.has_quorum(state, votes)


def test_inactive_validators_do_not_count(spec):
    state = make_state(spec, [32, 2048, 2048])
    state.validators[1].activation_epoch = spec.Epoch(1)
    state.validators[2].exit_epoch = spec.GENESIS_EPOCH
    votes = participation(spec, [True, True, True])
    assert spec.get_participating_weight(state, votes) == spec.get_validator_weight(state, 0)
    assert spec.has_quorum(state, votes)


@pytest.mark.parametrize("zero_balance", [False, True])
def test_zero_weight_cannot_form_quorum(spec, zero_balance):
    state = make_state(
        spec,
        [0 if zero_balance else 32],
        [0 if zero_balance else int(spec.EJECTION_INACTIVITY_SCORE)],
    )
    assert not spec.has_quorum(state, participation(spec, [True]))


def test_empty_participation_cannot_form_quorum(spec):
    state = make_state(spec, [32, 64])
    assert not spec.has_quorum(state, participation(spec, [False, False]))


def test_weight_arithmetic_exceeds_uint64(spec):
    # Exercise the type bounds without allocating millions of validators.
    balance = (2**64 - 1) // int(spec.EFFECTIVE_BALANCE_INCREMENT)
    state = make_state(spec, [balance] * 3)
    expected = balance * int(spec.EJECTION_INACTIVITY_SCORE) ** 2
    assert expected > 2**64 - 1
    assert spec.get_validator_weight(state, 0) == expected
    assert spec.get_total_weight(state, {0, 1, 2}) == 3 * expected
    assert spec.has_quorum(state, participation(spec, [True, True, False]))
    assert not spec.has_quorum(state, participation(spec, [True, False, False]))
