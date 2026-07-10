import math

import pytest

from agent_spice.sparam.target_fit import (
    SParamFitTarget,
    SParamOrderTrial,
    run_target_order_search,
)


def make_trial(order: int, *, target_met: bool, effective_order: int | None = None) -> SParamOrderTrial:
    return SParamOrderTrial(
        requested_order=order,
        effective_order=order if effective_order is None else effective_order,
        fit_frequency_points=11,
        evaluation_frequency_points=11,
        pre_mean_rms=0.002,
        final_mean_rms=0.0009 if target_met else 0.002,
        pre_max_sigma=None,
        final_max_sigma=None,
        fit_seconds=1.0,
        check_seconds=0.0,
        enforce_seconds=0.0,
        elapsed_seconds=1.0,
        peak_memory_mb=10.0,
        target_met=target_met,
        status="PASS" if target_met else "FAIL",
        rejection_reason=None if target_met else "final_rms_above_target",
        payload={"order": order},
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mean_rms": 0.0},
        {"mean_rms": -1.0},
        {"mean_rms": math.inf},
        {"mean_rms": math.nan},
        {"mean_rms": 0.001, "passivity": "repair"},
        {"mean_rms": 0.001, "max_order": 0},
        {"mean_rms": 0.001, "passivity_epsilon": -1.0},
    ],
)
def test_target_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        SParamFitTarget(**kwargs)


def test_target_defaults_to_check_policy():
    target = SParamFitTarget(mean_rms=0.001)

    assert target.passivity == "check"
    assert target.max_order == 40
    assert target.passivity_epsilon == pytest.approx(1e-6)


def test_scheduler_backfills_odd_order_after_first_even_pass():
    outcomes = {4: False, 6: False, 8: True, 7: True}
    calls = []

    def evaluate(order):
        calls.append(order)
        return make_trial(order, target_met=outcomes[order])

    result = run_target_order_search(
        SParamFitTarget(mean_rms=0.001, max_order=10),
        evaluate,
    )

    assert calls == [4, 6, 8, 7]
    assert result.selected_trial is not None
    assert result.selected_trial.requested_order == 7
    assert result.stop_reason == "target_met"


def test_scheduler_selects_smallest_effective_passing_order():
    outcomes = {
        4: make_trial(4, target_met=False),
        6: make_trial(6, target_met=False),
        8: make_trial(8, target_met=True, effective_order=8),
        7: make_trial(7, target_met=True, effective_order=6),
    }

    result = run_target_order_search(
        SParamFitTarget(mean_rms=0.001, max_order=8),
        outcomes.__getitem__,
    )

    assert result.selected_trial is outcomes[7]


def test_scheduler_evaluates_each_order_once():
    calls = []

    def evaluate(order):
        calls.append(order)
        return make_trial(order, target_met=order >= 8)

    result = run_target_order_search(
        SParamFitTarget(mean_rms=0.001, max_order=10),
        evaluate,
    )

    assert result.target_met is True
    assert len(calls) == len(set(calls))


def test_scheduler_reports_target_not_met():
    calls = []

    def evaluate(order):
        calls.append(order)
        return make_trial(order, target_met=False)

    result = run_target_order_search(
        SParamFitTarget(mean_rms=0.001, max_order=10),
        evaluate,
    )

    assert calls == [4, 6, 8, 10]
    assert result.selected_trial is None
    assert result.target_met is False
    assert result.stop_reason == "target_not_met_before_max_order"


def test_scheduler_supports_small_synthetic_max_order():
    calls = []

    def evaluate(order):
        calls.append(order)
        return make_trial(order, target_met=order == 2)

    result = run_target_order_search(
        SParamFitTarget(mean_rms=0.001, max_order=3),
        evaluate,
    )

    assert calls == [1, 2]
    assert result.selected_trial is not None
    assert result.selected_trial.requested_order == 2


def test_trial_dict_excludes_in_memory_payload():
    trial = make_trial(8, target_met=True)

    serialized = trial.to_dict()

    assert "payload" not in serialized
    assert serialized["requested_order"] == 8


def test_trial_dict_does_not_copy_in_memory_payload():
    class Payload:
        def __deepcopy__(self, memo):
            raise AssertionError("payload must not be copied during serialization")

    trial = make_trial(8, target_met=True)
    trial.payload = Payload()

    assert trial.to_dict()["requested_order"] == 8
