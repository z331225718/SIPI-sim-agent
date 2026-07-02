from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import skrf as rf
from skrf.vectorFitting import VectorFitting


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
    model_order_max: int = 100
    target_error: float = 0.01
    parameter_type: str = "s"
    enforce_passivity: bool = True
    passivity_samples: int = 200
    subckt_name: str = "s_equivalent"
    create_reference_pins: bool = False


@dataclass(frozen=True)
class SParamFitResult:
    touchstone_path: Path
    spice_path: Path
    report_path: Path | None
    ports: int
    frequency_points: int
    reference_impedance: list[float]
    config: SParamFitConfig
    rms_error: float | None
    passive_before_enforce: bool | None
    passive_after_enforce: bool | None
    passivity_violations_before: list[list[float]] | None
    passivity_violations_after: list[list[float]] | None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Path):
            return self.spice_path == other
        if isinstance(other, SParamFitResult):
            return self.to_dict() == other.to_dict()
        return NotImplemented

    def to_dict(self) -> dict[str, Any]:
        return {
            "touchstone_path": str(self.touchstone_path),
            "spice_path": str(self.spice_path),
            "report_path": None if self.report_path is None else str(self.report_path),
            "ports": self.ports,
            "frequency_points": self.frequency_points,
            "reference_impedance": self.reference_impedance,
            "config": asdict(self.config),
            "rms_error": self.rms_error,
            "passive_before_enforce": self.passive_before_enforce,
            "passive_after_enforce": self.passive_after_enforce,
            "passivity_violations_before": self.passivity_violations_before,
            "passivity_violations_after": self.passivity_violations_after,
        }


def _reference_impedance(network: Any) -> list[float]:
    if len(network.z0) == 0:
        return []
    return [float(value.real) for value in network.z0[0]]


def _safe_bool(method, **kwargs) -> bool | None:
    try:
        return bool(method(**kwargs))
    except Exception:
        return None


def _safe_passivity_violations(vector_fit: VectorFitting, parameter_type: str) -> list[list[float]] | None:
    try:
        violations = vector_fit.passivity_test(parameter_type=parameter_type)
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


def _safe_rms_error(vector_fit: VectorFitting, parameter_type: str) -> float | None:
    try:
        return float(vector_fit.get_rms_error(parameter_type=parameter_type))
    except Exception:
        return None


def _fit_model(vector_fit: VectorFitting, config: SParamFitConfig) -> None:
    if config.mode == "auto":
        vector_fit.auto_fit(
            n_poles_init_real=config.n_poles_init_real,
            n_poles_init_cmplx=config.n_poles_init_cmplx,
            n_poles_add=config.n_poles_add,
            model_order_max=config.model_order_max,
            target_error=config.target_error,
            parameter_type=config.parameter_type,
            enforce_dc=config.enforce_dc,
        )
        return
    if config.mode == "manual":
        vector_fit.vector_fit(
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


def fit_touchstone_to_spice(
    touchstone_path: Path,
    output_path: Path,
    config: SParamFitConfig | None = None,
    report_path: Path | None = None,
) -> SParamFitResult:
    config = config or SParamFitConfig()
    network = rf.Network(str(touchstone_path))
    vector_fit = VectorFitting(network)
    _fit_model(vector_fit, config)
    passive_before = _safe_bool(vector_fit.is_passive, parameter_type=config.parameter_type)
    violations_before = _safe_passivity_violations(vector_fit, config.parameter_type)
    if config.enforce_passivity:
        vector_fit.passivity_enforce(n_samples=config.passivity_samples, parameter_type=config.parameter_type)
    passive_after = _safe_bool(vector_fit.is_passive, parameter_type=config.parameter_type)
    violations_after = _safe_passivity_violations(vector_fit, config.parameter_type)
    rms_error = _safe_rms_error(vector_fit, config.parameter_type)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    vector_fit.write_spice_subcircuit_s(
        str(output_path),
        fitted_model_name=config.subckt_name,
        create_reference_pins=config.create_reference_pins,
    )
    result = SParamFitResult(
        touchstone_path=touchstone_path,
        spice_path=output_path,
        report_path=report_path,
        ports=network.nports,
        frequency_points=len(network.f),
        reference_impedance=_reference_impedance(network),
        config=config,
        rms_error=rms_error,
        passive_before_enforce=passive_before,
        passive_after_enforce=passive_after,
        passivity_violations_before=violations_before,
        passivity_violations_after=violations_after,
    )
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
