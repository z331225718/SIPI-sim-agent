"""Passivity assessment for symmetric pole-residue Y and S models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from agent_spice.sparam.mft_nnls.model import evaluate
from agent_spice.sparam.mft_nnls.types import PoleResidueModel


BandSource = Literal["half_size", "sweep"]
ParameterType = Literal["S", "Y"]


@dataclass(frozen=True)
class ViolationBand:
    start_hz: float
    end_hz: float
    band_source: BandSource


@dataclass(frozen=True)
class PassivityAssessment:
    parameter_type: ParameterType
    bands: tuple[ViolationBand, ...]
    worst_value: float
    band_source: BandSource
    sampled_frequencies_hz: NDArray[np.float64]

    @property
    def max_value(self) -> float:
        if self.parameter_type != "S":
            raise AttributeError("max_value is defined only for S assessments")
        return self.worst_value

    @property
    def min_value(self) -> float:
        if self.parameter_type != "Y":
            raise AttributeError("min_value is defined only for Y assessments")
        return self.worst_value


@dataclass(frozen=True)
class ViolationExtremum:
    frequency_hz: float
    value: float
    left_vector: NDArray[np.complex128]
    right_vector: NDArray[np.complex128] | None
    band_source: BandSource


def _default_f_max_hz(model: PoleResidueModel) -> float:
    pole_frequency = float(np.max(np.abs(model.poles))) / (2.0 * np.pi) if len(model.poles) else 1.0
    return max(1.0, 10.0 * pole_frequency)


def _state_space(model: PoleResidueModel) -> tuple[NDArray[np.complex128], NDArray[np.complex128], NDArray[np.complex128]]:
    ports = model.ports
    pole_count = len(model.poles)
    a = np.kron(np.eye(ports, dtype=complex), np.diag(model.poles))
    b = np.zeros((ports * pole_count, ports), dtype=complex)
    c = np.zeros((ports, ports * pole_count), dtype=complex)
    for port in range(ports):
        block = slice(port * pole_count, (port + 1) * pole_count)
        b[block, port] = 1.0
        c[:, block] = model.residues[:, port, :]
    return a, b, c


def _metric(model: PoleResidueModel, frequencies_hz: NDArray[np.float64], parameter_type: ParameterType) -> NDArray[np.float64]:
    values = evaluate(model, 2j * np.pi * frequencies_hz)
    if parameter_type == "S":
        return np.linalg.svd(values, compute_uv=False)[:, 0]
    hermitian = 0.5 * (values + np.swapaxes(values.conj(), 1, 2))
    return np.linalg.eigvalsh(hermitian)[:, 0]


def _is_violation(value: float, parameter_type: ParameterType) -> bool:
    return value > 1.0 if parameter_type == "S" else value < 0.0


def _half_size_crossovers_hz(model: PoleResidueModel, parameter_type: ParameterType) -> NDArray[np.float64]:
    if len(model.poles) == 0 or np.any(np.abs(model.proportional) > 1.0e-14):
        raise ValueError("half-size assessment requires a proper dynamic model")
    a, b, c = _state_space(model)
    d = np.asarray(model.constant, dtype=complex)
    ports = model.ports
    identity = np.eye(ports, dtype=complex)
    if parameter_type == "S":
        if np.linalg.cond(d - identity) > 1.0e12 or np.linalg.cond(d + identity) > 1.0e12:
            raise ValueError("half-size S matrix is singular")
        left = a - b @ np.linalg.solve(d - identity, c)
        right = a - b @ np.linalg.solve(d + identity, c)
        roots = np.sqrt(np.linalg.eigvals(left @ right))
        omega = np.abs(roots.imag[np.abs(roots.real) <= 1.0e-8 * (1.0 + np.abs(roots.imag))])
    else:
        if np.linalg.cond(d) > 1.0e12:
            raise ValueError("half-size Y feedthrough is singular")
        matrix = np.real_if_close(a @ ((b @ np.linalg.solve(d, c)) - a), tol=1000)
        roots = np.sqrt(np.asarray(np.linalg.eigvals(matrix), dtype=complex))
        omega = roots.real[np.abs(roots.imag) <= 1.0e-8 * (1.0 + np.abs(roots.real))]
        omega = np.abs(omega)
    omega = np.asarray(omega[np.isfinite(omega) & (omega > 1.0e-12)], dtype=float)
    return np.unique(np.sort(omega / (2.0 * np.pi)))


def _bands_from_boundaries(
    model: PoleResidueModel,
    parameter_type: ParameterType,
    boundaries_hz: NDArray[np.float64],
    f_max_hz: float,
    source: BandSource,
) -> tuple[ViolationBand, ...]:
    boundaries = np.concatenate(([0.0], boundaries_hz[(boundaries_hz > 0.0) & (boundaries_hz < f_max_hz)], [f_max_hz]))
    bands: list[ViolationBand] = []
    for start, end in zip(boundaries[:-1], boundaries[1:], strict=True):
        probe = 0.5 * (start + end)
        if _is_violation(float(_metric(model, np.asarray([probe]), parameter_type)[0]), parameter_type):
            if bands and np.isclose(bands[-1].end_hz, start):
                bands[-1] = ViolationBand(bands[-1].start_hz, float(end), source)
            else:
                bands.append(ViolationBand(float(start), float(end), source))
    return tuple(bands)


def _sweep_bands(model: PoleResidueModel, parameter_type: ParameterType, f_max_hz: float) -> tuple[tuple[ViolationBand, ...], NDArray[np.float64]]:
    frequencies = np.linspace(0.0, f_max_hz, 801)
    values = _metric(model, frequencies, parameter_type)
    bands: list[ViolationBand] = []
    start: float | None = None
    for frequency, value in zip(frequencies, values, strict=True):
        if _is_violation(float(value), parameter_type):
            start = float(frequency) if start is None else start
        elif start is not None:
            bands.append(ViolationBand(start, float(frequency), "sweep"))
            start = None
    if start is not None:
        bands.append(ViolationBand(start, float(frequencies[-1]), "sweep"))
    return tuple(bands), frequencies


def _assess(model: PoleResidueModel, parameter_type: ParameterType, f_max: float | None, *, force_sweep: bool) -> PassivityAssessment:
    f_max_hz = _default_f_max_hz(model) if f_max is None else float(f_max)
    if not np.isfinite(f_max_hz) or f_max_hz <= 0.0:
        raise ValueError("f_max must be finite and positive")
    try:
        if force_sweep:
            raise ValueError("sweep explicitly requested")
        crossovers = _half_size_crossovers_hz(model, parameter_type)
        bands = _bands_from_boundaries(model, parameter_type, crossovers, f_max_hz, "half_size")
        sampled = np.unique(np.concatenate(([0.0, f_max_hz], crossovers[(crossovers > 0.0) & (crossovers < f_max_hz)])))
        source: BandSource = "half_size"
    except (np.linalg.LinAlgError, ValueError):
        bands, sampled = _sweep_bands(model, parameter_type, f_max_hz)
        source = "sweep"
    metric = _metric(model, np.linspace(0.0, f_max_hz, 801), parameter_type)
    worst = float(np.max(metric) if parameter_type == "S" else np.min(metric))
    return PassivityAssessment(parameter_type, bands, worst, source, sampled)


def assess_s_passivity(model: PoleResidueModel, f_max: float | None = None, *, force_sweep: bool = False) -> PassivityAssessment:
    return _assess(model, "S", f_max, force_sweep=force_sweep)


def assess_y_passivity(model: PoleResidueModel, f_max: float | None = None, *, force_sweep: bool = False) -> PassivityAssessment:
    return _assess(model, "Y", f_max, force_sweep=force_sweep)


def _normalize_vector(vector: NDArray[np.complex128]) -> NDArray[np.complex128]:
    normalized = np.asarray(vector, dtype=complex) / np.linalg.norm(vector)
    pivot = int(np.argmax(np.abs(normalized)))
    return normalized * np.exp(-1j * np.angle(normalized[pivot]))


def select_violation_extrema(
    model: PoleResidueModel,
    assessment: PassivityAssessment,
    local: bool,
) -> tuple[ViolationExtremum, ...]:
    extrema: list[ViolationExtremum] = []
    for band in assessment.bands:
        frequencies = np.linspace(band.start_hz, band.end_hz, 129)
        values = _metric(model, frequencies, assessment.parameter_type)
        index = int(np.argmax(values) if assessment.parameter_type == "S" else np.argmin(values))
        frequency = float(frequencies[index])
        matrix = evaluate(model, np.asarray([2j * np.pi * frequency]))[0]
        if assessment.parameter_type == "S":
            left, singular_values, right_h = np.linalg.svd(matrix)
            extrema.append(
                ViolationExtremum(frequency, float(singular_values[0]), _normalize_vector(left[:, 0]), _normalize_vector(right_h[0].conj()), band.band_source)
            )
        else:
            values_y, vectors = np.linalg.eigh(0.5 * (matrix + matrix.conj().T))
            extrema.append(ViolationExtremum(frequency, float(values_y[0]), _normalize_vector(vectors[:, 0]), None, band.band_source))
    if local or not extrema:
        return tuple(extrema)
    selector = max if assessment.parameter_type == "S" else min
    return (selector(extrema, key=lambda extremum: extremum.value),)
