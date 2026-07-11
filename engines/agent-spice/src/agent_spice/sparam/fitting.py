from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from html import escape
import hashlib
import inspect
import json
import logging
import math
from pathlib import Path
import re
import shutil
import threading
import time
from typing import Any, Callable, Literal

import numpy as np

from agent_spice.sparam.native_vf import NativeVectorFitting
from agent_spice.sparam.pole_relocation import streaming_pole_relocation, streaming_reciprocal_pole_relocation
from agent_spice.sparam.quality import SCHEMA_VERSION, QualityReport, build_quality_report
from agent_spice.sparam.target_fit import (
    SParamFitTarget,
    SParamOrderTrial,
    SParamTargetSearchResult,
    run_target_order_search,
    trial_from_fit_result,
)


class _LazyRf:
    def Network(self, *args: Any, **kwargs: Any) -> Any:
        import skrf as rf

        return rf.Network(*args, **kwargs)


rf = _LazyRf()
NATIVE_BASELINE_VERSION = "native-idem-fast-v1"
NATIVE_SOURCE_IDENTITY_FILES = ("fitting.py", "native_vf.py", "passivity.py", "pole_relocation.py")


@dataclass
class _ResumedTargetFitPayload:
    data: dict[str, Any]
    spice_path: Path

    def __getattr__(self, name: str) -> Any:
        if name in self.data:
            return self.data[name]
        raise AttributeError(name)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.data)


def _native_relocation_mode(nports: int) -> Literal["streaming", "streaming-reciprocal"]:
    return "streaming-reciprocal" if nports >= 30 else "streaming"


def _validated_network_nports(network: Any) -> int:
    raw_nports = getattr(network, "nports", None)
    if isinstance(raw_nports, (bool, np.bool_)) or not isinstance(raw_nports, (int, np.integer)):
        raise ValueError("network.nports must be a positive integer")
    nports = int(raw_nports)
    if nports <= 0:
        raise ValueError("network.nports must be a positive integer")
    return nports


def _configure_native_vector_fitting(vector_fit: Any, config: "SParamFitConfig", nports: int) -> None:
    vector_fit.high_frequency_complex_pair_count = config.high_frequency_complex_pair_count
    vector_fit.high_frequency_complex_pair_damping = config.high_frequency_complex_pair_damping
    vector_fit.high_frequency_complex_pair_lower_fraction = config.high_frequency_complex_pair_lower_fraction
    vector_fit.high_frequency_complex_pair_frequency_gate_enabled = (
        config.native_high_frequency_complex_pair_frequency_gate
    )
    vector_fit.high_frequency_residual_injection_enabled = config.native_high_frequency_residual_injection
    vector_fit.high_frequency_residual_injection_lower_fraction = (
        config.native_high_frequency_residual_injection_lower_fraction
    )
    vector_fit.high_frequency_residual_injection_damping = config.native_high_frequency_residual_injection_damping
    vector_fit.high_frequency_complex_pair_anchor_bands_hz = config.high_frequency_complex_pair_anchor_bands_hz
    vector_fit.high_frequency_complex_pair_anchor_strength = config.high_frequency_complex_pair_anchor_strength
    vector_fit.high_frequency_complex_pair_anchor_damping = config.high_frequency_complex_pair_anchor_damping
    vector_fit.effective_order_max = config.native_effective_order_max
    vector_fit.effective_complex_pole_count = config.native_effective_complex_pole_count
    vector_fit.effective_order_selection = config.native_effective_order_selection
    vector_fit.effective_order_passivity_weight = config.native_effective_order_passivity_weight
    vector_fit.post_relocation_effective_order_max = config.native_post_relocation_effective_order_max
    vector_fit.high_frequency_relocation_weight_enabled = config.native_high_frequency_relocation_weight
    vector_fit.high_frequency_relocation_weight_lower_fraction = config.native_high_frequency_relocation_weight_lower_fraction
    vector_fit.high_frequency_relocation_weight_gain = config.native_high_frequency_relocation_weight_gain
    vector_fit.out_of_band_pole_regularization_weight = config.native_out_of_band_pole_regularization_weight
    vector_fit.out_of_band_pole_regularization_start_fraction = (
        config.native_out_of_band_pole_regularization_start_fraction
    )
    vector_fit.dynamic_edge_c_res_regularization_enabled = config.native_dynamic_edge_c_res_regularization
    vector_fit.dynamic_edge_c_res_regularization_base_weight = config.native_dynamic_edge_c_res_regularization_base_weight
    vector_fit.dynamic_edge_c_res_regularization_start_fraction = (
        config.native_dynamic_edge_c_res_regularization_start_fraction
    )
    vector_fit.dynamic_edge_c_res_regularization_growth_threshold = (
        config.native_dynamic_edge_c_res_regularization_growth_threshold
    )
    vector_fit.relocation_frontier_enabled = config.native_relocation_frontier_enabled
    vector_fit.relocation_frontier_passivity_weight = config.native_relocation_frontier_passivity_weight
    vector_fit.relocation_frontier_max_candidates = config.native_relocation_frontier_max_candidates
    vector_fit._pole_relocation = (
        streaming_reciprocal_pole_relocation
        if _native_relocation_mode(nports) == "streaming-reciprocal"
        else streaming_pole_relocation
    )


def _create_vector_fitting(network: Any, config: "SParamFitConfig") -> NativeVectorFitting:
    vector_fit = NativeVectorFitting(network)
    _configure_native_vector_fitting(vector_fit, config, _validated_network_nports(network))
    return vector_fit


@dataclass(frozen=True)
class SParamFitConfig:
    mode: str = "auto"
    n_poles_real: int = 2
    n_poles_cmplx: int = 2
    init_pole_spacing: str = "lin"
    fit_constant: bool = True
    fit_proportional: bool = False
    enforce_dc: bool = True
    n_poles_init_real: int = 3
    n_poles_init_cmplx: int = 3
    n_poles_add: int = 3
    iters_start: int = 3
    iters_inter: int = 3
    iters_final: int = 5
    model_order_max: int = 100
    target_error: float = 0.01
    alpha: float = 0.03
    gamma: float = 0.03
    nu_samples: float = 1.0
    max_iterations: int | None = None
    parameter_type: str = "s"
    check_passivity: bool = True
    enforce_passivity: bool = True
    passivity_samples: int = 200
    passivity_max_iterations: int = 1
    passivity_active_variables: int = 3072
    passivity_f_max: float | None = None
    passivity_enforce_rms_target: float | None = None
    passivity_check_rms_target: float | None = None
    preserve_dc: bool = True
    subckt_name: str = "s_equivalent"
    create_reference_pins: bool = False
    fit_frequency_stride: int = 1
    fit_max_frequency_points: int | None = None
    fit_f_min: float | None = None
    fit_f_max: float | None = None
    use_lightweight_network: bool = False
    high_frequency_complex_pair_count: int = 0
    high_frequency_complex_pair_damping: float = 0.03
    high_frequency_complex_pair_lower_fraction: float = 0.68
    native_high_frequency_complex_pair_frequency_gate: bool = False
    native_high_frequency_residual_injection: bool = False
    native_high_frequency_residual_injection_lower_fraction: float = 0.68
    native_high_frequency_residual_injection_damping: float = 0.03
    high_frequency_complex_pair_anchor_bands_hz: tuple[tuple[float, float], ...] = ()
    high_frequency_complex_pair_anchor_strength: float = 0.0
    high_frequency_complex_pair_anchor_damping: float = 0.03
    native_effective_order_max: int | None = None
    native_effective_complex_pole_count: int | None = None
    native_effective_order_selection: str = "frequency_rank"
    native_effective_order_passivity_weight: float = 1.0
    native_post_relocation_effective_order_max: int | None = None
    native_high_frequency_relocation_weight: bool = False
    native_high_frequency_relocation_weight_lower_fraction: float = 0.68
    native_high_frequency_relocation_weight_gain: float = 2.0
    native_out_of_band_pole_regularization_weight: float = 0.0
    native_out_of_band_pole_regularization_start_fraction: float = 1.0
    native_dynamic_edge_c_res_regularization: bool = False
    native_dynamic_edge_c_res_regularization_base_weight: float = 0.0
    native_dynamic_edge_c_res_regularization_start_fraction: float = 1.0
    native_dynamic_edge_c_res_regularization_growth_threshold: float = 1.5
    native_topology_sweep: bool = False
    native_topology_passivity_weight: float = 1.0
    native_relocation_frontier_enabled: bool = False
    native_relocation_frontier_passivity_weight: float = 1.0
    native_relocation_frontier_max_candidates: int = 0
    quality_profile: str = "explore"
    max_comparison_rms_error: float = 0.05
    max_passivity_epsilon: float = 1e-6
    require_dc: bool = False
    passivity_perturb_constant: bool = False
    passivity_perturb_poles: bool = False
    passivity_constant_only_candidates: bool = False
    passivity_global_damping_fallback: bool = False
    passivity_global_damping_mode: str = "uniform"
    passivity_global_damping_selective_min_frequency: float = 5e8
    passivity_global_damping_safety_margin: float = 1e-5
    passivity_spectral_projection_fallback: bool = False
    passivity_spectral_projection_max_delta_norm: float | None = None
    passivity_spectral_projection_max_response_delta_rms: float | None = None
    passivity_spectral_projection_max_sigma_regression: float = 0.0
    passivity_spectral_projection_iterations: int = 1
    passivity_spectral_projection_reweight_iterations: int = 0
    passivity_spectral_projection_max_reference_rms_increase: float | None = None
    passivity_spectral_projection_max_reference_rms_total_increase: float | None = None
    passivity_spectral_projection_max_reference_rms_per_sigma_improvement: float | None = None
    passivity_spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement: float | None = None
    passivity_spectral_projection_late_current_clip_start_iteration: int = 0
    passivity_spectral_projection_max_reference_band_sigma_regression: float | None = None
    passivity_spectral_projection_reference_band_holdout_start_iteration: int = 0
    passivity_spectral_projection_include_all_reference_violations: bool = False
    passivity_spectral_projection_weight_mode: str = "none"
    passivity_spectral_projection_weight_exponent: float = 1.0
    passivity_spectral_projection_active_mode_candidate: bool = False
    passivity_spectral_projection_active_mode_start_iteration: int = 0
    passivity_spectral_projection_non_active_stop_iteration: int | None = None
    passivity_spectral_projection_active_mode_max_responses: int = 0
    passivity_spectral_projection_active_mode_singular_modes: int = 1
    passivity_spectral_projection_active_mode_band_singular_modes: int = 1
    passivity_spectral_projection_active_mode_band_singular_mode_sample_count: int = 1
    passivity_spectral_projection_active_mode_solver: str = "min_norm"
    passivity_spectral_projection_active_mode_target_margin: float = 0.0
    passivity_spectral_projection_active_mode_target_margin_start_iteration: int = 0
    passivity_spectral_projection_active_mode_reference_max_points: int = 0
    passivity_spectral_projection_active_mode_frequency_selection: str = "top"
    passivity_spectral_projection_active_mode_reference_weight: float = 0.0
    passivity_spectral_projection_active_mode_reference_weight_mode: str = "none"
    passivity_spectral_projection_active_mode_reference_weight_candidates: tuple[float, ...] = ()
    passivity_spectral_projection_active_mode_global_reference_points: int = 0
    passivity_spectral_projection_active_mode_max_reference_rms_total_increase: float | None = None
    passivity_spectral_projection_active_mode_extra_scales: tuple[float, ...] = ()
    passivity_spectral_projection_active_mode_extra_scales_min_sigma: float = 0.0
    passivity_spectral_projection_current_clip_candidate: bool = False
    passivity_spectral_projection_current_clip_reference_weight: float = 0.0
    passivity_spectral_projection_candidate_reference_max_points: int = 0
    passivity_spectral_projection_frequency_selection: str = "top"
    passivity_spectral_projection_band_sample_count: int = 8
    passivity_spectral_projection_reference_rms_scope: str = "projection"
    passivity_spectral_projection_reference_rms_chunk_size: int = 0
    passivity_spectral_projection_candidate_selection_metric: str = "passivity"
    passivity_spectral_projection_post_damping_selection_start_iteration: int = 0
    passivity_spectral_projection_post_damping_max_sigma_regression: float | None = None
    passivity_spectral_projection_mode_screen_candidates: int = 0
    passivity_spectral_projection_mode_screen_modes: int = 2
    passivity_constant_weight: float = 1.0
    passivity_pole_weight: float = 1.0

@dataclass(frozen=True)
class SParamFitResult:
    touchstone_path: Path
    spice_path: Path
    report_path: Path | None
    html_report_path: Path | None
    log_path: Path | None
    ports: int
    frequency_points: int
    frequency_range_hz: list[float] | None
    fit_frequency_points: int
    fit_frequency_range_hz: list[float] | None
    fit_frequency_selection: dict[str, Any]
    reference_impedance: list[float]
    config: SParamFitConfig
    rms_error: float | None
    comparison_rms_error: float | None
    passive_before_enforce: bool | None
    passive_after_enforce: bool | None
    passivity_violations_before: list[list[float]] | None
    passivity_violations_after: list[list[float]] | None
    quality_report: QualityReport
    passivity_max_sigma_before: float | None = None
    passivity_max_sigma_after: float | None = None
    passivity_max_sigma_frequency_hz_before: float | None = None
    passivity_max_sigma_frequency_hz_after: float | None = None
    passivity_enforcement_diagnostics: list[dict[str, Any]] | None = None
    comparison_mean_rms_error: float | None = None
    pre_enforcement_mean_rms_error: float | None = None
    fit_seconds: float = 0.0
    check_seconds: float = 0.0
    enforce_seconds: float = 0.0
    passivity_enforcement_skip_reason: str | None = None
    passivity_check_skip_reason: str | None = None
    elapsed_seconds: float | None = None
    peak_memory_mb: float | None = None
    stored_pole_count: int | None = None
    real_pole_count: int | None = None
    complex_pair_count: int | None = None
    expanded_model_order: int | None = None
    constant_matrix_sigma: float | None = None
    topology_sweep_diagnostics: list[dict[str, Any]] | None = None
    relocation_frontier_diagnostics: list[dict[str, Any]] | None = None
    auto_model_order_trials: list[dict[str, Any]] | None = None
    auto_model_order_selected: int | None = None
    auto_model_order_stop_reason: str | None = None
    native_baseline_version: str = NATIVE_BASELINE_VERSION

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Path):
            return self.spice_path == other
        if isinstance(other, SParamFitResult):
            return self.to_dict() == other.to_dict()
        return NotImplemented

    def to_dict(self) -> dict[str, Any]:
        quality = _quality_summary(self)
        return {
            "schema_version": SCHEMA_VERSION,
            "native_baseline_version": self.native_baseline_version,
            "touchstone_path": str(self.touchstone_path),
            "spice_path": str(self.spice_path),
            "report_path": None if self.report_path is None else str(self.report_path),
            "html_report_path": None if self.html_report_path is None else str(self.html_report_path),
            "log_path": None if self.log_path is None else str(self.log_path),
            "ports": self.ports,
            "frequency_points": self.frequency_points,
            "frequency_range_hz": self.frequency_range_hz,
            "fit_frequency_points": self.fit_frequency_points,
            "fit_frequency_range_hz": self.fit_frequency_range_hz,
            "fit_frequency_selection": self.fit_frequency_selection,
            "reference_impedance": self.reference_impedance,
            "config": asdict(self.config),
            "quality": quality,
            "diagnostics": quality["diagnostics"],
            "rms_error": self.rms_error,
            "rms_error_scope": "fit_frequency_points",
            "comparison_rms_error": self.comparison_rms_error,
            "comparison_rms_error_scope": "original_frequency_points",
            "comparison_mean_rms_error": self.comparison_mean_rms_error,
            "pre_enforcement_mean_rms_error": self.pre_enforcement_mean_rms_error,
            "fit_seconds": self.fit_seconds,
            "check_seconds": self.check_seconds,
            "enforce_seconds": self.enforce_seconds,
            "passivity_enforcement_skip_reason": self.passivity_enforcement_skip_reason,
            "passivity_check_skip_reason": self.passivity_check_skip_reason,
            "elapsed_seconds": self.elapsed_seconds,
            "peak_memory_mb": self.peak_memory_mb,
            "stored_pole_count": self.stored_pole_count,
            "real_pole_count": self.real_pole_count,
            "complex_pair_count": self.complex_pair_count,
            "expanded_model_order": self.expanded_model_order,
            "constant_matrix_sigma": self.constant_matrix_sigma,
            "topology_sweep_diagnostics": self.topology_sweep_diagnostics,
            "relocation_frontier_diagnostics": self.relocation_frontier_diagnostics,
            "auto_model_order_trials": self.auto_model_order_trials,
            "auto_model_order_selected": self.auto_model_order_selected,
            "auto_model_order_stop_reason": self.auto_model_order_stop_reason,
            "passive_before_enforce": self.passive_before_enforce,
            "passive_after_enforce": self.passive_after_enforce,
            "passivity_violations_before": self.passivity_violations_before,
            "passivity_violations_after": self.passivity_violations_after,
            "passivity_max_sigma_before": self.passivity_max_sigma_before,
            "passivity_max_sigma_after": self.passivity_max_sigma_after,
            "passivity_max_sigma_frequency_hz_before": self.passivity_max_sigma_frequency_hz_before,
            "passivity_max_sigma_frequency_hz_after": self.passivity_max_sigma_frequency_hz_after,
            "passivity_enforcement_diagnostics": self.passivity_enforcement_diagnostics,
        }


@dataclass(frozen=True)
class _LightweightSNetwork:
    f: np.ndarray
    s: np.ndarray
    z0: np.ndarray
    name: str = "network"

    @property
    def nports(self) -> int:
        return int(self.s.shape[1])

    @property
    def frequency(self) -> "_LightweightSNetwork":
        return self

    def __getitem__(self, indices: Any) -> "_LightweightSNetwork":
        return self.subset(indices)

    def subset(self, indices: Any, name: str | None = None) -> "_LightweightSNetwork":
        index_array = np.asarray(indices)
        return _LightweightSNetwork(
            f=np.asarray(self.f)[index_array],
            s=np.asarray(self.s)[index_array, :, :],
            z0=_selected_z0(self, index_array),
            name=name or self.name,
        )

    def is_passive(self, *args: Any, **kwargs: Any) -> bool:
        return False


def _touchstone_ports_from_suffix(path: Path) -> int:
    match = re.search(r"\.s(\d+)p$", path.name.lower())
    if match is None:
        raise ValueError(f"Cannot infer Touchstone port count from suffix: {path}")
    return int(match.group(1))


def _load_touchstone_s_ri_lightweight(path: Path) -> _LightweightSNetwork:
    ports = _touchstone_ports_from_suffix(path)
    expected_values = 1 + 2 * ports * ports
    frequency_scale = 1.0
    reference_ohms = 50.0
    header_seen = False
    values: list[float] = []
    frequencies: list[float] = []
    responses: list[np.ndarray] = []

    scales = {
        "hz": 1.0,
        "khz": 1.0e3,
        "mhz": 1.0e6,
        "ghz": 1.0e9,
    }

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.split("!", 1)[0].strip()
            if not line:
                continue
            if line.startswith("#"):
                tokens = line[1:].lower().split()
                if len(tokens) < 3:
                    raise ValueError(f"Unsupported Touchstone option line: {line}")
                unit, parameter, data_format = tokens[:3]
                if unit not in scales or parameter != "s" or data_format != "ri":
                    raise ValueError("Lightweight Touchstone loader only supports '# Hz S RI R ...' style data")
                frequency_scale = scales[unit]
                if "r" in tokens:
                    r_index = tokens.index("r")
                    if r_index + 1 < len(tokens):
                        reference_ohms = float(tokens[r_index + 1])
                header_seen = True
                continue
            if not header_seen:
                continue

            values.extend(float(item) for item in line.split())
            while len(values) >= expected_values:
                point = values[:expected_values]
                del values[:expected_values]
                frequencies.append(point[0] * frequency_scale)
                pairs = point[1:]
                complex_values = [complex(pairs[i], pairs[i + 1]) for i in range(0, len(pairs), 2)]
                responses.append(np.asarray(complex_values, dtype=complex).reshape(ports, ports))

    if values:
        raise ValueError(f"Incomplete Touchstone data block in {path}")
    if not frequencies:
        raise ValueError(f"No S-parameter samples found in {path}")
    f = np.asarray(frequencies, dtype=float)
    s = np.asarray(responses, dtype=complex)
    z0 = np.full((len(frequencies), ports), complex(reference_ohms), dtype=complex)
    return _LightweightSNetwork(f=f, s=s, z0=z0, name=path.stem)


class _FitResourceMonitor:
    def __init__(self, interval_seconds: float = 0.05):
        self.interval_seconds = interval_seconds
        self.elapsed_seconds: float | None = None
        self.peak_memory_mb: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = 0.0
        self._process = None

    def __enter__(self) -> "_FitResourceMonitor":
        self._started = time.perf_counter()
        try:
            import psutil

            self._process = psutil.Process()
            self.peak_memory_mb = self._rss_mb()
            self._thread = threading.Thread(target=self._sample_loop, daemon=True)
            self._thread.start()
        except Exception:
            self._process = None
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.elapsed_seconds = time.perf_counter() - self._started
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=1.0)
        if self._process is not None:
            current = self._rss_mb()
            self.peak_memory_mb = current if self.peak_memory_mb is None else max(self.peak_memory_mb, current)

    def _rss_mb(self) -> float:
        return float(self._process.memory_info().rss) / (1024.0 * 1024.0)

    def _sample_loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            current = self._rss_mb()
            self.peak_memory_mb = current if self.peak_memory_mb is None else max(self.peak_memory_mb, current)


def _reference_impedance(network: Any) -> list[float]:
    if len(network.z0) == 0:
        return []
    return [float(value.real) for value in network.z0[0]]


def _frequency_range(network: Any) -> list[float] | None:
    if len(network.f) == 0:
        return None
    return [float(network.f[0]), float(network.f[-1])]


def _frequency_selection_summary(config: SParamFitConfig) -> dict[str, Any]:
    return {
        "stride": config.fit_frequency_stride,
        "max_points": config.fit_max_frequency_points,
        "f_min": config.fit_f_min,
        "f_max": config.fit_f_max,
    }


def _selected_z0(network: Any, indices: np.ndarray) -> Any:
    z0 = np.asarray(network.z0)
    if z0.ndim < 2:
        return network.z0
    return z0[indices, :]


def _select_fit_network(network: Any, config: SParamFitConfig) -> Any:
    if config.fit_frequency_stride < 1:
        raise ValueError("fit_frequency_stride must be >= 1")
    if config.fit_max_frequency_points is not None and config.fit_max_frequency_points < 1:
        raise ValueError("fit_max_frequency_points must be >= 1")

    indices = np.arange(len(network.f))
    if config.fit_f_min is not None:
        indices = indices[network.f[indices] >= config.fit_f_min]
    if config.fit_f_max is not None:
        indices = indices[network.f[indices] <= config.fit_f_max]
    if len(indices) == 0:
        raise ValueError("Frequency selection produced no samples for vector fitting")

    if config.fit_frequency_stride > 1:
        indices = indices[:: config.fit_frequency_stride]

    if config.fit_max_frequency_points is not None and len(indices) > config.fit_max_frequency_points:
        sampled_positions = np.linspace(0, len(indices) - 1, config.fit_max_frequency_points, dtype=int)
        indices = indices[np.unique(sampled_positions)]
    if len(indices) < 2:
        raise ValueError("Frequency selection must contain at least 2 samples for vector fitting")

    if len(indices) == len(network.f) and np.array_equal(indices, np.arange(len(network.f))):
        return network

    if isinstance(network, _LightweightSNetwork):
        return network.subset(indices, name=f"{getattr(network, 'name', 'network')}_fit_subset")

    return rf.Network(
        frequency=network.frequency[indices],
        s=network.s[indices, :, :],
        z0=_selected_z0(network, indices),
        name=f"{getattr(network, 'name', 'network')}_fit_subset",
    )


def _safe_bool(method, **kwargs) -> bool | None:
    try:
        return bool(_call_with_supported_kwargs(method, **kwargs))
    except Exception:
        return None


def _call_with_supported_kwargs(method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(*args, **kwargs)
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return method(*args, **kwargs)
    supported_kwargs = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return method(*args, **supported_kwargs)


class _ProgressLog:
    def __init__(self, path: Path | None):
        self.path = path
        self.handler: logging.Handler | None = None
        self.loggers: list[logging.Logger] = []
        self.old_levels: dict[logging.Logger, int] = {}
        self.progress_logger = logging.getLogger("agent_spice.sparam.fitting")

    def __enter__(self) -> "_ProgressLog":
        if self.path is None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handler = logging.FileHandler(self.path, mode="w", encoding="utf-8")
        self.handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        self.loggers = [
            self.progress_logger,
            logging.getLogger("agent_spice.sparam.native_vf"),
        ]
        for logger in self.loggers:
            self.old_levels[logger] = logger.level
            logger.addHandler(self.handler)
            logger.setLevel(logging.INFO)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc is not None:
            self.exception("fit-sparam failed")
        if self.handler is None:
            return
        for logger in self.loggers:
            logger.removeHandler(self.handler)
            logger.setLevel(self.old_levels[logger])
        self.handler.close()

    def info(self, message: str) -> None:
        if self.handler is None:
            return
        self.progress_logger.info(message)
        self.handler.flush()

    def exception(self, message: str) -> None:
        if self.handler is None:
            return
        self.progress_logger.exception(message)
        self.handler.flush()


def _safe_passivity_violations(vector_fit: Any, parameter_type: str) -> list[list[float]] | None:
    try:
        violations = _call_with_supported_kwargs(vector_fit.passivity_test, parameter_type=parameter_type)
    except Exception:
        return None
    if violations is None:
        return None
    if hasattr(violations, "tolist"):
        violations = violations.tolist()
    if violations == []:
        return []
    if violations and not isinstance(violations[0], (list, tuple)):
        violations = [violations]
    return [[float(value) for value in band] for band in violations]


def _safe_rms_error(vector_fit: Any, parameter_type: str) -> float | None:
    try:
        return float(_call_with_supported_kwargs(vector_fit.get_rms_error, parameter_type=parameter_type))
    except Exception:
        return None


def _model_response_at_frequencies(
    vector_fit: Any,
    row: int,
    column: int,
    freqs: Any,
) -> list[complex] | None:
    if not hasattr(vector_fit, "get_model_response"):
        return None
    method = vector_fit.get_model_response
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        try:
            fitted = method(row, column, freqs=freqs)
        except Exception:
            return None
    else:
        parameters = list(signature.parameters.values())
        supports_freqs_keyword = "freqs" in signature.parameters or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters
        )
        supports_third_positional = any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters)
        supports_third_positional = supports_third_positional or sum(
            parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            for parameter in parameters
        ) >= 3
        try:
            if supports_freqs_keyword:
                fitted = method(row, column, freqs=freqs)
            elif supports_third_positional:
                fitted = method(row, column, freqs)
            else:
                return None
        except Exception:
            return None
    try:
        fitted_values = [complex(value) for value in fitted]
    except Exception:
        return None
    if len(fitted_values) != len(freqs):
        return None
    return fitted_values


def _comparison_rms_error(network: Any, vector_fit: Any, parameter_type: str) -> float | None:
    network_values = getattr(network, parameter_type.lower(), None)
    if network_values is None or not hasattr(network, "f") or not hasattr(network, "nports"):
        return None
    try:
        network_array = np.asarray(network_values)
        error_mean_squared = 0.0
        for row in range(network.nports):
            for column in range(network.nports):
                fitted = _model_response_at_frequencies(vector_fit, row, column, network.f)
                if fitted is None:
                    return None
                original = network_array[:, row, column].astype(complex)
                error_mean_squared += float(np.mean(np.square(np.abs(original - np.asarray(fitted)))))
        return float(math.sqrt(error_mean_squared))
    except Exception:
        return None


def _mean_rms_error_from_sum_style(value: float | None, ports: int) -> float | None:
    if value is None:
        return None
    if ports <= 0:
        return float(value)
    return float(value) / float(ports)


def _pole_summary(vector_fit: Any) -> dict[str, int | None]:
    poles = getattr(vector_fit, "poles", None)
    if poles is None:
        return {
            "stored_pole_count": None,
            "real_pole_count": None,
            "complex_pair_count": None,
            "expanded_model_order": None,
        }
    try:
        pole_array = np.asarray(poles, dtype=complex).reshape(-1)
    except Exception:
        return {
            "stored_pole_count": None,
            "real_pole_count": None,
            "complex_pair_count": None,
            "expanded_model_order": None,
        }
    real_count = int(np.count_nonzero(np.isclose(pole_array.imag, 0.0)))
    complex_pair_count = int(len(pole_array) - real_count)
    return {
        "stored_pole_count": int(len(pole_array)),
        "real_pole_count": real_count,
        "complex_pair_count": complex_pair_count,
        "expanded_model_order": real_count + 2 * complex_pair_count,
    }


def _constant_matrix_sigma(vector_fit: Any, ports: int) -> float | None:
    if ports <= 0:
        return None
    constant_coeff = getattr(vector_fit, "constant_coeff", None)
    if constant_coeff is None:
        return None
    try:
        matrix = np.asarray(constant_coeff, dtype=complex).reshape(ports, ports)
        values = np.linalg.svd(matrix, compute_uv=False)
    except Exception:
        return None
    if values.size == 0:
        return None
    return float(values[0])


def _quality_summary(result: SParamFitResult) -> dict[str, Any]:
    if result.passive_after_enforce is True:
        passivity = "passive"
    elif result.passive_after_enforce is False:
        passivity = "violations remain"
    else:
        passivity = "unknown"
    payload = result.quality_report.to_dict()
    payload.update(
        {
            "rms_error": result.rms_error,
            "rms_error_scope": "fit_frequency_points",
            "comparison_rms_error": result.comparison_rms_error,
            "comparison_rms_error_scope": "original_frequency_points",
            "comparison_mean_rms_error": result.comparison_mean_rms_error,
            "passivity": passivity,
            "passivity_enforcement_enabled": result.config.enforce_passivity,
            "violation_bands_after": len(result.passivity_violations_after or []),
        }
    )
    return payload


def _format_float(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6g}"


def _format_hz(value: float | None) -> str:
    if value is None:
        return "n/a"
    units = [(1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz")]
    for scale, suffix in units:
        if abs(value) >= scale:
            return f"{value / scale:.6g} {suffix}"
    return f"{value:.6g} Hz"


def _format_bool(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _format_cell(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _network_s_value(network: Any, point_index: int, row: int, column: int) -> complex:
    try:
        return complex(network.s[point_index, row, column])
    except TypeError:
        return complex(network.s[point_index][row][column])


def _to_db(value: complex) -> float:
    magnitude = max(abs(value), 1e-300)
    return 20.0 * math.log10(magnitude)


def _comparison_traces(network: Any, vector_fit: Any, max_traces: int = 16) -> list[dict[str, Any]]:
    if not hasattr(network, "s") or not hasattr(vector_fit, "get_model_response"):
        return []
    traces: list[dict[str, Any]] = []
    freqs = [float(value) for value in network.f]
    for row in range(network.nports):
        for column in range(network.nports):
            if len(traces) >= max_traces:
                return traces
            try:
                fitted = _model_response_at_frequencies(vector_fit, row, column, network.f)
                if fitted is None:
                    continue
                original_db = [_to_db(_network_s_value(network, idx, row, column)) for idx in range(len(freqs))]
                fitted_db = [_to_db(value) for value in fitted]
            except Exception:
                continue
            traces.append(
                {
                    "label": f"S{row + 1}{column + 1}",
                    "frequencies_hz": freqs,
                    "original_db": original_db,
                    "fitted_db": fitted_db,
                }
            )
    return traces


def _svg_polyline(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def _render_trace_chart(trace: dict[str, Any]) -> str:
    width = 760
    height = 320
    left = 64
    right = 24
    top = 24
    bottom = 48
    plot_width = width - left - right
    plot_height = height - top - bottom
    freqs = trace["frequencies_hz"]
    values = trace["original_db"] + trace["fitted_db"]
    y_min = min(values)
    y_max = max(values)
    if math.isclose(y_min, y_max):
        y_min -= 1.0
        y_max += 1.0
    padding = max((y_max - y_min) * 0.08, 0.5)
    y_min -= padding
    y_max += padding
    positive_freqs = [max(freq, 1e-300) for freq in freqs]
    x_min = math.log10(min(positive_freqs))
    x_max = math.log10(max(positive_freqs))
    if math.isclose(x_min, x_max):
        x_max += 1.0

    def map_points(series: list[float]) -> list[tuple[float, float]]:
        points = []
        for freq, value in zip(positive_freqs, series):
            x = left + ((math.log10(freq) - x_min) / (x_max - x_min)) * plot_width
            y = top + ((y_max - value) / (y_max - y_min)) * plot_height
            points.append((x, y))
        return points

    original_points = _svg_polyline(map_points(trace["original_db"]))
    fitted_points = _svg_polyline(map_points(trace["fitted_db"]))
    x_start = _format_hz(min(freqs))
    x_end = _format_hz(max(freqs))
    y_top = _format_float(y_max)
    y_bottom = _format_float(y_min)
    label = escape(trace["label"])
    return f"""
<section class="chart">
  <h3>{label} Original vs Fitted</h3>
  <svg viewBox="0 0 {width} {height}" role="img" aria-label="{label} original vs fitted magnitude">
    <rect x="0" y="0" width="{width}" height="{height}" class="plot-bg" />
    <line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" class="axis" />
    <line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" class="axis" />
    <text x="12" y="{top + 4}" class="tick">{y_top} dB</text>
    <text x="12" y="{height - bottom}" class="tick">{y_bottom} dB</text>
    <text x="{left}" y="{height - 18}" class="tick">{escape(x_start)}</text>
    <text x="{width - right - 92}" y="{height - 18}" class="tick">{escape(x_end)}</text>
    <polyline points="{original_points}" class="line original" />
    <polyline points="{fitted_points}" class="line fitted" />
  </svg>
  <div class="legend"><span class="swatch original"></span>Original Touchstone <span class="swatch fitted"></span>Fitted model</div>
</section>
"""


def _render_html_report(result: SParamFitResult, traces: list[dict[str, Any]]) -> str:
    quality = _quality_summary(result)
    freq_start = None if result.frequency_range_hz is None else result.frequency_range_hz[0]
    freq_end = None if result.frequency_range_hz is None else result.frequency_range_hz[1]
    fit_freq_start = None if result.fit_frequency_range_hz is None else result.fit_frequency_range_hz[0]
    fit_freq_end = None if result.fit_frequency_range_hz is None else result.fit_frequency_range_hz[1]
    selection_rows = "".join(
        f"<tr><td>{escape(key)}</td><td>{escape(_format_cell(value))}</td></tr>"
        for key, value in result.fit_frequency_selection.items()
    )
    violation_rows = "\n".join(
        f"<tr><td>{_format_hz(band[0])}</td><td>{_format_hz(band[1])}</td></tr>"
        for band in (result.passivity_violations_after or [])
    )
    if not violation_rows:
        violation_rows = "<tr><td colspan=\"2\">No violation bands reported after enforcement.</td></tr>"
    diagnostic_rows = "\n".join(
        "<tr>"
        f"<td>{escape(_format_cell(diagnostic['id']))}</td>"
        f"<td>{escape(_format_cell(diagnostic['status']))}</td>"
        f"<td>{escape(_format_cell(diagnostic['severity']))}</td>"
        f"<td>{escape(_format_cell(diagnostic['metric']))}</td>"
        f"<td>{escape(_format_cell(diagnostic['threshold']))}</td>"
        f"<td>{escape(_format_cell(diagnostic['message']))}</td>"
        f"<td>{escape(_format_cell(diagnostic['recommendation']))}</td>"
        "</tr>"
        for diagnostic in quality["diagnostics"]
    )
    if not diagnostic_rows:
        diagnostic_rows = "<tr><td colspan=\"7\">No quality diagnostics reported.</td></tr>"
    trace_sections = "\n".join(_render_trace_chart(trace) for trace in traces)
    if not trace_sections:
        trace_sections = "<p class=\"muted\">Comparison plot unavailable for this scikit-rf version or input.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>S-Parameter Fit Report</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; color: #17202a; background: #f7f9fb; }}
    h1, h2, h3 {{ color: #102a43; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }}
    .card {{ background: white; border: 1px solid #d9e2ec; border-radius: 8px; padding: 14px; }}
    .label {{ color: #627d98; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    .value {{ font-size: 20px; font-weight: 650; margin-top: 6px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; margin: 12px 0 24px; }}
    th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #d9e2ec; }}
    th {{ background: #eef2f7; }}
    .chart {{ background: white; border: 1px solid #d9e2ec; border-radius: 8px; padding: 16px; margin: 14px 0; }}
    svg {{ width: 100%; max-width: 900px; height: auto; }}
    .plot-bg {{ fill: #fbfdff; }}
    .axis {{ stroke: #829ab1; stroke-width: 1.2; }}
    .tick {{ fill: #52606d; font-size: 12px; }}
    .line {{ fill: none; stroke-width: 2.4; }}
    .original {{ stroke: #1f77b4; }}
    .fitted {{ stroke: #d62728; stroke-dasharray: 6 4; }}
    .legend {{ color: #52606d; font-size: 13px; }}
    .swatch {{ display: inline-block; width: 22px; height: 3px; margin: 0 6px 3px 14px; vertical-align: middle; }}
    .swatch.original {{ background: #1f77b4; }}
    .swatch.fitted {{ background: repeating-linear-gradient(90deg, #d62728 0 8px, transparent 8px 13px); }}
    .muted {{ color: #627d98; }}
  </style>
</head>
<body>
  <h1>S-Parameter Fit Report</h1>
  <div class="cards">
    <div class="card"><div class="label">Ports</div><div class="value">{result.ports}</div></div>
    <div class="card"><div class="label">Frequency Points</div><div class="value">{result.frequency_points}</div></div>
    <div class="card"><div class="label">Fit Frequency Points</div><div class="value">{result.fit_frequency_points}</div></div>
    <div class="card"><div class="label">Fit-Sample RMS Error</div><div class="value">{_format_float(result.rms_error)}</div></div>
    <div class="card"><div class="label">Original-Point RMS Error</div><div class="value">{_format_float(result.comparison_rms_error)}</div></div>
    <div class="card"><div class="label">Quality</div><div class="value">{escape(str(quality["status"]))}</div></div>
    <div class="card"><div class="label">Passivity</div><div class="value">{escape(str(quality["passivity"]))}</div></div>
  </div>

  <h2>Quality Gate</h2>
  <table>
    <tr><th>Item</th><th>Value</th></tr>
    <tr><td>Profile</td><td>{escape(str(quality["profile"]))}</td></tr>
    <tr><td>Status</td><td>{escape(str(quality["status"]))}</td></tr>
    <tr><td>Allowed for</td><td>{escape(str(quality["allowed_for"]))}</td></tr>
    <tr><td>Blocking reasons</td><td>{escape(', '.join(quality["blocking_reasons"]))}</td></tr>
    <tr><td>Warnings</td><td>{escape(', '.join(quality["warnings"]))}</td></tr>
  </table>
  <table>
    <tr><th>Diagnostic</th><th>Status</th><th>Severity</th><th>Metric</th><th>Threshold</th><th>Message</th><th>Recommendation</th></tr>
    {diagnostic_rows}
  </table>

  <h2>Input And Output</h2>
  <table>
    <tr><th>Item</th><th>Value</th></tr>
    <tr><td>Touchstone</td><td>{escape(str(result.touchstone_path))}</td></tr>
    <tr><td>SPICE subcircuit</td><td>{escape(str(result.spice_path))}</td></tr>
    <tr><td>JSON report</td><td>{escape(str(result.report_path))}</td></tr>
    <tr><td>Frequency span</td><td>{_format_hz(freq_start)} to {_format_hz(freq_end)}</td></tr>
    <tr><td>Reference impedance</td><td>{escape(', '.join(_format_float(value) for value in result.reference_impedance))}</td></tr>
  </table>

  <h2>Fit Sample Selection</h2>
  <table>
    <tr><th>Item</th><th>Value</th></tr>
    <tr><td>Original frequency points</td><td>{result.frequency_points}</td></tr>
    <tr><td>Fit frequency points</td><td>{result.fit_frequency_points}</td></tr>
    <tr><td>Original frequency span</td><td>{_format_hz(freq_start)} to {_format_hz(freq_end)}</td></tr>
    <tr><td>Fit frequency span</td><td>{_format_hz(fit_freq_start)} to {_format_hz(fit_freq_end)}</td></tr>
    <tr><td>Fit-sample RMS error</td><td>{_format_float(result.rms_error)}</td></tr>
    <tr><td>Original-point comparison RMS error</td><td>{_format_float(result.comparison_rms_error)}</td></tr>
    {selection_rows}
  </table>

  <h2>Fit Configuration</h2>
  <table>
    <tr><th>Field</th><th>Value</th></tr>
    {''.join(f'<tr><td>{escape(key)}</td><td>{escape(_format_cell(value))}</td></tr>' for key, value in asdict(result.config).items())}
  </table>

  <h2>Passivity</h2>
  <table>
    <tr><th>Check</th><th>Value</th></tr>
    <tr><td>Passive before enforcement</td><td>{_format_bool(result.passive_before_enforce)}</td></tr>
    <tr><td>Passive after enforcement</td><td>{_format_bool(result.passive_after_enforce)}</td></tr>
    <tr><td>Enforcement enabled</td><td>{_format_bool(result.config.enforce_passivity)}</td></tr>
  </table>
  <table>
    <tr><th>Violation band start</th><th>Violation band end</th></tr>
    {violation_rows}
  </table>

  <h2>Original vs Fitted</h2>
  {trace_sections}
</body>
</html>
"""


def _fit_model(vector_fit: Any, config: SParamFitConfig) -> None:
    if config.max_iterations is not None and hasattr(vector_fit, "max_iterations"):
        vector_fit.max_iterations = config.max_iterations
    network = getattr(vector_fit, "network", None)
    original_is_passive = getattr(network, "is_passive", None)
    if not config.check_passivity and original_is_passive is not None:
        try:
            setattr(network, "is_passive", lambda *args, **kwargs: False)
        except Exception:
            original_is_passive = None
    try:
        _fit_model_inner(vector_fit, config)
    finally:
        if original_is_passive is not None:
            try:
                setattr(network, "is_passive", original_is_passive)
            except Exception:
                pass


def _fit_model_inner(vector_fit: Any, config: SParamFitConfig) -> None:
    if config.mode == "auto":
        _call_with_supported_kwargs(
            vector_fit.auto_fit,
            n_poles_init_real=config.n_poles_init_real,
            n_poles_init_cmplx=config.n_poles_init_cmplx,
            n_poles_add=config.n_poles_add,
            model_order_max=config.model_order_max,
            iters_start=config.iters_start,
            iters_inter=config.iters_inter,
            iters_final=config.iters_final,
            target_error=config.target_error,
            alpha=config.alpha,
            gamma=config.gamma,
            nu_samples=config.nu_samples,
            parameter_type=config.parameter_type,
            enforce_dc=config.enforce_dc,
        )
        return
    if config.mode == "manual":
        if config.native_topology_sweep and hasattr(vector_fit, "vector_fit_topology_sweep"):
            _call_with_supported_kwargs(
                vector_fit.vector_fit_topology_sweep,
                candidate_configs=_native_topology_sweep_candidate_configs(config),
                init_pole_spacing=config.init_pole_spacing,
                parameter_type=config.parameter_type,
                fit_constant=config.fit_constant,
                fit_proportional=config.fit_proportional,
                enforce_dc=config.enforce_dc,
                passivity_weight=config.native_topology_passivity_weight,
            )
            return
        _call_with_supported_kwargs(
            vector_fit.vector_fit,
            n_poles_real=config.n_poles_real,
            n_poles_cmplx=config.n_poles_cmplx,
            init_pole_spacing=config.init_pole_spacing,
            parameter_type=config.parameter_type,
            fit_constant=config.fit_constant,
            fit_proportional=config.fit_proportional,
            enforce_dc=config.enforce_dc,
        )
        return
    raise ValueError(f"Unsupported S-parameter fit mode '{config.mode}'")


def _native_topology_sweep_candidate_configs(config: SParamFitConfig) -> list[dict[str, Any]]:
    base = {
        "n_poles_real": int(config.n_poles_real),
        "n_poles_cmplx": int(config.n_poles_cmplx),
        "high_frequency_complex_pair_count": int(config.high_frequency_complex_pair_count),
        "high_frequency_complex_pair_damping": float(config.high_frequency_complex_pair_damping),
        "high_frequency_complex_pair_lower_fraction": float(config.high_frequency_complex_pair_lower_fraction),
    }
    candidates = [base]
    richer = {
        **base,
        "n_poles_cmplx": int(config.n_poles_cmplx) + 1,
        "high_frequency_complex_pair_count": max(
            int(config.high_frequency_complex_pair_count),
            int(config.n_poles_cmplx) + 1,
        ),
    }
    if richer != base:
        candidates.append(richer)
    aggressive = {
        **base,
        "n_poles_real": max(0, int(config.n_poles_real) - 2),
        "n_poles_cmplx": int(config.n_poles_cmplx) + 2,
        "high_frequency_complex_pair_count": max(
            int(config.high_frequency_complex_pair_count),
            int(config.n_poles_cmplx) + 2,
        ),
    }
    if aggressive not in candidates:
        candidates.append(aggressive)
    return candidates


def _uses_low_memory_passivity(config: SParamFitConfig) -> bool:
    return config.parameter_type.lower() == "s"


def _effective_passivity_f_max(config: SParamFitConfig, network: Any) -> float | None:
    if config.passivity_f_max is not None:
        return config.passivity_f_max
    if _uses_low_memory_passivity(config):
        freqs = getattr(network, "f", None)
        if freqs is not None and len(freqs) > 0:
            return float(freqs[-1])
    return None


def _native_manual_auto_order_config(base_config: SParamFitConfig, order: int) -> SParamFitConfig:
    if order < 1:
        raise ValueError("order must be >= 1")
    trial_config = replace(base_config, model_order_max=order)
    if base_config.mode != "manual":
        return trial_config

    preferred_complex_count = 2
    n_poles_cmplx = min(preferred_complex_count, order // 2)
    n_poles_real = order - 2 * n_poles_cmplx
    return replace(
        trial_config,
        n_poles_real=n_poles_real,
        n_poles_cmplx=n_poles_cmplx,
        native_post_relocation_effective_order_max=order,
        native_effective_complex_pole_count=n_poles_cmplx,
    )


def fit_touchstone_to_spice(
    touchstone_path: Path,
    output_path: Path,
    config: SParamFitConfig | None = None,
    report_path: Path | None = None,
    html_report_path: Path | None = None,
    log_path: Path | None = None,
) -> SParamFitResult:
    config = config or SParamFitConfig()
    resource_monitor = _FitResourceMonitor()
    resource_monitor.__enter__()
    with _ProgressLog(log_path) as progress:
        progress.info(f"loading Touchstone: {touchstone_path}")
        if config.use_lightweight_network:
            if config.parameter_type.lower() != "s":
                raise ValueError("use_lightweight_network only supports S-parameter fitting")
            network = _load_touchstone_s_ri_lightweight(touchstone_path)
        else:
            network = rf.Network(str(touchstone_path))
        progress.info(
            f"loaded Touchstone: ports={network.nports}, frequency_points={len(network.f)}, "
            f"frequency_range={_frequency_range(network)}"
        )
        fit_network = _select_fit_network(network, config)
        if fit_network is network:
            progress.info("using all frequency points for vector fit")
        else:
            progress.info(
                f"using frequency subset for vector fit: {len(fit_network.f)} of {len(network.f)} points, "
                f"range={_frequency_range(fit_network)}, selection={_frequency_selection_summary(config)}"
            )
        vector_fit = _create_vector_fitting(fit_network, config)
        progress.info(f"starting vector fit: mode={config.mode}, parameter_type={config.parameter_type}")
        fit_started = time.perf_counter()
        _fit_model(vector_fit, config)
        fit_seconds = time.perf_counter() - fit_started
        progress.info("vector fit finished")
        check_seconds = 0.0
        enforce_seconds = 0.0
        pre_comparison_rms_error = _comparison_rms_error(network, vector_fit, config.parameter_type)
        pre_enforcement_mean_rms_error = _mean_rms_error_from_sum_style(
            pre_comparison_rms_error,
            network.nports,
        )
        if config.passivity_enforce_rms_target is not None and (
            not math.isfinite(config.passivity_enforce_rms_target)
            or config.passivity_enforce_rms_target <= 0.0
        ):
            raise ValueError("passivity_enforce_rms_target must be finite and > 0")
        if config.passivity_check_rms_target is not None and (
            not math.isfinite(config.passivity_check_rms_target)
            or config.passivity_check_rms_target <= 0.0
        ):
            raise ValueError("passivity_check_rms_target must be finite and > 0")
        passivity_enforcement_skip_reason = None
        passivity_check_skip_reason = None
        should_enforce = bool(config.enforce_passivity)
        should_check = bool(config.check_passivity)
        if (
            should_enforce
            and config.passivity_enforce_rms_target is not None
            and pre_enforcement_mean_rms_error is not None
            and pre_enforcement_mean_rms_error > config.passivity_enforce_rms_target
        ):
            should_enforce = False
            passivity_enforcement_skip_reason = "pre_rms_above_target"
            progress.info(
                "skipping passivity enforcement because pre-enforcement mean RMS "
                f"{pre_enforcement_mean_rms_error:.9g} exceeds target "
                f"{config.passivity_enforce_rms_target:.9g}"
            )
        if (
            should_check
            and config.passivity_check_rms_target is not None
            and pre_enforcement_mean_rms_error is not None
            and pre_enforcement_mean_rms_error > config.passivity_check_rms_target
        ):
            should_check = False
            passivity_check_skip_reason = "pre_rms_above_target"
            progress.info(
                "skipping passivity check because pre-enforcement mean RMS "
                f"{pre_enforcement_mean_rms_error:.9g} exceeds target "
                f"{config.passivity_check_rms_target:.9g}"
            )
        use_low_memory_passivity = _uses_low_memory_passivity(config)
        passivity_f_max = _effective_passivity_f_max(config, network)
        if not should_check:
            progress.info("passivity checks skipped")
            passive_before = None
            violations_before = None
            passivity_max_sigma_before = None
            passivity_max_sigma_frequency_before = None
            if should_enforce:
                enforce_started = time.perf_counter()
                if use_low_memory_passivity:
                    progress.info("starting passivity enforcement using low-memory residue perturbation")
                    from .passivity import enforce_passivity_hamiltonian

                    enforce_passivity_hamiltonian(
                        vector_fit,
                        nports=network.nports,
                        epsilon=config.max_passivity_epsilon,
                        max_iterations=config.passivity_max_iterations,
                        f_max=passivity_f_max,
                        max_violation_samples=config.passivity_samples,
                        max_active_variables=config.passivity_active_variables,
                        perturb_constant=config.passivity_perturb_constant,
                        perturb_poles=config.passivity_perturb_poles,
                        constant_only_candidates=config.passivity_constant_only_candidates,
                        global_damping_fallback=config.passivity_global_damping_fallback,
                        global_damping_mode=config.passivity_global_damping_mode,
                        global_damping_selective_min_frequency=(
                            config.passivity_global_damping_selective_min_frequency
                        ),
                        global_damping_safety_margin=config.passivity_global_damping_safety_margin,
                        spectral_projection_fallback=config.passivity_spectral_projection_fallback,
                        spectral_projection_max_delta_norm=config.passivity_spectral_projection_max_delta_norm,
                        spectral_projection_max_response_delta_rms=(
                            config.passivity_spectral_projection_max_response_delta_rms
                        ),
                        spectral_projection_max_sigma_regression=(
                            config.passivity_spectral_projection_max_sigma_regression
                        ),
                        spectral_projection_iterations=config.passivity_spectral_projection_iterations,
                        spectral_projection_reweight_iterations=(
                            config.passivity_spectral_projection_reweight_iterations
                        ),
                        spectral_projection_reference_freqs=network.f,
                        spectral_projection_reference_s=network.s,
                        spectral_projection_max_reference_rms_increase=(
                            config.passivity_spectral_projection_max_reference_rms_increase
                        ),
                        spectral_projection_max_reference_rms_total_increase=(
                            config.passivity_spectral_projection_max_reference_rms_total_increase
                        ),
                        spectral_projection_max_reference_rms_per_sigma_improvement=(
                            config.passivity_spectral_projection_max_reference_rms_per_sigma_improvement
                        ),
                        spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement=(
                            config.passivity_spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement
                        ),
                        spectral_projection_late_current_clip_start_iteration=(
                            config.passivity_spectral_projection_late_current_clip_start_iteration
                        ),
                        spectral_projection_max_reference_band_sigma_regression=(
                            config.passivity_spectral_projection_max_reference_band_sigma_regression
                        ),
                        spectral_projection_reference_band_holdout_start_iteration=(
                            config.passivity_spectral_projection_reference_band_holdout_start_iteration
                        ),
                        spectral_projection_include_all_reference_violations=(
                            config.passivity_spectral_projection_include_all_reference_violations
                        ),
                        spectral_projection_weight_mode=config.passivity_spectral_projection_weight_mode,
                        spectral_projection_weight_exponent=config.passivity_spectral_projection_weight_exponent,
                        spectral_projection_active_mode_candidate=(
                            config.passivity_spectral_projection_active_mode_candidate
                        ),
                        spectral_projection_active_mode_start_iteration=(
                            config.passivity_spectral_projection_active_mode_start_iteration
                        ),
                        spectral_projection_non_active_stop_iteration=(
                            config.passivity_spectral_projection_non_active_stop_iteration
                        ),
                        spectral_projection_active_mode_max_responses=(
                            config.passivity_spectral_projection_active_mode_max_responses
                        ),
                        spectral_projection_active_mode_singular_modes=(
                            config.passivity_spectral_projection_active_mode_singular_modes
                        ),
                        spectral_projection_active_mode_band_singular_modes=(
                            config.passivity_spectral_projection_active_mode_band_singular_modes
                        ),
                        spectral_projection_active_mode_band_singular_mode_sample_count=(
                            config.passivity_spectral_projection_active_mode_band_singular_mode_sample_count
                        ),
                        spectral_projection_active_mode_solver=(
                            config.passivity_spectral_projection_active_mode_solver
                        ),
                        spectral_projection_active_mode_target_margin=(
                            config.passivity_spectral_projection_active_mode_target_margin
                        ),
                        spectral_projection_active_mode_target_margin_start_iteration=(
                            config.passivity_spectral_projection_active_mode_target_margin_start_iteration
                        ),
                        spectral_projection_active_mode_reference_max_points=(
                            config.passivity_spectral_projection_active_mode_reference_max_points
                        ),
                        spectral_projection_active_mode_frequency_selection=(
                            config.passivity_spectral_projection_active_mode_frequency_selection
                        ),
                        spectral_projection_active_mode_reference_weight=(
                            config.passivity_spectral_projection_active_mode_reference_weight
                        ),
                        spectral_projection_active_mode_reference_weight_mode=(
                            config.passivity_spectral_projection_active_mode_reference_weight_mode
                        ),
                        spectral_projection_active_mode_reference_weight_candidates=(
                            config.passivity_spectral_projection_active_mode_reference_weight_candidates
                        ),
                        spectral_projection_active_mode_global_reference_points=(
                            config.passivity_spectral_projection_active_mode_global_reference_points
                        ),
                        spectral_projection_active_mode_max_reference_rms_total_increase=(
                            config.passivity_spectral_projection_active_mode_max_reference_rms_total_increase
                        ),
                        spectral_projection_active_mode_extra_scales=(
                            config.passivity_spectral_projection_active_mode_extra_scales
                        ),
                        spectral_projection_active_mode_extra_scales_min_sigma=(
                            config.passivity_spectral_projection_active_mode_extra_scales_min_sigma
                        ),
                        spectral_projection_current_clip_candidate=(
                            config.passivity_spectral_projection_current_clip_candidate
                        ),
                        spectral_projection_current_clip_reference_weight=(
                            config.passivity_spectral_projection_current_clip_reference_weight
                        ),
                        spectral_projection_candidate_reference_max_points=(
                            config.passivity_spectral_projection_candidate_reference_max_points
                        ),
                        spectral_projection_frequency_selection=(
                            config.passivity_spectral_projection_frequency_selection
                        ),
                        spectral_projection_band_sample_count=(
                            config.passivity_spectral_projection_band_sample_count
                        ),
                        spectral_projection_reference_rms_scope=(
                            config.passivity_spectral_projection_reference_rms_scope
                        ),
                        spectral_projection_reference_rms_chunk_size=(
                            config.passivity_spectral_projection_reference_rms_chunk_size
                        ),
                        spectral_projection_candidate_selection_metric=(
                            config.passivity_spectral_projection_candidate_selection_metric
                        ),
                        spectral_projection_post_damping_selection_start_iteration=(
                            config.passivity_spectral_projection_post_damping_selection_start_iteration
                        ),
                        spectral_projection_post_damping_max_sigma_regression=(
                            config.passivity_spectral_projection_post_damping_max_sigma_regression
                        ),
                        spectral_projection_mode_screen_candidates=(
                            config.passivity_spectral_projection_mode_screen_candidates
                        ),
                        spectral_projection_mode_screen_modes=(
                            config.passivity_spectral_projection_mode_screen_modes
                        ),
                        constant_weight=config.passivity_constant_weight,
                        pole_weight=config.passivity_pole_weight,
                    )
                else:
                    progress.info(
                        f"starting passivity enforcement: n_samples={config.passivity_samples}, "
                        f"f_max={config.passivity_f_max}, preserve_dc={config.preserve_dc}"
                    )
                    _call_with_supported_kwargs(
                        vector_fit.passivity_enforce,
                        n_samples=config.passivity_samples,
                        f_max=config.passivity_f_max,
                        parameter_type=config.parameter_type,
                        preserve_dc=config.preserve_dc,
                    )
                enforce_seconds += time.perf_counter() - enforce_started
                progress.info("passivity enforcement finished")
            else:
                progress.info("passivity enforcement skipped")
            passive_after = None
            violations_after = None
            passivity_max_sigma_after = None
            passivity_max_sigma_frequency_after = None
        elif use_low_memory_passivity:
            progress.info("checking passivity before enforcement using low-memory Hamiltonian method")
            from .passivity import check_vector_fit_passivity_hamiltonian, enforce_passivity_hamiltonian
            check_started = time.perf_counter()
            report_before = check_vector_fit_passivity_hamiltonian(
                vector_fit,
                nports=network.nports,
                epsilon=config.max_passivity_epsilon,
                f_max=passivity_f_max,
            )
            check_seconds += time.perf_counter() - check_started
            passive_before = (len(report_before.violation_bands_hz) == 0)
            violations_before = report_before.violation_bands_hz
            passivity_max_sigma_before = report_before.max_sigma
            passivity_max_sigma_frequency_before = report_before.max_sigma_frequency_hz
            if should_enforce:
                progress.info("starting passivity enforcement using low-memory residue perturbation")
                enforce_started = time.perf_counter()
                enforce_passivity_hamiltonian(
                    vector_fit,
                    nports=network.nports,
                    epsilon=config.max_passivity_epsilon,
                    max_iterations=config.passivity_max_iterations,
                    f_max=passivity_f_max,
                    max_violation_samples=config.passivity_samples,
                    max_active_variables=config.passivity_active_variables,
                    perturb_constant=config.passivity_perturb_constant,
                    perturb_poles=config.passivity_perturb_poles,
                    constant_only_candidates=config.passivity_constant_only_candidates,
                    global_damping_fallback=config.passivity_global_damping_fallback,
                    global_damping_mode=config.passivity_global_damping_mode,
                    global_damping_selective_min_frequency=config.passivity_global_damping_selective_min_frequency,
                    global_damping_safety_margin=config.passivity_global_damping_safety_margin,
                    spectral_projection_fallback=config.passivity_spectral_projection_fallback,
                    spectral_projection_max_delta_norm=config.passivity_spectral_projection_max_delta_norm,
                    spectral_projection_max_response_delta_rms=config.passivity_spectral_projection_max_response_delta_rms,
                    spectral_projection_max_sigma_regression=(
                        config.passivity_spectral_projection_max_sigma_regression
                    ),
                    spectral_projection_iterations=config.passivity_spectral_projection_iterations,
                    spectral_projection_reweight_iterations=config.passivity_spectral_projection_reweight_iterations,
                    spectral_projection_reference_freqs=network.f,
                    spectral_projection_reference_s=network.s,
                    spectral_projection_max_reference_rms_increase=(
                        config.passivity_spectral_projection_max_reference_rms_increase
                    ),
                    spectral_projection_max_reference_rms_total_increase=(
                        config.passivity_spectral_projection_max_reference_rms_total_increase
                    ),
                    spectral_projection_max_reference_rms_per_sigma_improvement=(
                        config.passivity_spectral_projection_max_reference_rms_per_sigma_improvement
                    ),
                    spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement=(
                        config.passivity_spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement
                    ),
                    spectral_projection_late_current_clip_start_iteration=(
                        config.passivity_spectral_projection_late_current_clip_start_iteration
                    ),
                    spectral_projection_max_reference_band_sigma_regression=(
                        config.passivity_spectral_projection_max_reference_band_sigma_regression
                    ),
                    spectral_projection_reference_band_holdout_start_iteration=(
                        config.passivity_spectral_projection_reference_band_holdout_start_iteration
                    ),
                    spectral_projection_include_all_reference_violations=(
                        config.passivity_spectral_projection_include_all_reference_violations
                    ),
                    spectral_projection_weight_mode=config.passivity_spectral_projection_weight_mode,
                    spectral_projection_weight_exponent=config.passivity_spectral_projection_weight_exponent,
                    spectral_projection_active_mode_candidate=(
                        config.passivity_spectral_projection_active_mode_candidate
                    ),
                    spectral_projection_active_mode_start_iteration=(
                        config.passivity_spectral_projection_active_mode_start_iteration
                    ),
                    spectral_projection_non_active_stop_iteration=(
                        config.passivity_spectral_projection_non_active_stop_iteration
                    ),
                    spectral_projection_active_mode_max_responses=(
                        config.passivity_spectral_projection_active_mode_max_responses
                    ),
                    spectral_projection_active_mode_singular_modes=(
                        config.passivity_spectral_projection_active_mode_singular_modes
                    ),
                    spectral_projection_active_mode_band_singular_modes=(
                        config.passivity_spectral_projection_active_mode_band_singular_modes
                    ),
                    spectral_projection_active_mode_band_singular_mode_sample_count=(
                        config.passivity_spectral_projection_active_mode_band_singular_mode_sample_count
                    ),
                    spectral_projection_active_mode_solver=(
                        config.passivity_spectral_projection_active_mode_solver
                    ),
                    spectral_projection_active_mode_target_margin=(
                        config.passivity_spectral_projection_active_mode_target_margin
                    ),
                    spectral_projection_active_mode_target_margin_start_iteration=(
                        config.passivity_spectral_projection_active_mode_target_margin_start_iteration
                    ),
                    spectral_projection_active_mode_reference_max_points=(
                        config.passivity_spectral_projection_active_mode_reference_max_points
                    ),
                    spectral_projection_active_mode_frequency_selection=(
                        config.passivity_spectral_projection_active_mode_frequency_selection
                    ),
                    spectral_projection_active_mode_reference_weight=(
                        config.passivity_spectral_projection_active_mode_reference_weight
                    ),
                    spectral_projection_active_mode_reference_weight_mode=(
                        config.passivity_spectral_projection_active_mode_reference_weight_mode
                    ),
                    spectral_projection_active_mode_reference_weight_candidates=(
                        config.passivity_spectral_projection_active_mode_reference_weight_candidates
                    ),
                    spectral_projection_active_mode_global_reference_points=(
                        config.passivity_spectral_projection_active_mode_global_reference_points
                    ),
                    spectral_projection_active_mode_max_reference_rms_total_increase=(
                        config.passivity_spectral_projection_active_mode_max_reference_rms_total_increase
                    ),
                    spectral_projection_active_mode_extra_scales=(
                        config.passivity_spectral_projection_active_mode_extra_scales
                    ),
                    spectral_projection_active_mode_extra_scales_min_sigma=(
                        config.passivity_spectral_projection_active_mode_extra_scales_min_sigma
                    ),
                    spectral_projection_current_clip_candidate=(
                        config.passivity_spectral_projection_current_clip_candidate
                    ),
                    spectral_projection_current_clip_reference_weight=(
                        config.passivity_spectral_projection_current_clip_reference_weight
                    ),
                    spectral_projection_candidate_reference_max_points=(
                        config.passivity_spectral_projection_candidate_reference_max_points
                    ),
                    spectral_projection_frequency_selection=config.passivity_spectral_projection_frequency_selection,
                    spectral_projection_band_sample_count=config.passivity_spectral_projection_band_sample_count,
                    spectral_projection_reference_rms_scope=config.passivity_spectral_projection_reference_rms_scope,
                    spectral_projection_reference_rms_chunk_size=(
                        config.passivity_spectral_projection_reference_rms_chunk_size
                    ),
                    spectral_projection_candidate_selection_metric=(
                        config.passivity_spectral_projection_candidate_selection_metric
                    ),
                    spectral_projection_post_damping_selection_start_iteration=(
                        config.passivity_spectral_projection_post_damping_selection_start_iteration
                    ),
                    spectral_projection_post_damping_max_sigma_regression=(
                        config.passivity_spectral_projection_post_damping_max_sigma_regression
                    ),
                    spectral_projection_mode_screen_candidates=(
                        config.passivity_spectral_projection_mode_screen_candidates
                    ),
                    spectral_projection_mode_screen_modes=config.passivity_spectral_projection_mode_screen_modes,
                    constant_weight=config.passivity_constant_weight,
                    pole_weight=config.passivity_pole_weight,
                )
                enforce_seconds += time.perf_counter() - enforce_started
                progress.info("passivity enforcement finished")
            else:
                progress.info("passivity enforcement skipped")
            progress.info("checking passivity after enforcement using low-memory Hamiltonian method")
            check_started = time.perf_counter()
            report_after = check_vector_fit_passivity_hamiltonian(
                vector_fit,
                nports=network.nports,
                epsilon=config.max_passivity_epsilon,
                f_max=passivity_f_max,
            )
            check_seconds += time.perf_counter() - check_started
            passive_after = (len(report_after.violation_bands_hz) == 0)
            violations_after = report_after.violation_bands_hz
            passivity_max_sigma_after = report_after.max_sigma
            passivity_max_sigma_frequency_after = report_after.max_sigma_frequency_hz
        else:
            progress.info("checking passivity before enforcement")
            check_started = time.perf_counter()
            passive_before = _safe_bool(vector_fit.is_passive, parameter_type=config.parameter_type)
            violations_before = _safe_passivity_violations(vector_fit, config.parameter_type)
            check_seconds += time.perf_counter() - check_started
            passivity_max_sigma_before = None
            passivity_max_sigma_frequency_before = None
            if should_enforce:
                progress.info(
                    f"starting passivity enforcement: n_samples={config.passivity_samples}, "
                    f"f_max={config.passivity_f_max}, preserve_dc={config.preserve_dc}"
                )
                enforce_started = time.perf_counter()
                _call_with_supported_kwargs(
                    vector_fit.passivity_enforce,
                    n_samples=config.passivity_samples,
                    f_max=config.passivity_f_max,
                    parameter_type=config.parameter_type,
                    preserve_dc=config.preserve_dc,
                )
                enforce_seconds += time.perf_counter() - enforce_started
                progress.info("passivity enforcement finished")
            else:
                progress.info("passivity enforcement skipped")
            check_started = time.perf_counter()
            passive_after = _safe_bool(vector_fit.is_passive, parameter_type=config.parameter_type)
            violations_after = _safe_passivity_violations(vector_fit, config.parameter_type)
            check_seconds += time.perf_counter() - check_started
            passivity_max_sigma_after = None
            passivity_max_sigma_frequency_after = None

        rms_error = _safe_rms_error(vector_fit, config.parameter_type)
        comparison_rms_error = _comparison_rms_error(network, vector_fit, config.parameter_type)
        quality_report = build_quality_report(
            network=network,
            frequency_points=len(network.f),
            fit_frequency_points=len(fit_network.f),
            comparison_rms_error=comparison_rms_error,
            passive_after_enforce=passive_after,
            passivity_violations_after=violations_after,
            enforce_passivity=config.enforce_passivity,
            poles=getattr(vector_fit, "poles", None),
            profile=config.quality_profile,
            comparison_rms_limit=config.max_comparison_rms_error,
            passivity_epsilon=config.max_passivity_epsilon,
            require_dc=config.require_dc,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        progress.info(f"writing SPICE subcircuit: {output_path}")
        _call_with_supported_kwargs(
            vector_fit.write_spice_subcircuit_s,
            str(output_path),
            fitted_model_name=config.subckt_name,
            create_reference_pins=config.create_reference_pins,
        )
        resource_monitor.__exit__(None, None, None)

        pole_summary = _pole_summary(vector_fit)
        result = SParamFitResult(
            touchstone_path=touchstone_path,
            spice_path=output_path,
            report_path=report_path,
            html_report_path=html_report_path,
            log_path=log_path,
            ports=network.nports,
            frequency_points=len(network.f),
            frequency_range_hz=_frequency_range(network),
            fit_frequency_points=len(fit_network.f),
            fit_frequency_range_hz=_frequency_range(fit_network),
            fit_frequency_selection=_frequency_selection_summary(config),
            reference_impedance=_reference_impedance(network),
            config=config,
            rms_error=rms_error,
            comparison_rms_error=comparison_rms_error,
            passive_before_enforce=passive_before,
            passive_after_enforce=passive_after,
            passivity_violations_before=violations_before,
            passivity_violations_after=violations_after,
            passivity_max_sigma_before=passivity_max_sigma_before,
            passivity_max_sigma_after=passivity_max_sigma_after,
            passivity_max_sigma_frequency_hz_before=passivity_max_sigma_frequency_before,
            passivity_max_sigma_frequency_hz_after=passivity_max_sigma_frequency_after,
            passivity_enforcement_diagnostics=getattr(vector_fit, "passivity_enforcement_diagnostics", None),
            quality_report=quality_report,
            native_baseline_version=NATIVE_BASELINE_VERSION,
            comparison_mean_rms_error=_mean_rms_error_from_sum_style(comparison_rms_error, network.nports),
            pre_enforcement_mean_rms_error=pre_enforcement_mean_rms_error,
            fit_seconds=fit_seconds,
            check_seconds=check_seconds,
            enforce_seconds=enforce_seconds,
            passivity_enforcement_skip_reason=passivity_enforcement_skip_reason,
            passivity_check_skip_reason=passivity_check_skip_reason,
            elapsed_seconds=resource_monitor.elapsed_seconds,
            peak_memory_mb=resource_monitor.peak_memory_mb,
            topology_sweep_diagnostics=getattr(vector_fit, "topology_sweep_diagnostics", None) or None,
            relocation_frontier_diagnostics=getattr(vector_fit, "relocation_frontier_diagnostics", None) or None,
            constant_matrix_sigma=_constant_matrix_sigma(vector_fit, network.nports),
            **pole_summary,
        )
        if report_path is not None:
            progress.info(f"writing JSON report: {report_path}")
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if html_report_path is not None:
            progress.info(f"writing HTML report: {html_report_path}")
            html_report_path.parent.mkdir(parents=True, exist_ok=True)
            html_report_path.write_text(
                _render_html_report(result, _comparison_traces(network, vector_fit)),
                encoding="utf-8",
            )
        progress.info("fit-sparam completed")
        return result


def fit_touchstone_to_spice_auto_order(
    touchstone_path: Path,
    output_path: Path,
    *,
    config: SParamFitConfig | None = None,
    order_candidates: list[int],
    target_mean_rms_error: float,
    report_path: Path | None = None,
    html_report_path: Path | None = None,
    log_path: Path | None = None,
) -> SParamFitResult:
    if not order_candidates:
        raise ValueError("order_candidates must contain at least one order")
    if target_mean_rms_error <= 0.0:
        raise ValueError("target_mean_rms_error must be > 0")

    base_config = config or SParamFitConfig()
    trials: list[dict[str, Any]] = []
    selected: SParamFitResult | None = None
    stop_reason = "exhausted"
    output_stem = output_path.stem

    for order in order_candidates:
        if order < 1:
            raise ValueError("order candidates must be >= 1")
        trial_dir = output_path.parent / f"{output_stem}_order{order}"
        trial_output = trial_dir / output_path.name
        trial_report = trial_dir / "fit_report.json"
        trial_html = trial_dir / "fit_report.html" if html_report_path is not None else None
        trial_config = _native_manual_auto_order_config(base_config, order)
        trial = fit_touchstone_to_spice(
            touchstone_path,
            trial_output,
            config=trial_config,
            report_path=trial_report,
            html_report_path=trial_html,
            log_path=log_path,
        )
        mean_rms = trial.comparison_mean_rms_error
        trials.append(
            {
                "order": order,
                "comparison_rms_error": trial.comparison_rms_error,
                "comparison_mean_rms_error": mean_rms,
                "elapsed_seconds": trial.elapsed_seconds,
                "peak_memory_mb": trial.peak_memory_mb,
                "stored_pole_count": trial.stored_pole_count,
                "real_pole_count": trial.real_pole_count,
                "complex_pair_count": trial.complex_pair_count,
                "expanded_model_order": trial.expanded_model_order,
                "spice_path": str(trial.spice_path),
                "report_path": str(trial.report_path) if trial.report_path is not None else None,
            }
        )
        selected = trial
        if mean_rms is not None and mean_rms <= target_mean_rms_error:
            stop_reason = "target_met"
            break

    assert selected is not None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(selected.spice_path, output_path)

    result = replace(
        selected,
        spice_path=output_path,
        report_path=report_path,
        html_report_path=html_report_path,
        log_path=log_path,
        auto_model_order_trials=trials,
        auto_model_order_selected=selected.config.model_order_max,
        auto_model_order_stop_reason=stop_reason,
    )
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if html_report_path is not None:
        html_report_path.parent.mkdir(parents=True, exist_ok=True)
        rows = "\n".join(
            "<tr>"
            f"<td>{trial['order']}</td>"
            f"<td>{_format_float(trial['comparison_mean_rms_error'])}</td>"
            f"<td>{_format_float(trial['comparison_rms_error'])}</td>"
            f"<td>{_format_float(trial['elapsed_seconds'])}</td>"
            f"<td>{_format_float(trial['peak_memory_mb'])}</td>"
            "</tr>"
            for trial in trials
        )
        html_report_path.write_text(
            f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>S-Parameter Auto Order Fit</title></head>
<body>
  <h1>S-Parameter Auto Order Fit</h1>
  <p>Selected order: {result.auto_model_order_selected}; stop reason: {escape(str(stop_reason))}</p>
  <table>
    <tr><th>Order</th><th>Mean RMS</th><th>Sum-style RMS</th><th>Seconds</th><th>Peak MB</th></tr>
    {rows}
  </table>
</body>
</html>
""",
            encoding="utf-8",
        )
    return result


def _target_trial_input_sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _target_trial_frequency_points(path: Path) -> int | None:
    match = re.search(r"\.s(\d+)p$", path.name, flags=re.IGNORECASE)
    if match is None:
        return None
    ports = int(match.group(1))
    values_per_frequency = 1 + (2 * ports * ports)
    token_count = 0
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw_line in handle:
                line = raw_line.split("!", 1)[0].strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("["):
                    return None
                token_count += len(line.split())
    except OSError:
        return None
    points, remainder = divmod(token_count, values_per_frequency)
    return points if points > 0 and remainder == 0 else None


def _target_trial_json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _target_trial_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_target_trial_json_safe(item) for item in value]
    return value


def _target_trial_fingerprint(
    *,
    input_sha256: str | None,
    target: SParamFitTarget,
    order: int,
    config: SParamFitConfig,
) -> tuple[str, str, str]:
    config_payload = _target_trial_json_safe(asdict(config))
    config_canonical = json.dumps(config_payload, sort_keys=True, separators=(",", ":"))
    config_fingerprint = hashlib.sha256(config_canonical.encode("utf-8")).hexdigest()
    source_identities = []
    source_root = Path(__file__).resolve().parent
    for name in NATIVE_SOURCE_IDENTITY_FILES:
        source_path = source_root / name
        try:
            stat = source_path.stat()
        except OSError:
            source_identities.append(str(source_path))
        else:
            source_identities.append(
                f"{source_path}|size={stat.st_size}|mtime_ns={stat.st_mtime_ns}"
            )
    tool_identity = "|".join(source_identities)
    payload = {
        "contract_version": "sparam_target_trial_v1",
        "input_sha256": input_sha256,
        "target": asdict(target),
        "requested_order": order,
        "options": {"native_baseline_version": NATIVE_BASELINE_VERSION},
        "config_fingerprint": config_fingerprint,
        "tool_identity": tool_identity,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), config_fingerprint, tool_identity


def _write_target_trial_report(
    path: Path,
    fit_result: Any,
    trial: SParamOrderTrial,
    *,
    input_sha256: str | None,
    fingerprint: str,
    config_fingerprint: str,
    tool_identity: str,
    target: SParamFitTarget,
) -> None:
    payload = fit_result.to_dict() if hasattr(fit_result, "to_dict") else {}
    payload.update(
        {
            "target_trial_contract_version": "sparam_target_trial_v1",
            "input_sha256": input_sha256,
            "target_trial_fingerprint": fingerprint,
            "target_config_fingerprint": config_fingerprint,
            "target_tool_identity": tool_identity,
            "target_contract": asdict(target),
            "target_order_trial": trial.to_dict(),
            "full_grid_frequency_points": trial.evaluation_frequency_points,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(_target_trial_json_safe(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _resume_target_trial(
    report_path: Path,
    output_path: Path,
    *,
    fingerprint: str,
    input_sha256: str | None,
    requested_order: int,
    expected_frequency_points: int | None,
    target: SParamFitTarget,
) -> SParamOrderTrial | None:
    if input_sha256 is None or not report_path.is_file() or not output_path.is_file():
        return None
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("target_trial_contract_version") != "sparam_target_trial_v1":
        return None
    if payload.get("input_sha256") != input_sha256:
        return None
    if payload.get("target_trial_fingerprint") != fingerprint:
        return None
    raw_trial = payload.get("target_order_trial")
    if not isinstance(raw_trial, dict):
        return None
    required = {
        "requested_order",
        "effective_order",
        "fit_frequency_points",
        "evaluation_frequency_points",
        "pre_mean_rms",
        "final_mean_rms",
        "fit_seconds",
        "check_seconds",
        "enforce_seconds",
        "elapsed_seconds",
        "peak_memory_mb",
        "target_met",
        "status",
        "rejection_reason",
    }
    if not required.issubset(raw_trial):
        return None
    if raw_trial.get("requested_order") != requested_order:
        return None
    full_grid_points = payload.get("full_grid_frequency_points")
    if not isinstance(full_grid_points, int) or full_grid_points < 1:
        return None
    if raw_trial.get("evaluation_frequency_points") != full_grid_points:
        return None
    trial_fields = {item.name for item in fields(SParamOrderTrial) if item.name != "payload"}
    try:
        trial_data = {name: raw_trial.get(name) for name in trial_fields}
        resumed_payload = _ResumedTargetFitPayload(payload, output_path)
        trial = SParamOrderTrial(**trial_data, payload=resumed_payload)
    except (TypeError, ValueError):
        return None
    numeric_non_negative = (
        trial.fit_seconds,
        trial.check_seconds,
        trial.enforce_seconds,
        trial.elapsed_seconds,
        trial.peak_memory_mb,
    )
    if not all(isinstance(value, (int, float)) and math.isfinite(value) and value >= 0.0 for value in numeric_non_negative):
        return None
    if trial.fit_frequency_points != trial.evaluation_frequency_points:
        return None
    if expected_frequency_points is not None and trial.evaluation_frequency_points != expected_frequency_points:
        return None
    if trial.target_met:
        if trial.effective_order != requested_order or trial.status != "PASS":
            return None
        if (
            not isinstance(trial.final_mean_rms, (int, float))
            or not math.isfinite(trial.final_mean_rms)
            or trial.final_mean_rms > target.mean_rms
        ):
            return None
        if target.passivity == "enforce":
            if (
                not isinstance(trial.final_max_sigma, (int, float))
                or not math.isfinite(trial.final_max_sigma)
                or trial.final_max_sigma > 1.0 + target.passivity_epsilon
            ):
                return None
    return trial


def fit_touchstone_to_spice_target(
    touchstone_path: Path,
    output_path: Path,
    *,
    target: SParamFitTarget,
    config: SParamFitConfig | None = None,
    report_path: Path | None = None,
    html_report_path: Path | None = None,
    log_path: Path | None = None,
    resume_trials: bool = False,
) -> SParamTargetSearchResult:
    base_config = config or SParamFitConfig()
    policy_config = replace(
        base_config,
        check_passivity=target.passivity != "off",
        enforce_passivity=target.passivity == "enforce",
        passivity_enforce_rms_target=target.mean_rms if target.passivity == "enforce" else None,
        passivity_check_rms_target=target.mean_rms if target.passivity != "off" else None,
        max_passivity_epsilon=target.passivity_epsilon,
        fit_frequency_stride=1,
        fit_max_frequency_points=None,
        fit_f_min=None,
        fit_f_max=None,
    )
    output_stem = output_path.stem
    trial_logs: list[tuple[int, Path]] = []
    input_sha256 = _target_trial_input_sha256(touchstone_path)
    expected_frequency_points = _target_trial_frequency_points(touchstone_path)

    def evaluate_order(order: int) -> SParamOrderTrial:
        trial_dir = output_path.parent / f"{output_stem}_order{order}"
        trial_output = trial_dir / output_path.name
        trial_report = trial_dir / "fit_report.json"
        trial_html = trial_dir / "fit_report.html" if html_report_path is not None else None
        trial_log = trial_dir / "fit.log" if log_path is not None else None
        trial_config = _native_manual_auto_order_config(policy_config, order)
        fingerprint, config_fingerprint, tool_identity = _target_trial_fingerprint(
            input_sha256=input_sha256,
            target=target,
            order=order,
            config=trial_config,
        )
        if resume_trials:
            resumed = _resume_target_trial(
                trial_report,
                trial_output,
                fingerprint=fingerprint,
                input_sha256=input_sha256,
                requested_order=order,
                expected_frequency_points=expected_frequency_points,
                target=target,
            )
            if resumed is not None:
                return resumed
        try:
            fit_result = fit_touchstone_to_spice(
                touchstone_path,
                trial_output,
                config=trial_config,
                report_path=trial_report,
                html_report_path=trial_html,
                log_path=trial_log,
            )
        except Exception as exc:
            return SParamOrderTrial(
                requested_order=order,
                effective_order=order,
                fit_frequency_points=0,
                evaluation_frequency_points=0,
                pre_mean_rms=math.inf,
                final_mean_rms=math.inf,
                pre_max_sigma=None,
                final_max_sigma=None,
                fit_seconds=0.0,
                check_seconds=0.0,
                enforce_seconds=0.0,
                elapsed_seconds=0.0,
                peak_memory_mb=0.0,
                target_met=False,
                status="FAIL",
                rejection_reason="fit_failed",
                payload={"error": str(exc), "trial_dir": str(trial_dir)},
            )
        if trial_log is not None:
            trial_logs.append((order, trial_log))
        trial = trial_from_fit_result(target, fit_result, requested_order=order)
        _write_target_trial_report(
            trial_report,
            fit_result,
            trial,
            input_sha256=input_sha256,
            fingerprint=fingerprint,
            config_fingerprint=config_fingerprint,
            tool_identity=tool_identity,
            target=target,
        )
        return trial

    search_result = run_target_order_search(target, evaluate_order)
    selected_fit_result = None if search_result.selected_trial is None else search_result.selected_trial.payload
    if selected_fit_result is None:
        output_path.unlink(missing_ok=True)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(selected_fit_result.spice_path), output_path)

    payload = search_result.to_dict()
    if selected_fit_result is not None and hasattr(selected_fit_result, "to_dict"):
        selected_payload = selected_fit_result.to_dict()
        selected_payload["spice_path"] = str(output_path)
        selected_payload.update(payload)
        payload = selected_payload
    payload["rms_formula"] = "mean_s_rms_v1"
    payload["order_formula"] = "real_plus_twice_complex_v1"
    payload["touchstone_path"] = str(touchstone_path)
    payload["spice_path"] = str(output_path) if search_result.target_met else None
    payload["report_path"] = None if report_path is None else str(report_path)
    payload["html_report_path"] = None if html_report_path is None else str(html_report_path)
    payload["log_path"] = None if log_path is None else str(log_path)

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    if html_report_path is not None:
        html_report_path.parent.mkdir(parents=True, exist_ok=True)
        rows = "\n".join(
            "<tr>"
            f"<td>{trial.requested_order}</td>"
            f"<td>{trial.effective_order}</td>"
            f"<td>{_format_float(trial.pre_mean_rms)}</td>"
            f"<td>{_format_float(trial.final_mean_rms)}</td>"
            f"<td>{_format_float(trial.final_max_sigma)}</td>"
            f"<td>{escape(trial.status)}</td>"
            f"<td>{escape(str(trial.rejection_reason or ''))}</td>"
            "</tr>"
            for trial in search_result.trials
        )
        html_report_path.write_text(
            f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>Target-Driven S-Parameter Fit</title></head>
<body>
  <h1>Target-Driven S-Parameter Fit</h1>
  <p>Target RMS: {_format_float(target.mean_rms)}; passivity: {escape(target.passivity)}; result: {escape(search_result.stop_reason)}</p>
  <table>
    <tr><th>Requested order</th><th>Effective order</th><th>Pre RMS</th><th>Final RMS</th><th>Final sigma</th><th>Status</th><th>Reason</th></tr>
    {rows}
  </table>
</body>
</html>
""",
            encoding="utf-8",
        )
    if log_path is not None and trial_logs:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        chunks = []
        for order, trial_log in trial_logs:
            if trial_log.exists():
                chunks.append(f"===== order {order} =====\n{trial_log.read_text(encoding='utf-8')}")
        log_path.write_text("\n".join(chunks), encoding="utf-8")
    return search_result
