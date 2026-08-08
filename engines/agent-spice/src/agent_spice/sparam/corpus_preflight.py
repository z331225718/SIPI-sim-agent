"""Validation and provenance capture for the MFT-NNLS promotion corpus."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import numpy as np
import skrf
import yaml


_TOUCHSTONE_SUFFIX_RE = re.compile(r"\.s(?P<ports>\d+)p$", re.IGNORECASE)


@dataclass(frozen=True)
class PromotionCorpusCase:
    """Immutable provenance for one validated Touchstone input."""

    id: str
    path: str
    sha256: str
    size_bytes: int
    ports: int
    frequency_points: int
    frequency_min_hz: float
    frequency_max_hz: float
    reference_impedance_by_port: tuple[float, ...]


@dataclass(frozen=True)
class PromotionCorpusReport:
    """Successful promotion-corpus preflight result."""

    manifest: str
    manifest_sha256: str
    status: str
    case_count: int
    cases: tuple[PromotionCorpusCase, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest,
            "manifest_sha256": self.manifest_sha256,
            "status": self.status,
            "case_count": self.case_count,
            "cases": [asdict(case) for case in self.cases],
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_path(manifest_path: Path, base_dir: str | Path, touchstone: str | Path) -> Path:
    path = Path(touchstone)
    if path.is_absolute():
        return path.resolve()
    base = Path(base_dir)
    if not base.is_absolute():
        base = manifest_path.parent / base
    return (base / path).resolve()


def _validate_fit(case_id: str, fit: Any) -> None:
    if not isinstance(fit, dict):
        raise ValueError(f"Promotion case '{case_id}' must define a fit mapping")
    if fit.get("mode") != "auto":
        raise ValueError(f"Promotion case '{case_id}' must use mode=auto")
    if fit.get("target_error") != 0.001:
        raise ValueError(f"Promotion case '{case_id}' must use target_error=0.001")
    if fit.get("enforce_passivity") is not True:
        raise ValueError(f"Promotion case '{case_id}' must set enforce_passivity=true")
    prohibited = {
        "response_scale",
        "fit_max_frequency_points",
        "comparison_max_frequency_points",
        "quality_max_frequency_points",
        "passivity_check_f_max",
    }
    used = sorted(key for key in prohibited if key in fit)
    if used:
        raise ValueError(f"Promotion case '{case_id}' uses prohibited fit settings: {', '.join(used)}")


def _raw_frequency_axis(path: Path, ports: int) -> np.ndarray:
    """Read the original frequency ordering before scikit-rf normalizes it."""

    values_per_sample = 1 + 2 * ports * ports
    values: list[float] = []
    try:
        with path.open("r", encoding="ascii", errors="strict") as handle:
            for raw_line in handle:
                line = raw_line.split("!", 1)[0].strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("["):
                    raise ValueError(f"Touchstone 2.0 is not supported by promotion preflight: {path}")
                try:
                    values.extend(float(token) for token in line.split())
                except ValueError as exc:
                    raise ValueError(f"Invalid Touchstone numeric data: {path}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"Touchstone must be ASCII text: {path}") from exc
    if len(values) % values_per_sample != 0:
        raise ValueError(f"Touchstone data rows are incomplete: {path}")
    return np.asarray(values[::values_per_sample], dtype=float)


def _validate_network(case_id: str, path: Path) -> PromotionCorpusCase:
    match = _TOUCHSTONE_SUFFIX_RE.search(path.name)
    if match is None:
        raise ValueError(f"Promotion input must use a .sNp suffix: {path}")
    expected_ports = int(match.group("ports"))
    raw_frequencies = _raw_frequency_axis(path, expected_ports)
    if len(raw_frequencies) < 2 or not np.isfinite(raw_frequencies).all():
        raise ValueError(f"Touchstone frequencies must be finite with at least two samples: {path}")
    if not np.all(np.diff(raw_frequencies) > 0.0):
        raise ValueError(f"Touchstone frequencies must be strictly increasing: {path}")
    try:
        network = skrf.Network(str(path))
    except Exception as exc:
        raise ValueError(f"Unable to read Touchstone input for case '{case_id}': {path}") from exc

    frequencies = np.asarray(network.f, dtype=float)
    response = np.asarray(network.s, dtype=complex)
    z0 = np.asarray(network.z0, dtype=complex)
    if network.nports != expected_ports:
        raise ValueError(f"Touchstone suffix/metadata port mismatch: {path}")
    if frequencies.ndim != 1 or len(frequencies) != len(raw_frequencies) or not np.isfinite(frequencies).all():
        raise ValueError(f"Touchstone frequencies must be finite with at least two samples: {path}")
    if response.shape != (len(frequencies), expected_ports, expected_ports):
        raise ValueError(f"Touchstone response shape is inconsistent with port count: {path}")
    if not np.isfinite(response).all():
        raise ValueError(f"Touchstone contains non-finite S-parameter values: {path}")
    if z0.shape != (len(frequencies), expected_ports) or not np.isfinite(z0).all():
        raise ValueError(f"Touchstone reference impedance metadata is inconsistent: {path}")
    if not np.allclose(z0.imag, 0.0):
        raise ValueError(f"Touchstone reference impedance must be real: {path}")
    reference_impedance = tuple(float(value) for value in z0[0].real)
    if not np.allclose(z0.real, reference_impedance, rtol=0.0, atol=0.0):
        raise ValueError(f"Touchstone reference impedance must not vary by frequency: {path}")
    return PromotionCorpusCase(
        id=case_id,
        path=str(path),
        sha256=_sha256_file(path),
        size_bytes=path.stat().st_size,
        ports=expected_ports,
        frequency_points=len(frequencies),
        frequency_min_hz=float(frequencies[0]),
        frequency_max_hz=float(frequencies[-1]),
        reference_impedance_by_port=reference_impedance,
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def preflight_promotion_corpus(manifest: Path, report_path: Path) -> PromotionCorpusReport:
    """Validate a promotion manifest and atomically persist its provenance report."""

    manifest = Path(manifest).resolve()
    payload = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Promotion manifest must contain at least one case")
    base_dir = payload.get("base_dir", ".")
    expected_reference_impedance = payload.get("reference_impedance_ohm")
    if expected_reference_impedance is not None:
        if not isinstance(expected_reference_impedance, (int, float)) or not np.isfinite(expected_reference_impedance):
            raise ValueError("Promotion manifest reference_impedance_ohm must be finite")
        expected_reference_impedance = float(expected_reference_impedance)
    cases: list[PromotionCorpusCase] = []
    ids: set[str] = set()
    hashes: set[str] = set()
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise ValueError("Promotion manifest cases must be mappings")
        case_id = str(raw_case.get("id", ""))
        if not case_id:
            raise ValueError("Promotion case id must not be empty")
        if case_id in ids:
            raise ValueError(f"Duplicate promotion case id: {case_id}")
        ids.add(case_id)
        _validate_fit(case_id, raw_case.get("fit"))
        if "touchstone" not in raw_case:
            raise ValueError(f"Promotion case '{case_id}' must define touchstone")
        path = _resolve_path(manifest, base_dir, raw_case["touchstone"])
        if not path.is_file():
            raise ValueError(f"Touchstone file not found: {path}")
        case = _validate_network(case_id, path)
        if expected_reference_impedance is not None and not np.allclose(
            case.reference_impedance_by_port,
            expected_reference_impedance,
            rtol=0.0,
            atol=0.0,
        ):
            raise ValueError(f"Promotion input does not match manifest reference impedance: {path}")
        if case.sha256 in hashes:
            raise ValueError(f"duplicate input SHA-256 in promotion corpus: {path}")
        hashes.add(case.sha256)
        cases.append(case)

    cases.sort(key=lambda case: (case.ports, Path(case.path).name.lower()))
    result = PromotionCorpusReport(
        manifest=str(manifest),
        manifest_sha256=_sha256_file(manifest),
        status="PASS",
        case_count=len(cases),
        cases=tuple(cases),
    )
    _atomic_write_json(Path(report_path), result.to_dict())
    return result
