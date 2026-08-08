from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

import numpy as np

from .native_vf import NativeVectorFitting


_IMAG_TOLERANCE = 1e-15
_MIN_DAMPING = 0.01
_MAX_DAMPING = 0.20


@dataclass(frozen=True)
class PoleTopology:
    real_count: int
    complex_pair_count: int

    @property
    def effective_order(self) -> int:
        return self.real_count + 2 * self.complex_pair_count


@dataclass(frozen=True)
class PoleCandidate:
    poles: np.ndarray
    topology: PoleTopology
    source: str
    seed_index: int
    fingerprint: str


@dataclass(frozen=True)
class PoleCandidateEvaluation:
    candidate: PoleCandidate
    mean_rms: float
    max_sigma: float | None
    max_sigma_frequency_hz: float | None
    violation_band_count: int | None


def effective_order(poles: Any) -> int:
    pole_array = np.asarray(poles, dtype=complex).reshape(-1)
    return int(
        np.count_nonzero(np.abs(pole_array.imag) <= _IMAG_TOLERANCE)
        + 2 * np.count_nonzero(pole_array.imag > _IMAG_TOLERANCE)
    )


def make_stable_poles(
    *,
    real_decay_hz: Any,
    complex_frequency_hz: Any,
    damping_ratio: Any,
) -> np.ndarray:
    real_decay = np.asarray(real_decay_hz, dtype=float).reshape(-1)
    complex_frequency = np.asarray(complex_frequency_hz, dtype=float).reshape(-1)
    damping = np.asarray(damping_ratio, dtype=float).reshape(-1)
    if complex_frequency.size != damping.size:
        raise ValueError("complex_frequency_hz and damping_ratio must have equal lengths")
    if np.any(real_decay <= 0.0) or np.any(complex_frequency <= 0.0):
        raise ValueError("pole frequencies must be positive")
    if np.any((damping < _MIN_DAMPING) | (damping > _MAX_DAMPING)):
        raise ValueError("damping_ratio must be in [0.01, 0.20]")

    real_poles = -2.0 * np.pi * real_decay
    complex_omega = 2.0 * np.pi * complex_frequency
    complex_poles = -damping * complex_omega + 1j * complex_omega
    return np.concatenate((real_poles.astype(complex), complex_poles.astype(complex)))


def generate_data_only_candidates(
    freqs_hz: Any,
    responses: Any,
    topology: PoleTopology,
    *,
    candidate_count: int = 32,
    seed: int = 0,
) -> list[PoleCandidate]:
    freqs, response_array, lower, upper = _validated_inputs(freqs_hz, responses, topology)
    if candidate_count < 1:
        raise ValueError("candidate_count must be positive")

    rng = np.random.default_rng(seed)
    candidates = []
    log_frequency = np.geomspace(lower, upper, topology.real_count + topology.complex_pair_count)
    candidates.append(
        _candidate_from_components(
            log_frequency[: topology.real_count],
            log_frequency[topology.real_count :],
            topology,
            source="log_grid",
            seed_index=0,
            damping=np.linspace(_MIN_DAMPING, _MAX_DAMPING, topology.complex_pair_count),
        )
    )

    remaining = candidate_count - 1
    activity_count = (remaining + 1) // 2
    activity = np.sqrt(np.mean(np.abs(np.diff(response_array, axis=1)) ** 2, axis=0))
    activity_frequencies = _activity_frequency_centers(freqs, lower)
    positive_freqs = freqs[freqs > 0.0]

    for offset in range(activity_count):
        phase = (offset + rng.uniform(0.1, 0.9)) / activity_count
        real_frequencies = _activity_stratified_frequencies(
            activity_frequencies,
            activity,
            topology.real_count,
            phase=phase,
            rng=rng,
            minimum_log_separation=0.02,
        )
        complex_frequencies = _activity_stratified_frequencies(
            activity_frequencies,
            activity,
            topology.complex_pair_count,
            phase=phase + 0.5,
            rng=rng,
            minimum_log_separation=0.05,
        )
        candidates.append(
            _candidate_from_components(
                real_frequencies,
                complex_frequencies,
                topology,
                source="response_activity",
                seed_index=len(candidates),
                damping=rng.uniform(_MIN_DAMPING, _MAX_DAMPING, topology.complex_pair_count),
            )
        )

    while len(candidates) < candidate_count:
        index = len(candidates)
        real_frequencies = _empirical_stratified_frequencies(positive_freqs, topology.real_count, rng=rng)
        complex_frequencies = _activity_stratified_frequencies(
            activity_frequencies,
            activity,
            topology.complex_pair_count,
            phase=rng.uniform(0.0, 1.0),
            rng=rng,
            minimum_log_separation=0.05,
        )
        candidates.append(
            _candidate_from_components(
                real_frequencies,
                complex_frequencies,
                topology,
                source="stratified",
                seed_index=index,
                damping=rng.uniform(_MIN_DAMPING, _MAX_DAMPING, topology.complex_pair_count),
            )
        )
    return candidates


def evaluate_pole_candidates(
    freqs_hz: Any,
    responses: Any,
    *,
    nports: int,
    candidates: list[PoleCandidate],
    full_sigma_candidate_count: int = 8,
) -> list[PoleCandidateEvaluation]:
    freqs = np.asarray(freqs_hz, dtype=float).reshape(-1)
    response_array = np.asarray(responses, dtype=complex)
    if response_array.ndim != 2 or response_array.shape[1] != freqs.size:
        raise ValueError("responses must be flattened with one column per raw frequency point")
    if response_array.shape[0] != nports * nports:
        raise ValueError("responses must contain nports squared rows")
    if full_sigma_candidate_count < 0:
        raise ValueError("full_sigma_candidate_count must not be negative")

    preliminary: list[tuple[PoleCandidateEvaluation, np.ndarray]] = []
    for candidate in candidates:
        residues, constant, proportional, *_ = NativeVectorFitting._fit_residues(
            candidate.poles,
            freqs,
            response_array,
            True,
            False,
            bool(freqs[0] == 0.0),
        )
        fitted = NativeVectorFitting._evaluate_residue_model(
            candidate.poles,
            residues,
            constant,
            proportional,
            freqs,
        )
        mean_rms = float(np.sqrt(np.mean(np.abs(fitted - response_array) ** 2)))
        preliminary.append((PoleCandidateEvaluation(candidate, mean_rms, None, None, None), fitted))

    ranked = sorted(preliminary, key=lambda item: (item[0].mean_rms, item[0].candidate.fingerprint))
    sigma_by_fingerprint = {}
    for evaluation, fitted in ranked[:full_sigma_candidate_count]:
        candidate = evaluation.candidate
        sigma_by_fingerprint[candidate.fingerprint] = _full_grid_sigma(fitted, freqs, nports)

    return [
        PoleCandidateEvaluation(
            candidate=item.candidate,
            mean_rms=item.mean_rms,
            max_sigma=sigma_by_fingerprint[item.candidate.fingerprint][0]
            if item.candidate.fingerprint in sigma_by_fingerprint
            else None,
            max_sigma_frequency_hz=sigma_by_fingerprint[item.candidate.fingerprint][1]
            if item.candidate.fingerprint in sigma_by_fingerprint
            else None,
            violation_band_count=sigma_by_fingerprint[item.candidate.fingerprint][2]
            if item.candidate.fingerprint in sigma_by_fingerprint
            else None,
        )
        for item, _ in ranked
    ]


def pareto_front(evaluations: list[PoleCandidateEvaluation]) -> list[PoleCandidateEvaluation]:
    eligible = [item for item in evaluations if item.max_sigma is not None]
    return [
        item
        for item in eligible
        if not any(other is not item and dominates(other, item) for other in eligible)
    ]


def dominates(left: PoleCandidateEvaluation, right: PoleCandidateEvaluation) -> bool:
    if left.max_sigma is None or right.max_sigma is None:
        return False
    return (
        left.mean_rms <= right.mean_rms
        and left.max_sigma <= right.max_sigma
        and (left.mean_rms < right.mean_rms or left.max_sigma < right.max_sigma)
    )


def _validated_inputs(
    freqs_hz: Any, responses: Any, topology: PoleTopology
) -> tuple[np.ndarray, np.ndarray, float, float]:
    freqs = np.asarray(freqs_hz, dtype=float).reshape(-1)
    response_array = np.asarray(responses, dtype=complex)
    if freqs.size < 2 or np.any(np.diff(freqs) <= 0.0):
        raise ValueError("freqs_hz must contain at least two ascending values")
    if response_array.ndim != 2 or response_array.shape[1] != freqs.size:
        raise ValueError("responses must be flattened with one column per frequency")
    if topology.real_count < 0 or topology.complex_pair_count < 0 or topology.effective_order < 1:
        raise ValueError("topology must contain at least one pole")
    positive = freqs[freqs > 0.0]
    if positive.size == 0:
        raise ValueError("freqs_hz must contain a positive frequency")
    return freqs, response_array, float(np.min(positive)), float(np.max(freqs))


def _activity_cdf(activity: np.ndarray) -> np.ndarray:
    weights = np.asarray(activity, dtype=float)
    if not np.all(np.isfinite(weights)) or float(np.sum(weights)) <= 0.0:
        weights = np.ones_like(weights)
    return np.cumsum(weights) / float(np.sum(weights))


def _activity_frequency_centers(freqs_hz: np.ndarray, lower_hz: float) -> np.ndarray:
    lower = np.maximum(np.asarray(freqs_hz[:-1], dtype=float), lower_hz)
    upper = np.maximum(np.asarray(freqs_hz[1:], dtype=float), lower_hz)
    return np.sqrt(lower * upper)


def _empirical_stratified_frequencies(
    samples_hz: np.ndarray,
    count: int,
    *,
    rng: np.random.Generator,
) -> np.ndarray:
    if count == 0:
        return np.array([], dtype=float)
    samples = np.asarray(samples_hz, dtype=float).reshape(-1)
    quantiles = (np.arange(count, dtype=float) + rng.uniform(0.1, 0.9, count)) / count
    indices = np.minimum((quantiles * len(samples)).astype(int), len(samples) - 1)
    return np.sort(samples[indices])


def _activity_stratified_frequencies(
    frequencies_hz: np.ndarray,
    activity: np.ndarray,
    count: int,
    *,
    phase: float,
    rng: np.random.Generator,
    minimum_log_separation: float,
) -> np.ndarray:
    if count == 0:
        return np.array([], dtype=float)
    frequencies = np.asarray(frequencies_hz, dtype=float).reshape(-1)
    cdf = _activity_cdf(activity)
    phase_offset = float(phase) % 1.0
    targets = (np.arange(count, dtype=float) + phase_offset + rng.uniform(-0.12, 0.12, count)) / count
    targets = np.mod(targets, 1.0)
    selected: list[int] = []
    for target in targets:
        candidate_indices = [
            index
            for index, frequency in enumerate(frequencies)
            if index not in selected
            and all(abs(float(np.log(frequency / frequencies[existing]))) >= minimum_log_separation for existing in selected)
        ]
        if not candidate_indices:
            candidate_indices = [index for index in range(len(frequencies)) if index not in selected]
        chosen = min(
            candidate_indices,
            key=lambda index: (abs(float(cdf[index]) - float(target)), -float(activity[index]), index),
        )
        selected.append(chosen)
    return np.sort(frequencies[np.asarray(selected, dtype=int)])


def _candidate_from_components(
    real_frequencies: np.ndarray,
    complex_frequencies: np.ndarray,
    topology: PoleTopology,
    *,
    source: str,
    seed_index: int,
    damping: np.ndarray,
) -> PoleCandidate:
    real_frequency_array = np.asarray(real_frequencies, dtype=float).reshape(-1)
    complex_frequency_array = np.asarray(complex_frequencies, dtype=float).reshape(-1)
    if real_frequency_array.size != topology.real_count or complex_frequency_array.size != topology.complex_pair_count:
        raise ValueError("candidate frequencies must match the requested topology")
    poles = make_stable_poles(
        real_decay_hz=real_frequency_array,
        complex_frequency_hz=complex_frequency_array,
        damping_ratio=damping,
    )
    poles.setflags(write=False)
    digest = hashlib.sha256()
    digest.update(source.encode("ascii"))
    digest.update(str(seed_index).encode("ascii"))
    digest.update(np.ascontiguousarray(poles).view(np.uint8))
    return PoleCandidate(poles, topology, source, seed_index, digest.hexdigest()[:16])


def _full_grid_sigma(responses: np.ndarray, freqs_hz: np.ndarray, nports: int) -> tuple[float, float, int]:
    max_sigma = -np.inf
    max_frequency = float(freqs_hz[0])
    violating = []
    for index in range(responses.shape[1]):
        matrix = responses[:, index].reshape(nports, nports)
        sigma = float(np.max(np.linalg.svd(matrix, compute_uv=False)))
        if sigma > max_sigma:
            max_sigma = sigma
            max_frequency = float(freqs_hz[index])
        violating.append(sigma > 1.0 + 1e-12)
    band_count = sum(current and (index == 0 or not violating[index - 1]) for index, current in enumerate(violating))
    return float(max_sigma), max_frequency, int(band_count)
