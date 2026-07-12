"""Portable verification artifacts for native S-parameter vector fits."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ElementRms:
    """RMS error for one zero-based S-matrix element."""

    row: int
    column: int
    rms: float


def _model_port_count(model: Any) -> int:
    network = getattr(model, "network", None)
    ports = getattr(network, "nports", None)
    if isinstance(ports, (int, np.integer)) and not isinstance(ports, (bool, np.bool_)) and ports > 0:
        return int(ports)

    constant = np.asarray(getattr(model, "constant_coeff", None), dtype=complex).reshape(-1)
    root = int(np.sqrt(constant.size))
    if root <= 0 or root * root != constant.size:
        raise ValueError("Native vector-fit coefficients do not describe a square S-matrix")
    return root


def evaluate_fitted_s(model: Any, frequencies_hz: Any) -> np.ndarray:
    """Evaluate native vector-fit arrays on ``frequencies_hz`` as ``(F, P, P)`` S data."""

    frequencies = np.asarray(frequencies_hz, dtype=float)
    if frequencies.ndim != 1 or frequencies.size == 0 or not np.all(np.isfinite(frequencies)):
        raise ValueError("frequencies_hz must be a non-empty, finite one-dimensional array")

    ports = _model_port_count(model)
    response_count = ports * ports
    poles = np.asarray(getattr(model, "poles", None), dtype=complex).reshape(-1)
    residues = np.asarray(getattr(model, "residues", None), dtype=complex)
    constant = np.asarray(getattr(model, "constant_coeff", None), dtype=complex).reshape(-1)
    proportional = np.asarray(
        getattr(model, "proportional_coeff", np.zeros(response_count, dtype=complex)), dtype=complex
    ).reshape(-1)
    if residues.shape != (response_count, poles.size):
        raise ValueError("Native vector-fit residues must have shape (ports * ports, poles)")
    if constant.size != response_count or proportional.size != response_count:
        raise ValueError("Native vector-fit constant/proportional coefficients have invalid length")

    s_axis = 2j * np.pi * frequencies
    response = constant[None, :] + proportional[None, :] * s_axis[:, None]
    for pole_index, pole in enumerate(poles):
        residue = residues[None, :, pole_index]
        response += residue / (s_axis[:, None] - pole)
        if pole.imag != 0.0:
            response += np.conj(residue) / (s_axis[:, None] - np.conj(pole))
    return response.reshape(frequencies.size, ports, ports)


def rank_element_rms(original_s: Any, fitted_s: Any) -> list[ElementRms]:
    """Return all S-parameter element RMS values, descending and deterministically tied."""

    original = np.asarray(original_s, dtype=complex)
    fitted = np.asarray(fitted_s, dtype=complex)
    if original.ndim != 3 or original.shape != fitted.shape or original.shape[1] != original.shape[2]:
        raise ValueError("original_s and fitted_s must have identical (frequency, port, port) shapes")
    if original.shape[0] == 0:
        raise ValueError("At least one frequency point is required to calculate RMS")
    if not np.isfinite(original).all() or not np.isfinite(fitted).all():
        raise ValueError("original_s and fitted_s must contain only finite values")

    rms = np.sqrt(np.mean(np.abs(fitted - original) ** 2, axis=0))
    ranking = [
        ElementRms(row=row, column=column, rms=float(rms[row, column]))
        for row in range(original.shape[1])
        for column in range(original.shape[2])
    ]
    return sorted(ranking, key=lambda item: (-item.rms, item.row, item.column))


def write_fitted_touchstone(path: str | Path, frequencies_hz: Any, fitted_s: Any, z0: Any) -> Path:
    """Write fitted S data as Touchstone while retaining the supplied reference impedance."""

    output = Path(path)
    frequencies = np.asarray(frequencies_hz, dtype=float)
    values = np.asarray(fitted_s, dtype=complex)
    if frequencies.ndim != 1 or frequencies.size == 0 or not np.all(np.isfinite(frequencies)):
        raise ValueError("frequencies_hz must be a non-empty, finite one-dimensional array")
    if values.ndim != 3 or values.shape[0] != frequencies.size or values.shape[1] != values.shape[2]:
        raise ValueError("fitted_s must have shape (frequency, port, port)")
    expected_suffix = f".s{values.shape[1]}p"
    if output.suffix.lower() != expected_suffix:
        raise ValueError(f"Fitted Touchstone path must end with '{expected_suffix}'")

    import skrf as rf

    network = rf.Network(
        frequency=rf.Frequency.from_f(frequencies, unit="hz"),
        s=values,
        z0=np.asarray(z0, dtype=complex),
        name=output.stem,
    )
    content = network.write_touchstone(return_string=True, form="ri", write_z0=True)
    if not isinstance(content, str):
        raise RuntimeError("scikit-rf did not return Touchstone contents")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return output
