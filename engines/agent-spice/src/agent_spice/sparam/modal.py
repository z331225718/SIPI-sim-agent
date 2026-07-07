from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations
import math
import warnings
from typing import Any, Iterable

import numpy as np
import skrf as rf
from skrf.network import z2s
from skrf.vectorFitting import VectorFitting


@dataclass(frozen=True)
class ModalZFitConfig:
    auto_preset: str | None = None
    mode_count: int = 8
    basis_anchor_ports: tuple[int, ...] = ()
    basis_frequency_indices: tuple[int, ...] | None = None
    basis_frequency_sample_count: int = 9
    basis_frequency_sampling: str = "linear"
    decomposition: str = "hermitian"
    scalar_fit_order: int = 12
    frequency_sample_count: int | None = None
    frequency_sample_head_count: int = 0
    pole_damping: float = 0.05
    peak_pole_frequency_head_count: int = 0
    peak_pole_entry_count: int = 0
    peak_pole_full_pair_count: int = 0
    peak_pole_complete_order: bool = False
    reduced_fit_method: str = "fixed"
    vector_n_poles_init_real: int = 1
    vector_n_poles_init_cmplx: int = 1
    vector_n_poles_add: int = 1
    vector_iters_start: int = 1
    vector_iters_inter: int = 1
    vector_iters_final: int = 2
    vector_target_error: float = 0.01
    shared_pole_trace_count: int = 3
    relative_weight_power: float = 1.0
    relative_weight_mode: str = "trace"
    relative_weight_iterations: int = 1
    relative_weight_update: str = "original"
    target_error_weight_power: float = 0.0
    target_error_weight_max: float = 8.0
    target_error_pair_count: int = 0
    residual_pair_count: int = 0
    residual_fit_order: int = 12
    residual_pole_damping: float | None = None
    residual_weight_power: float = 0.0
    residual_gain: float = 1.0
    residual_include_diagonal: bool = False
    residual_mirror_pairs: bool = False
    auto_order_candidates: tuple[int, ...] | None = None
    auto_basis_mode_counts: tuple[int, ...] | None = None
    auto_basis_sample_counts: tuple[int, ...] | None = None
    auto_basis_anchor_port_counts: tuple[int, ...] | None = None
    auto_basis_anchor_candidate_count: int | None = None
    auto_basis_anchor_combo_count: int = 1
    auto_pole_dampings: tuple[float, ...] | None = None
    auto_shared_pole_trace_counts: tuple[int, ...] | None = None
    auto_peak_pole_entry_counts: tuple[int, ...] | None = None
    auto_basis_diagonal_weight: float = 0.0
    auto_order_max_z_log_magnitude_rms_error: float | None = None
    auto_order_max_diagonal_z_log_magnitude_rms_error: float | None = None


@dataclass(frozen=True)
class ModalZAutoOrderTrial:
    scalar_fit_order: int
    z_log_magnitude_rms_error: float
    diagonal_z_log_magnitude_rms_error: float
    basis_projection_z_log_magnitude_rms_error: float
    worst_error_frequency_hz: float
    worst_error_port_pair: tuple[int, int]
    selected_pole_count: int
    selected_pole_frequencies_hz: tuple[float, ...]


@dataclass(frozen=True)
class ModalZAutoBasisTrial:
    mode_count: int
    basis_anchor_ports: tuple[int, ...]
    basis_frequency_sample_count: int
    scalar_fit_order: int
    pole_damping: float
    shared_pole_trace_count: int
    peak_pole_entry_count: int
    selection_score: float
    z_log_magnitude_rms_error: float
    diagonal_z_log_magnitude_rms_error: float
    basis_projection_z_log_magnitude_rms_error: float
    worst_error_frequency_hz: float
    worst_error_port_pair: tuple[int, int]
    selected_pole_count: int
    residual_correction_pair_count: int


@dataclass(frozen=True)
class ModalZFitResult:
    ports: int
    frequency_points: int
    mode_count: int
    basis_anchor_ports: tuple[int, ...]
    basis_frequency_sample_count: int
    scalar_fit_order: int
    pole_damping: float
    shared_pole_trace_count: int
    peak_pole_entry_count: int
    decomposition: str
    reduced_fit_method: str
    z_log_magnitude_rms_error: float
    basis_projection_z_log_magnitude_rms_error: float
    diagonal_z_log_magnitude_rms_error: float
    max_abs_z_error_ohm: float
    worst_error_frequency_hz: float
    worst_error_port_pair: tuple[int, int]
    frequencies_hz: np.ndarray
    original_z: np.ndarray
    basis: np.ndarray
    fitted_z: np.ndarray
    projected_z: np.ndarray
    original_s: np.ndarray | None = None
    fitted_s: np.ndarray | None = None
    s_rms_error: float | None = None
    selected_poles: np.ndarray | None = None
    residual_correction_pairs: tuple[tuple[int, int], ...] = ()
    auto_order_trials: tuple[ModalZAutoOrderTrial, ...] = ()
    auto_basis_trials: tuple[ModalZAutoBasisTrial, ...] = ()


def _as_z_array(z_samples: Any) -> np.ndarray:
    z = np.asarray(z_samples, dtype=complex)
    if z.ndim != 3 or z.shape[1] != z.shape[2]:
        raise ValueError("z_samples must have shape (frequency_points, nports, nports)")
    return z


def _sample_indices(length: int, max_points: int | None) -> np.ndarray:
    if max_points is None or length <= max_points:
        return np.arange(length)
    if max_points < 1:
        raise ValueError("frequency_sample_count must be >= 1")
    return np.unique(np.linspace(0, length - 1, max_points, dtype=int))


def _fit_sample_indices(length: int, max_points: int | None, head_count: int) -> np.ndarray:
    indices = _sample_indices(length, max_points)
    if head_count <= 0:
        return indices
    head = np.arange(min(length, head_count), dtype=int)
    return np.unique(np.concatenate([head, indices]))


def _basis_sample_indices(frequencies: np.ndarray, config: ModalZFitConfig) -> tuple[int, ...]:
    if config.basis_frequency_indices is not None:
        return config.basis_frequency_indices
    count = min(len(frequencies), config.basis_frequency_sample_count)
    if config.basis_frequency_sampling == "linear":
        indices = np.unique(np.linspace(0, len(frequencies) - 1, count, dtype=int))
    else:
        positive = np.flatnonzero(frequencies > 0.0)
        if len(positive) == 0:
            indices = np.unique(np.linspace(0, len(frequencies) - 1, count, dtype=int))
        else:
            interior_count = max(1, count - 2)
            log_freqs = np.geomspace(max(float(frequencies[positive[0]]), 1e-300), float(frequencies[-1]), interior_count)
            log_indices = np.searchsorted(frequencies, log_freqs)
            log_indices = np.clip(log_indices, 0, len(frequencies) - 1)
            indices = np.unique(np.concatenate(([0], log_indices, [len(frequencies) - 1])))
    return tuple(int(index) for index in indices)


def z_log_magnitude_rms_error(original_z: Any, fitted_z: Any, floor: float = 1e-300) -> float:
    original = np.asarray(original_z, dtype=complex)
    fitted = np.asarray(fitted_z, dtype=complex)
    if original.shape != fitted.shape:
        raise ValueError("original_z and fitted_z must have the same shape")
    original_mag = np.maximum(np.abs(original), floor)
    fitted_mag = np.maximum(np.abs(fitted), floor)
    delta = np.log10(fitted_mag / original_mag)
    finite_delta = delta[np.isfinite(delta)]
    if finite_delta.size == 0:
        return math.inf
    return float(math.sqrt(float(np.mean(np.square(finite_delta)))))


def s_rms_error(original_s: Any, fitted_s: Any) -> float:
    original = np.asarray(original_s, dtype=complex)
    fitted = np.asarray(fitted_s, dtype=complex)
    if original.shape != fitted.shape:
        raise ValueError("original_s and fitted_s must have the same shape")
    if original.ndim != 3 or original.shape[1] != original.shape[2]:
        raise ValueError("s parameters must have shape (frequency_points, nports, nports)")
    return float(math.sqrt(float(np.sum(np.mean(np.square(np.abs(original - fitted)), axis=0)))))


def _diagonal_z_log_magnitude_rms_error(original_z: np.ndarray, fitted_z: np.ndarray) -> float:
    return z_log_magnitude_rms_error(
        np.diagonal(original_z, axis1=1, axis2=2),
        np.diagonal(fitted_z, axis1=1, axis2=2),
    )


def _selection_score(z_log_error: float, diagonal_z_log_error: float, diagonal_weight: float) -> float:
    return float(z_log_error + diagonal_weight * diagonal_z_log_error)


def build_modal_basis(
    z_samples: Any,
    mode_count: int,
    decomposition: str = "hermitian",
    basis_indices: tuple[int, ...] | None = None,
    anchor_ports: tuple[int, ...] = (),
) -> np.ndarray:
    z = _as_z_array(z_samples)
    nports = z.shape[1]
    if mode_count < 1 or mode_count > nports:
        raise ValueError("mode_count must be between 1 and the number of ports")
    if decomposition not in {"svd", "hermitian"}:
        raise ValueError("decomposition must be 'svd' or 'hermitian'")
    unique_anchor_ports = tuple(dict.fromkeys(anchor_ports))
    if any(port < 1 or port > nports for port in unique_anchor_ports):
        raise ValueError("basis_anchor_ports must contain 1-based port numbers within the network")
    if len(unique_anchor_ports) > mode_count:
        raise ValueError("basis_anchor_ports cannot contain more ports than mode_count")
    if basis_indices is None:
        basis_positions = np.unique(np.linspace(0, len(z) - 1, min(len(z), 9), dtype=int))
    else:
        basis_positions = np.asarray(basis_indices, dtype=int)
        if np.any(basis_positions < 0) or np.any(basis_positions >= len(z)):
            raise ValueError("basis_frequency_indices contains an out-of-range index")

    candidates: list[np.ndarray] = []
    for idx in basis_positions:
        matrix = z[int(idx)]
        if decomposition == "svd":
            u, _, _ = np.linalg.svd(matrix, full_matrices=False)
            candidates.append(u[:, :mode_count])
        else:
            hermitian_proxy = 0.5 * (matrix + matrix.conj().T)
            values, vectors = np.linalg.eigh(hermitian_proxy)
            order = np.argsort(np.abs(values))[::-1]
            candidates.append(vectors[:, order[:mode_count]])

    candidate_matrix = np.hstack(candidates)
    if unique_anchor_ports:
        anchor_matrix = np.zeros((nports, len(unique_anchor_ports)), dtype=complex)
        for column, port in enumerate(unique_anchor_ports):
            anchor_matrix[port - 1, column] = 1.0
        anchor_basis = anchor_matrix
        remaining_count = mode_count - anchor_basis.shape[1]
        if remaining_count <= 0:
            return anchor_basis[:, :mode_count]
        residual_candidates = candidate_matrix - anchor_basis @ (anchor_basis.conj().T @ candidate_matrix)
        residual_basis, _, _ = np.linalg.svd(residual_candidates, full_matrices=False)
        residual_basis = residual_basis[:, :remaining_count]
        return np.hstack([anchor_basis, residual_basis])

    basis, _, _ = np.linalg.svd(candidate_matrix, full_matrices=False)
    return basis[:, :mode_count]


def project_z_to_basis(z_samples: Any, basis: np.ndarray) -> np.ndarray:
    z = _as_z_array(z_samples)
    q = np.asarray(basis, dtype=complex)
    if q.ndim != 2 or q.shape[0] != z.shape[1]:
        raise ValueError("basis must have shape (nports, mode_count)")
    return np.einsum("ai,fab,bj->fij", q.conj(), z, q, optimize=True)


def reconstruct_z_from_basis(reduced_z: Any, basis: np.ndarray) -> np.ndarray:
    reduced = np.asarray(reduced_z, dtype=complex)
    q = np.asarray(basis, dtype=complex)
    if reduced.ndim != 3 or reduced.shape[1] != reduced.shape[2] or reduced.shape[1] != q.shape[1]:
        raise ValueError("reduced_z must have shape (frequency_points, mode_count, mode_count)")
    return np.einsum("ai,fij,bj->fab", q, reduced, q.conj(), optimize=True)


def stable_poles(freqs: Any, scalar_fit_order: int, damping: float = 0.05) -> np.ndarray:
    if scalar_fit_order < 1:
        raise ValueError("scalar_fit_order must be >= 1")
    if damping <= 0.0:
        raise ValueError("pole_damping must be > 0")
    frequencies = np.asarray(freqs, dtype=float)
    positive = frequencies[frequencies > 0.0]
    if positive.size == 0:
        base = np.array([1.0])
    else:
        f_min = float(np.min(positive))
        f_max = float(np.max(positive))
        if math.isclose(f_min, f_max):
            base = np.array([f_min])
        else:
            pair_count = max(1, math.ceil(scalar_fit_order / 2))
            base = np.geomspace(f_min, f_max, pair_count)

    poles: list[complex] = []
    for frequency in base:
        omega = 2.0 * math.pi * float(frequency)
        poles.append(complex(-damping * omega, omega))
        if len(poles) < scalar_fit_order:
            poles.append(complex(-damping * omega, -omega))
        if len(poles) >= scalar_fit_order:
            break
    while len(poles) < scalar_fit_order:
        omega = 2.0 * math.pi * float(base[-1])
        poles.append(complex(-damping * omega * (len(poles) + 1), 0.0))
    return np.asarray(poles[:scalar_fit_order], dtype=complex)


def pole_frequencies_hz(poles: Any) -> tuple[float, ...]:
    if poles is None:
        return ()
    poles_array = np.asarray(poles, dtype=complex)
    if poles_array.size == 0:
        return ()
    frequencies: list[float] = []
    for pole in poles_array.reshape(-1):
        if abs(pole.imag) > 0.0:
            frequency = abs(float(pole.imag)) / (2.0 * math.pi)
        else:
            frequency = abs(float(pole.real)) / (2.0 * math.pi)
        if not math.isfinite(frequency):
            continue
        if any(abs(frequency - existing) <= 1e-9 * max(1.0, abs(existing)) for existing in frequencies):
            continue
        frequencies.append(frequency)
    return tuple(sorted(frequencies))


def _design_matrix(freqs: np.ndarray, poles: np.ndarray) -> np.ndarray:
    s = 2j * math.pi * freqs
    rational_columns = 1.0 / (s[:, None] - poles[None, :])
    return np.hstack([rational_columns, np.ones((len(freqs), 1), dtype=complex)])


def fit_response_with_poles(
    freqs: Any,
    values: Any,
    poles: Any,
    fit_indices: np.ndarray | None = None,
    relative_weight: bool = False,
    relative_weight_power: float = 1.0,
    fit_weights: np.ndarray | None = None,
) -> np.ndarray:
    frequencies = np.asarray(freqs, dtype=float)
    response = np.asarray(values, dtype=complex)
    if response.shape != frequencies.shape:
        raise ValueError("values must have the same shape as freqs")
    poles_array = np.asarray(poles, dtype=complex)
    if poles_array.ndim != 1 or len(poles_array) == 0:
        raise ValueError("poles must be a non-empty 1D array")
    selected = np.arange(len(frequencies)) if fit_indices is None else np.asarray(fit_indices, dtype=int)
    if len(selected) == 0:
        raise ValueError("fit_indices must select at least one frequency")
    a_fit = _design_matrix(frequencies[selected], poles_array)
    rhs = response[selected]
    if fit_weights is not None:
        weights = np.asarray(fit_weights, dtype=float)
        if weights.shape != rhs.shape:
            raise ValueError("fit_weights must have the same shape as selected values")
        a_fit = a_fit * weights[:, None]
        rhs = rhs * weights
    elif relative_weight:
        if relative_weight_power < 0.0:
            raise ValueError("relative_weight_power must be >= 0")
        magnitude = np.abs(rhs)
        positive = magnitude[magnitude > 0.0]
        floor = 1e-300 if positive.size == 0 else max(float(np.percentile(positive, 5)) * 1e-3, 1e-300)
        weights = 1.0 / np.power(np.maximum(magnitude, floor), relative_weight_power)
        a_fit = a_fit * weights[:, None]
        rhs = rhs * weights
    column_norms = np.linalg.norm(a_fit, axis=0)
    column_norms[column_norms == 0.0] = 1.0
    scaled_a = a_fit / column_norms
    coeffs, *_ = np.linalg.lstsq(scaled_a, rhs, rcond=None)
    coeffs = coeffs / column_norms
    return _design_matrix(frequencies, poles_array) @ coeffs


def fit_fixed_pole_response(
    freqs: Any,
    values: Any,
    scalar_fit_order: int,
    damping: float = 0.05,
    fit_indices: np.ndarray | None = None,
) -> np.ndarray:
    frequencies = np.asarray(freqs, dtype=float)
    poles = stable_poles(frequencies, scalar_fit_order, damping)
    return fit_response_with_poles(frequencies, values, poles, fit_indices=fit_indices)


def _fit_reduced_z_with_fixed_poles(
    frequencies: np.ndarray,
    reduced: np.ndarray,
    config: ModalZFitConfig,
    fit_indices: np.ndarray,
) -> np.ndarray:
    fitted_reduced = np.empty_like(reduced)
    for row in range(config.mode_count):
        for column in range(config.mode_count):
            fitted_reduced[:, row, column] = fit_fixed_pole_response(
                frequencies,
                reduced[:, row, column],
                scalar_fit_order=config.scalar_fit_order,
                damping=config.pole_damping,
                fit_indices=fit_indices,
            )
    return fitted_reduced


def _full_projected_reduced_weights(
    original_z: np.ndarray,
    basis: np.ndarray,
    fit_indices: np.ndarray,
    power: float,
    reference_z: np.ndarray | None = None,
    update: str = "original",
    target_error_weight_power: float = 0.0,
    target_error_weight_max: float = 8.0,
    target_error_pair_count: int = 0,
) -> np.ndarray:
    magnitude = np.abs(original_z[fit_indices])
    positive_magnitude = np.where(magnitude > 0.0, magnitude, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        global_floor = float(np.nanpercentile(positive_magnitude, 5))
        floors = np.nanpercentile(positive_magnitude, 5, axis=0)
    if not math.isfinite(global_floor) or global_floor <= 0.0:
        global_floor = 1.0
    floors = np.nan_to_num(floors, nan=global_floor, posinf=global_floor, neginf=global_floor)
    floors = np.maximum(floors * 1e-3, 1e-300)
    original_scale = np.maximum(magnitude, floors[None, :, :])
    if reference_z is None or update == "original":
        denominator = original_scale
    else:
        fitted_scale = np.maximum(np.abs(reference_z[fit_indices]), floors[None, :, :])
        if update == "max":
            denominator = np.maximum(original_scale, fitted_scale)
        else:
            denominator = np.sqrt(original_scale * fitted_scale)
    full_weights = 1.0 / np.power(denominator, power)
    if reference_z is not None and target_error_weight_power > 0.0:
        full_weights = full_weights * _target_error_weight_multiplier(
            original_z,
            reference_z,
            fit_indices,
            power=target_error_weight_power,
            max_weight=target_error_weight_max,
            pair_count=target_error_pair_count,
        )
    basis_energy = np.square(np.abs(basis))
    reduced_weight_squared = np.einsum(
        "fab,ai,bj->fij",
        np.square(full_weights),
        basis_energy,
        basis_energy,
        optimize=True,
    )
    return np.sqrt(np.maximum(reduced_weight_squared, 1e-300))


def _target_error_weight_multiplier(
    original_z: np.ndarray,
    reference_z: np.ndarray,
    fit_indices: np.ndarray,
    power: float,
    max_weight: float,
    pair_count: int,
) -> np.ndarray:
    original_mag = np.maximum(np.abs(original_z[fit_indices]), 1e-300)
    reference_mag = np.maximum(np.abs(reference_z[fit_indices]), 1e-300)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_error = np.abs(np.log10(reference_mag / original_mag))
    log_error = np.nan_to_num(log_error, nan=0.0, posinf=max_weight, neginf=0.0)
    multiplier = np.ones_like(log_error, dtype=float)
    if pair_count > 0:
        pair_scores = np.sqrt(np.mean(np.square(log_error), axis=0))
        flat_scores = pair_scores.reshape(-1)
        selected_count = min(pair_count, flat_scores.size)
        selected_flat = np.argsort(flat_scores)[::-1][:selected_count]
        mask = np.zeros(flat_scores.size, dtype=bool)
        mask[selected_flat] = True
        mask_2d = mask.reshape(pair_scores.shape)
        selected_error = log_error[:, mask_2d]
        multiplier[:, mask_2d] = np.minimum(max_weight, np.power(1.0 + selected_error, power))
        return multiplier
    return np.minimum(max_weight, np.power(1.0 + log_error, power))


def _reduced_fit_weights(
    original_z: np.ndarray,
    basis: np.ndarray,
    config: ModalZFitConfig,
    fit_indices: np.ndarray,
    reference_z: np.ndarray | None = None,
) -> np.ndarray | None:
    if config.relative_weight_mode == "trace":
        return None
    return _full_projected_reduced_weights(
        original_z,
        basis,
        fit_indices,
        config.relative_weight_power,
        reference_z=reference_z,
        update=config.relative_weight_update,
        target_error_weight_power=config.target_error_weight_power,
        target_error_weight_max=config.target_error_weight_max,
        target_error_pair_count=config.target_error_pair_count,
    )


def _fit_reduced_z_with_vector_fitting(
    frequencies: np.ndarray,
    reduced: np.ndarray,
    config: ModalZFitConfig,
    fit_indices: np.ndarray,
) -> np.ndarray:
    fit_freqs = frequencies[fit_indices]
    fit_reduced = reduced[fit_indices, :, :]
    network = rf.Network(
        frequency=rf.Frequency.from_f(fit_freqs, unit="hz"),
        z=fit_reduced,
        z0=50,
        name="modal_z_reduced",
    )
    vector_fit = VectorFitting(network)
    vector_fit.auto_fit(
        n_poles_init_real=config.vector_n_poles_init_real,
        n_poles_init_cmplx=config.vector_n_poles_init_cmplx,
        n_poles_add=config.vector_n_poles_add,
        model_order_max=config.scalar_fit_order,
        iters_start=config.vector_iters_start,
        iters_inter=config.vector_iters_inter,
        iters_final=config.vector_iters_final,
        target_error=config.vector_target_error,
        parameter_type="z",
    )
    fitted_reduced = np.empty_like(reduced)
    for row in range(config.mode_count):
        for column in range(config.mode_count):
            fitted_reduced[:, row, column] = vector_fit.get_model_response(row, column, freqs=frequencies)
    return fitted_reduced


def _append_stable_pole_pair(poles: list[complex], pole: complex, max_count: int) -> None:
    if len(poles) >= max_count:
        return
    stable_real = pole.real if pole.real < 0.0 else -max(abs(pole.real), 1.0)
    stable_pole = complex(stable_real, pole.imag)
    poles.append(stable_pole)
    if abs(stable_pole.imag) > 0.0 and len(poles) < max_count:
        poles.append(stable_pole.conjugate())


def _dedupe_poles(poles: list[complex], max_count: int) -> np.ndarray:
    unique: list[complex] = []
    for pole in poles:
        if not np.isfinite(pole.real) or not np.isfinite(pole.imag):
            continue
        if any(abs(pole - existing) <= 1e-6 * max(1.0, abs(existing)) for existing in unique):
            continue
        unique.append(pole)
        if len(unique) >= max_count:
            break
    return np.asarray(unique, dtype=complex)


def _complete_with_stable_poles(
    poles: list[complex],
    frequencies: np.ndarray,
    config: ModalZFitConfig,
) -> np.ndarray:
    return _complete_poles_to_order(poles, frequencies, config.scalar_fit_order, config.pole_damping)


def _complete_poles_to_order(
    poles: list[complex],
    frequencies: np.ndarray,
    pole_count: int,
    damping: float,
) -> np.ndarray:
    unique_poles = list(_dedupe_poles(poles, pole_count))
    for frequency in pole_frequencies_hz(stable_poles(frequencies, pole_count, damping)):
        if len(unique_poles) >= pole_count:
            break
        omega = 2.0 * math.pi * frequency
        _append_stable_pole_pair(unique_poles, complex(-damping * omega, omega), pole_count)
        unique_poles = list(_dedupe_poles(unique_poles, pole_count))
    return _dedupe_poles(unique_poles, pole_count)


def _fit_scalar_surrogate_poles(
    frequencies: np.ndarray,
    response: np.ndarray,
    config: ModalZFitConfig,
    fit_indices: np.ndarray,
) -> np.ndarray:
    network = rf.Network(
        frequency=rf.Frequency.from_f(frequencies[fit_indices], unit="hz"),
        z=response[fit_indices].reshape(-1, 1, 1),
        z0=50,
        name="modal_z_shared_pole_surrogate",
    )
    vector_fit = VectorFitting(network)
    vector_fit.auto_fit(
        n_poles_init_real=config.vector_n_poles_init_real,
        n_poles_init_cmplx=config.vector_n_poles_init_cmplx,
        n_poles_add=config.vector_n_poles_add,
        model_order_max=config.scalar_fit_order,
        iters_start=config.vector_iters_start,
        iters_inter=config.vector_iters_inter,
        iters_final=config.vector_iters_final,
        target_error=config.vector_target_error,
        parameter_type="z",
    )
    return np.asarray(vector_fit.poles, dtype=complex)


def _identify_shared_poles(
    frequencies: np.ndarray,
    reduced: np.ndarray,
    config: ModalZFitConfig,
    fit_indices: np.ndarray,
) -> np.ndarray:
    expanded_poles: list[complex] = []
    for response in _candidate_pole_responses(reduced, config):
        surrogate_poles = _fit_scalar_surrogate_poles(frequencies, response, config, fit_indices)
        for pole in surrogate_poles:
            _append_stable_pole_pair(expanded_poles, complex(pole), config.scalar_fit_order)
    shared = _dedupe_poles(expanded_poles, config.scalar_fit_order)
    if config.peak_pole_complete_order and len(shared) < config.scalar_fit_order:
        shared = _complete_with_stable_poles(list(shared), frequencies, config)
    elif len(shared) == 0:
        shared = stable_poles(frequencies, config.scalar_fit_order, config.pole_damping)
    return shared


def _fit_reduced_z_with_shared_poles(
    frequencies: np.ndarray,
    original_z: np.ndarray,
    basis: np.ndarray,
    reduced: np.ndarray,
    config: ModalZFitConfig,
    fit_indices: np.ndarray,
) -> np.ndarray:
    shared_poles = _identify_shared_poles(frequencies, reduced, config, fit_indices)
    return _fit_reduced_z_entries_with_poles(frequencies, original_z, basis, reduced, shared_poles, config, fit_indices)


def _select_full_pair_pole_candidates(
    original_z: np.ndarray,
    projected_z: np.ndarray,
    pair_count: int,
) -> tuple[tuple[int, int], ...]:
    if pair_count <= 0:
        return ()
    pair_scores = _pair_log_rms(original_z, projected_z)
    ranked_pairs: list[tuple[float, int, int]] = []
    for row in range(pair_scores.shape[0]):
        for column in range(pair_scores.shape[1]):
            score = float(pair_scores[row, column])
            if math.isfinite(score):
                ranked_pairs.append((score, row, column))
    selected: list[tuple[int, int]] = []
    for _, row, column in sorted(ranked_pairs, reverse=True):
        selected.append((row, column))
        if len(selected) >= pair_count:
            break
    return tuple(selected)


def _full_pair_response_from_reduced(reduced: np.ndarray, basis: np.ndarray, row: int, column: int) -> np.ndarray:
    return np.einsum("i,fij,j->f", basis[row, :], reduced, basis[column, :].conj(), optimize=True)


def _candidate_pole_responses(
    reduced: np.ndarray,
    config: ModalZFitConfig,
    basis: np.ndarray | None = None,
    original_z: np.ndarray | None = None,
) -> list[np.ndarray]:
    candidates: list[np.ndarray] = [np.trace(reduced, axis1=1, axis2=2) / reduced.shape[1]]
    seen_entries: set[tuple[int, int]] = set()
    for mode in range(min(config.shared_pole_trace_count, config.mode_count)):
        candidates.append(reduced[:, mode, mode])
        seen_entries.add((mode, mode))
    if config.peak_pole_full_pair_count > 0 and basis is not None and original_z is not None:
        projected_z = reconstruct_z_from_basis(reduced, basis)
        for row, column in _select_full_pair_pole_candidates(
            original_z,
            projected_z,
            config.peak_pole_full_pair_count,
        ):
            candidates.append(_full_pair_response_from_reduced(reduced, basis, row, column))
    if config.peak_pole_entry_count > 0:
        entry_energy = np.sqrt(np.mean(np.square(np.abs(reduced)), axis=0))
        ranked_entries: list[tuple[float, int, int]] = []
        for row in range(config.mode_count):
            for column in range(config.mode_count):
                ranked_entries.append((float(entry_energy[row, column]), row, column))
        added_entries = 0
        for _, row, column in sorted(ranked_entries, reverse=True):
            if (row, column) in seen_entries:
                continue
            candidates.append(reduced[:, row, column])
            seen_entries.add((row, column))
            added_entries += 1
            if added_entries >= config.peak_pole_entry_count:
                break
    return candidates


def _append_peak_frequency(chosen: list[float], frequency: float, max_count: int) -> None:
    if len(chosen) >= max_count or not math.isfinite(frequency) or frequency <= 0.0:
        return
    if any(abs(math.log(frequency / existing)) < 0.03 for existing in chosen):
        return
    chosen.append(frequency)


def _select_peak_frequencies(
    frequencies: np.ndarray,
    reduced: np.ndarray,
    config: ModalZFitConfig,
    fit_indices: np.ndarray,
    basis: np.ndarray | None = None,
    original_z: np.ndarray | None = None,
) -> list[float]:
    pair_budget = max(1, math.ceil(config.scalar_fit_order / 4))
    selected = np.asarray(fit_indices, dtype=int)
    selected = selected[frequencies[selected] > 0.0]
    if len(selected) == 0:
        return []

    chosen: list[float] = []
    for index in selected[: config.peak_pole_frequency_head_count]:
        _append_peak_frequency(chosen, float(frequencies[index]), pair_budget)

    scored: list[tuple[float, float]] = []
    for response in _candidate_pole_responses(reduced, config, basis=basis, original_z=original_z):
        magnitude = np.maximum(np.abs(response[selected]), 1e-300)
        log_magnitude = np.log10(magnitude)
        local_positions: list[int] = []
        if len(log_magnitude) >= 3:
            center = log_magnitude[1:-1]
            left = log_magnitude[:-2]
            right = log_magnitude[2:]
            local_positions.extend((np.flatnonzero((center >= left) & (center >= right)) + 1).tolist())
        local_positions.append(int(np.argmax(log_magnitude)))
        for position in local_positions:
            frequency = float(frequencies[selected[position]])
            score = float(log_magnitude[position])
            scored.append((score, frequency))

    for _, frequency in sorted(scored, key=lambda item: item[0], reverse=True):
        _append_peak_frequency(chosen, frequency, pair_budget)
        if len(chosen) >= pair_budget:
            break
    return sorted(chosen)


def _identify_peak_poles(
    frequencies: np.ndarray,
    reduced: np.ndarray,
    config: ModalZFitConfig,
    fit_indices: np.ndarray,
    basis: np.ndarray | None = None,
    original_z: np.ndarray | None = None,
) -> np.ndarray:
    poles: list[complex] = []
    for frequency in _select_peak_frequencies(
        frequencies,
        reduced,
        config,
        fit_indices,
        basis=basis,
        original_z=original_z,
    ):
        omega = 2.0 * math.pi * frequency
        _append_stable_pole_pair(poles, complex(-config.pole_damping * omega, omega), config.scalar_fit_order)
    if config.peak_pole_complete_order:
        return _complete_with_stable_poles(poles, frequencies, config)
    for pole in stable_poles(frequencies, config.scalar_fit_order, config.pole_damping):
        _append_stable_pole_pair(poles, complex(pole), config.scalar_fit_order)
        if len(poles) >= config.scalar_fit_order:
            break
    return _dedupe_poles(poles, config.scalar_fit_order)


def _fit_reduced_z_with_peak_poles(
    frequencies: np.ndarray,
    original_z: np.ndarray,
    basis: np.ndarray,
    reduced: np.ndarray,
    config: ModalZFitConfig,
    fit_indices: np.ndarray,
) -> np.ndarray:
    peak_poles = _identify_peak_poles(frequencies, reduced, config, fit_indices)
    return _fit_reduced_z_entries_with_poles(frequencies, original_z, basis, reduced, peak_poles, config, fit_indices)


def _fit_reduced_z_entries_with_poles(
    frequencies: np.ndarray,
    original_z: np.ndarray,
    basis: np.ndarray,
    reduced: np.ndarray,
    poles: np.ndarray,
    config: ModalZFitConfig,
    fit_indices: np.ndarray,
) -> np.ndarray:
    reference_z: np.ndarray | None = None
    fitted_reduced = np.empty_like(reduced)
    iteration_count = config.relative_weight_iterations if config.relative_weight_mode == "full-projected" else 1
    for _ in range(iteration_count):
        fit_weights = _reduced_fit_weights(original_z, basis, config, fit_indices, reference_z=reference_z)
        for row in range(config.mode_count):
            for column in range(config.mode_count):
                entry_weights = None if fit_weights is None else fit_weights[:, row, column]
                fitted_reduced[:, row, column] = fit_response_with_poles(
                    frequencies,
                    reduced[:, row, column],
                    poles,
                    fit_indices=fit_indices,
                    relative_weight=fit_weights is None,
                    relative_weight_power=config.relative_weight_power,
                    fit_weights=entry_weights,
                )
        reference_z = reconstruct_z_from_basis(fitted_reduced, basis)
    return fitted_reduced


def _worst_error(original_z: np.ndarray, fitted_z: np.ndarray, freqs: np.ndarray) -> tuple[float, tuple[int, int]]:
    original_mag = np.maximum(np.abs(original_z), 1e-300)
    fitted_mag = np.maximum(np.abs(fitted_z), 1e-300)
    abs_log_error = np.abs(np.log10(fitted_mag / original_mag))
    flat_index = int(np.nanargmax(abs_log_error))
    freq_index, row, column = np.unravel_index(flat_index, abs_log_error.shape)
    return float(freqs[freq_index]), (int(row + 1), int(column + 1))


def _pair_log_rms(original_z: np.ndarray, fitted_z: np.ndarray) -> np.ndarray:
    original_mag = np.maximum(np.abs(original_z), 1e-300)
    fitted_mag = np.maximum(np.abs(fitted_z), 1e-300)
    delta = np.log10(fitted_mag / original_mag)
    return np.sqrt(np.nanmean(np.square(delta), axis=0))


def _select_anchor_ports_from_projection(
    original_z: np.ndarray,
    projected_z: np.ndarray,
    count: int,
    max_candidate_ports: int | None = None,
) -> tuple[int, ...]:
    if count <= 0:
        return ()
    pair_scores = _pair_log_rms(original_z, projected_z)
    port_scores = np.zeros(pair_scores.shape[0], dtype=float)
    for port in range(pair_scores.shape[0]):
        related = np.concatenate([pair_scores[port, :], pair_scores[:, port]])
        finite = related[np.isfinite(related)]
        port_scores[port] = 0.0 if finite.size == 0 else float(np.sqrt(np.mean(np.square(finite))))
    ranked_ports = np.argsort(port_scores)[::-1]
    limit = count if max_candidate_ports is None else min(pair_scores.shape[0], max(count, max_candidate_ports))
    candidates = [int(port + 1) for port in ranked_ports[:limit]]

    ranked_pairs: list[tuple[float, int, int]] = []
    for row in range(pair_scores.shape[0]):
        for column in range(pair_scores.shape[1]):
            score = float(pair_scores[row, column])
            if math.isfinite(score):
                ranked_pairs.append((score, row + 1, column + 1))
    for _, row, column in sorted(ranked_pairs, reverse=True):
        if row not in candidates:
            candidates.append(row)
        if column not in candidates:
            candidates.append(column)
        if len(candidates) >= limit:
            break
    return tuple(candidates[:limit])


def _select_anchor_port_sets_by_projection_search(
    frequencies: np.ndarray,
    z: np.ndarray,
    cfg: ModalZFitConfig,
    mode_count: int,
    basis_sample_count: int,
    anchor_count: int,
    unanchored_projected: np.ndarray,
    diagonal_weight: float = 0.0,
    candidate_count: int | None = None,
    combo_count: int = 1,
) -> tuple[tuple[int, ...], ...]:
    if anchor_count <= 0:
        return ((),)
    candidate_ports = _select_anchor_ports_from_projection(
        z,
        unanchored_projected,
        anchor_count,
        max_candidate_ports=candidate_count if candidate_count is not None else max(6, anchor_count + 4),
    )
    if len(candidate_ports) <= anchor_count:
        return (tuple(candidate_ports[:anchor_count]),)

    trial_cfg = replace(
        cfg,
        mode_count=mode_count,
        basis_frequency_sample_count=basis_sample_count,
        auto_order_candidates=None,
        auto_basis_mode_counts=None,
        auto_basis_sample_counts=None,
        auto_basis_anchor_port_counts=None,
    )
    basis_indices = _basis_sample_indices(frequencies, trial_cfg)
    scored_ports: list[tuple[float, tuple[int, ...]]] = []
    for ports in combinations(candidate_ports, anchor_count):
        basis = build_modal_basis(
            z,
            mode_count=mode_count,
            decomposition=cfg.decomposition,
            basis_indices=basis_indices,
            anchor_ports=tuple(int(port) for port in ports),
        )
        reduced = project_z_to_basis(z, basis)
        projected = reconstruct_z_from_basis(reduced, basis)
        projection_error = z_log_magnitude_rms_error(z, projected)
        diagonal_projection_error = _diagonal_z_log_magnitude_rms_error(z, projected)
        projection_score = _selection_score(projection_error, diagonal_projection_error, diagonal_weight)
        scored_ports.append((projection_score, tuple(int(port) for port in ports)))
    if not scored_ports:
        return (tuple(candidate_ports[:anchor_count]),)
    selected: list[tuple[int, ...]] = []
    for _, ports in sorted(scored_ports, key=lambda item: item[0]):
        if ports in selected:
            continue
        selected.append(ports)
        if len(selected) >= combo_count:
            break
    return tuple(selected)


def _merge_anchor_port_sets(*port_sets: Iterable[tuple[int, ...]]) -> tuple[tuple[int, ...], ...]:
    merged: list[tuple[int, ...]] = []
    for port_set_group in port_sets:
        for ports in port_set_group:
            normalized = tuple(int(port) for port in ports)
            if normalized in merged:
                continue
            merged.append(normalized)
    return tuple(merged)


def _select_anchor_ports_by_projection_search(
    frequencies: np.ndarray,
    z: np.ndarray,
    cfg: ModalZFitConfig,
    mode_count: int,
    basis_sample_count: int,
    anchor_count: int,
    unanchored_projected: np.ndarray,
    diagonal_weight: float = 0.0,
    candidate_count: int | None = None,
) -> tuple[int, ...]:
    return _select_anchor_port_sets_by_projection_search(
        frequencies,
        z,
        cfg,
        mode_count,
        basis_sample_count,
        anchor_count,
        unanchored_projected,
        diagonal_weight=diagonal_weight,
        candidate_count=candidate_count,
        combo_count=1,
    )[0]


def _select_residual_pairs(
    original_z: np.ndarray,
    fitted_z: np.ndarray,
    pair_count: int,
    include_diagonal: bool,
) -> tuple[tuple[int, int], ...]:
    if pair_count <= 0:
        return ()
    pair_scores = _pair_log_rms(original_z, fitted_z)
    ranked_pairs: list[tuple[float, int, int]] = []
    for row in range(pair_scores.shape[0]):
        for column in range(pair_scores.shape[1]):
            if row == column and not include_diagonal:
                continue
            ranked_pairs.append((float(pair_scores[row, column]), row, column))
    selected: list[tuple[int, int]] = []
    for score, row, column in sorted(ranked_pairs, reverse=True):
        if not math.isfinite(score):
            continue
        selected.append((row, column))
        if len(selected) >= pair_count:
            break
    return tuple(selected)


def _reference_magnitude_weights(reference: np.ndarray, fit_indices: np.ndarray, power: float) -> np.ndarray | None:
    if power <= 0.0:
        return None
    magnitude = np.abs(reference[fit_indices])
    positive = magnitude[magnitude > 0.0]
    floor = 1.0 if positive.size == 0 else max(float(np.percentile(positive, 5)) * 1e-3, 1e-300)
    return 1.0 / np.power(np.maximum(magnitude, floor), power)


def _identify_response_peak_poles(
    frequencies: np.ndarray,
    response: np.ndarray,
    pole_count: int,
    damping: float,
    fit_indices: np.ndarray,
) -> np.ndarray:
    selected = np.asarray(fit_indices, dtype=int)
    selected = selected[frequencies[selected] > 0.0]
    poles: list[complex] = []
    if len(selected) > 0:
        pair_budget = max(1, math.ceil(pole_count / 4))
        magnitude = np.maximum(np.abs(response[selected]), 1e-300)
        log_magnitude = np.log10(magnitude)
        scored: list[tuple[float, float]] = []
        if len(log_magnitude) >= 3:
            center = log_magnitude[1:-1]
            left = log_magnitude[:-2]
            right = log_magnitude[2:]
            for position in (np.flatnonzero((center >= left) & (center >= right)) + 1).tolist():
                scored.append((float(log_magnitude[position]), float(frequencies[selected[position]])))
        peak_position = int(np.argmax(log_magnitude))
        scored.append((float(log_magnitude[peak_position]), float(frequencies[selected[peak_position]])))
        chosen: list[float] = []
        for _, frequency in sorted(scored, key=lambda item: item[0], reverse=True):
            _append_peak_frequency(chosen, frequency, pair_budget)
            if len(chosen) >= pair_budget:
                break
        for frequency in chosen:
            omega = 2.0 * math.pi * frequency
            _append_stable_pole_pair(poles, complex(-damping * omega, omega), pole_count)
    return _complete_poles_to_order(poles, frequencies, pole_count, damping)


def _apply_residual_pair_correction(
    frequencies: np.ndarray,
    original_z: np.ndarray,
    fitted_z: np.ndarray,
    cfg: ModalZFitConfig,
    fit_indices: np.ndarray,
) -> tuple[np.ndarray, tuple[tuple[int, int], ...]]:
    selected_pairs = _select_residual_pairs(
        original_z,
        fitted_z,
        cfg.residual_pair_count,
        include_diagonal=cfg.residual_include_diagonal,
    )
    if not selected_pairs:
        return fitted_z, ()
    corrected = np.array(fitted_z, copy=True)
    corrected_pairs: list[tuple[int, int]] = []
    damping = cfg.pole_damping if cfg.residual_pole_damping is None else cfg.residual_pole_damping
    for row, column in selected_pairs:
        residual = original_z[:, row, column] - corrected[:, row, column]
        poles = _identify_response_peak_poles(
            frequencies,
            residual,
            cfg.residual_fit_order,
            damping,
            fit_indices,
        )
        weights = _reference_magnitude_weights(original_z[:, row, column], fit_indices, cfg.residual_weight_power)
        correction = fit_response_with_poles(
            frequencies,
            residual,
            poles,
            fit_indices=fit_indices,
            fit_weights=weights,
        )
        corrected[:, row, column] = corrected[:, row, column] + cfg.residual_gain * correction
        corrected_pairs.append((row + 1, column + 1))
        if cfg.residual_mirror_pairs and row != column and (column, row) not in selected_pairs:
            corrected[:, column, row] = corrected[:, column, row] + cfg.residual_gain * correction
            corrected_pairs.append((column + 1, row + 1))
    return corrected, tuple(corrected_pairs)


def _validate_modal_z_fit_config(cfg: ModalZFitConfig) -> None:
    if cfg.scalar_fit_order < 1:
        raise ValueError("scalar_fit_order must be >= 1")
    if any(port < 1 for port in cfg.basis_anchor_ports):
        raise ValueError("basis_anchor_ports must contain 1-based port numbers >= 1")
    if len(set(cfg.basis_anchor_ports)) != len(cfg.basis_anchor_ports):
        raise ValueError("basis_anchor_ports must not contain duplicates")
    if len(cfg.basis_anchor_ports) > cfg.mode_count:
        raise ValueError("basis_anchor_ports cannot contain more ports than mode_count")
    if cfg.reduced_fit_method not in {"fixed", "vector", "shared-poles", "peak-poles"}:
        raise ValueError("reduced_fit_method must be 'fixed', 'vector', 'shared-poles', or 'peak-poles'")
    if cfg.reduced_fit_method in {"vector", "shared-poles"}:
        if cfg.vector_n_poles_init_real < 0 or cfg.vector_n_poles_init_cmplx < 0:
            raise ValueError("vector initial pole counts must be >= 0")
        if cfg.vector_n_poles_init_real + cfg.vector_n_poles_init_cmplx < 1:
            raise ValueError("vector fitting needs at least one initial pole")
        if cfg.vector_n_poles_add < 1:
            raise ValueError("vector_n_poles_add must be >= 1")
        if cfg.vector_iters_start < 1 or cfg.vector_iters_inter < 1 or cfg.vector_iters_final < 1:
            raise ValueError("vector iteration counts must be >= 1")
        if cfg.vector_target_error <= 0.0:
            raise ValueError("vector_target_error must be > 0")
    if cfg.shared_pole_trace_count < 1:
        raise ValueError("shared_pole_trace_count must be >= 1")
    if cfg.relative_weight_power < 0.0:
        raise ValueError("relative_weight_power must be >= 0")
    if cfg.relative_weight_mode not in {"trace", "full-projected"}:
        raise ValueError("relative_weight_mode must be 'trace' or 'full-projected'")
    if cfg.relative_weight_iterations < 1:
        raise ValueError("relative_weight_iterations must be >= 1")
    if cfg.relative_weight_update not in {"original", "max", "geometric"}:
        raise ValueError("relative_weight_update must be 'original', 'max', or 'geometric'")
    if cfg.target_error_weight_power < 0.0:
        raise ValueError("target_error_weight_power must be >= 0")
    if cfg.target_error_weight_max < 1.0:
        raise ValueError("target_error_weight_max must be >= 1")
    if cfg.target_error_pair_count < 0:
        raise ValueError("target_error_pair_count must be >= 0")
    if cfg.residual_pair_count < 0:
        raise ValueError("residual_pair_count must be >= 0")
    if cfg.residual_fit_order < 1:
        raise ValueError("residual_fit_order must be >= 1")
    if cfg.residual_pole_damping is not None and cfg.residual_pole_damping <= 0.0:
        raise ValueError("residual_pole_damping must be > 0")
    if cfg.residual_weight_power < 0.0:
        raise ValueError("residual_weight_power must be >= 0")
    if cfg.residual_gain < 0.0:
        raise ValueError("residual_gain must be >= 0")
    if cfg.basis_frequency_sample_count < 1:
        raise ValueError("basis_frequency_sample_count must be >= 1")
    if cfg.basis_frequency_sampling not in {"linear", "log"}:
        raise ValueError("basis_frequency_sampling must be 'linear' or 'log'")
    if cfg.frequency_sample_head_count < 0:
        raise ValueError("frequency_sample_head_count must be >= 0")
    if cfg.peak_pole_frequency_head_count < 0:
        raise ValueError("peak_pole_frequency_head_count must be >= 0")
    if cfg.peak_pole_entry_count < 0:
        raise ValueError("peak_pole_entry_count must be >= 0")
    if cfg.peak_pole_full_pair_count < 0:
        raise ValueError("peak_pole_full_pair_count must be >= 0")
    if cfg.peak_pole_frequency_head_count < 0:
        raise ValueError("peak_pole_frequency_head_count must be >= 0")
    if cfg.peak_pole_entry_count < 0:
        raise ValueError("peak_pole_entry_count must be >= 0")
    if cfg.auto_order_candidates is not None:
        if len(cfg.auto_order_candidates) == 0:
            raise ValueError("auto_order_candidates must not be empty")
        if any(order < 1 for order in cfg.auto_order_candidates):
            raise ValueError("auto_order_candidates must contain orders >= 1")
    if cfg.auto_basis_mode_counts is not None:
        if len(cfg.auto_basis_mode_counts) == 0:
            raise ValueError("auto_basis_mode_counts must not be empty")
        if any(mode < 1 for mode in cfg.auto_basis_mode_counts):
            raise ValueError("auto_basis_mode_counts must contain values >= 1")
    if cfg.auto_basis_sample_counts is not None:
        if len(cfg.auto_basis_sample_counts) == 0:
            raise ValueError("auto_basis_sample_counts must not be empty")
        if any(count < 1 for count in cfg.auto_basis_sample_counts):
            raise ValueError("auto_basis_sample_counts must contain values >= 1")
        if cfg.basis_frequency_indices is not None:
            raise ValueError("auto_basis_sample_counts cannot be used with explicit basis_frequency_indices")
    if cfg.auto_basis_anchor_port_counts is not None:
        if len(cfg.auto_basis_anchor_port_counts) == 0:
            raise ValueError("auto_basis_anchor_port_counts must not be empty")
        if any(count < 0 for count in cfg.auto_basis_anchor_port_counts):
            raise ValueError("auto_basis_anchor_port_counts must contain values >= 0")
    if cfg.auto_basis_anchor_candidate_count is not None and cfg.auto_basis_anchor_candidate_count < 1:
        raise ValueError("auto_basis_anchor_candidate_count must be >= 1")
    if cfg.auto_basis_anchor_combo_count < 1:
        raise ValueError("auto_basis_anchor_combo_count must be >= 1")
    if cfg.auto_pole_dampings is not None:
        if len(cfg.auto_pole_dampings) == 0:
            raise ValueError("auto_pole_dampings must not be empty")
        if any(damping <= 0.0 for damping in cfg.auto_pole_dampings):
            raise ValueError("auto_pole_dampings must contain values > 0")
    if cfg.auto_shared_pole_trace_counts is not None:
        if len(cfg.auto_shared_pole_trace_counts) == 0:
            raise ValueError("auto_shared_pole_trace_counts must not be empty")
        if any(count < 1 for count in cfg.auto_shared_pole_trace_counts):
            raise ValueError("auto_shared_pole_trace_counts must contain values >= 1")
    if cfg.auto_peak_pole_entry_counts is not None:
        if len(cfg.auto_peak_pole_entry_counts) == 0:
            raise ValueError("auto_peak_pole_entry_counts must not be empty")
        if any(count < 0 for count in cfg.auto_peak_pole_entry_counts):
            raise ValueError("auto_peak_pole_entry_counts must contain values >= 0")
    if cfg.auto_basis_diagonal_weight < 0.0:
        raise ValueError("auto_basis_diagonal_weight must be >= 0")
    if (
        cfg.auto_order_max_z_log_magnitude_rms_error is not None
        and cfg.auto_order_max_z_log_magnitude_rms_error < 0.0
    ):
        raise ValueError("auto_order_max_z_log_magnitude_rms_error must be >= 0")
    if (
        cfg.auto_order_max_diagonal_z_log_magnitude_rms_error is not None
        and cfg.auto_order_max_diagonal_z_log_magnitude_rms_error < 0.0
    ):
        raise ValueError("auto_order_max_diagonal_z_log_magnitude_rms_error must be >= 0")


def _auto_order_trial(result: ModalZFitResult) -> ModalZAutoOrderTrial:
    selected_pole_frequencies = pole_frequencies_hz(result.selected_poles)
    return ModalZAutoOrderTrial(
        scalar_fit_order=result.scalar_fit_order,
        z_log_magnitude_rms_error=result.z_log_magnitude_rms_error,
        diagonal_z_log_magnitude_rms_error=result.diagonal_z_log_magnitude_rms_error,
        basis_projection_z_log_magnitude_rms_error=result.basis_projection_z_log_magnitude_rms_error,
        worst_error_frequency_hz=result.worst_error_frequency_hz,
        worst_error_port_pair=result.worst_error_port_pair,
        selected_pole_count=0 if result.selected_poles is None else int(len(result.selected_poles)),
        selected_pole_frequencies_hz=selected_pole_frequencies,
    )


def _auto_basis_trial(result: ModalZFitResult, diagonal_weight: float = 0.0) -> ModalZAutoBasisTrial:
    return ModalZAutoBasisTrial(
        mode_count=result.mode_count,
        basis_anchor_ports=result.basis_anchor_ports,
        basis_frequency_sample_count=result.basis_frequency_sample_count,
        scalar_fit_order=result.scalar_fit_order,
        pole_damping=result.pole_damping,
        shared_pole_trace_count=result.shared_pole_trace_count,
        peak_pole_entry_count=result.peak_pole_entry_count,
        selection_score=_selection_score(
            result.z_log_magnitude_rms_error,
            result.diagonal_z_log_magnitude_rms_error,
            diagonal_weight,
        ),
        z_log_magnitude_rms_error=result.z_log_magnitude_rms_error,
        diagonal_z_log_magnitude_rms_error=result.diagonal_z_log_magnitude_rms_error,
        basis_projection_z_log_magnitude_rms_error=result.basis_projection_z_log_magnitude_rms_error,
        worst_error_frequency_hz=result.worst_error_frequency_hz,
        worst_error_port_pair=result.worst_error_port_pair,
        selected_pole_count=0 if result.selected_poles is None else int(len(result.selected_poles)),
        residual_correction_pair_count=len(result.residual_correction_pairs),
    )


def _auto_order_passes_thresholds(result: ModalZFitResult, cfg: ModalZFitConfig) -> bool:
    z_threshold = cfg.auto_order_max_z_log_magnitude_rms_error
    diagonal_threshold = cfg.auto_order_max_diagonal_z_log_magnitude_rms_error
    if z_threshold is None and diagonal_threshold is None:
        return False
    if z_threshold is not None and result.z_log_magnitude_rms_error > z_threshold:
        return False
    if diagonal_threshold is not None and result.diagonal_z_log_magnitude_rms_error > diagonal_threshold:
        return False
    return True


def _fit_reduced_modal_z_fixed_order(
    frequencies: np.ndarray,
    z: np.ndarray,
    cfg: ModalZFitConfig,
    basis: np.ndarray,
    reduced: np.ndarray,
    projected_z: np.ndarray,
    fit_indices: np.ndarray,
) -> ModalZFitResult:
    fixed_cfg = replace(cfg, auto_order_candidates=None)
    selected_poles: np.ndarray | None = None
    if fixed_cfg.reduced_fit_method == "fixed":
        selected_poles = stable_poles(frequencies, fixed_cfg.scalar_fit_order, fixed_cfg.pole_damping)
        fitted_reduced = _fit_reduced_z_with_fixed_poles(frequencies, reduced, fixed_cfg, fit_indices)
    elif fixed_cfg.reduced_fit_method == "vector":
        fitted_reduced = _fit_reduced_z_with_vector_fitting(frequencies, reduced, fixed_cfg, fit_indices)
    elif fixed_cfg.reduced_fit_method == "shared-poles":
        selected_poles = _identify_shared_poles(frequencies, reduced, fixed_cfg, fit_indices)
        fitted_reduced = _fit_reduced_z_entries_with_poles(
            frequencies,
            z,
            basis,
            reduced,
            selected_poles,
            fixed_cfg,
            fit_indices,
        )
    else:
        selected_poles = _identify_peak_poles(
            frequencies,
            reduced,
            fixed_cfg,
            fit_indices,
            basis=basis,
            original_z=z,
        )
        fitted_reduced = _fit_reduced_z_entries_with_poles(
            frequencies,
            z,
            basis,
            reduced,
            selected_poles,
            fixed_cfg,
            fit_indices,
        )
    fitted_z = reconstruct_z_from_basis(fitted_reduced, basis)
    fitted_z, residual_correction_pairs = _apply_residual_pair_correction(
        frequencies,
        z,
        fitted_z,
        fixed_cfg,
        fit_indices,
    )
    diagonal_original = np.diagonal(z, axis1=1, axis2=2)
    diagonal_fitted = np.diagonal(fitted_z, axis1=1, axis2=2)
    worst_frequency, worst_pair = _worst_error(z, fitted_z, frequencies)
    return ModalZFitResult(
        ports=int(z.shape[1]),
        frequency_points=int(len(frequencies)),
        mode_count=fixed_cfg.mode_count,
        basis_anchor_ports=fixed_cfg.basis_anchor_ports,
        basis_frequency_sample_count=fixed_cfg.basis_frequency_sample_count,
        scalar_fit_order=fixed_cfg.scalar_fit_order,
        pole_damping=fixed_cfg.pole_damping,
        shared_pole_trace_count=fixed_cfg.shared_pole_trace_count,
        peak_pole_entry_count=fixed_cfg.peak_pole_entry_count,
        decomposition=fixed_cfg.decomposition,
        reduced_fit_method=fixed_cfg.reduced_fit_method,
        z_log_magnitude_rms_error=z_log_magnitude_rms_error(z, fitted_z),
        basis_projection_z_log_magnitude_rms_error=z_log_magnitude_rms_error(z, projected_z),
        diagonal_z_log_magnitude_rms_error=z_log_magnitude_rms_error(diagonal_original, diagonal_fitted),
        max_abs_z_error_ohm=float(np.max(np.abs(z - fitted_z))),
        worst_error_frequency_hz=worst_frequency,
        worst_error_port_pair=worst_pair,
        frequencies_hz=frequencies,
        original_z=z,
        basis=basis,
        fitted_z=fitted_z,
        projected_z=projected_z,
        selected_poles=selected_poles,
        residual_correction_pairs=residual_correction_pairs,
    )


def _fit_modal_z_for_basis(
    frequencies: np.ndarray,
    z: np.ndarray,
    cfg: ModalZFitConfig,
    fit_indices: np.ndarray,
) -> ModalZFitResult:
    basis = build_modal_basis(
        z,
        mode_count=cfg.mode_count,
        decomposition=cfg.decomposition,
        basis_indices=_basis_sample_indices(frequencies, cfg),
        anchor_ports=cfg.basis_anchor_ports,
    )
    reduced = project_z_to_basis(z, basis)
    projected_z = reconstruct_z_from_basis(reduced, basis)
    fit_indices = _fit_sample_indices(len(frequencies), cfg.frequency_sample_count, cfg.frequency_sample_head_count)
    if cfg.auto_order_candidates is None:
        return _fit_reduced_modal_z_fixed_order(frequencies, z, cfg, basis, reduced, projected_z, fit_indices)

    trials: list[ModalZAutoOrderTrial] = []
    best_result: ModalZFitResult | None = None
    for order in sorted(set(cfg.auto_order_candidates)):
        order_cfg = replace(cfg, scalar_fit_order=order, auto_order_candidates=None)
        result = _fit_reduced_modal_z_fixed_order(frequencies, z, order_cfg, basis, reduced, projected_z, fit_indices)
        trials.append(_auto_order_trial(result))
        if best_result is None or result.z_log_magnitude_rms_error < best_result.z_log_magnitude_rms_error:
            best_result = result
        if _auto_order_passes_thresholds(result, cfg):
            return replace(result, auto_order_trials=tuple(trials))

    if best_result is None:
        raise ValueError("auto_order_candidates must contain at least one order")
    return replace(best_result, auto_order_trials=tuple(trials))


def _fit_modal_z_auto_basis(
    frequencies: np.ndarray,
    z: np.ndarray,
    cfg: ModalZFitConfig,
    fit_indices: np.ndarray,
) -> ModalZFitResult:
    mode_candidates = tuple(sorted(set(cfg.auto_basis_mode_counts or (cfg.mode_count,))))
    basis_sample_candidates = tuple(sorted(set(cfg.auto_basis_sample_counts or (cfg.basis_frequency_sample_count,))))
    anchor_count_candidates = tuple(sorted(set(cfg.auto_basis_anchor_port_counts or (len(cfg.basis_anchor_ports),))))
    order_candidates = tuple(sorted(set(cfg.auto_order_candidates or (cfg.scalar_fit_order,))))
    damping_candidates = tuple(sorted(set(cfg.auto_pole_dampings or (cfg.pole_damping,))))
    trace_count_candidates = tuple(sorted(set(cfg.auto_shared_pole_trace_counts or (cfg.shared_pole_trace_count,))))
    peak_entry_candidates = tuple(sorted(set(cfg.auto_peak_pole_entry_counts or (cfg.peak_pole_entry_count,))))
    trials: list[ModalZAutoBasisTrial] = []
    best_result: ModalZFitResult | None = None
    carried_anchor_port_sets: dict[int, list[tuple[int, ...]]] = {}
    for mode_count in mode_candidates:
        for basis_sample_count in basis_sample_candidates:
            inferred_anchor_port_sets: dict[int, tuple[tuple[int, ...], ...]] = {}
            for anchor_count in anchor_count_candidates:
                if cfg.basis_anchor_ports:
                    anchor_port_sets = (cfg.basis_anchor_ports,)
                elif anchor_count <= 0:
                    anchor_port_sets = ((),)
                else:
                    if anchor_count not in inferred_anchor_port_sets:
                        unanchored_cfg = replace(
                            cfg,
                            mode_count=mode_count,
                            basis_frequency_sample_count=basis_sample_count,
                            basis_anchor_ports=(),
                            auto_order_candidates=None,
                            auto_basis_mode_counts=None,
                            auto_basis_sample_counts=None,
                            auto_basis_anchor_port_counts=None,
                            auto_basis_anchor_candidate_count=None,
                            auto_pole_dampings=None,
                            auto_shared_pole_trace_counts=None,
                            auto_peak_pole_entry_counts=None,
                        )
                        unanchored_basis = build_modal_basis(
                            z,
                            mode_count=mode_count,
                            decomposition=unanchored_cfg.decomposition,
                            basis_indices=_basis_sample_indices(frequencies, unanchored_cfg),
                        )
                        unanchored_reduced = project_z_to_basis(z, unanchored_basis)
                        unanchored_projected = reconstruct_z_from_basis(unanchored_reduced, unanchored_basis)
                        inferred_anchor_port_sets[anchor_count] = _select_anchor_port_sets_by_projection_search(
                            frequencies,
                            z,
                            cfg,
                            mode_count,
                            basis_sample_count,
                            anchor_count,
                            unanchored_projected,
                            diagonal_weight=cfg.auto_basis_diagonal_weight,
                            candidate_count=cfg.auto_basis_anchor_candidate_count,
                            combo_count=cfg.auto_basis_anchor_combo_count,
                        )
                    anchor_port_sets = inferred_anchor_port_sets[anchor_count]
                carryover_anchor_port_sets = tuple(
                    ports
                    for ports in carried_anchor_port_sets.get(anchor_count, [])
                    if len(ports) <= mode_count and all(1 <= port <= z.shape[1] for port in ports)
                )
                anchor_port_sets = _merge_anchor_port_sets(anchor_port_sets, carryover_anchor_port_sets)
                for anchor_ports in anchor_port_sets:
                    for order in order_candidates:
                        for damping in damping_candidates:
                            for trace_count in trace_count_candidates:
                                for peak_entry_count in peak_entry_candidates:
                                    trial_cfg = replace(
                                        cfg,
                                        mode_count=mode_count,
                                        basis_anchor_ports=anchor_ports,
                                        basis_frequency_sample_count=basis_sample_count,
                                        scalar_fit_order=order,
                                        pole_damping=damping,
                                        shared_pole_trace_count=trace_count,
                                        peak_pole_entry_count=peak_entry_count,
                                        auto_order_candidates=None,
                                        auto_basis_mode_counts=None,
                                        auto_basis_sample_counts=None,
                                        auto_basis_anchor_port_counts=None,
                                        auto_basis_anchor_candidate_count=None,
                                        auto_pole_dampings=None,
                                        auto_shared_pole_trace_counts=None,
                                        auto_peak_pole_entry_counts=None,
                                    )
                                    result = _fit_modal_z_for_basis(frequencies, z, trial_cfg, fit_indices)
                                    trials.append(_auto_basis_trial(result, cfg.auto_basis_diagonal_weight))
                                    result_score = _selection_score(
                                        result.z_log_magnitude_rms_error,
                                        result.diagonal_z_log_magnitude_rms_error,
                                        cfg.auto_basis_diagonal_weight,
                                    )
                                    best_score = (
                                        math.inf
                                        if best_result is None
                                        else _selection_score(
                                            best_result.z_log_magnitude_rms_error,
                                            best_result.diagonal_z_log_magnitude_rms_error,
                                            cfg.auto_basis_diagonal_weight,
                                        )
                                    )
                                    if result_score < best_score:
                                        best_result = result
                                    if _auto_order_passes_thresholds(result, cfg):
                                        return replace(result, auto_basis_trials=tuple(trials))
                    if anchor_ports:
                        carried_anchor_port_sets.setdefault(len(anchor_ports), [])
                        if anchor_ports not in carried_anchor_port_sets[len(anchor_ports)]:
                            carried_anchor_port_sets[len(anchor_ports)].append(anchor_ports)
    if best_result is None:
        raise ValueError("auto-basis candidates must contain at least one trial")
    return replace(best_result, auto_basis_trials=tuple(trials))


def fit_reduced_modal_z(freqs: Any, z_samples: Any, config: ModalZFitConfig | None = None) -> ModalZFitResult:
    cfg = config or ModalZFitConfig()
    _validate_modal_z_fit_config(cfg)
    frequencies = np.asarray(freqs, dtype=float)
    z = _as_z_array(z_samples)
    if len(frequencies) != len(z):
        raise ValueError("freqs length must match z_samples frequency dimension")
    fit_indices = _fit_sample_indices(len(frequencies), cfg.frequency_sample_count, cfg.frequency_sample_head_count)
    if (
        cfg.auto_basis_mode_counts is not None
        or cfg.auto_basis_sample_counts is not None
        or cfg.auto_basis_anchor_port_counts is not None
        or cfg.auto_basis_anchor_candidate_count is not None
        or cfg.auto_pole_dampings is not None
        or cfg.auto_shared_pole_trace_counts is not None
        or cfg.auto_peak_pole_entry_counts is not None
    ):
        return _fit_modal_z_auto_basis(frequencies, z, cfg, fit_indices)
    return _fit_modal_z_for_basis(frequencies, z, cfg, fit_indices)


def _attach_s_parameter_metrics(
    result: ModalZFitResult,
    original_s: Any,
    z0: Any,
    s_def: str = "power",
) -> ModalZFitResult:
    try:
        original_s_array = np.asarray(original_s, dtype=complex)
        fitted_s = z2s(result.fitted_z, z0=z0, s_def=s_def)
        return replace(
            result,
            original_s=original_s_array,
            fitted_s=fitted_s,
            s_rms_error=s_rms_error(original_s_array, fitted_s),
        )
    except Exception as exc:
        warnings.warn(f"Could not compute modal-Z S-parameter metrics: {exc}", RuntimeWarning, stacklevel=2)
        return result


def fit_modal_z_touchstone(touchstone_path: str | Any, config: ModalZFitConfig | None = None) -> ModalZFitResult:
    network = rf.Network(str(touchstone_path))
    result = fit_reduced_modal_z(network.f, network.z, config or ModalZFitConfig())
    return _attach_s_parameter_metrics(result, network.s, network.z0, getattr(network, "s_def", "power"))
