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
    max_order_step: int = 8
    passivity_epsilon: float = 1e-6
    min_order: int = 1

    def __post_init__(self) -> None:
        if not math.isfinite(self.mean_rms) or self.mean_rms <= 0.0:
            raise ValueError("mean_rms must be finite and > 0")
        if self.passivity not in {"off", "check", "enforce"}:
            raise ValueError("passivity must be 'off', 'check', or 'enforce'")
        if self.max_order < 1:
            raise ValueError("max_order must be >= 1")
        if self.min_order < 1 or self.min_order > self.max_order:
            raise ValueError("min_order must be between 1 and max_order")
        if self.max_order_step < 1:
            raise ValueError("max_order_step must be >= 1")
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
    full_band_mean_rms: float | None = None
    full_band_rms_target: float | None = None
    priority_band_mean_rms_errors: tuple[float | None, ...] = ()
    priority_band_rms_targets: tuple[float, ...] = ()
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

    @property
    def best_trial(self) -> SParamOrderTrial | None:
        """Return the finite-RMS trial to export when the target search fails."""
        candidates = [
            trial
            for trial in self.trials
            if math.isfinite(trial.final_mean_rms)
        ]
        return min(
            candidates,
            key=lambda trial: (
                _trial_rms_target_ratio(trial, self.target.mean_rms),
                trial.final_mean_rms,
                trial.effective_order,
                trial.requested_order,
            ),
            default=None,
        )

    def to_dict(self) -> dict[str, Any]:
        reference_trial = self.selected_trial or self.best_trial
        return {
            "rms_target": float(self.target.mean_rms),
            "full_band_rms_target": float(self.target.mean_rms),
            "priority_band_rms_targets": (
                list(reference_trial.priority_band_rms_targets)
                if reference_trial is not None
                else []
            ),
            "passivity_policy": self.target.passivity,
            "max_order": int(self.target.max_order),
            "min_order": int(self.target.min_order),
            "max_order_step": int(self.target.max_order_step),
            "selected_effective_order": None
            if self.selected_trial is None
            else int(self.selected_trial.effective_order),
            "best_effort_effective_order": None
            if self.best_trial is None
            else int(self.best_trial.effective_order),
            "best_effort_requested_order": None
            if self.best_trial is None
            else int(self.best_trial.requested_order),
            "best_effort_final_mean_rms": None
            if self.best_trial is None
            else float(self.best_trial.final_mean_rms),
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
            "rms_acceptance_contract": "per_priority_band_and_full_band_v1",
            "benchmark_contract_version": "sparam_target_v1",
        }


def _trial_rms_target_ratio(trial: SParamOrderTrial, fallback_target: float) -> float:
    full_value = trial.full_band_mean_rms
    if full_value is None:
        full_value = trial.final_mean_rms
    full_target = trial.full_band_rms_target
    if full_target is None:
        full_target = fallback_target
    ratios = [float(full_value) / float(full_target)]
    ratios.extend(
        math.inf if value is None else float(value) / float(limit)
        for value, limit in zip(
            trial.priority_band_mean_rms_errors,
            trial.priority_band_rms_targets,
            strict=True,
        )
    )
    return max(ratios, default=math.inf)


def trial_from_fit_result(
    target: SParamFitTarget,
    fit_result: Any,
    *,
    requested_order: int,
) -> SParamOrderTrial:
    effective_order = int(getattr(fit_result, "expanded_model_order", 0) or 0)
    pre_mean_rms = getattr(fit_result, "pre_enforcement_mean_rms_error", None)
    if pre_mean_rms is None:
        pre_mean_rms = getattr(fit_result, "pre_enforcement_target_mean_rms_error", None)
    final_mean_rms = getattr(fit_result, "comparison_mean_rms_error", None)
    if final_mean_rms is None:
        final_mean_rms = getattr(fit_result, "target_mean_rms_error", None)
    pre_value = float(final_mean_rms if pre_mean_rms is None else pre_mean_rms)
    final_value = math.inf if final_mean_rms is None else float(final_mean_rms)
    configured_bands = tuple(
        getattr(getattr(fit_result, "config", None), "priority_bands_hz", ()) or ()
    )
    raw_band_metrics = tuple(getattr(fit_result, "frequency_band_metrics", ()) or ())
    priority_band_targets = tuple(float(band[2]) for band in configured_bands)
    priority_band_errors: tuple[float | None, ...]
    band_metrics_missing = bool(configured_bands) and len(raw_band_metrics) != len(configured_bands)
    if band_metrics_missing:
        priority_band_errors = tuple(None for _ in configured_bands)
    else:
        priority_band_errors = tuple(
            None if metric.get("mean_rms_error") is None else float(metric["mean_rms_error"])
            for metric in raw_band_metrics
        )
    pre_sigma = getattr(fit_result, "passivity_max_sigma_before", None)
    final_sigma = getattr(fit_result, "passivity_max_sigma_after", None)
    constant_sigma = getattr(fit_result, "constant_matrix_sigma", None)
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
            else "full_band_rms_above_target"
        )
    elif band_metrics_missing:
        rejection_reason = "priority_band_metrics_missing"
    elif any(
        value is None or not math.isfinite(value) or value > limit
        for value, limit in zip(priority_band_errors, priority_band_targets, strict=True)
    ):
        rejection_reason = "priority_band_rms_above_target"
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
        constant_sigma is not None
        and float(constant_sigma) >= 1.0
    ):
        rejection_reason = "asymptotic_passivity_failed"
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
        full_band_mean_rms=final_value,
        full_band_rms_target=float(target.mean_rms),
        priority_band_mean_rms_errors=priority_band_errors,
        priority_band_rms_targets=priority_band_targets,
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

    if target.min_order == 1 and target.max_order < 4:
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

    if target.min_order == 1:
        previous_failed_order = 2
        order = 4
    else:
        previous_failed_order = target.min_order - 1
        order = target.min_order
    first_passing_order: int | None = None
    while order <= target.max_order:
        trial = evaluate(order)
        if trial.target_met:
            first_passing_order = order
            break
        previous_failed_order = order
        ratio = _trial_rms_target_ratio(trial, target.mean_rms)
        if not math.isfinite(ratio) or ratio >= 100.0:
            step = target.max_order_step
        elif ratio >= 10.0:
            step = min(target.max_order_step, 4)
        elif ratio >= 3.0:
            step = min(target.max_order_step, 3)
        else:
            step = min(target.max_order_step, 2)
        order = min(order + max(1, step), target.max_order)
        if order == previous_failed_order:
            break

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
