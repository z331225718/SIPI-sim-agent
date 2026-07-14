"""Portable verification artifacts for native S-parameter vector fits."""

from __future__ import annotations

from dataclasses import dataclass
import os
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
    reference = complex(network.z0[0, 0])
    if not np.isfinite(reference) or reference.real <= 0.0:
        raise ValueError("Touchstone reference impedance must have a positive, finite real part")
    lines = content.splitlines(keepends=True)
    for index, line in enumerate(lines):
        tokens = line.split()
        if tokens and tokens[0] == "#":
            if len(tokens) == 5 and tokens[-1].upper() == "R":
                newline = "\r\n" if line.endswith("\r\n") else "\n"
                lines[index] = f"{line.rstrip()} {reference.real:.12g}{newline}"
            break
    content = "".join(lines)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return output


def _rfm_real(value: complex, *, label: str) -> float:
    """Return an RFM scalar after rejecting coefficients it cannot represent."""

    scalar = complex(value)
    if not np.isfinite(scalar):
        raise ValueError(f"Cadence RFM cannot represent non-finite {label}")
    if scalar.imag != 0.0:
        raise ValueError(f"Cadence RFM requires real {label}")
    return float(scalar.real)


def _rfm_reference_impedance(z0: Any) -> float:
    """RFM has one Z0 field, unlike Touchstone's potentially per-port Z0."""

    values = np.asarray(z0, dtype=complex).reshape(-1)
    if values.size == 0:
        raise ValueError("Cadence RFM requires a reference impedance")
    if not np.isfinite(values).all():
        raise ValueError("Cadence RFM requires finite reference impedance")
    if not np.allclose(values, values[0], rtol=0.0, atol=1e-12):
        raise ValueError("Cadence RFM supports only one shared reference impedance")
    reference = _rfm_real(values[0], label="reference impedance")
    if reference <= 0.0:
        raise ValueError("Cadence RFM requires a positive reference impedance")
    return reference


def _rfm_pole_groups(model: Any, response_count: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Validate native canonical poles and return RFM real/complex pole indices."""

    poles = np.asarray(getattr(model, "poles", None), dtype=complex).reshape(-1)
    residues = np.asarray(getattr(model, "residues", None), dtype=complex)
    proportional = np.asarray(
        getattr(model, "proportional_coeff", np.zeros(response_count, dtype=complex)), dtype=complex
    ).reshape(-1)
    if residues.shape != (response_count, poles.size):
        raise ValueError("Native vector-fit residues must have shape (ports * ports, poles)")
    if proportional.size != response_count:
        raise ValueError("Native vector-fit proportional coefficients have invalid length")
    if not np.isfinite(poles).all() or not np.isfinite(residues).all() or not np.isfinite(proportional).all():
        raise ValueError("Cadence RFM cannot represent non-finite vector-fit coefficients")
    if np.any(proportional != 0.0):
        raise ValueError("Cadence RFM does not support proportional coefficients")
    if np.any(poles.real >= 0.0):
        raise ValueError("Cadence RFM requires stable poles with negative real part")

    real_indices = np.flatnonzero(poles.imag == 0.0)
    complex_indices = np.flatnonzero(poles.imag > 0.0)
    if real_indices.size + complex_indices.size != poles.size:
        raise ValueError("Cadence RFM complex poles must use the positive imaginary representative")
    for index in real_indices:
        if np.any(residues[:, index].imag != 0.0):
            raise ValueError("Cadence RFM requires real residues for real poles")
    return poles, residues, real_indices, complex_indices


def write_cadence_rfm(model: Any, path: str | Path, z0: Any) -> Path:
    """Write a Cadence Broadband SPICE ``VERSION 200600`` S-parameter RFM.

    The native vector-fit representation stores one positive-imaginary system
    pole ``p`` from each conjugate pair.  RFM stores the denominator coefficient
    ``omega_c = -p`` for ``A_c / (s + omega_c)``.  Proportional terms and
    non-canonical pole sets are rejected rather than silently exported with
    changed transfer behaviour.
    """

    output = Path(path)
    ports = _model_port_count(model)
    response_count = ports * ports
    constants = np.asarray(getattr(model, "constant_coeff", None), dtype=complex).reshape(-1)
    if constants.size != response_count:
        raise ValueError("Native vector-fit constant coefficients have invalid length")
    poles, residues, real_indices, complex_indices = _rfm_pole_groups(model, response_count)
    reference = _rfm_reference_impedance(z0)

    lines = [
        "VERSION 200600",
        f"NPORT {ports}",
        "MATRIX_TYPE S",
        f"Z0 {reference:.12e}",
    ]
    for row in range(ports):
        for column in range(ports):
            response_index = row * ports + column
            lines.extend(
                (
                    f"BEGIN {row + 1} {column + 1}",
                    f"CONST {_rfm_real(constants[response_index], label='constant coefficient'):.12e}",
                    "C 0.000000000000e+00",
                    "DELAY 0.000000000000e+00",
                )
            )
            lines.append(f"BEGIN_REAL {real_indices.size}")
            for pole_index in real_indices:
                lines.append(f"  {-poles[pole_index].real:.12e}  {residues[response_index, pole_index].real:.12e}")
            lines.append(f"BEGIN_COMPLEX {complex_indices.size}")
            for pole_index in complex_indices:
                pole = poles[pole_index]
                # HSPICE stores omega_c, not the system pole p. Since
                # omega_c=-p, a positive-imaginary native pole is written with
                # negative omega and its residue must not be conjugated.
                residue = residues[response_index, pole_index]
                lines.append(
                    f"  {-pole.real:.12e}  {-pole.imag:.12e}  {residue.real:.12e}  {residue.imag:.12e}"
                )
            lines.append("END")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="ascii")
    return output


def write_cadence_rfm_wrapper(
    path: str | Path,
    rfm_path: str | Path,
    *,
    nports: int,
    subcircuit_name: str | None = None,
) -> Path:
    """Write a minimal HSPICE/Sigrity wrapper referring to an RFM relatively."""

    output = Path(path)
    reference = Path(rfm_path)
    if not isinstance(nports, (int, np.integer)) or isinstance(nports, (bool, np.bool_)) or nports <= 0:
        raise ValueError("nports must be a positive integer")
    name = subcircuit_name if subcircuit_name is not None else output.stem
    if not name or any(character.isspace() for character in name):
        raise ValueError("subcircuit_name must be a non-empty SPICE token")
    relative_rfm = os.path.relpath(reference, start=output.parent).replace("\\", "/")
    if "'" in relative_rfm:
        raise ValueError("rfm_path must not contain a single quote")
    # An HSPICE S element takes a positive/negative node pair for *each*
    # port.  It does not take N signal nodes followed by one shared reference.
    # The latter silently changes port pairing and can make an otherwise valid
    # RFM behave like an open or a short in a transient deck.
    port_pairs = tuple((f"n{index}", f"n{index}_ref") for index in range(1, int(nports) + 1))
    continuation_pairs = tuple(f"+ {positive} {reference}" for positive, reference in port_pairs)
    content = "\n".join(
        (
            f".subckt {name}",
            *continuation_pairs,
            "S1",
            *continuation_pairs,
            "+ mname=s_model",
            f".model s_model S n={int(nports)}",
            f"+ rfmfile='{relative_rfm}'",
            ".ends",
            "",
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="ascii")
    return output
