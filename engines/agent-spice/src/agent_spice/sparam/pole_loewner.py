from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import linalg


@dataclass(frozen=True)
class LoewnerConfig:
    requested_orders: tuple[int, ...] = (6, 8, 10)
    probe_count: int = 4
    partition_count: int = 4
    seed: int = 20260710
    conjugate_tolerance: float = 1e-5
    duplicate_tolerance: float = 1e-3


@dataclass(frozen=True)
class LoewnerCandidateDiagnostics:
    requested_order: int
    numerical_rank: int
    singular_values: np.ndarray
    raw_eigenvalues: np.ndarray
    poles: np.ndarray
    effective_order: int
    accepted: bool
    rejection_reason: str | None
    partition_index: int


@dataclass(frozen=True)
class StackedLoewnerPencil:
    s_axis: np.ndarray
    augmented_traces: np.ndarray
    left_indices: np.ndarray
    right_indices: np.ndarray
    loewner: np.ndarray
    shifted_loewner: np.ndarray
    partition_index: int


def project_sparameter_traces(
    freqs_hz: np.ndarray,
    s_parameters: np.ndarray,
    *,
    probe_count: int,
    seed: int,
) -> np.ndarray:
    freqs = _validated_frequency_axis(freqs_hz)
    matrices = np.asarray(s_parameters, dtype=complex)
    if matrices.ndim != 3 or matrices.shape[0] != freqs.size:
        raise ValueError("s_parameters must have shape (nfreq, nports, nports)")
    if matrices.shape[1] < 1 or matrices.shape[1] != matrices.shape[2]:
        raise ValueError("s_parameters must contain nonempty square port matrices")

    left_vectors, right_vectors = _deterministic_probe_vectors(
        nports=matrices.shape[1], probe_count=probe_count, seed=seed
    )
    return np.einsum("ki,fij,kj->kf", left_vectors.conj(), matrices, right_vectors, optimize=True)


def _deterministic_probe_vectors(*, nports: int, probe_count: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    if nports < 1:
        raise ValueError("nports must be positive")
    if probe_count < 1:
        raise ValueError("probe_count must be positive")

    rng = np.random.default_rng(seed)
    # Real tangential directions preserve H(-jw) = conj(H(jw)) for real systems.
    left_vectors = rng.normal(size=(probe_count, nports))
    right_vectors = rng.normal(size=(probe_count, nports))
    left_vectors /= np.linalg.norm(left_vectors, axis=1, keepdims=True)
    right_vectors /= np.linalg.norm(right_vectors, axis=1, keepdims=True)
    return left_vectors, right_vectors


def build_stacked_loewner_pencil(
    freqs_hz: np.ndarray,
    traces: np.ndarray,
    *,
    partition_index: int = 0,
) -> StackedLoewnerPencil:
    freqs = _validated_frequency_axis(freqs_hz)
    trace_array = np.asarray(traces, dtype=complex)
    if trace_array.ndim != 2 or trace_array.shape[1] != freqs.size:
        raise ValueError("traces must have shape (nprobes, nfreq)")
    if trace_array.shape[0] < 1:
        raise ValueError("traces must contain at least one projected trace")
    if partition_index < 0:
        raise ValueError("partition_index must be nonnegative")

    s_axis, augmented_traces = _augment_conjugate_frequency_axis(freqs, trace_array)
    left_indices, right_indices = _deterministic_partition(s_axis.size, partition_index)
    left_s = s_axis[left_indices]
    right_s = s_axis[right_indices]
    denominator = left_s[:, np.newaxis] - right_s[np.newaxis, :]

    loewner_blocks = []
    shifted_blocks = []
    for trace in augmented_traces:
        left_samples = trace[left_indices]
        right_samples = trace[right_indices]
        loewner_blocks.append(
            (left_samples[:, np.newaxis] - right_samples[np.newaxis, :]) / denominator
        )
        shifted_blocks.append(
            (
                left_s[:, np.newaxis] * left_samples[:, np.newaxis]
                - right_s[np.newaxis, :] * right_samples[np.newaxis, :]
            )
            / denominator
        )

    return StackedLoewnerPencil(
        s_axis=s_axis,
        augmented_traces=augmented_traces,
        left_indices=left_indices,
        right_indices=right_indices,
        loewner=np.vstack(loewner_blocks),
        shifted_loewner=np.vstack(shifted_blocks),
        partition_index=partition_index,
    )


def extract_stable_half_pair_poles(
    pencil: StackedLoewnerPencil,
    requested_order: int,
    *,
    conjugate_tolerance: float = 1e-5,
    duplicate_tolerance: float = 1e-3,
) -> LoewnerCandidateDiagnostics:
    if requested_order < 1:
        raise ValueError("requested_order must be positive")
    if conjugate_tolerance < 0.0 or duplicate_tolerance < 0.0:
        raise ValueError("pole tolerances must be nonnegative")

    loewner = np.asarray(pencil.loewner, dtype=complex)
    shifted_loewner = np.asarray(pencil.shifted_loewner, dtype=complex)
    if loewner.ndim != 2 or shifted_loewner.shape != loewner.shape:
        raise ValueError("Loewner matrices must be two-dimensional with identical shapes")

    partition_index = int(pencil.partition_index)
    if min(loewner.shape) == 0:
        return _rejected_diagnostics(
            requested_order=requested_order,
            singular_values=np.array([], dtype=float),
            numerical_rank=0,
            partition_index=partition_index,
            reason="insufficient_points",
        )

    left_singular_vectors, singular_values, right_singular_vectors_h = np.linalg.svd(
        loewner, full_matrices=False
    )
    numerical_rank = _numerical_rank(loewner, singular_values)
    if requested_order > numerical_rank:
        return _rejected_diagnostics(
            requested_order=requested_order,
            singular_values=singular_values,
            numerical_rank=numerical_rank,
            partition_index=partition_index,
            reason="requested_order_exceeds_numerical_rank",
        )

    left_reduced = left_singular_vectors[:, :requested_order]
    right_reduced = right_singular_vectors_h.conj().T[:, :requested_order]
    reduced_e = left_reduced.conj().T @ loewner @ right_reduced
    reduced_a = left_reduced.conj().T @ shifted_loewner @ right_reduced
    raw_eigenvalues = linalg.eigvals(reduced_a, reduced_e)

    if not np.all(np.isfinite(raw_eigenvalues)):
        return _rejected_diagnostics(
            requested_order=requested_order,
            singular_values=singular_values,
            numerical_rank=numerical_rank,
            raw_eigenvalues=raw_eigenvalues,
            partition_index=partition_index,
            reason="non_finite_eigenvalue",
        )
    if any(pole.real >= -1e-12 * max(1.0, abs(pole)) for pole in raw_eigenvalues):
        return _rejected_diagnostics(
            requested_order=requested_order,
            singular_values=singular_values,
            numerical_rank=numerical_rank,
            raw_eigenvalues=raw_eigenvalues,
            partition_index=partition_index,
            reason="unstable_eigenvalue",
        )

    poles, rejection_reason = _stable_half_pair_poles(
        raw_eigenvalues,
        conjugate_tolerance=conjugate_tolerance,
        duplicate_tolerance=duplicate_tolerance,
    )
    if rejection_reason is not None:
        return _rejected_diagnostics(
            requested_order=requested_order,
            singular_values=singular_values,
            numerical_rank=numerical_rank,
            raw_eigenvalues=raw_eigenvalues,
            partition_index=partition_index,
            reason=rejection_reason,
        )

    effective_order = _effective_order(poles)
    if effective_order != requested_order:
        return _rejected_diagnostics(
            requested_order=requested_order,
            singular_values=singular_values,
            numerical_rank=numerical_rank,
            raw_eigenvalues=raw_eigenvalues,
            partition_index=partition_index,
            reason="effective_order_mismatch",
        )

    return LoewnerCandidateDiagnostics(
        requested_order=requested_order,
        numerical_rank=numerical_rank,
        singular_values=singular_values,
        raw_eigenvalues=raw_eigenvalues,
        poles=poles,
        effective_order=effective_order,
        accepted=True,
        rejection_reason=None,
        partition_index=partition_index,
    )


def discover_loewner_candidates(
    freqs_hz: np.ndarray,
    s_parameters: np.ndarray,
    *,
    config: LoewnerConfig = LoewnerConfig(),
) -> list[LoewnerCandidateDiagnostics]:
    allowed_orders = {6, 8, 10}
    if (
        not config.requested_orders
        or len(set(config.requested_orders)) != len(config.requested_orders)
        or any(order not in allowed_orders for order in config.requested_orders)
    ):
        raise ValueError("requested_orders must contain only unique orders from exactly 6, 8, and 10")
    if config.partition_count < 1:
        raise ValueError("partition_count must be positive")
    if config.conjugate_tolerance < 0.0 or config.duplicate_tolerance < 0.0:
        raise ValueError("pole tolerances must be nonnegative")

    traces = project_sparameter_traces(
        freqs_hz,
        s_parameters,
        probe_count=config.probe_count,
        seed=config.seed,
    )
    diagnostics = []
    for partition_index in range(config.partition_count):
        pencil = build_stacked_loewner_pencil(
            freqs_hz, traces, partition_index=partition_index
        )
        for requested_order in config.requested_orders:
            diagnostics.append(
                extract_stable_half_pair_poles(
                    pencil,
                    requested_order,
                    conjugate_tolerance=config.conjugate_tolerance,
                    duplicate_tolerance=config.duplicate_tolerance,
                )
            )
    return diagnostics


def _validated_frequency_axis(freqs_hz: np.ndarray) -> np.ndarray:
    freqs = np.asarray(freqs_hz, dtype=float).reshape(-1)
    if freqs.size < 1 or not np.all(np.isfinite(freqs)):
        raise ValueError("freqs_hz must contain finite values")
    if np.any(freqs < 0.0) or np.any(np.diff(freqs) <= 0.0):
        raise ValueError("freqs_hz must contain ascending nonnegative values")
    return freqs


def _augment_conjugate_frequency_axis(
    freqs_hz: np.ndarray, traces: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    positive = freqs_hz > 0.0
    s_axis = np.concatenate((-2j * np.pi * freqs_hz[positive][::-1], 2j * np.pi * freqs_hz))
    augmented = np.concatenate((np.conj(traces[:, positive][:, ::-1]), traces), axis=1)
    order = np.argsort(s_axis.imag, kind="stable")
    s_axis = s_axis[order]
    augmented = augmented[:, order]
    if np.unique(s_axis).size != s_axis.size:
        raise ValueError("conjugate augmentation produced duplicate s-axis values")
    return s_axis, augmented


def _deterministic_partition(sample_count: int, partition_index: int) -> tuple[np.ndarray, np.ndarray]:
    if sample_count < 1:
        raise ValueError("sample_count must be positive")
    cyclic_indices = np.roll(np.arange(sample_count), -(partition_index % sample_count))
    return np.sort(cyclic_indices[::2]), np.sort(cyclic_indices[1::2])


def _numerical_rank(loewner: np.ndarray, singular_values: np.ndarray) -> int:
    if singular_values.size == 0 or singular_values[0] == 0.0:
        return 0
    threshold = singular_values[0] * max(loewner.shape) * np.finfo(float).eps
    return int(np.count_nonzero(singular_values > threshold))


def _stable_half_pair_poles(
    raw_eigenvalues: np.ndarray,
    *,
    conjugate_tolerance: float,
    duplicate_tolerance: float,
) -> tuple[np.ndarray, str | None]:
    clustered = _cluster_duplicate_poles(raw_eigenvalues, duplicate_tolerance)
    real_poles = []
    positive_imaginary = []
    negative_imaginary = []
    for pole in clustered:
        scale = max(1.0, abs(pole))
        if abs(pole.imag) <= conjugate_tolerance * scale:
            real_poles.append(complex(float(pole.real), 0.0))
        elif pole.imag > 0.0:
            positive_imaginary.append(pole)
        else:
            negative_imaginary.append(pole)

    half_pair_poles = list(real_poles)
    used_negative_indices: set[int] = set()
    for positive_pole in positive_imaginary:
        matching_indices = [
            index
            for index, negative_pole in enumerate(negative_imaginary)
            if _relative_distance(positive_pole, np.conj(negative_pole)) <= conjugate_tolerance
        ]
        if len(matching_indices) != 1 or matching_indices[0] in used_negative_indices:
            return np.array([], dtype=complex), "missing_conjugate_partner"
        negative_index = matching_indices[0]
        used_negative_indices.add(negative_index)
        half_pair_poles.append(
            0.5 * (positive_pole + np.conj(negative_imaginary[negative_index]))
        )
    if len(used_negative_indices) != len(negative_imaginary):
        return np.array([], dtype=complex), "missing_conjugate_partner"

    poles = np.asarray(half_pair_poles, dtype=complex)
    order = np.lexsort((poles.imag, poles.real))
    return poles[order], None


def _cluster_duplicate_poles(poles: np.ndarray, tolerance: float) -> np.ndarray:
    unassigned = list(
        sorted(np.asarray(poles, dtype=complex).reshape(-1), key=lambda pole: (pole.real, pole.imag))
    )
    clusters = []
    while unassigned:
        cluster = [unassigned.pop(0)]
        changed = True
        while changed:
            changed = False
            for index in range(len(unassigned) - 1, -1, -1):
                if any(_relative_distance(unassigned[index], member) <= tolerance for member in cluster):
                    cluster.append(unassigned.pop(index))
                    changed = True
        clusters.append(np.mean(cluster))
    return np.asarray(clusters, dtype=complex)


def _relative_distance(left: complex, right: complex) -> float:
    return float(abs(left - right) / max(1.0, abs(left), abs(right)))


def _effective_order(poles: np.ndarray) -> int:
    return int(
        np.count_nonzero(np.abs(poles.imag) <= 1e-15)
        + 2 * np.count_nonzero(poles.imag > 1e-15)
    )


def _rejected_diagnostics(
    *,
    requested_order: int,
    singular_values: np.ndarray,
    numerical_rank: int,
    partition_index: int,
    reason: str,
    raw_eigenvalues: np.ndarray | None = None,
) -> LoewnerCandidateDiagnostics:
    return LoewnerCandidateDiagnostics(
        requested_order=requested_order,
        numerical_rank=numerical_rank,
        singular_values=singular_values,
        raw_eigenvalues=(
            np.array([], dtype=complex) if raw_eigenvalues is None else np.asarray(raw_eigenvalues, dtype=complex)
        ),
        poles=np.array([], dtype=complex),
        effective_order=0,
        accepted=False,
        rejection_reason=reason,
        partition_index=partition_index,
    )
