"""Y-domain Touchstone fitting and common-ground Norton/MNA delivery."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import logging
from pathlib import Path
import time
from typing import Any, Literal

import numpy as np

from .artifacts import evaluate_fitted_y, rank_element_rms, write_fitted_touchstone, write_spice_subcircuit_y
from .native_vf import NativeVectorFitting
from .z_metrics import invert_y_strict, z_log_metric_summary


YPassivityPolicy = Literal["off", "check"]


class _YProgressLog:
    def __init__(self, path: Path | None, *, mode: str = "w"):
        self.path = path
        self.mode = mode
        self.handler: logging.Handler | None = None
        self.loggers: list[logging.Logger] = []
        self.old_levels: dict[logging.Logger, int] = {}
        self.progress_logger = logging.getLogger("agent_spice.sparam.yparam")

    def __enter__(self) -> "_YProgressLog":
        if self.path is None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handler = logging.FileHandler(self.path, mode=self.mode, encoding="utf-8")
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
            self.progress_logger.error(
                "fit-yparam failed",
                exc_info=(exc_type, exc, traceback),
            )
            if self.handler is not None:
                self.handler.flush()
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


def append_yparam_progress(log_path: str | Path | None, message: str) -> None:
    """Append and flush a later fit-yparam delivery stage to an existing progress log."""

    path = None if log_path is None else Path(log_path)
    with _YProgressLog(path, mode="a") as progress:
        progress.info(message)


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
    fit_proportional: bool = True
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
    z_log_metrics: dict[str, float | None]
    fitted_y_condition_max: float | None
    original_y_condition_max: float
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
    fitted_model: NativeVectorFitting

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
            **self.z_log_metrics,
            "fitted_y_condition_max": self.fitted_y_condition_max,
            "original_y_condition_max": self.original_y_condition_max,
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
            "fit_proportional": self.config.fit_proportional,
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


def convert_y_to_s_strict(y_values: np.ndarray, z0: float, *, condition_limit: float) -> tuple[np.ndarray, np.ndarray]:
    """Convert common-reference Y samples to S without a pseudo-inverse."""

    y = np.asarray(y_values, dtype=complex)
    if y.ndim != 3 or y.shape[1] != y.shape[2] or y.shape[0] == 0 or not np.isfinite(y).all():
        raise ValueError("y_values must be a non-empty finite (frequency, port, port) array")
    if not np.isfinite(z0) or z0 <= 0.0:
        raise ValueError("z0 must be a finite positive real value")
    if not np.isfinite(condition_limit) or condition_limit <= 1.0:
        raise ValueError("condition_limit must be finite and > 1")

    identity = np.eye(y.shape[1], dtype=complex)
    converted = np.empty_like(y)
    conditions = np.empty(y.shape[0], dtype=float)
    for index, value in enumerate(y):
        denominator = identity + z0 * value
        condition = float(np.linalg.cond(denominator))
        if not np.isfinite(condition) or condition > condition_limit:
            raise ValueError(
                f"Y-to-S conversion is ill-conditioned at sample {index} "
                f"(cond(I+z0Y)={condition:.12g}; limit={condition_limit:.12g})"
            )
        # Solve S(I+z0Y)=I-z0Y on the right; never use an inverse/pseudo-inverse.
        converted[index] = np.linalg.solve(denominator.T, (identity - z0 * value).T).T
        conditions[index] = condition
    return converted, conditions


def fit_touchstone_to_y_spice(
    touchstone_path: str | Path,
    spice_path: str | Path,
    *,
    config: YParamFitConfig | None = None,
    report_path: str | Path | None = None,
    html_report_path: str | Path | None = None,
    log_path: str | Path | None = None,
    derived_s_touchstone_path: str | Path | None = None,
) -> YParamFitResult:
    """Fit Touchstone-derived Y data and write a common-ground SPICE model."""

    progress_path = None if log_path is None else Path(log_path)
    with _YProgressLog(progress_path) as progress:
        return _fit_touchstone_to_y_spice_impl(
            touchstone_path,
            spice_path,
            config=config,
            report_path=report_path,
            html_report_path=html_report_path,
            log_path=log_path,
            derived_s_touchstone_path=derived_s_touchstone_path,
            progress=progress,
        )


def _fit_touchstone_to_y_spice_impl(
    touchstone_path: str | Path,
    spice_path: str | Path,
    *,
    config: YParamFitConfig | None,
    report_path: str | Path | None,
    html_report_path: str | Path | None,
    log_path: str | Path | None,
    derived_s_touchstone_path: str | Path | None,
    progress: _YProgressLog,
) -> YParamFitResult:
    """Internal Y fit implementation with an active progress log."""

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
    progress.info(f"loading Touchstone: {source}")
    network = rf.Network(str(source))
    progress.info(
        f"loaded Touchstone: ports={network.nports}, frequency_points={len(network.f)}, "
        f"frequency_range=[{float(network.f[0]):.12g}, {float(network.f[-1]):.12g}] Hz"
    )
    progress.info("converting input S parameters to Y")
    y_values = np.asarray(network.y, dtype=complex)
    if not np.isfinite(y_values).all():
        raise ValueError("Touchstone S-to-Y conversion produced non-finite Y values")
    conditions = _conversion_conditions(network, cfg.conversion_condition_limit)
    progress.info(
        f"S-to-Y conversion validated: condition_max={max(conditions):.12g}, "
        f"condition_limit={cfg.conversion_condition_limit:.12g}"
    )

    vector_fit = NativeVectorFitting(network)
    vector_fit.max_iterations = cfg.max_iterations
    progress.info(
        "starting vector fit: parameter_type=y, "
        f"n_poles_real={cfg.n_poles_real}, n_poles_cmplx={cfg.n_poles_cmplx}, "
        f"pole_spacing={cfg.init_pole_spacing}, max_iterations={cfg.max_iterations}, "
        f"fit_proportional={cfg.fit_proportional}"
    )
    started = time.perf_counter()
    vector_fit.vector_fit(
        n_poles_real=cfg.n_poles_real,
        n_poles_cmplx=cfg.n_poles_cmplx,
        init_pole_spacing=cfg.init_pole_spacing,
        parameter_type="y",
        fit_constant=True,
        fit_proportional=cfg.fit_proportional,
        enforce_dc=True,
    )
    fit_seconds = time.perf_counter() - started
    progress.info(
        f"vector fit finished: elapsed_seconds={fit_seconds:.6f}, "
        f"stored_poles={len(np.asarray(vector_fit.poles))}, "
        f"model_order={vector_fit.get_model_order(np.asarray(vector_fit.poles, dtype=complex))}"
    )
    progress.info("evaluating fitted Y on the input frequency grid")
    fitted = evaluate_fitted_y(vector_fit, network.f)
    element_rms = np.sqrt(np.mean(np.abs(y_values - fitted) ** 2, axis=0))
    rms = float(np.sqrt(np.sum(element_rms**2)))
    mean_rms = rms / network.nports
    progress.info(f"Y error evaluated: rms_siemens={rms:.12g}, mean_rms_siemens={mean_rms:.12g}")
    derived_s_path = None if derived_s_touchstone_path is None else Path(derived_s_touchstone_path)
    if derived_s_path is not None:
        progress.info(f"converting fitted Y to sampled S: output={derived_s_path}")
        z0 = float(np.asarray(network.z0, dtype=complex)[0, 0].real)
        derived_s, derived_s_conditions = convert_y_to_s_strict(
            fitted,
            z0,
            condition_limit=cfg.conversion_condition_limit,
        )
        write_fitted_touchstone(derived_s_path, network.f, derived_s, network.z0)
        derived_s_element_rms = np.sqrt(np.mean(np.abs(np.asarray(network.s, dtype=complex) - derived_s) ** 2, axis=0))
        derived_s_metrics: dict[str, Any] | None = {
            "path": str(derived_s_path),
            "matrix": "S=(I-z0Y)(I+z0Y)^-1",
            "condition_matrix": "I+z0Y",
            "condition_max": float(np.max(derived_s_conditions)),
            "rms_error_against_input": float(np.sqrt(np.sum(derived_s_element_rms**2))),
            "mean_rms_error_against_input": float(np.sqrt(np.sum(derived_s_element_rms**2)) / network.nports),
            "element_rms": [item.__dict__ for item in rank_element_rms(np.asarray(network.s, dtype=complex), derived_s)],
        }
        progress.info(
            "sampled Y-to-S conversion finished: "
            f"mean_rms_error={derived_s_metrics['mean_rms_error_against_input']:.12g}, "
            f"condition_max={derived_s_metrics['condition_max']:.12g}"
        )
    else:
        derived_s_metrics = None
    progress.info("evaluating Z-log metrics")
    try:
        fitted_z, fitted_y_conditions = invert_y_strict(fitted)
        z_log_metrics = z_log_metric_summary(np.asarray(network.z, dtype=complex), fitted_z)
        fitted_y_condition_max: float | None = float(np.max(fitted_y_conditions))
    except ValueError:
        z_log_metrics = {
            "z_log_magnitude_rms_error": None,
            "diagonal_z_log_magnitude_rms_error": None,
            "offdiagonal_z_log_magnitude_rms_error": None,
        }
        fitted_y_condition_max = None
        progress.info("Z-log metrics unavailable because fitted Y inversion failed")
    else:
        progress.info(
            "Z-log metrics evaluated: "
            f"z_log_rms={z_log_metrics['z_log_magnitude_rms_error']:.12g}, "
            f"fitted_y_condition_max={fitted_y_condition_max:.12g}"
        )
    if cfg.passivity == "check":
        progress.info("starting sampled Y positive-real check")
        minimum, minimum_frequency, violations, passivity_samples = _assess_y_passivity(vector_fit, np.asarray(network.f, dtype=float), cfg.passivity_epsilon)
        constant_minimum = _hermitian_minimum(vector_fit.constant_coeff, network.nports)
        proportional_minimum = _hermitian_minimum(vector_fit.proportional_coeff, network.nports)
        progress.info(
            "sampled Y positive-real check finished: "
            f"min_eigenvalue={minimum:.12g}, min_frequency_hz={minimum_frequency:.12g}, "
            f"violation_count={violations}"
        )
    else:
        minimum = minimum_frequency = None
        violations = None
        constant_minimum = proportional_minimum = None
        passivity_samples = None
        progress.info("sampled Y positive-real check skipped")
    target_met = (cfg.max_y_rms_siemens is None or mean_rms <= cfg.max_y_rms_siemens) and (violations in {None, 0})
    progress.info(f"writing Y-domain SPICE subcircuit: {output}")
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
        z_log_metrics=z_log_metrics,
        fitted_y_condition_max=fitted_y_condition_max,
        original_y_condition_max=float(np.max([np.linalg.cond(value) for value in y_values])),
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
        fitted_model=vector_fit,
    )
    payload = result.to_dict()
    payload["element_rms_siemens"] = [item.__dict__ for item in rank_element_rms(y_values, fitted)]
    payload["y_derived_s"] = derived_s_metrics
    if result.report_path is not None:
        progress.info(f"writing JSON report: {result.report_path}")
        result.report_path.parent.mkdir(parents=True, exist_ok=True)
        result.report_path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    if result.html_report_path is not None:
        progress.info(f"writing HTML report: {result.html_report_path}")
        result.html_report_path.parent.mkdir(parents=True, exist_ok=True)
        result.html_report_path.write_text(
            "<!doctype html><html><head><meta charset=\"utf-8\"><title>Y-Parameter Fit</title></head>"
            f"<body><h1>Y-Parameter Fit</h1><p>RMS: {rms:.12g} S; target met: {target_met}</p></body></html>\n",
            encoding="utf-8",
        )
    progress.info(
        f"fit-yparam completed: ports={network.nports}, rms_siemens={rms:.12g}, "
        f"mean_rms_siemens={mean_rms:.12g}, target_met={target_met}"
    )
    return result
