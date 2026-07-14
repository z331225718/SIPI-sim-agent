"""Y-domain Touchstone fitting and common-ground Norton/MNA delivery."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time
from typing import Any, Literal

import numpy as np

from .artifacts import evaluate_fitted_y, rank_element_rms, write_spice_subcircuit_y
from .native_vf import NativeVectorFitting


YPassivityPolicy = Literal["off", "check"]


@dataclass(frozen=True)
class YParamFitConfig:
    n_poles_real: int = 1
    n_poles_cmplx: int = 3
    init_pole_spacing: str = "log"
    max_iterations: int = 20
    max_y_rms_siemens: float | None = None
    passivity: YPassivityPolicy = "check"
    passivity_epsilon: float = 1.0e-9
    conversion_condition_limit: float = 1.0e12
    subckt_name: str = "y_equivalent"


@dataclass(frozen=True)
class YParamFitResult:
    touchstone_path: Path
    spice_path: Path
    report_path: Path | None
    html_report_path: Path | None
    log_path: Path | None
    config: YParamFitConfig
    ports: int
    frequency_points: int
    frequency_range_hz: list[float]
    reference_impedance: list[float]
    s_def: str
    y_rms_siemens: float
    y_mean_rms_siemens: float
    passivity_min_eigenvalue: float | None
    passivity_min_frequency_hz: float | None
    passivity_violation_count: int | None
    constant_hermitian_min_eigenvalue: float | None
    proportional_hermitian_min_eigenvalue: float | None
    passivity_sample_frequencies_hz: list[float] | None
    poles_rad_per_s: list[list[float]]
    conversion_condition_max: float
    conversion_condition_by_frequency: list[float]
    fit_seconds: float
    target_met: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "parameter_type": "y",
            "response_unit": "siemens",
            "spice_convention": "I=Y(s)V; current is positive into each port; reference is global ground",
            "touchstone_path": str(self.touchstone_path),
            "spice_path": str(self.spice_path),
            "report_path": None if self.report_path is None else str(self.report_path),
            "html_report_path": None if self.html_report_path is None else str(self.html_report_path),
            "log_path": None if self.log_path is None else str(self.log_path),
            "ports": self.ports,
            "frequency_points": self.frequency_points,
            "frequency_range_hz": self.frequency_range_hz,
            "reference_impedance": self.reference_impedance,
            "s_def": self.s_def,
            "y_rms_siemens": self.y_rms_siemens,
            "y_mean_rms_siemens": self.y_mean_rms_siemens,
            "passivity": {
                "policy": self.config.passivity,
                "criterion": "lambda_min((Y+Y^H)/2) >= -epsilon",
                "epsilon": self.config.passivity_epsilon,
                "min_eigenvalue": self.passivity_min_eigenvalue,
                "min_eigenvalue_frequency_hz": self.passivity_min_frequency_hz,
                "violation_count": self.passivity_violation_count,
                "constant_hermitian_min_eigenvalue": self.constant_hermitian_min_eigenvalue,
                "proportional_hermitian_min_eigenvalue": self.proportional_hermitian_min_eigenvalue,
                "sample_frequencies_hz": self.passivity_sample_frequencies_hz,
                "coverage": "input frequencies, geometric midpoints, and pole-frequency probes; finite-frequency check only",
                "enforcement": "not implemented",
            },
            "s_to_y_conversion": {
                "condition_limit": self.config.conversion_condition_limit,
                "condition_max": self.conversion_condition_max,
                "condition_by_frequency": self.conversion_condition_by_frequency,
                "matrix": "I+S",
            },
            "fit_seconds": self.fit_seconds,
            "fit_proportional": True,
            "fit_dc": True,
            "poles_rad_per_s": self.poles_rad_per_s,
            "stable_poles": True,
            "target_met": self.target_met,
            "config": asdict(self.config),
        }


def _conversion_conditions(network: Any, limit: float) -> list[float]:
    if not np.isfinite(limit) or limit <= 1.0:
        raise ValueError("conversion_condition_limit must be finite and > 1")
    s_def = str(getattr(network, "s_def", "power")).lower()
    z0 = np.asarray(network.z0, dtype=complex)
    reference = z0[0]
    if s_def not in {"power", "traveling"} or np.any(np.abs(z0.imag) > 1.0e-12) or not np.allclose(z0, reference, rtol=0.0, atol=1.0e-12) or reference[0].real <= 0.0:
        raise ValueError(
            "Y MVP supports only a shared positive real reference impedance with power or traveling S-wave definition"
        )
    s = np.asarray(network.s, dtype=complex)
    identity = np.eye(network.nports, dtype=complex)
    conditions = [float(np.linalg.cond(identity + point)) for point in s]
    bad = [index for index, value in enumerate(conditions) if not np.isfinite(value) or value > limit]
    if bad:
        frequencies = np.asarray(network.f, dtype=float)
        first = bad[0]
        raise ValueError(
            "S-to-Y conversion is ill-conditioned at "
            f"{frequencies[first]:.12g} Hz (cond(I+S)={conditions[first]:.12g}; limit={limit:.12g})"
        )
    return conditions


def _passivity_sample_frequencies(frequencies_hz: np.ndarray, poles: np.ndarray) -> np.ndarray:
    points = [np.asarray(frequencies_hz, dtype=float)]
    if len(frequencies_hz) > 1:
        points.append(np.sqrt(frequencies_hz[:-1] * frequencies_hz[1:]))
    pole_frequencies = np.abs(np.imag(poles)) / (2.0 * np.pi)
    real_pole_frequencies = np.abs(np.real(poles)) / (2.0 * np.pi)
    points.append(np.concatenate((pole_frequencies, real_pole_frequencies)))
    return np.unique(np.concatenate(points))


def _assess_y_passivity(model: NativeVectorFitting, frequencies_hz: np.ndarray, epsilon: float) -> tuple[float, float, int, np.ndarray]:
    samples = _passivity_sample_frequencies(frequencies_hz, np.asarray(model.poles, dtype=complex))
    values = evaluate_fitted_y(model, samples)
    hermitian = 0.5 * (values + np.swapaxes(values.conj(), 1, 2))
    eigenvalues = np.linalg.eigvalsh(hermitian)
    flat = int(np.argmin(eigenvalues))
    sample_index, _ = np.unravel_index(flat, eigenvalues.shape)
    return float(eigenvalues.flat[flat]), float(samples[sample_index]), int(np.count_nonzero(eigenvalues[:, 0] < -epsilon)), samples


def _hermitian_minimum(values: np.ndarray, ports: int) -> float:
    matrix = np.asarray(values, dtype=complex).reshape(ports, ports)
    return float(np.linalg.eigvalsh(0.5 * (matrix + matrix.conj().T))[0])


def fit_touchstone_to_y_spice(
    touchstone_path: str | Path,
    spice_path: str | Path,
    *,
    config: YParamFitConfig | None = None,
    report_path: str | Path | None = None,
    html_report_path: str | Path | None = None,
    log_path: str | Path | None = None,
) -> YParamFitResult:
    """Fit Touchstone-derived Y data and write a common-ground SPICE model."""

    import skrf as rf

    cfg = config or YParamFitConfig()
    if cfg.passivity not in {"off", "check"}:
        raise ValueError("Y passivity must be 'off' or 'check'; enforcement is not available")
    if not np.isfinite(cfg.passivity_epsilon) or cfg.passivity_epsilon < 0.0:
        raise ValueError("passivity_epsilon must be finite and >= 0")
    if cfg.max_y_rms_siemens is not None and (not np.isfinite(cfg.max_y_rms_siemens) or cfg.max_y_rms_siemens <= 0.0):
        raise ValueError("max_y_rms_siemens must be finite and > 0")
    if cfg.n_poles_real < 0 or cfg.n_poles_cmplx < 0 or cfg.n_poles_real + cfg.n_poles_cmplx < 1:
        raise ValueError("at least one Y fitting pole is required")
    if not isinstance(cfg.max_iterations, int) or cfg.max_iterations < 1:
        raise ValueError("max_iterations must be an integer >= 1")
    source = Path(touchstone_path)
    output = Path(spice_path)
    network = rf.Network(str(source))
    y_values = np.asarray(network.y, dtype=complex)
    if not np.isfinite(y_values).all():
        raise ValueError("Touchstone S-to-Y conversion produced non-finite Y values")
    conditions = _conversion_conditions(network, cfg.conversion_condition_limit)

    vector_fit = NativeVectorFitting(network)
    vector_fit.max_iterations = cfg.max_iterations
    started = time.perf_counter()
    vector_fit.vector_fit(
        n_poles_real=cfg.n_poles_real,
        n_poles_cmplx=cfg.n_poles_cmplx,
        init_pole_spacing=cfg.init_pole_spacing,
        parameter_type="y",
        fit_constant=True,
        fit_proportional=True,
        enforce_dc=True,
    )
    fit_seconds = time.perf_counter() - started
    fitted = evaluate_fitted_y(vector_fit, network.f)
    element_rms = np.sqrt(np.mean(np.abs(y_values - fitted) ** 2, axis=0))
    rms = float(np.sqrt(np.sum(element_rms**2)))
    mean_rms = rms / network.nports
    if cfg.passivity == "check":
        minimum, minimum_frequency, violations, passivity_samples = _assess_y_passivity(vector_fit, np.asarray(network.f, dtype=float), cfg.passivity_epsilon)
        constant_minimum = _hermitian_minimum(vector_fit.constant_coeff, network.nports)
        proportional_minimum = _hermitian_minimum(vector_fit.proportional_coeff, network.nports)
    else:
        minimum = minimum_frequency = None
        violations = None
        constant_minimum = proportional_minimum = None
        passivity_samples = None
    target_met = (cfg.max_y_rms_siemens is None or mean_rms <= cfg.max_y_rms_siemens) and (violations in {None, 0})
    write_spice_subcircuit_y(vector_fit, output, fitted_model_name=cfg.subckt_name)

    result = YParamFitResult(
        touchstone_path=source,
        spice_path=output,
        report_path=None if report_path is None else Path(report_path),
        html_report_path=None if html_report_path is None else Path(html_report_path),
        log_path=None if log_path is None else Path(log_path),
        config=cfg,
        ports=network.nports,
        frequency_points=len(network.f),
        frequency_range_hz=[float(network.f[0]), float(network.f[-1])],
        reference_impedance=[float(value.real) for value in network.z0[0]],
        s_def=str(getattr(network, "s_def", "power")),
        y_rms_siemens=rms,
        y_mean_rms_siemens=mean_rms,
        passivity_min_eigenvalue=minimum,
        passivity_min_frequency_hz=minimum_frequency,
        passivity_violation_count=violations,
        constant_hermitian_min_eigenvalue=constant_minimum,
        proportional_hermitian_min_eigenvalue=proportional_minimum,
        passivity_sample_frequencies_hz=None if passivity_samples is None else [float(value) for value in passivity_samples],
        poles_rad_per_s=[[float(value.real), float(value.imag)] for value in np.asarray(vector_fit.poles, dtype=complex)],
        conversion_condition_max=max(conditions),
        conversion_condition_by_frequency=conditions,
        fit_seconds=fit_seconds,
        target_met=target_met,
    )
    payload = result.to_dict()
    payload["element_rms_siemens"] = [item.__dict__ for item in rank_element_rms(y_values, fitted)]
    if result.report_path is not None:
        result.report_path.parent.mkdir(parents=True, exist_ok=True)
        result.report_path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    if result.log_path is not None:
        result.log_path.parent.mkdir(parents=True, exist_ok=True)
        result.log_path.write_text(
            f"fit-yparam ports={network.nports} rms_siemens={rms:.12g} target_met={target_met}\n",
            encoding="utf-8",
        )
    if result.html_report_path is not None:
        result.html_report_path.parent.mkdir(parents=True, exist_ok=True)
        result.html_report_path.write_text(
            "<!doctype html><html><head><meta charset=\"utf-8\"><title>Y-Parameter Fit</title></head>"
            f"<body><h1>Y-Parameter Fit</h1><p>RMS: {rms:.12g} S; target met: {target_met}</p></body></html>\n",
            encoding="utf-8",
        )
    return result
