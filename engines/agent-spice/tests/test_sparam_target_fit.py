import math
from types import SimpleNamespace

import pytest

from agent_spice.sparam.target_fit import (
    SParamFitTarget,
    SParamOrderTrial,
    run_target_order_search,
    trial_from_fit_result,
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
        {"mean_rms": 0.001, "min_order": 0},
        {"mean_rms": 0.001, "min_order": 9, "max_order": 8},
        {"mean_rms": 0.001, "max_order_step": 0},
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
    assert target.min_order == 1
    assert target.max_order_step == 8
    assert target.passivity_epsilon == pytest.approx(1e-6)


def test_target_keeps_existing_positional_argument_order():
    target = SParamFitTarget(0.001, "enforce", 20, 3, 1e-5)

    assert target.max_order_step == 3
    assert target.passivity_epsilon == pytest.approx(1e-5)
    assert target.min_order == 1


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


def test_scheduler_uses_larger_steps_when_rms_is_far_above_target():
    calls = []

    def evaluate(order):
        calls.append(order)
        trial = make_trial(order, target_met=order >= 20)
        if not trial.target_met:
            trial.final_mean_rms = 0.2
        return trial

    result = run_target_order_search(
        SParamFitTarget(mean_rms=0.001, max_order=24, max_order_step=8),
        evaluate,
    )

    assert calls[:3] == [4, 12, 20]
    assert result.selected_trial is not None
    assert result.selected_trial.requested_order == 20


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


def test_scheduler_honors_a_validated_minimum_order_bound():
    calls = []

    def evaluate(order):
        calls.append(order)
        return make_trial(order, target_met=order == 9)

    result = run_target_order_search(
        SParamFitTarget(mean_rms=0.001, min_order=9, max_order=20),
        evaluate,
    )

    assert calls == [9]
    assert result.selected_trial is not None
    assert result.selected_trial.requested_order == 9


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


def test_trial_dict_serializes_non_finite_metrics_as_null():
    trial = make_trial(8, target_met=False)
    trial.pre_mean_rms = math.inf
    trial.final_mean_rms = math.nan

    serialized = trial.to_dict()

    assert serialized["pre_mean_rms"] is None
    assert serialized["final_mean_rms"] is None


def test_search_report_aggregates_all_trial_time_and_peak_memory():
    def evaluate(order):
        trial = make_trial(order, target_met=order == 8)
        trial.fit_seconds = float(order)
        trial.check_seconds = float(order) / 10.0
        trial.enforce_seconds = float(order) / 20.0
        trial.elapsed_seconds = float(order) + 0.5
        trial.peak_memory_mb = float(order * 10)
        return trial

    result = run_target_order_search(
        SParamFitTarget(mean_rms=0.001, max_order=8),
        evaluate,
    )

    payload = result.to_dict()
    assert [trial["requested_order"] for trial in payload["order_trials"]] == [4, 6, 8, 7]
    assert payload["fit_seconds"] == pytest.approx(25.0)
    assert payload["check_seconds"] == pytest.approx(2.5)
    assert payload["enforce_seconds"] == pytest.approx(1.25)
    assert payload["elapsed_seconds"] == pytest.approx(27.0)
    assert payload["peak_memory_mb"] == pytest.approx(80.0)


def make_fit_result(
    *,
    pre_rms=0.0008,
    final_rms=0.0009,
    final_sigma=0.999,
    passive_after=True,
    effective_order=8,
    skip_reason=None,
):
    return SimpleNamespace(
        expanded_model_order=effective_order,
        fit_frequency_points=611,
        frequency_points=611,
        pre_enforcement_mean_rms_error=pre_rms,
        comparison_mean_rms_error=final_rms,
        passivity_max_sigma_before=1.01,
        passivity_max_sigma_after=final_sigma,
        passive_after_enforce=passive_after,
        fit_seconds=10.0,
        check_seconds=2.0,
        enforce_seconds=3.0,
        elapsed_seconds=15.0,
        peak_memory_mb=100.0,
        real_pole_count=4,
        complex_pair_count=2,
        stored_pole_count=6,
        passivity_enforcement_skip_reason=skip_reason,
    )


def test_off_policy_uses_final_rms_only():
    trial = trial_from_fit_result(
        SParamFitTarget(0.001, passivity="off"),
        make_fit_result(final_sigma=None, passive_after=None),
        requested_order=8,
    )

    assert trial.target_met is True
    assert trial.status == "PASS"
    assert trial.rejection_reason is None


def test_check_policy_accepts_nonpassive_model_with_warning():
    trial = trial_from_fit_result(
        SParamFitTarget(0.001, passivity="check"),
        make_fit_result(final_sigma=1.02, passive_after=False),
        requested_order=8,
    )

    assert trial.target_met is True
    assert trial.status == "PASS_WITH_PASSIVITY_WARNING"
    assert trial.rejection_reason is None


def test_check_policy_rejects_missing_check_metrics():
    trial = trial_from_fit_result(
        SParamFitTarget(0.001, passivity="check"),
        make_fit_result(final_sigma=None, passive_after=None),
        requested_order=8,
    )

    assert trial.target_met is False
    assert trial.rejection_reason == "passivity_check_failed"


def test_enforce_policy_requires_final_passivity():
    trial = trial_from_fit_result(
        SParamFitTarget(0.001, passivity="enforce"),
        make_fit_result(final_sigma=1.02, passive_after=False),
        requested_order=8,
    )

    assert trial.target_met is False
    assert trial.rejection_reason == "passivity_enforcement_failed"


def test_enforce_policy_rejects_final_rms_regression():
    trial = trial_from_fit_result(
        SParamFitTarget(0.001, passivity="enforce"),
        make_fit_result(pre_rms=0.0008, final_rms=0.0011),
        requested_order=8,
    )

    assert trial.target_met is False
    assert trial.rejection_reason == "final_rms_above_target"


def test_enforce_policy_records_pre_rms_cost_gate():
    trial = trial_from_fit_result(
        SParamFitTarget(0.001, passivity="enforce"),
        make_fit_result(
            pre_rms=0.0011,
            final_rms=0.0011,
            final_sigma=1.02,
            passive_after=False,
            skip_reason="pre_rms_above_target",
        ),
        requested_order=8,
    )

    assert trial.target_met is False
    assert trial.rejection_reason == "pre_rms_above_target"
    assert trial.enforce_seconds == 0.0


def test_trial_rejects_effective_order_mismatch():
    trial = trial_from_fit_result(
        SParamFitTarget(0.001, passivity="off"),
        make_fit_result(effective_order=9),
        requested_order=8,
    )

    assert trial.target_met is False
    assert trial.rejection_reason == "effective_order_mismatch"
