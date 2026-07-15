"""Scenario-bound HSPICE residual tuning for an existing Y-derived S RFM."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace

import numpy as np
import skrf as rf
from scipy.optimize import minimize

from .artifacts import evaluate_fitted_s, write_cadence_rfm
from .rfm import RfmModel, parse_cadence_rfm


_UNIT_SCALE = {"": 1.0, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}


@dataclass(frozen=True)
class YTranTuneConfig:
    """Explicit contract for a transient-specific RFM residual search."""

    touchstone: Path
    input_rfm: Path
    deck: Path
    output_rfm: Path
    rfm_token: str
    rms_measure: str
    residual_damping: tuple[float, ...]
    band_boundaries: tuple[float, ...]
    peak_measure: str | None = None
    report: Path | None = None
    work_dir: Path | None = None
    hspice_bin: str = "hspice"
    license_file: str | None = None
    max_evaluations: int = 150
    max_static_rms_growth: float = 0.003
    max_sigma: float = 0.999


def parse_float_csv(value: str, *, label: str) -> tuple[float, ...]:
    try:
        parsed = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise ValueError(f"{label} must be a comma-separated finite float list") from exc
    if not parsed or not np.isfinite(parsed).all() or any(item <= 0.0 for item in parsed):
        raise ValueError(f"{label} must contain one or more positive finite values")
    if tuple(sorted(parsed)) != parsed or len(set(parsed)) != len(parsed):
        raise ValueError(f"{label} must be strictly increasing")
    return parsed


def correction_pole_indices(poles: np.ndarray, damping: tuple[float, ...]) -> np.ndarray:
    """Locate the declared real residual poles without guessing their order."""

    indices: list[int] = []
    for value in damping:
        matches = np.flatnonzero(
            (np.asarray(poles, dtype=complex).imag == 0.0)
            & np.isclose(-np.asarray(poles, dtype=complex).real, value, rtol=2e-12, atol=1e-10)
        )
        if matches.size != 1:
            raise ValueError(f"residual pole {value:.12g} rad/s is not uniquely present in the RFM")
        indices.append(int(matches[0]))
    return np.asarray(indices, dtype=int)


def _band_indices(damping: tuple[float, ...], boundaries: tuple[float, ...]) -> tuple[np.ndarray, ...]:
    if any(boundary <= damping[0] or boundary >= damping[-1] for boundary in boundaries):
        raise ValueError("band boundaries must lie inside the residual damping range")
    if tuple(sorted(boundaries)) != boundaries or len(set(boundaries)) != len(boundaries):
        raise ValueError("band boundaries must be strictly increasing")
    values = np.asarray(damping, dtype=float)
    cuts = np.searchsorted(values, np.asarray(boundaries, dtype=float), side="right")
    return tuple(group for group in np.split(np.arange(values.size), cuts) if group.size)


def _static_metrics(model: object, network: rf.Network) -> tuple[float, float]:
    fitted = evaluate_fitted_s(model, network.f)
    rms = float(np.sqrt(np.mean(np.abs(fitted - network.s) ** 2)))
    max_sigma = float(max(np.linalg.svd(value, compute_uv=False)[0] for value in fitted))
    return rms, max_sigma


def _scaled_trial(
    base: RfmModel,
    correction_indices: np.ndarray,
    bands: tuple[np.ndarray, ...],
    scales: np.ndarray,
    path: Path,
) -> SimpleNamespace:
    residues = np.asarray(base.residues, dtype=complex).copy()
    response_groups = ((0,), (1, 2), (3,)) if base.nports == 2 else tuple((index,) for index in range(base.nports**2))
    for band_index, band in enumerate(bands):
        pole_indices = correction_indices[band]
        for response_index, responses in enumerate(response_groups):
            factor = float(scales[band_index * len(response_groups) + response_index])
            for response in responses:
                residues[response, pole_indices] *= factor
    trial = SimpleNamespace(
        nports=base.nports,
        poles=np.asarray(base.poles, dtype=complex),
        residues=residues,
        constant_coeff=np.asarray(base.constant_coeff, dtype=complex),
        proportional_coeff=np.zeros(base.nports**2, dtype=complex),
    )
    write_cadence_rfm(trial, path, base.z0)
    return trial


def parse_hspice_measure(listing: Path, name: str) -> float:
    """Read a scalar HSPICE measure, accepting standard engineering suffixes."""

    text = listing.read_text(encoding="utf-8", errors="ignore")
    matches = re.findall(rf"\b{re.escape(name)}\s*=\s*([0-9.eE+-]+)\s*([munpf]?)\b", text, flags=re.IGNORECASE)
    if not matches:
        raise ValueError(f"HSPICE measure '{name}' is missing from {listing}")
    number, suffix = matches[-1]
    return float(number) * _UNIT_SCALE[suffix.lower()]


def _render_trial_deck(source: str, *, token: str, rfm_reference: str) -> str:
    if source.count(token) != 1:
        raise ValueError("--rfm-token must occur exactly once in the supplied HSPICE deck")
    return source.replace(token, rfm_reference)


def tune_y_rfm_for_tran(config: YTranTuneConfig) -> dict[str, object]:
    """Tune declared residual poles against one explicit HSPICE signoff scenario."""

    if config.max_evaluations < 2:
        raise ValueError("max_evaluations must be at least 2")
    if not 0.0 <= config.max_static_rms_growth <= 1.0:
        raise ValueError("max_static_rms_growth must be in [0, 1]")
    if not 0.0 < config.max_sigma <= 1.0:
        raise ValueError("max_sigma must be in (0, 1]")
    if not config.deck.is_file() or not config.input_rfm.is_file() or not config.touchstone.is_file():
        raise ValueError("touchstone, input RFM, and HSPICE deck must exist")

    deck_dir = config.deck.resolve().parent
    work_dir = (config.work_dir or (deck_dir / f"{config.output_rfm.stem}_tran_tune")).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    base = parse_cadence_rfm(config.input_rfm)
    network = rf.Network(str(config.touchstone))
    if network.nports != base.nports:
        raise ValueError("Touchstone and RFM port counts differ")
    indices = correction_pole_indices(base.poles, config.residual_damping)
    bands = _band_indices(config.residual_damping, config.band_boundaries)
    response_group_count = 3 if base.nports == 2 else base.nports**2
    baseline_rms, baseline_sigma = _static_metrics(base, network)
    deck_source = config.deck.read_text(encoding="utf-8")
    history: list[dict[str, object]] = []
    best: dict[str, object] | None = None
    environment = os.environ.copy()
    if config.license_file:
        environment["SNPSLMD_LICENSE_FILE"] = config.license_file
        environment["LM_LICENSE_FILE"] = config.license_file

    def objective(scales: np.ndarray) -> float:
        nonlocal best
        ordinal = len(history)
        trial_rfm = work_dir / f"trial_{ordinal:03d}.rfm"
        trial = _scaled_trial(base, indices, bands, scales, trial_rfm)
        static_rms, static_sigma = _static_metrics(trial, network)
        record: dict[str, object] = {
            "ordinal": ordinal,
            "scales": [float(value) for value in scales],
            "s_rms": static_rms,
            "max_sigma": static_sigma,
        }
        if static_rms > baseline_rms * (1.0 + config.max_static_rms_growth) or static_sigma > config.max_sigma:
            record["objective"] = 1.0 + static_rms
            history.append(record)
            return float(record["objective"])

        relative_rfm = os.path.relpath(trial_rfm, start=deck_dir).replace("\\", "/")
        trial_deck = work_dir / f"trial_{ordinal:03d}.sp"
        trial_deck.write_text(_render_trial_deck(deck_source, token=config.rfm_token, rfm_reference=relative_rfm), encoding="utf-8")
        output_stem = work_dir / f"trial_{ordinal:03d}"
        completed = subprocess.run(
            [config.hspice_bin, os.path.relpath(trial_deck, start=deck_dir), "-o", os.path.relpath(output_stem, start=deck_dir)],
            cwd=deck_dir,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        listing = output_stem.with_suffix(".lis")
        if completed.returncode or not listing.is_file():
            record["objective"] = 2.0
            record["hspice_returncode"] = int(completed.returncode)
        else:
            rms = parse_hspice_measure(listing, config.rms_measure)
            record["tran_rms"] = rms
            if config.peak_measure:
                record["tran_peak"] = parse_hspice_measure(listing, config.peak_measure)
            record["objective"] = rms
            if best is None or rms < float(best["tran_rms"]):
                best = record.copy()
                shutil.copy2(trial_rfm, work_dir / "best.rfm")
        history.append(record)
        return float(record["objective"])

    parameter_count = len(bands) * response_group_count
    initial = np.ones(parameter_count, dtype=float)
    simplex = np.vstack((initial, *(initial + np.eye(parameter_count)[index] * 0.012 for index in range(parameter_count))))
    result = minimize(
        objective,
        initial,
        method="Nelder-Mead",
        options={"maxfev": config.max_evaluations, "initial_simplex": simplex, "xatol": 4e-4, "fatol": 1e-7},
    )
    if best is None:
        raise ValueError("no candidate completed HSPICE transient scoring")
    config.output_rfm.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(work_dir / "best.rfm", config.output_rfm)
    payload: dict[str, object] = {
        "input_rfm": str(config.input_rfm),
        "output_rfm": str(config.output_rfm),
        "touchstone": str(config.touchstone),
        "deck": str(config.deck),
        "rms_measure": config.rms_measure,
        "peak_measure": config.peak_measure,
        "residual_damping_rad_per_s": list(config.residual_damping),
        "band_boundaries_rad_per_s": list(config.band_boundaries),
        "baseline": {"s_rms": baseline_rms, "max_sigma": baseline_sigma},
        "optimizer": {"success": bool(result.success), "message": str(result.message), "evaluations": int(result.nfev)},
        "best": best,
        "history": history,
    }
    report = config.report or config.output_rfm.with_suffix(".json")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
