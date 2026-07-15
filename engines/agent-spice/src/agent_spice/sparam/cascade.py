from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import re
from typing import Any

import numpy as np

from agent_spice.sparam.artifacts import evaluate_fitted_s, write_fitted_touchstone
from agent_spice.sparam.fitting import (
    SParamFitConfig,
    _FitExecution,
    _comparison_frequency_metrics,
    _comparison_rms_error,
    _constant_matrix_sigma,
    _mean_rms_error_from_sum_style,
    _safe_rms_error,
    _write_fit_outputs,
    fit_touchstone_to_spice_target,
)
from agent_spice.sparam.passivity import check_vector_fit_passivity_hamiltonian
from agent_spice.sparam.quality import build_quality_report
from agent_spice.sparam.target_fit import SParamFitTarget, SParamTargetSearchResult


@dataclass(frozen=True)
class CascadeBlockSpec:
    name: str
    touchstone: Path
    rms_target: float
    max_order: int


@dataclass(frozen=True)
class CascadeFitConfig:
    rms_target: float
    max_order: int = 100
    min_order: int = 1
    max_order_step: int = 8
    passivity_epsilon: float = 1e-6
    cascade_passivity_epsilon: float = 1e-8
    cascade_samples: int = 1001
    reference_impedance_ohm: float = 50.0
    adjustment_iterations: int = 12
    minimum_scale: float = 0.8
    priority_bands_hz: tuple[tuple[float, float, float, float], ...] = ()
    outside_band_weight: float = 0.1

    def __post_init__(self) -> None:
        if not math.isfinite(self.rms_target) or self.rms_target <= 0.0:
            raise ValueError("rms_target must be finite and > 0")
        if self.max_order < 1:
            raise ValueError("max_order must be >= 1")
        if self.min_order < 1 or self.min_order > self.max_order:
            raise ValueError("min_order must be between 1 and max_order")
        if self.max_order_step < 1:
            raise ValueError("max_order_step must be >= 1")
        if not math.isfinite(self.passivity_epsilon) or self.passivity_epsilon < 0.0:
            raise ValueError("passivity_epsilon must be finite and >= 0")
        if not math.isfinite(self.cascade_passivity_epsilon) or self.cascade_passivity_epsilon < 0.0:
            raise ValueError("cascade_passivity_epsilon must be finite and >= 0")
        if self.cascade_samples < 2:
            raise ValueError("cascade_samples must be >= 2")
        if not math.isfinite(self.reference_impedance_ohm) or self.reference_impedance_ohm <= 0.0:
            raise ValueError("reference_impedance_ohm must be finite and > 0")
        if self.adjustment_iterations < 1:
            raise ValueError("adjustment_iterations must be >= 1")
        if not math.isfinite(self.minimum_scale) or not 0.0 < self.minimum_scale <= 1.0:
            raise ValueError("minimum_scale must satisfy 0 < minimum_scale <= 1")


@dataclass
class _CascadeBlockState:
    spec: CascadeBlockSpec
    target: SParamFitTarget
    search_result: SParamTargetSearchResult
    execution: _FitExecution
    directory: Path
    spice_path: Path
    report_path: Path
    html_report_path: Path
    log_path: Path
    fitted_touchstone_path: Path
    rfm_path: Path
    rfm_wrapper_path: Path


def _load_manifest(path: Path, config: CascadeFitConfig) -> tuple[list[CascadeBlockSpec], list[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cannot read cascade manifest {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid cascade manifest JSON {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("cascade manifest must be a JSON object")
    if payload.get("version") != 1:
        raise ValueError("cascade manifest version must be 1")
    raw_blocks = payload.get("blocks")
    raw_order = payload.get("cascade")
    if not isinstance(raw_blocks, list) or len(raw_blocks) < 2:
        raise ValueError("cascade manifest blocks must contain at least two entries")
    if not isinstance(raw_order, list) or len(raw_order) < 2 or not all(isinstance(item, str) for item in raw_order):
        raise ValueError("cascade manifest cascade must be an ordered list of block names")

    base = path.resolve().parent
    names: set[str] = set()
    specs: list[CascadeBlockSpec] = []
    for index, raw in enumerate(raw_blocks, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"cascade block {index} must be an object")
        unknown = set(raw) - {"name", "touchstone", "rms_target", "max_order"}
        if unknown:
            raise ValueError(f"cascade block {index} has unsupported keys: {', '.join(sorted(unknown))}")
        name = raw.get("name")
        touchstone_value = raw.get("touchstone")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", name):
            raise ValueError(f"cascade block {index} name must match [A-Za-z][A-Za-z0-9_.-]*")
        if name in names:
            raise ValueError(f"duplicate cascade block name '{name}'")
        if not isinstance(touchstone_value, str) or not touchstone_value.strip():
            raise ValueError(f"cascade block '{name}' requires a touchstone path")
        touchstone = Path(touchstone_value)
        if not touchstone.is_absolute():
            touchstone = base / touchstone
        touchstone = touchstone.resolve()
        if not touchstone.is_file():
            raise ValueError(f"cascade block '{name}' Touchstone does not exist: {touchstone}")
        if re.search(r"\.s2p$", touchstone.name, re.IGNORECASE) is None:
            raise ValueError(f"cascade block '{name}' must be a 2-port .s2p file")
        rms_target = float(raw.get("rms_target", config.rms_target))
        max_order = int(raw.get("max_order", config.max_order))
        if not math.isfinite(rms_target) or rms_target <= 0.0:
            raise ValueError(f"cascade block '{name}' rms_target must be finite and > 0")
        if max_order < config.min_order:
            raise ValueError(f"cascade block '{name}' max_order must be >= min_order")
        names.add(name)
        specs.append(CascadeBlockSpec(name, touchstone, rms_target, max_order))

    if len(set(raw_order)) != len(raw_order):
        raise ValueError("cascade order cannot repeat a block")
    if set(raw_order) != names:
        missing = sorted(names - set(raw_order))
        unknown = sorted(set(raw_order) - names)
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if unknown:
            details.append(f"unknown={','.join(unknown)}")
        raise ValueError("cascade order must contain every block exactly once: " + " ".join(details))
    return specs, list(raw_order)


def _fit_config(config: CascadeFitConfig, name: str) -> SParamFitConfig:
    return SParamFitConfig(
        mode="manual",
        n_poles_real=0,
        n_poles_cmplx=2,
        init_pole_spacing="log",
        max_iterations=14,
        enforce_dc=True,
        check_passivity=True,
        enforce_passivity=True,
        passivity_samples=8,
        passivity_max_iterations=3,
        passivity_active_variables=3072,
        preserve_dc=True,
        fit_frequency_stride=1,
        fit_max_frequency_points=256,
        use_lightweight_network=True,
        high_frequency_complex_pair_count=2,
        high_frequency_complex_pair_damping=0.03,
        high_frequency_complex_pair_lower_fraction=0.68,
        max_passivity_epsilon=config.passivity_epsilon,
        passivity_global_damping_fallback=True,
        passivity_global_damping_safety_margin=max(1e-7, config.cascade_passivity_epsilon),
        priority_bands_hz=config.priority_bands_hz,
        outside_band_weight=config.outside_band_weight,
        subckt_name=f"cascade_{re.sub(r'[^A-Za-z0-9_$]', '_', name)}",
    )


def _fit_block(spec: CascadeBlockSpec, output_root: Path, config: CascadeFitConfig) -> _CascadeBlockState:
    directory = output_root / "blocks" / spec.name
    directory.mkdir(parents=True, exist_ok=True)
    spice_path = directory / f"{spec.name}.sp"
    report_path = directory / "fit_report.json"
    html_report_path = directory / "fit_report.html"
    log_path = directory / "fit.log"
    fitted_touchstone_path = directory / f"{spec.name}_fitted.s2p"
    rfm_path = directory / f"{spec.name}.rfm"
    rfm_wrapper_path = directory / f"{spec.name}_rfm_wrapper.sp"
    target = SParamFitTarget(
        mean_rms=spec.rms_target,
        passivity="enforce",
        max_order=spec.max_order,
        min_order=config.min_order,
        max_order_step=config.max_order_step,
        passivity_epsilon=config.passivity_epsilon,
    )
    selected: list[_FitExecution] = []
    search_result = fit_touchstone_to_spice_target(
        spec.touchstone,
        spice_path,
        target=target,
        config=_fit_config(config, spec.name),
        report_path=report_path,
        html_report_path=html_report_path,
        log_path=log_path,
        fitted_touchstone_path=fitted_touchstone_path,
        rfm_path=rfm_path,
        rfm_wrapper_path=rfm_wrapper_path,
        max_order_step=config.max_order_step,
        _selected_execution_sink=selected.append,
    )
    if not selected:
        raise RuntimeError(f"cascade block '{spec.name}' did not produce a fitted model")
    return _CascadeBlockState(
        spec=spec,
        target=target,
        search_result=search_result,
        execution=selected[-1],
        directory=directory,
        spice_path=spice_path,
        report_path=report_path,
        html_report_path=html_report_path,
        log_path=log_path,
        fitted_touchstone_path=fitted_touchstone_path,
        rfm_path=rfm_path,
        rfm_wrapper_path=rfm_wrapper_path,
    )


def _evaluation_frequencies(states: list[_CascadeBlockState], sample_count: int) -> np.ndarray:
    minima = [float(np.min(state.execution.network.f)) for state in states]
    maxima = [float(np.max(state.execution.network.f)) for state in states]
    f_min = max(minima)
    f_max = min(maxima)
    if not f_min < f_max:
        raise ValueError("cascade blocks have no overlapping frequency range")
    if f_min > 0.0:
        return np.geomspace(f_min, f_max, sample_count)
    positive = [
        float(value)
        for state in states
        for value in np.asarray(state.execution.network.f, dtype=float)
        if value > 0.0
    ]
    if not positive:
        return np.linspace(f_min, f_max, sample_count)
    return np.concatenate(([0.0], np.geomspace(max(min(positive), np.finfo(float).tiny), f_max, sample_count - 1)))


def _rf_module() -> Any:
    import skrf as rf

    return rf


def _sample_block_networks(
    state: _CascadeBlockState,
    freqs: np.ndarray,
    reference_impedance: float,
) -> tuple[Any, Any]:
    rf = _rf_module()
    frequency = rf.Frequency.from_f(freqs, unit="hz")
    raw = rf.Network(str(state.spec.touchstone)).interpolate(frequency)
    fitted = rf.Network(
        frequency=frequency,
        s=evaluate_fitted_s(state.execution.vector_fit, freqs),
        z0=np.asarray(raw.z0),
        name=f"{state.spec.name}_fitted",
    )
    raw.renormalize(reference_impedance)
    fitted.renormalize(reference_impedance)
    return raw, fitted


def _cascade_networks(networks: list[Any]) -> Any:
    cascaded = networks[0]
    for network in networks[1:]:
        cascaded = cascaded ** network
    return cascaded


def _passivity_metrics(network: Any) -> dict[str, Any]:
    singular_values = np.linalg.svd(np.asarray(network.s, dtype=complex), compute_uv=False)[:, 0]
    index = int(np.argmax(singular_values))
    return {
        "passive": bool(singular_values[index] <= 1.0),
        "max_sigma": float(singular_values[index]),
        "max_sigma_frequency_hz": float(network.f[index]),
    }


def _cascade_mean_rms(reference: Any, fitted: Any) -> float:
    squared_error = np.mean(np.square(np.abs(np.asarray(reference.s) - np.asarray(fitted.s))), axis=0)
    return float(np.sqrt(np.sum(squared_error)) / 2.0)


def _rms_gate_metrics(state: _CascadeBlockState) -> dict[str, Any]:
    result = state.execution.result
    comparison = _comparison_rms_error(state.execution.network, state.execution.vector_fit, "s")
    global_mean = _mean_rms_error_from_sum_style(comparison, state.execution.network.nports)
    metrics = _comparison_frequency_metrics(state.execution.network, state.execution.vector_fit, result.config)
    full_value = math.inf if global_mean is None else float(global_mean)
    bands = [] if metrics is None else metrics["bands"]
    expected_band_count = len(result.config.priority_bands_hz)
    band_metrics_available = len(bands) == expected_band_count
    ratios = [full_value / state.target.mean_rms]
    if not band_metrics_available:
        ratios.append(math.inf)
    ratios.extend(
        math.inf
        if band["mean_rms_error"] is None
        else float(band["mean_rms_error"]) / float(band["rms_target"])
        for band in bands
    )
    return {
        "full_band_mean_rms_error": full_value,
        "full_band_rms_target": state.target.mean_rms,
        "priority_bands": bands,
        "target_met": bool(
            math.isfinite(full_value)
            and full_value <= state.target.mean_rms
            and band_metrics_available
            and all(band["target_met"] for band in bands)
        ),
        "worst_rms_ratio": max(ratios, default=math.inf),
    }


def _base_coefficients(states: list[_CascadeBlockState]) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    return [
        (
            np.asarray(state.execution.vector_fit.residues).copy(),
            np.asarray(state.execution.vector_fit.constant_coeff).copy(),
            np.asarray(state.execution.vector_fit.proportional_coeff).copy(),
        )
        for state in states
    ]


def _apply_scales(
    states: list[_CascadeBlockState],
    base: list[tuple[np.ndarray, np.ndarray, np.ndarray]],
    scales: tuple[float, ...],
) -> None:
    for state, (residues, constant, proportional), scale in zip(states, base, scales, strict=True):
        state.execution.vector_fit.residues = residues * scale
        state.execution.vector_fit.constant_coeff = constant * scale
        state.execution.vector_fit.proportional_coeff = proportional * scale


def _evaluate_scales(
    states: list[_CascadeBlockState],
    base: list[tuple[np.ndarray, np.ndarray, np.ndarray]],
    scales: tuple[float, ...],
    freqs: np.ndarray,
    config: CascadeFitConfig,
) -> tuple[dict[str, Any], list[dict[str, Any]], Any]:
    _apply_scales(states, base, scales)
    fitted_networks = [
        _sample_block_networks(state, freqs, config.reference_impedance_ohm)[1]
        for state in states
    ]
    cascaded = _cascade_networks(fitted_networks)
    return _passivity_metrics(cascaded), [_rms_gate_metrics(state) for state in states], cascaded


def _find_adjustment(
    states: list[_CascadeBlockState],
    freqs: np.ndarray,
    config: CascadeFitConfig,
) -> tuple[tuple[float, ...] | None, list[dict[str, Any]]]:
    base = _base_coefficients(states)
    identity = tuple(1.0 for _ in states)
    diagnostics: list[dict[str, Any]] = []
    baseline_metrics, baseline_rms, _ = _evaluate_scales(states, base, identity, freqs, config)
    if baseline_metrics["max_sigma"] <= 1.0 + config.cascade_passivity_epsilon:
        return identity, diagnostics

    groups = [(index,) for index in range(len(states))]
    if len(states) > 1:
        groups.append(tuple(range(len(states))))
    candidates: list[tuple[float, float, tuple[float, ...], dict[str, Any], list[dict[str, Any]]]] = []
    for group in groups:
        previous_scale = 1.0
        passing_scale: float | None = None
        passing_metrics: dict[str, Any] | None = None
        passing_rms: list[dict[str, Any]] | None = None
        for scale in np.linspace(1.0, config.minimum_scale, config.adjustment_iterations + 1)[1:]:
            scales = tuple(float(scale) if index in group else 1.0 for index in range(len(states)))
            metrics, block_rms, _ = _evaluate_scales(states, base, scales, freqs, config)
            rms_ok = all(item["target_met"] for item in block_rms)
            diagnostics.append(
                {
                    "blocks": [states[index].spec.name for index in group],
                    "scale": float(scale),
                    "cascade_max_sigma": metrics["max_sigma"],
                    "block_full_band_mean_rms": [
                        item["full_band_mean_rms_error"] for item in block_rms
                    ],
                    "block_rms_gates": block_rms,
                    "rms_ok": rms_ok,
                }
            )
            if metrics["max_sigma"] <= 1.0 + config.cascade_passivity_epsilon and rms_ok:
                passing_scale = float(scale)
                passing_metrics = metrics
                passing_rms = block_rms
                break
            previous_scale = float(scale)
        if passing_scale is None or passing_metrics is None or passing_rms is None:
            continue

        low = passing_scale
        high = previous_scale
        for _ in range(config.adjustment_iterations):
            scale = 0.5 * (low + high)
            scales = tuple(scale if index in group else 1.0 for index in range(len(states)))
            metrics, block_rms, _ = _evaluate_scales(states, base, scales, freqs, config)
            rms_ok = all(item["target_met"] for item in block_rms)
            if metrics["max_sigma"] <= 1.0 + config.cascade_passivity_epsilon and rms_ok:
                low = scale
                passing_metrics = metrics
                passing_rms = block_rms
            else:
                high = scale
        scales = tuple(low if index in group else 1.0 for index in range(len(states)))
        rms_increase = sum(
            max(0.0, value["worst_rms_ratio"] - baseline["worst_rms_ratio"])
            for value, baseline in zip(passing_rms, baseline_rms, strict=True)
        )
        total_attenuation = sum(1.0 - value for value in scales)
        candidates.append((rms_increase, total_attenuation, scales, passing_metrics, passing_rms))

    _apply_scales(states, base, identity)
    if not candidates:
        return None, diagnostics
    selected = min(candidates, key=lambda item: (item[0], item[1]))
    return selected[2], diagnostics


def _refresh_adjusted_block(
    state: _CascadeBlockState,
    scale: float,
    config: CascadeFitConfig,
) -> None:
    vector_fit = state.execution.vector_fit
    network = state.execution.network
    comparison = _comparison_rms_error(network, vector_fit, "s")
    comparison_mean = _mean_rms_error_from_sum_style(comparison, network.nports)
    frequency_metrics = _comparison_frequency_metrics(network, vector_fit, state.execution.result.config)
    target_mean = comparison_mean if frequency_metrics is None else frequency_metrics["priority_mean_rms_error"]
    passivity = check_vector_fit_passivity_hamiltonian(
        vector_fit,
        nports=network.nports,
        epsilon=config.passivity_epsilon,
    )
    passive = len(passivity.violation_bands_hz) == 0
    constant_sigma = _constant_matrix_sigma(vector_fit, network.nports)
    quality = build_quality_report(
        network=network,
        frequency_points=len(network.f),
        fit_frequency_points=state.execution.result.fit_frequency_points,
        comparison_rms_error=comparison,
        passive_after_enforce=passive,
        passivity_violations_after=passivity.violation_bands_hz,
        enforce_passivity=True,
        poles=getattr(vector_fit, "poles", None),
        profile=state.execution.result.config.quality_profile,
        comparison_rms_limit=state.execution.result.config.max_comparison_rms_error,
        passivity_epsilon=config.passivity_epsilon,
        require_dc=state.execution.result.config.require_dc,
        constant_matrix_sigma=constant_sigma,
    )
    updated_result = replace(
        state.execution.result,
        rms_error=_safe_rms_error(vector_fit, "s"),
        comparison_rms_error=comparison,
        comparison_mean_rms_error=comparison_mean,
        target_mean_rms_error=target_mean,
        priority_band_mean_rms_error=(
            None if frequency_metrics is None else frequency_metrics["priority_mean_rms_error"]
        ),
        outside_band_mean_rms_error=(
            None if frequency_metrics is None else frequency_metrics["outside_mean_rms_error"]
        ),
        weighted_mean_rms_error=(
            None if frequency_metrics is None else frequency_metrics["weighted_mean_rms_error"]
        ),
        frequency_band_metrics=None if frequency_metrics is None else frequency_metrics["bands"],
        passive_after_enforce=passive,
        passivity_violations_after=passivity.violation_bands_hz,
        passivity_max_sigma_after=passivity.max_sigma,
        passivity_max_sigma_frequency_hz_after=passivity.max_sigma_frequency_hz,
        constant_matrix_sigma=constant_sigma,
        quality_report=quality,
    )
    old_payload = json.loads(state.report_path.read_text(encoding="utf-8"))
    refreshed = _write_fit_outputs(
        replace(state.execution, result=updated_result),
        state.spice_path,
        report_path=state.report_path,
        html_report_path=state.html_report_path,
        fitted_touchstone_path=state.fitted_touchstone_path,
        rfm_path=state.rfm_path,
        rfm_wrapper_path=state.rfm_wrapper_path,
        report_top_rms=6,
        report_configuration={"cascade_adjustment_scale": scale},
    )
    state.execution = replace(state.execution, result=refreshed)
    new_payload = json.loads(state.report_path.read_text(encoding="utf-8"))
    merged_payload = dict(old_payload)
    merged_payload.update(new_payload)
    gate_metrics = _rms_gate_metrics(state)
    merged_payload["cascade_adjustment"] = {
        "method": "uniform_s_contraction",
        "scale": scale,
        "target_mean_rms_error": target_mean,
        "full_band_mean_rms_error": gate_metrics["full_band_mean_rms_error"],
        "full_band_rms_target": gate_metrics["full_band_rms_target"],
        "priority_bands": gate_metrics["priority_bands"],
        "rms_targets_met": gate_metrics["target_met"],
    }
    state.report_path.write_text(json.dumps(merged_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fit_sparam_cascade(
    manifest_path: Path,
    output_root: Path,
    *,
    config: CascadeFitConfig,
    report_path: Path | None = None,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = (report_path or output_root / "cascade_report.json").resolve()
    specs, order = _load_manifest(manifest_path, config)
    states_by_name: dict[str, _CascadeBlockState] = {}
    for spec in specs:
        state = _fit_block(spec, output_root, config)
        states_by_name[spec.name] = state
        if not state.search_result.target_met:
            payload = {
                "schema_version": "sparam_cascade_v1",
                "status": "FAIL",
                "reason": "block_fit_target_not_met",
                "failed_block": spec.name,
                "manifest_path": str(manifest_path),
                "output_root": str(output_root),
            }
            report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return payload

    states = [states_by_name[name] for name in order]
    freqs = _evaluation_frequencies(states, config.cascade_samples)
    raw_networks = []
    fitted_networks = []
    for state in states:
        raw, fitted = _sample_block_networks(state, freqs, config.reference_impedance_ohm)
        raw_networks.append(raw)
        fitted_networks.append(fitted)
    raw_cascade = _cascade_networks(raw_networks)
    fitted_cascade = _cascade_networks(fitted_networks)
    before = _passivity_metrics(fitted_cascade)

    selected_scales, adjustment_trials = _find_adjustment(states, freqs, config)
    if selected_scales is None:
        payload = {
            "schema_version": "sparam_cascade_v1",
            "status": "FAIL",
            "reason": "cascade_passivity_adjustment_failed_within_block_rms_limits",
            "manifest_path": str(manifest_path),
            "output_root": str(output_root),
            "cascade_order": order,
            "frequency_range_hz": [float(freqs[0]), float(freqs[-1])],
            "frequency_points": len(freqs),
            "passivity_before_adjustment": before,
            "adjustment_trials": adjustment_trials,
        }
        report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload

    base = _base_coefficients(states)
    _apply_scales(states, base, selected_scales)
    adjusted_fitted_networks = [
        _sample_block_networks(state, freqs, config.reference_impedance_ohm)[1]
        for state in states
    ]
    fitted_cascade = _cascade_networks(adjusted_fitted_networks)
    after = _passivity_metrics(fitted_cascade)
    for state, scale in zip(states, selected_scales, strict=True):
        if scale < 1.0:
            _refresh_adjusted_block(state, scale, config)

    cascade_touchstone = output_root / "cascade_fitted.s2p"
    write_fitted_touchstone(
        cascade_touchstone,
        freqs,
        fitted_cascade.s,
        np.full((len(freqs), 2), config.reference_impedance_ohm, dtype=float),
    )
    block_payloads = []
    for state, scale in zip(states, selected_scales, strict=True):
        gate_metrics = _rms_gate_metrics(state)
        block_payloads.append(
            {
                "name": state.spec.name,
                "touchstone_path": str(state.spec.touchstone),
                "scale": scale,
                "target_mean_rms_error": gate_metrics["full_band_mean_rms_error"],
                "target_mean_rms_limit": gate_metrics["full_band_rms_target"],
                "full_band_mean_rms_error": gate_metrics["full_band_mean_rms_error"],
                "full_band_rms_target": gate_metrics["full_band_rms_target"],
                "priority_bands": gate_metrics["priority_bands"],
                "rms_targets_met": gate_metrics["target_met"],
                "spice_path": str(state.spice_path),
                "fitted_touchstone_path": str(state.fitted_touchstone_path),
                "rfm_path": str(state.rfm_path),
                "rfm_wrapper_path": str(state.rfm_wrapper_path),
                "report_path": str(state.report_path),
                "html_report_path": str(state.html_report_path),
                "log_path": str(state.log_path),
            }
        )
    payload = {
        "schema_version": "sparam_cascade_v1",
        "status": "PASS" if after["max_sigma"] <= 1.0 + config.cascade_passivity_epsilon else "FAIL",
        "manifest_path": str(manifest_path),
        "output_root": str(output_root),
        "cascade_order": order,
        "reference_impedance_ohm": config.reference_impedance_ohm,
        "frequency_range_hz": [float(freqs[0]), float(freqs[-1])],
        "frequency_points": len(freqs),
        "evaluation_scope": "intersection_only_no_extrapolation",
        "cascade_mean_rms_error": _cascade_mean_rms(raw_cascade, fitted_cascade),
        "passivity_before_adjustment": before,
        "passivity_after_adjustment": after,
        "cascade_passivity_epsilon": config.cascade_passivity_epsilon,
        "adjustment_method": "none" if all(scale == 1.0 for scale in selected_scales) else "uniform_s_contraction",
        "selected_scales": dict(zip(order, selected_scales, strict=True)),
        "adjustment_trials": adjustment_trials,
        "cascade_touchstone_path": str(cascade_touchstone),
        "blocks": block_payloads,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
