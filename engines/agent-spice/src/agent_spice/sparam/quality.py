from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


SCHEMA_VERSION = "0.2"


@dataclass(frozen=True)
class QualityDiagnostic:
    id: str
    status: str
    severity: str
    message: str
    metric: Any = None
    threshold: Any = None
    frequency_hz: float | None = None
    frequency_range_hz: list[float] | None = None
    ports: list[int] | None = None
    recommendation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "severity": self.severity,
            "metric": self.metric,
            "threshold": self.threshold,
            "frequency_hz": self.frequency_hz,
            "frequency_range_hz": self.frequency_range_hz,
            "ports": self.ports,
            "message": self.message,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class QualityReport:
    profile: str
    status: str
    allowed_for: str
    blocking_reasons: list[str]
    warnings: list[str]
    diagnostics: list[QualityDiagnostic]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "status": self.status,
            "allowed_for": self.allowed_for,
            "blocking_reasons": self.blocking_reasons,
            "warnings": self.warnings,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def _frequency_range(values: np.ndarray) -> list[float] | None:
    if len(values) == 0:
        return None
    return [float(values[0]), float(values[-1])]


def _status_from_diagnostics(diagnostics: list[QualityDiagnostic], profile: str) -> str:
    if any(diagnostic.status == "FAIL" for diagnostic in diagnostics):
        return "FAIL"
    if profile == "signoff" and any(diagnostic.status == "UNKNOWN" for diagnostic in diagnostics):
        return "FAIL"
    if any(diagnostic.status in {"WARN", "UNKNOWN"} for diagnostic in diagnostics):
        return "WARN"
    return "PASS"


def _allowed_for(status: str) -> str:
    if status == "PASS":
        return "tran_candidate"
    if status == "WARN":
        return "report_only"
    return "report_only"


def _real_range(values: Any) -> dict[str, float] | None:
    values_array = np.asarray(values)
    if values_array.size == 0:
        return None
    return {
        "min_real": float(np.min(values_array.real)),
        "max_real": float(np.max(values_array.real)),
    }


def _check_frequency_axis(freqs: np.ndarray, require_dc: bool) -> list[QualityDiagnostic]:
    diagnostics: list[QualityDiagnostic] = []
    if len(freqs) < 2:
        diagnostics.append(
            QualityDiagnostic(
                id="frequency_points",
                status="FAIL",
                severity="error",
                metric=int(len(freqs)),
                threshold=2,
                message="At least two frequency points are required.",
                recommendation="Provide a Touchstone file with at least two frequency samples.",
            )
        )
        return diagnostics

    finite = bool(np.all(np.isfinite(freqs)))
    diagnostics.append(
        QualityDiagnostic(
            id="frequency_finite",
            status="PASS" if finite else "FAIL",
            severity="info" if finite else "error",
            message="Frequency samples are finite." if finite else "Frequency samples contain NaN or Inf.",
            recommendation=None if finite else "Fix or remove invalid frequency samples before fitting.",
        )
    )

    monotonic = bool(np.all(np.diff(freqs) > 0))
    diagnostics.append(
        QualityDiagnostic(
            id="frequency_monotonic",
            status="PASS" if monotonic else "FAIL",
            severity="info" if monotonic else "error",
            message="Frequency samples are strictly increasing."
            if monotonic
            else "Frequency samples are not strictly increasing.",
            recommendation=None if monotonic else "Sort, deduplicate, or repair the Touchstone frequency axis.",
        )
    )

    has_dc = bool(freqs[0] == 0.0)
    dc_status = "PASS" if has_dc else ("FAIL" if require_dc else "WARN")
    diagnostics.append(
        QualityDiagnostic(
            id="dc_coverage",
            status=dc_status,
            severity="info" if has_dc else ("error" if require_dc else "warning"),
            metric=float(freqs[0]),
            threshold=0.0,
            frequency_hz=float(freqs[0]),
            message="Input includes a DC sample."
            if has_dc
            else (
                "Input does not include the required DC sample."
                if require_dc
                else "Input does not include a DC sample."
            ),
            recommendation=None
            if has_dc
            else "Use explicit DC extrapolation before signoff-quality transient use.",
        )
    )
    return diagnostics


def _check_network_values(network: Any, passivity_epsilon: float) -> list[QualityDiagnostic]:
    diagnostics: list[QualityDiagnostic] = []
    s_values = getattr(network, "s", None)
    if s_values is None:
        diagnostics.append(
            QualityDiagnostic(
                id="s_parameters_available",
                status="UNKNOWN",
                severity="warning",
                message="S-parameter matrix is unavailable.",
                recommendation="Use a scikit-rf Network with S-parameter data.",
            )
        )
    else:
        s_array = np.asarray(s_values)
        finite = bool(np.all(np.isfinite(s_array)))
        diagnostics.append(
            QualityDiagnostic(
                id="s_parameters_finite",
                status="PASS" if finite else "FAIL",
                severity="info" if finite else "error",
                message="S-parameter samples are finite." if finite else "S-parameter samples contain NaN or Inf.",
                recommendation=None if finite else "Repair or filter invalid S-parameter samples before fitting.",
            )
        )
        if finite and s_array.ndim == 3 and s_array.shape[1] == s_array.shape[2]:
            try:
                max_sigma = float(np.max(np.linalg.svd(s_array, compute_uv=False)))
            except Exception:
                max_sigma = None
            diagnostics.append(
                QualityDiagnostic(
                    id="input_sample_max_singular_value",
                    status="UNKNOWN"
                    if max_sigma is None
                    else ("PASS" if max_sigma <= 1.0 + passivity_epsilon else "WARN"),
                    severity="warning" if max_sigma is None or max_sigma > 1.0 + passivity_epsilon else "info",
                    metric=max_sigma,
                    threshold=1.0 + passivity_epsilon,
                    message="Input sampled max singular value is within the passivity threshold."
                    if max_sigma is not None and max_sigma <= 1.0 + passivity_epsilon
                    else "Input sampled max singular value is unknown or exceeds the passivity threshold.",
                    recommendation=None
                    if max_sigma is not None and max_sigma <= 1.0 + passivity_epsilon
                    else "Run passivity enforcement and inspect passivity diagnostics before transient use.",
                )
            )

    z0 = getattr(network, "z0", None)
    if z0 is None:
        diagnostics.append(
            QualityDiagnostic(
                id="z0_available",
                status="UNKNOWN",
                severity="warning",
                message="Reference impedance data is unavailable.",
                recommendation="Preserve Touchstone reference impedance metadata in the input report.",
            )
        )
        return diagnostics

    z0_array = np.asarray(z0)
    finite = bool(np.all(np.isfinite(z0_array)))
    positive_real = bool(np.all(z0_array.real > 0)) if finite else False
    diagnostics.append(
        QualityDiagnostic(
            id="z0_finite_positive",
            status="PASS" if finite and positive_real else "WARN",
            severity="info" if finite and positive_real else "warning",
            metric=None if not finite else _real_range(z0_array),
            message="Reference impedance values are finite and have positive real parts."
            if finite and positive_real
            else "Reference impedance values are missing, invalid, or non-positive.",
            recommendation=None
            if finite and positive_real
            else "Inspect Touchstone reference impedance metadata before fitting.",
        )
    )

    if finite and z0_array.ndim >= 2 and len(z0_array) > 1:
        varies = not bool(np.allclose(z0_array, z0_array[0], rtol=1e-9, atol=1e-12))
        diagnostics.append(
            QualityDiagnostic(
                id="z0_frequency_variation",
                status="WARN" if varies else "PASS",
                severity="warning" if varies else "info",
                message="Reference impedance varies with frequency."
                if varies
                else "Reference impedance is constant over frequency.",
                recommendation="Record frequency-dependent Z0 in the handoff report; avoid collapsing it to one row."
                if varies
                else None,
            )
        )
    return diagnostics


def _check_fit_metrics(
    *,
    profile: str,
    frequency_points: int,
    fit_frequency_points: int,
    comparison_rms_error: float | None,
    comparison_rms_limit: float,
    passive_after_enforce: bool | None,
    passivity_violations_after: list[list[float]] | None,
    enforce_passivity: bool,
    poles: Any,
    stability_epsilon: float,
) -> list[QualityDiagnostic]:
    diagnostics: list[QualityDiagnostic] = []
    if fit_frequency_points < frequency_points:
        diagnostics.append(
            QualityDiagnostic(
                id="fit_frequency_subset",
                status="WARN",
                severity="warning",
                metric=fit_frequency_points,
                threshold=frequency_points,
                message="Vector fitting used a frequency subset.",
                recommendation="Use Original vs Fitted plots and comparison_rms_error to validate full-band quality.",
            )
        )
    else:
        diagnostics.append(
            QualityDiagnostic(
                id="fit_frequency_subset",
                status="PASS",
                severity="info",
                metric=fit_frequency_points,
                threshold=frequency_points,
                message="Vector fitting used all frequency points.",
            )
        )

    if comparison_rms_error is None:
        diagnostics.append(
            QualityDiagnostic(
                id="comparison_rms_error",
                status="UNKNOWN",
                severity="warning",
                threshold=comparison_rms_limit,
                message="Original-point comparison RMS error is unavailable.",
                recommendation="Use a scikit-rf version that can evaluate model response at requested frequencies.",
            )
        )
    else:
        comparison_status = "PASS" if comparison_rms_error <= comparison_rms_limit else "WARN"
        if profile == "signoff" and comparison_status == "WARN":
            comparison_status = "FAIL"
        diagnostics.append(
            QualityDiagnostic(
                id="comparison_rms_error",
                status=comparison_status,
                severity="info" if comparison_status == "PASS" else ("error" if comparison_status == "FAIL" else "warning"),
                metric=float(comparison_rms_error),
                threshold=comparison_rms_limit,
                message="Original-point comparison RMS error is within the configured threshold."
                if comparison_status == "PASS"
                else "Original-point comparison RMS error exceeds the configured threshold.",
                recommendation=None
                if comparison_status == "PASS"
                else "Increase fit density, model order, or adjust the target frequency band.",
            )
        )

    if not enforce_passivity:
        diagnostics.append(
            QualityDiagnostic(
                id="passivity_enforcement",
                status="FAIL" if profile == "signoff" else "WARN",
                severity="error" if profile == "signoff" else "warning",
                message="Passivity enforcement was skipped.",
                recommendation="Treat this artifact as preview/debug only; enable passivity enforcement for handoff.",
            )
        )
    elif passive_after_enforce is True:
        diagnostics.append(
            QualityDiagnostic(
                id="passivity_after_enforce",
                status="PASS",
                severity="info",
                message="Model reports passive after enforcement.",
            )
        )
    elif passive_after_enforce is False:
        diagnostics.append(
            QualityDiagnostic(
                id="passivity_after_enforce",
                status="FAIL",
                severity="error",
                message="Passivity violations remain after enforcement.",
                recommendation="Lower model order, increase passivity samples, or revisit input conditioning.",
            )
        )
    else:
        diagnostics.append(
            QualityDiagnostic(
                id="passivity_after_enforce",
                status="UNKNOWN",
                severity="warning",
                message="Passivity status after enforcement is unavailable.",
                recommendation="Inspect fit logs and scikit-rf passivity support before transient use.",
            )
        )

    if passivity_violations_after:
        diagnostics.append(
            QualityDiagnostic(
                id="passivity_violation_bands_after",
                status="FAIL",
                severity="error",
                metric=len(passivity_violations_after),
                message="Passivity violation bands remain after enforcement.",
                recommendation="Increase passivity sample density or revisit fitting order and conditioning.",
            )
        )
    else:
        diagnostics.append(
            QualityDiagnostic(
                id="passivity_violation_bands_after",
                status="PASS" if passivity_violations_after == [] else "UNKNOWN",
                severity="info" if passivity_violations_after == [] else "warning",
                metric=0 if passivity_violations_after == [] else None,
                message="No passivity violation bands were reported after enforcement."
                if passivity_violations_after == []
                else "Passivity violation bands after enforcement are unavailable.",
                recommendation=None
                if passivity_violations_after == []
                else "Use strict quality mode only after passivity violation bands can be evaluated.",
            )
        )

    if poles is None:
        diagnostics.append(
            QualityDiagnostic(
                id="pole_stability",
                status="UNKNOWN",
                severity="warning",
                message="Fitted poles are unavailable for stability checking.",
                recommendation="Expose poles in the fit report before signoff-quality handoff.",
            )
        )
    else:
        poles_array = np.asarray(poles)
        if len(poles_array) == 0:
            diagnostics.append(
                QualityDiagnostic(
                    id="pole_stability",
                    status="UNKNOWN",
                    severity="warning",
                    message="No fitted poles were reported.",
                    recommendation="Inspect vector fitting logs and model order.",
                )
            )
        else:
            max_real = float(np.max(poles_array.real))
            stable = max_real < -abs(stability_epsilon)
            diagnostics.append(
                QualityDiagnostic(
                    id="pole_stability",
                    status="PASS" if stable else "FAIL",
                    severity="info" if stable else "error",
                    metric=max_real,
                    threshold=-abs(stability_epsilon),
                    message="All fitted poles are in the left half-plane."
                    if stable
                    else "At least one fitted pole is not safely in the left half-plane.",
                    recommendation=None if stable else "Refit with different order, conditioning, or pole settings.",
                )
            )
    return diagnostics


def build_quality_report(
    *,
    network: Any,
    frequency_points: int,
    fit_frequency_points: int,
    comparison_rms_error: float | None,
    passive_after_enforce: bool | None,
    passivity_violations_after: list[list[float]] | None,
    enforce_passivity: bool,
    poles: Any = None,
    profile: str = "explore",
    comparison_rms_limit: float = 0.05,
    passivity_epsilon: float = 1e-6,
    stability_epsilon: float = 1e-12,
    require_dc: bool = False,
) -> QualityReport:
    if profile not in {"explore", "signoff"}:
        raise ValueError(f"Unsupported quality profile '{profile}'")
    freqs = np.asarray(getattr(network, "f", []), dtype=float)
    diagnostics: list[QualityDiagnostic] = []
    diagnostics.extend(_check_frequency_axis(freqs, require_dc))
    diagnostics.extend(_check_network_values(network, passivity_epsilon))
    diagnostics.extend(
        _check_fit_metrics(
            profile=profile,
            frequency_points=frequency_points,
            fit_frequency_points=fit_frequency_points,
            comparison_rms_error=comparison_rms_error,
            comparison_rms_limit=comparison_rms_limit,
            passive_after_enforce=passive_after_enforce,
            passivity_violations_after=passivity_violations_after,
            enforce_passivity=enforce_passivity,
            poles=poles,
            stability_epsilon=stability_epsilon,
        )
    )

    status = _status_from_diagnostics(diagnostics, profile)
    blocking_reasons = [diagnostic.id for diagnostic in diagnostics if diagnostic.status == "FAIL"]
    if profile == "signoff":
        blocking_reasons.extend(diagnostic.id for diagnostic in diagnostics if diagnostic.status == "UNKNOWN")
    warnings = [
        diagnostic.id
        for diagnostic in diagnostics
        if diagnostic.status in {"WARN", "UNKNOWN"} and diagnostic.id not in blocking_reasons
    ]
    return QualityReport(
        profile=profile,
        status=status,
        allowed_for=_allowed_for(status),
        blocking_reasons=blocking_reasons,
        warnings=warnings,
        diagnostics=diagnostics,
    )
