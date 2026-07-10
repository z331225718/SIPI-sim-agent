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
        _candidate_from_frequencies(
            log_frequency,
            topology,
            source="log_grid",
            seed_index=0,
            damping=np.linspace(_MIN_DAMPING, _MAX_DAMPING, topology.complex_pair_count),
        )
    )

    remaining = candidate_count - 1
    activity_count = (remaining + 1) // 2
    activity = np.sqrt(np.mean(np.abs(np.diff(response_array, axis=1)) ** 2, axis=0))
    activity_cdf = _activity_cdf(activity)
    log_lower = float(np.log(lower))
    log_upper = float(np.log(upper))
    log_span = log_upper - log_lower
    total_poles = topology.real_count + topology.complex_pair_count

    for offset in range(activity_count):
        quantile = (offset + 0.5 + rng.uniform(-0.2, 0.2)) / max(activity_count, 1)
        center_index = int(np.searchsorted(activity_cdf, np.clip(quantile, 0.0, 1.0), side="left"))
        center_index = min(center_index, len(activity) - 1)
        center = float(np.sqrt(freqs[center_index] * freqs[center_index + 1]))
        offsets = np.linspace(-0.55, 0.55, total_poles) + rng.uniform(-0.08, 0.08, total_poles)
        frequencies = np.exp(np.clip(np.log(center) + offsets * log_span, log_lower, log_upper))
        candidates.append(
            _candidate_from_frequencies(
                np.sort(frequencies),
                topology,
                source="response_activity",
                seed_index=len(candidates),
                damping=rng.uniform(_MIN_DAMPING, _MAX_DAMPING, topology.complex_pair_count),
            )
        )

    while len(candidates) < candidate_count:
        index = len(candidates)
        strata = (np.arange(total_poles, dtype=float) + rng.uniform(0.0, 1.0, total_poles)) / total_poles
        rng.shuffle(strata)
        frequencies = np.exp(log_lower + np.sort(strata) * log_span)
        candidates.append(
            _candidate_from_frequencies(
                frequencies,
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


def _candidate_from_frequencies(
    frequencies: np.ndarray,
    topology: PoleTopology,
    *,
    source: str,
    seed_index: int,
    damping: np.ndarray,
) -> PoleCandidate:
    frequency_array = np.asarray(frequencies, dtype=float).reshape(-1)
    real_count = topology.real_count
    poles = make_stable_poles(
        real_decay_hz=frequency_array[:real_count],
        complex_frequency_hz=frequency_array[real_count:],
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
