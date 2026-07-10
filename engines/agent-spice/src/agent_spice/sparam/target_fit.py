from __future__ import annotations

from dataclasses import dataclass, field, fields
import math
from typing import Any, Callable, Literal


PassivityPolicy = Literal["off", "check", "enforce"]


@dataclass(frozen=True)
class SParamFitTarget:
    mean_rms: float
    passivity: PassivityPolicy = "check"
    max_order: int = 40
    passivity_epsilon: float = 1e-6

    def __post_init__(self) -> None:
        if not math.isfinite(self.mean_rms) or self.mean_rms <= 0.0:
            raise ValueError("mean_rms must be finite and > 0")
        if self.passivity not in {"off", "check", "enforce"}:
            raise ValueError("passivity must be 'off', 'check', or 'enforce'")
        if self.max_order < 1:
            raise ValueError("max_order must be >= 1")
        if not math.isfinite(self.passivity_epsilon) or self.passivity_epsilon < 0.0:
            raise ValueError("passivity_epsilon must be finite and >= 0")


@dataclass
class SParamOrderTrial:
    requested_order: int
    effective_order: int
    fit_frequency_points: int
    evaluation_frequency_points: int
    pre_mean_rms: float
    final_mean_rms: float
    pre_max_sigma: float | None
    final_max_sigma: float | None
    fit_seconds: float
    check_seconds: float
    enforce_seconds: float
    elapsed_seconds: float
    peak_memory_mb: float
    target_met: bool
    status: str
    rejection_reason: str | None
    real_pole_count: int | None = None
    complex_pair_count: int | None = None
    stored_pole_count: int | None = None
    payload: Any = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        serialized: dict[str, Any] = {}
        for item in fields(self):
            if item.name == "payload":
                continue
            value = getattr(self, item.name)
            serialized[item.name] = (
                None
                if isinstance(value, float) and not math.isfinite(value)
                else value
            )
        return serialized


@dataclass(frozen=True)
class SParamTargetSearchResult:
    target: SParamFitTarget
    trials: tuple[SParamOrderTrial, ...]
    selected_trial: SParamOrderTrial | None
    stop_reason: str

    @property
    def target_met(self) -> bool:
        return self.selected_trial is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rms_target": float(self.target.mean_rms),
            "passivity_policy": self.target.passivity,
            "max_order": int(self.target.max_order),
            "selected_effective_order": None
            if self.selected_trial is None
            else int(self.selected_trial.effective_order),
            "target_met": bool(self.target_met),
            "target_stop_reason": self.stop_reason,
            "fit_seconds": sum(trial.fit_seconds for trial in self.trials),
            "check_seconds": sum(trial.check_seconds for trial in self.trials),
            "enforce_seconds": sum(trial.enforce_seconds for trial in self.trials),
            "elapsed_seconds": sum(trial.elapsed_seconds for trial in self.trials),
            "peak_memory_mb": max(
                (trial.peak_memory_mb for trial in self.trials),
                default=0.0,
            ),
            "order_trials": [trial.to_dict() for trial in self.trials],
            "benchmark_contract_version": "sparam_target_v1",
        }


def trial_from_fit_result(
    target: SParamFitTarget,
    fit_result: Any,
    *,
    requested_order: int,
) -> SParamOrderTrial:
    effective_order = int(getattr(fit_result, "expanded_model_order", 0) or 0)
    pre_mean_rms = getattr(fit_result, "pre_enforcement_mean_rms_error", None)
    final_mean_rms = getattr(fit_result, "comparison_mean_rms_error", None)
    pre_value = float(final_mean_rms if pre_mean_rms is None else pre_mean_rms)
    final_value = math.inf if final_mean_rms is None else float(final_mean_rms)
    pre_sigma = getattr(fit_result, "passivity_max_sigma_before", None)
    final_sigma = getattr(fit_result, "passivity_max_sigma_after", None)
    passive_after = getattr(fit_result, "passive_after_enforce", None)
    skip_reason = getattr(fit_result, "passivity_enforcement_skip_reason", None)

    target_met = False
    status = "FAIL"
    rejection_reason: str | None = None
    if effective_order != requested_order:
        rejection_reason = "effective_order_mismatch"
    elif not math.isfinite(final_value) or final_value > target.mean_rms:
        rejection_reason = (
            "pre_rms_above_target"
            if target.passivity == "enforce" and skip_reason == "pre_rms_above_target"
            else "final_rms_above_target"
        )
    elif target.passivity == "off":
        target_met = True
        status = "PASS"
    elif target.passivity == "check":
        if final_sigma is None or passive_after is None:
            rejection_reason = "passivity_check_failed"
        else:
            target_met = True
            status = (
                "PASS"
                if bool(passive_after) and float(final_sigma) <= 1.0 + target.passivity_epsilon
                else "PASS_WITH_PASSIVITY_WARNING"
            )
    elif skip_reason == "pre_rms_above_target":
        rejection_reason = "pre_rms_above_target"
    elif (
        final_sigma is None
        or passive_after is not True
        or float(final_sigma) > 1.0 + target.passivity_epsilon
    ):
        rejection_reason = "passivity_enforcement_failed"
    else:
        target_met = True
        status = "PASS"

    return SParamOrderTrial(
        requested_order=int(requested_order),
        effective_order=effective_order,
        fit_frequency_points=int(getattr(fit_result, "fit_frequency_points", 0) or 0),
        evaluation_frequency_points=int(getattr(fit_result, "frequency_points", 0) or 0),
        pre_mean_rms=pre_value,
        final_mean_rms=final_value,
        pre_max_sigma=None if pre_sigma is None else float(pre_sigma),
        final_max_sigma=None if final_sigma is None else float(final_sigma),
        fit_seconds=float(getattr(fit_result, "fit_seconds", 0.0) or 0.0),
        check_seconds=float(getattr(fit_result, "check_seconds", 0.0) or 0.0),
        enforce_seconds=0.0
        if skip_reason == "pre_rms_above_target"
        else float(getattr(fit_result, "enforce_seconds", 0.0) or 0.0),
        elapsed_seconds=float(getattr(fit_result, "elapsed_seconds", 0.0) or 0.0),
        peak_memory_mb=float(getattr(fit_result, "peak_memory_mb", 0.0) or 0.0),
        target_met=target_met,
        status=status,
        rejection_reason=rejection_reason,
        real_pole_count=getattr(fit_result, "real_pole_count", None),
        complex_pair_count=getattr(fit_result, "complex_pair_count", None),
        stored_pole_count=getattr(fit_result, "stored_pole_count", None),
        payload=fit_result,
    )


def run_target_order_search(
    target: SParamFitTarget,
    evaluate_order: Callable[[int], SParamOrderTrial],
) -> SParamTargetSearchResult:
    cache: dict[int, SParamOrderTrial] = {}
    evaluation_order: list[int] = []

    def evaluate(order: int) -> SParamOrderTrial:
        if order not in cache:
            trial = evaluate_order(order)
            if trial.requested_order != order:
                raise ValueError("order evaluator returned a mismatched requested_order")
            cache[order] = trial
            evaluation_order.append(order)
        return cache[order]

    if target.max_order < 4:
        for order in range(1, target.max_order + 1):
            trial = evaluate(order)
            if trial.target_met:
                return SParamTargetSearchResult(
                    target=target,
                    trials=tuple(cache[item] for item in evaluation_order),
                    selected_trial=trial,
                    stop_reason="target_met",
                )
        return SParamTargetSearchResult(
            target=target,
            trials=tuple(cache[item] for item in evaluation_order),
            selected_trial=None,
            stop_reason="target_not_met_before_max_order",
        )

    coarse_orders = list(range(4, target.max_order + 1, 2))
    if coarse_orders[-1] != target.max_order and target.max_order % 2 == 1:
        coarse_orders.append(target.max_order)

    previous_failed_order = 2
    first_passing_order: int | None = None
    for order in coarse_orders:
        trial = evaluate(order)
        if trial.target_met:
            first_passing_order = order
            break
        previous_failed_order = order

    if first_passing_order is None:
        return SParamTargetSearchResult(
            target=target,
            trials=tuple(cache[item] for item in evaluation_order),
            selected_trial=None,
            stop_reason="target_not_met_before_max_order",
        )

    for order in range(previous_failed_order + 1, first_passing_order):
        evaluate(order)

    passing_trials = [trial for trial in cache.values() if trial.target_met]
    selected = min(
        passing_trials,
        key=lambda trial: (trial.effective_order, trial.requested_order),
    )
    return SParamTargetSearchResult(
        target=target,
        trials=tuple(cache[item] for item in evaluation_order),
        selected_trial=selected,
        stop_reason="target_met",
    )
