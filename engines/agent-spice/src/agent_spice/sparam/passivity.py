from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable

import numpy as np
import scipy.linalg as la
import scipy.optimize as opt




@dataclass(frozen=True)
class PassivityQpResult:
    x: np.ndarray
    success: bool
    message: str
    regularization: float = 0.0
    dual_condition_number: float = np.inf
    slack: float | None = None


@dataclass(frozen=True)
class ActiveModeResidueSensitivitySystem:
    """Linearized active singular-mode constraints for residue perturbations."""

    A_ineq: np.ndarray
    b_ineq: np.ndarray
    constraint_frequencies_hz: tuple[float, ...]
    constraint_sigmas: tuple[float, ...]
    constraint_mode_indices: tuple[int, ...]
    real_poles: tuple[tuple[int, float], ...]
    complex_pairs: tuple[tuple[int, int, float, float], ...]
    response_indices: tuple[int, ...]
    full_variable_indices: np.ndarray
    full_variable_count: int
    residue_variable_count: int
    constant_variable_count: int
    perturb_constant: bool

    @property
    def constraint_count(self) -> int:
        return int(self.A_ineq.shape[0])

    @property
    def variable_count(self) -> int:
        return int(self.A_ineq.shape[1])

    @property
    def vars_per_response(self) -> int:
        return len(self.real_poles) + (2 * len(self.complex_pairs))

    def diagnostics(self) -> dict[str, Any]:
        return {
            "constraint_count": self.constraint_count,
            "variable_count": self.variable_count,
            "full_variable_count": int(self.full_variable_count),
            "response_count": len(self.response_indices),
            "response_indices": list(self.response_indices),
            "residue_variable_count": int(self.residue_variable_count),
            "constant_variable_count": int(self.constant_variable_count),
            "constraint_rank": int(np.linalg.matrix_rank(self.A_ineq)),
            "constraint_condition_number": float(_safe_condition_number(self.A_ineq)),
            "finite": bool(np.all(np.isfinite(self.A_ineq)) and np.all(np.isfinite(self.b_ineq))),
            "constraint_frequencies_hz": list(self.constraint_frequencies_hz),
            "constraint_mode_indices": list(self.constraint_mode_indices),
        }


@dataclass(frozen=True)
class _PassivityScore:
    violation_count: int
    max_sigma: float

    def is_better_than(self, other: "_PassivityScore | None") -> bool:
        if other is None:
            return True
        return (self.max_sigma, self.violation_count) < (other.max_sigma, other.violation_count)


def _is_candidate_update_better(
    candidate_score: _PassivityScore,
    candidate_delta_norm: float,
    best_score: _PassivityScore | None,
    best_delta_norm: float,
    *,
    candidate_priority: int = 0,
    best_priority: int = 0,
    score_abs_tol: float = 0.0,
) -> bool:
    if best_score is None:
        return True

    sigma_improvement = best_score.max_sigma - candidate_score.max_sigma
    if candidate_priority > best_priority and sigma_improvement <= score_abs_tol:
        return False
    if (
        candidate_priority < best_priority
        and candidate_score.max_sigma <= best_score.max_sigma + score_abs_tol
        and candidate_score.violation_count <= best_score.violation_count
    ):
        return True

    if candidate_score.is_better_than(best_score):
        return True
    if abs(candidate_score.max_sigma - best_score.max_sigma) > score_abs_tol:
        return False
    if candidate_score.violation_count < best_score.violation_count:
        return True
    if candidate_score.violation_count > best_score.violation_count:
        return False
    if candidate_priority < best_priority:
        return True
    if candidate_priority > best_priority:
        return False
    return candidate_delta_norm < best_delta_norm


def _should_try_fit_weighted_qp(accepted_score: _PassivityScore | None) -> bool:
    _ = accepted_score
    return True


def _candidate_delta_norm(
    residues_before: np.ndarray,
    residues_after: np.ndarray,
    constant_before: np.ndarray,
    constant_after: np.ndarray,
    poles_before: np.ndarray,
    poles_after: np.ndarray,
) -> float:
    residue_base = float(np.linalg.norm(residues_before))
    constant_base = float(np.linalg.norm(constant_before))
    pole_base = float(np.linalg.norm(poles_before))
    base_norm = max(residue_base + constant_base + pole_base, 1e-30)
    delta_norm = (
        float(np.linalg.norm(residues_after - residues_before))
        + float(np.linalg.norm(constant_after - constant_before))
        + float(np.linalg.norm(poles_after - poles_before))
    )
    return delta_norm / base_norm


def _trust_region_limit(
    iteration: int,
    current_score: _PassivityScore,
    *,
    base_limit: float = 0.05,
) -> float:
    _ = current_score
    return float(base_limit) / math.sqrt(float(iteration) + 1.0)


def _global_damping_factor(
    *,
    max_sigma: float,
    epsilon: float,
    safety_margin: float = 1e-5,
) -> float:
    sigma = float(max_sigma)
    if sigma <= 1.0 + float(epsilon):
        return 1.0
    target = max(0.0, 1.0 - float(epsilon) - float(safety_margin))
    if target <= 0.0 or not np.isfinite(sigma) or sigma <= 0.0:
        return 1.0
    return min(1.0, target / sigma)


def _apply_selective_pole_damping(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    damping_factor: float,
    min_frequency_hz: float,
) -> tuple[np.ndarray, np.ndarray]:
    pole_array = np.asarray(poles, dtype=complex).reshape(-1)
    damped_residues = np.asarray(residues, dtype=complex).copy()
    damped_constant = np.asarray(constant_coeff, dtype=complex).copy()
    factor = float(damping_factor)
    threshold_rad = max(0.0, float(min_frequency_hz)) * 2.0 * np.pi
    pole_rates = np.maximum(np.abs(np.imag(pole_array)), np.abs(np.real(pole_array)))
    high_frequency_mask = pole_rates >= threshold_rad
    if high_frequency_mask.size:
        damped_residues[:, high_frequency_mask] *= factor
    damped_constant *= factor
    return damped_residues, damped_constant


def _optimized_pole_damping_global_energy_weights(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
) -> np.ndarray:
    pole_array = np.asarray(poles, dtype=complex).reshape(-1)
    residue_array = np.asarray(residues, dtype=complex)
    constant_array = np.asarray(constant_coeff, dtype=complex)
    weights = np.full(len(pole_array) + 1, 1e-18, dtype=float)
    for pole_idx, pole in enumerate(pole_array):
        residue_norm_sq = float(np.vdot(residue_array[:, pole_idx], residue_array[:, pole_idx]).real)
        decay_rate = max(abs(float(np.real(pole))), 1e-18)
        weights[pole_idx] = max(residue_norm_sq / (2.0 * decay_rate), 1e-18)
    weights[-1] = max(float(np.vdot(constant_array, constant_array).real), 1e-18)
    scale = max(float(np.max(weights)), 1e-18)
    return np.maximum(weights / scale, 1e-12)


def _optimized_pole_damping_candidate(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
    damping_factor: float,
    epsilon: float,
    safety_margin: float = 1e-5,
    max_beta_scale: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    pole_array = np.asarray(poles, dtype=complex).reshape(-1)
    residue_array = np.asarray(residues, dtype=complex)
    constant_array = np.asarray(constant_coeff, dtype=complex)
    freq_list = [float(freq) for freq in freqs]
    max_beta = max(0.0, min(0.25, (1.0 - float(damping_factor)) * max(1.0, float(max_beta_scale))))
    variable_count = len(pole_array) + 1
    if max_beta <= 0.0 or not freq_list or variable_count == 0:
        return residue_array.copy(), constant_array.copy(), {
            "success": False,
            "message": "no damping variables",
        }

    target_norm = max(0.0, 1.0 - float(epsilon) - float(safety_margin))
    constraint_rows: list[np.ndarray] = []
    constraint_rhs: list[float] = []
    for freq in freq_list:
        current = _evaluate_s_matrix_at_freq(
            pole_array,
            residue_array,
            constant_array,
            nports=nports,
            freq=freq,
        )
        U, singular_values, Vh = la.svd(current)
        if len(singular_values) == 0:
            continue
        sigma = float(singular_values[0])
        if sigma <= target_norm:
            continue
        u_vec = U[:, 0]
        v_vec = Vh.conj().T[:, 0]
        s_val = 1j * 2.0 * np.pi * freq
        row = np.zeros(variable_count, dtype=float)
        for pole_idx, pole in enumerate(pole_array):
            component = residue_array[:, pole_idx].reshape((nports, nports)) / (s_val - pole)
            row[pole_idx] = float(np.real(np.vdot(u_vec, component @ v_vec)))
        constant_component = constant_array.reshape((nports, nports))
        row[-1] = float(np.real(np.vdot(u_vec, constant_component @ v_vec)))
        constraint_rows.append(row)
        constraint_rhs.append(sigma - target_norm)
    if not constraint_rows:
        return residue_array.copy(), constant_array.copy(), {
            "success": False,
            "message": "no active damping constraints",
        }

    A = np.asarray(constraint_rows, dtype=float)
    b = np.asarray(constraint_rhs, dtype=float)
    weights = _optimized_pole_damping_global_energy_weights(pole_array, residue_array, constant_array)

    def objective(beta: np.ndarray) -> float:
        return float(np.sum(weights * beta * beta))

    def gradient(beta: np.ndarray) -> np.ndarray:
        return 2.0 * weights * beta

    constraints = ({"type": "ineq", "fun": lambda beta: A @ beta - b, "jac": lambda beta: A},)
    initial_beta = np.full(variable_count, max_beta, dtype=float)
    result = opt.minimize(
        objective,
        x0=initial_beta,
        jac=gradient,
        bounds=[(0.0, max_beta)] * variable_count,
        constraints=constraints,
        method="SLSQP",
        options={"maxiter": 100, "ftol": 1e-10},
    )
    if not result.success:
        return residue_array.copy(), constant_array.copy(), {
            "success": False,
            "message": str(result.message),
            "constraint_count": int(A.shape[0]),
            "variable_count": int(variable_count),
            "max_beta": float(max_beta),
            "weight_min": float(np.min(weights)) if len(weights) else 0.0,
            "weight_max": float(np.max(weights)) if len(weights) else 0.0,
        }

    beta = np.asarray(result.x, dtype=float)
    damped_residues = residue_array.copy()
    for pole_idx in range(len(pole_array)):
        damped_residues[:, pole_idx] *= 1.0 - beta[pole_idx]
    damped_constant = constant_array * (1.0 - beta[-1])
    residual = A @ beta - b
    return damped_residues, damped_constant, {
        "success": True,
        "message": str(result.message),
        "constraint_count": int(A.shape[0]),
        "variable_count": int(variable_count),
        "max_beta": float(np.max(beta)) if len(beta) else 0.0,
        "mean_beta": float(np.mean(beta)) if len(beta) else 0.0,
        "d_beta": float(beta[-1]),
        "pole_beta_max": float(np.max(beta[:-1])) if len(beta) > 1 else 0.0,
        "weight_min": float(np.min(weights)) if len(weights) else 0.0,
        "weight_max": float(np.max(weights)) if len(weights) else 0.0,
        "linearized_min_margin": float(np.min(residual)) if len(residual) else 0.0,
    }


def _validate_candidate_on_holdout(
    *,
    sampled_score: _PassivityScore,
    candidate_score: _PassivityScore,
    holdout_score: _PassivityScore,
    candidate_holdout_score: _PassivityScore,
    candidate_delta_norm: float,
    trust_region_limit: float,
    candidate_improves_best: bool,
) -> tuple[bool, dict[str, Any]]:
    candidate_improves_sample = candidate_score.is_better_than(sampled_score)
    candidate_preserves_holdout = candidate_holdout_score.max_sigma <= holdout_score.max_sigma + 1e-10
    candidate_within_trust = candidate_delta_norm <= trust_region_limit
    accepted = (
        candidate_improves_sample
        and candidate_preserves_holdout
        and candidate_within_trust
        and candidate_improves_best
    )
    reject_reason = None
    if not candidate_improves_sample:
        reject_reason = "no_sampled_improvement"
    elif not candidate_preserves_holdout:
        reject_reason = "holdout_regression"
    elif not candidate_within_trust:
        reject_reason = "trust_region_exceeded"
    elif not candidate_improves_best:
        reject_reason = "worse_than_selected_candidate"
    return accepted, {
        "reject_reason": reject_reason,
        "candidate_delta_norm": float(candidate_delta_norm),
        "trust_region_limit": float(trust_region_limit),
        "candidate_within_trust": bool(candidate_within_trust),
        "candidate_preserves_holdout": bool(candidate_preserves_holdout),
        "candidate_improves_sample": bool(candidate_improves_sample),
    }


def _full_frequency_passivity_score(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    epsilon: float,
    f_max: float | None,
    max_violation_samples: int,
) -> _PassivityScore:
    crossover_freqs = check_passivity_hamiltonian_s(
        poles,
        residues,
        constant_coeff,
        nports,
        f_max=f_max,
    )
    f_limit = 100e9
    if crossover_freqs:
        f_limit = max(f_limit, float(crossover_freqs[-1]) * 2.0)
    if f_max is not None:
        f_limit = min(f_limit, float(f_max))
    points = [0.0, *crossover_freqs, f_limit]
    violating_freqs = _adaptive_violation_frequencies_for_enforcement(
        poles,
        residues,
        constant_coeff,
        nports=nports,
        points=points,
        epsilon=epsilon,
        max_violation_samples=max_violation_samples,
        f_max=f_max,
        max_depth=2,
        curvature_tol=1e-3,
    )
    if not violating_freqs:
        return _PassivityScore(0, 1.0)
    return _PassivityScore(
        violation_count=len(violating_freqs),
        max_sigma=max(float(sigma) for _freq, sigma in violating_freqs),
    )


def _best_passivity_snapshot(
    candidate_residues: np.ndarray,
    candidate_score: _PassivityScore,
    best_residues: np.ndarray,
    best_score: _PassivityScore | None,
) -> tuple[np.ndarray, _PassivityScore | None]:
    if candidate_score.is_better_than(best_score):
        return candidate_residues.copy(), candidate_score
    return best_residues, best_score


def _line_search_eval_frequencies(points: list[float], violating_freqs: list[tuple[float, float]]) -> list[float]:
    eval_freqs: set[float] = set()
    for violating_freq, _sigma in violating_freqs:
        eval_freqs.add(float(violating_freq))
        for idx in range(len(points) - 1):
            start = float(points[idx])
            stop = float(points[idx + 1])
            if start <= violating_freq <= stop:
                eval_freqs.add((start + float(violating_freq)) / 2.0)
                eval_freqs.add((float(violating_freq) + stop) / 2.0)
                break
    return sorted(eval_freqs)


def _safe_condition_number(matrix: np.ndarray) -> float:
    if matrix.size == 0:
        return 0.0
    try:
        value = float(np.linalg.cond(matrix))
    except np.linalg.LinAlgError:
        return np.inf
    return value


def _qp_attempt_diagnostic(
    *,
    iteration: int,
    active_budget: int,
    active_matrix: np.ndarray,
    qp_result: PassivityQpResult,
    A_ineq: np.ndarray,
    b_ineq: np.ndarray,
    x_delta: np.ndarray,
    scale: float,
    sampled_score: _PassivityScore,
    candidate_score: _PassivityScore,
    accepted: bool,
    reject_reason: str | None,
    variable_weights: np.ndarray | None = None,
) -> dict[str, Any]:
    predicted_sigma = float(np.max(1.0 - b_ineq + A_ineq @ (x_delta * scale)))
    diagnostic = {
        "iteration": int(iteration),
        "active_budget": int(active_budget),
        "active_rank": int(np.linalg.matrix_rank(active_matrix)),
        "active_condition_number": float(_safe_condition_number(active_matrix)),
        "dual_condition_number": float(qp_result.dual_condition_number),
        "dual_regularization": float(qp_result.regularization),
        "scale": float(scale),
        "sampled_max_sigma_before": float(sampled_score.max_sigma),
        "candidate_max_sigma_after": float(candidate_score.max_sigma),
        "predicted_max_sigma_after": predicted_sigma,
        "predicted_improvement": float(sampled_score.max_sigma - predicted_sigma),
        "actual_improvement": float(sampled_score.max_sigma - candidate_score.max_sigma),
        "candidate_violation_count_after": int(candidate_score.violation_count),
        "line_search_accepted": bool(accepted),
        "selected_for_iteration": False,
        "accepted": bool(accepted),
        "reject_reason": reject_reason,
        "qp_success": bool(qp_result.success),
        "qp_message": qp_result.message,
    }
    if variable_weights is not None:
        diagnostic["active_weight_min"] = float(np.min(variable_weights))
        diagnostic["active_weight_max"] = float(np.max(variable_weights))
        diagnostic["weighted_delta_norm"] = float(np.linalg.norm(np.sqrt(variable_weights) * x_delta * scale))
    if qp_result.slack is not None:
        diagnostic["qp_slack"] = float(qp_result.slack)
    return diagnostic


@dataclass(frozen=True)
class PassivitySampleReport:
    max_sigma: float
    max_sigma_frequency_hz: float
    violation_bands_hz: list[list[float]]
    frequency_points: int
    chunk_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_sigma": self.max_sigma,
            "max_sigma_frequency_hz": self.max_sigma_frequency_hz,
            "violation_bands_hz": self.violation_bands_hz,
            "frequency_points": self.frequency_points,
            "chunk_size": self.chunk_size,
        }


def _chunks(values: np.ndarray, chunk_size: int):
    for start in range(0, len(values), chunk_size):
        yield values[start : start + chunk_size]


def sample_streaming_singular_values(
    s_provider: Callable[[np.ndarray], np.ndarray],
    freqs: Any,
    *,
    nports: int,
    chunk_size: int = 32,
    epsilon: float = 1e-6,
) -> PassivitySampleReport:
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    if nports < 1:
        raise ValueError("nports must be >= 1")
    freq_array = np.asarray(freqs, dtype=float)
    if len(freq_array) == 0:
        raise ValueError("freqs must contain at least one sample")

    max_sigma = -np.inf
    max_sigma_frequency_hz = float(freq_array[0])
    violation_bands: list[list[float]] = []
    open_violation_start: float | None = None
    last_violation_freq: float | None = None

    for chunk_freqs in _chunks(freq_array, chunk_size):
        s_chunk = np.asarray(s_provider(chunk_freqs), dtype=complex)
        expected_shape = (len(chunk_freqs), nports, nports)
        if s_chunk.shape != expected_shape:
            raise ValueError(f"provider returned shape {s_chunk.shape}, expected {expected_shape}")
        sigma = np.linalg.svd(s_chunk, compute_uv=False)
        chunk_max_by_freq = np.max(sigma, axis=1)
        chunk_argmax = int(np.argmax(chunk_max_by_freq))
        if float(chunk_max_by_freq[chunk_argmax]) > max_sigma:
            max_sigma = float(chunk_max_by_freq[chunk_argmax])
            max_sigma_frequency_hz = float(chunk_freqs[chunk_argmax])

        for freq, sample_max_sigma in zip(chunk_freqs, chunk_max_by_freq):
            if float(sample_max_sigma) > 1.0 + epsilon:
                if open_violation_start is None:
                    open_violation_start = float(freq)
                last_violation_freq = float(freq)
            elif open_violation_start is not None:
                violation_bands.append([open_violation_start, float(last_violation_freq)])
                open_violation_start = None
                last_violation_freq = None

    if open_violation_start is not None:
        violation_bands.append([open_violation_start, float(last_violation_freq)])

    return PassivitySampleReport(
        max_sigma=float(max_sigma),
        max_sigma_frequency_hz=max_sigma_frequency_hz,
        violation_bands_hz=violation_bands,
        frequency_points=int(len(freq_array)),
        chunk_size=int(chunk_size),
    )


def sample_vector_fit_passivity(
    vector_fit: Any,
    freqs: Any,
    *,
    nports: int,
    chunk_size: int = 32,
    epsilon: float = 1e-6,
) -> PassivitySampleReport:
    def provider(chunk_freqs: np.ndarray) -> np.ndarray:
        s_chunk = np.empty((len(chunk_freqs), nports, nports), dtype=complex)
        for row in range(nports):
            for column in range(nports):
                values = vector_fit.get_model_response(row, column, freqs=chunk_freqs)
                if len(values) != len(chunk_freqs):
                    raise ValueError(
                        f"model response length {len(values)} for S{row + 1}{column + 1}, expected {len(chunk_freqs)}"
                    )
                s_chunk[:, row, column] = np.asarray(values, dtype=complex)
        return s_chunk

    return sample_streaming_singular_values(
        provider,
        freqs,
        nports=nports,
        chunk_size=chunk_size,
        epsilon=epsilon,
    )


def _solve_min_norm_upper_bound_dual_qp(
    A_ineq: np.ndarray,
    b_ineq: np.ndarray,
    *,
    regularization: float = 1e-8,
    variable_weights: np.ndarray | None = None,
) -> PassivityQpResult:
    """Solve min 0.5 sum(w_i x_i^2) subject to A_ineq x <= b_ineq through its small dual."""
    A_ineq = np.asarray(A_ineq, dtype=float)
    b_ineq = np.asarray(b_ineq, dtype=float)
    if A_ineq.ndim != 2:
        raise ValueError("A_ineq must be a 2D array")
    if b_ineq.ndim != 1 or b_ineq.shape[0] != A_ineq.shape[0]:
        raise ValueError("b_ineq must be a vector with one entry per constraint")
    if variable_weights is None:
        inverse_weights = np.ones(A_ineq.shape[1], dtype=float)
    else:
        weights = np.asarray(variable_weights, dtype=float)
        if weights.ndim != 1 or weights.shape[0] != A_ineq.shape[1]:
            raise ValueError("variable_weights must contain one positive entry per variable")
        if np.any(weights <= 0.0) or not np.all(np.isfinite(weights)):
            raise ValueError("variable_weights must contain finite positive values")
        inverse_weights = 1.0 / weights
    if A_ineq.shape[0] == 0:
        return PassivityQpResult(x=np.zeros(A_ineq.shape[1]), success=True, message="no constraints")

    weighted_A_t = inverse_weights[:, None] * A_ineq.T
    K = A_ineq @ weighted_A_t
    regularization_value = 0.0
    if regularization > 0.0:
        scale = float(np.max(np.abs(K))) if K.size else 0.0
        if scale > 0.0:
            regularization_value = regularization * scale
            K = K + regularization_value * np.eye(K.shape[0])
    dual_condition_number = _safe_condition_number(K)
    result = opt.minimize(
        fun=lambda lmbda: 0.5 * lmbda @ K @ lmbda + b_ineq @ lmbda,
        x0=np.zeros(len(b_ineq)),
        bounds=[(0.0, None)] * len(b_ineq),
        method="SLSQP",
        options={"maxiter": 100, "ftol": 1e-8},
    )
    if not result.success:
        return PassivityQpResult(
            x=np.zeros(A_ineq.shape[1]),
            success=False,
            message=str(result.message),
            regularization=regularization_value,
            dual_condition_number=dual_condition_number,
        )
    return PassivityQpResult(
        x=-(inverse_weights * (A_ineq.T @ result.x)),
        success=True,
        message=str(result.message),
        regularization=regularization_value,
        dual_condition_number=dual_condition_number,
    )


def _solve_min_norm_upper_bound_nnls(
    A_ineq: np.ndarray,
    b_ineq: np.ndarray,
    *,
    regularization: float = 1e-8,
    variable_weights: np.ndarray | None = None,
) -> PassivityQpResult:
    """Solve the min-norm upper-bound problem through its NNLS dual form.

    For ``min 0.5 x' W x`` subject to ``A x <= b``, the nonnegative dual
    is a least-squares problem after a Cholesky factorization of
    ``A W^-1 A'``. The Gram matrix is only constraint-sized; response-space
    compression must therefore happen before this solver is called.
    """
    A_ineq = np.asarray(A_ineq, dtype=float)
    b_ineq = np.asarray(b_ineq, dtype=float)
    if A_ineq.ndim != 2:
        raise ValueError("A_ineq must be a 2D array")
    if b_ineq.ndim != 1 or b_ineq.shape[0] != A_ineq.shape[0]:
        raise ValueError("b_ineq must be a vector with one entry per constraint")
    if variable_weights is None:
        inverse_weights = np.ones(A_ineq.shape[1], dtype=float)
    else:
        weights = np.asarray(variable_weights, dtype=float)
        if weights.ndim != 1 or weights.shape[0] != A_ineq.shape[1]:
            raise ValueError("variable_weights must contain one positive entry per variable")
        if np.any(weights <= 0.0) or not np.all(np.isfinite(weights)):
            raise ValueError("variable_weights must contain finite positive values")
        inverse_weights = 1.0 / weights
    if A_ineq.shape[0] == 0:
        return PassivityQpResult(x=np.zeros(A_ineq.shape[1]), success=True, message="no constraints")

    gram = A_ineq @ (inverse_weights[:, None] * A_ineq.T)
    regularization_value = 0.0
    if regularization > 0.0:
        scale = float(np.max(np.abs(gram))) if gram.size else 0.0
        if scale > 0.0:
            regularization_value = float(regularization) * scale
            gram = gram + regularization_value * np.eye(gram.shape[0])
    dual_condition_number = _safe_condition_number(gram)
    if not np.all(np.isfinite(gram)):
        return PassivityQpResult(
            x=np.zeros(A_ineq.shape[1]),
            success=False,
            message="non-finite NNLS dual Gram matrix",
            regularization=regularization_value,
            dual_condition_number=dual_condition_number,
        )
    try:
        lower = la.cholesky(gram, lower=True, check_finite=False)
        rhs = -la.solve_triangular(lower, b_ineq, lower=True, check_finite=False)
        dual, residual_norm = opt.nnls(lower.T, rhs)
    except (la.LinAlgError, ValueError) as exc:
        return PassivityQpResult(
            x=np.zeros(A_ineq.shape[1]),
            success=False,
            message=f"NNLS dual factorization failed: {exc}",
            regularization=regularization_value,
            dual_condition_number=dual_condition_number,
        )
    x_value = -(inverse_weights * (A_ineq.T @ dual))
    slack = max(float(np.max(A_ineq @ x_value - b_ineq)), 0.0)
    return PassivityQpResult(
        x=x_value,
        success=bool(np.all(np.isfinite(x_value))),
        message=f"nnls residual={float(residual_norm):.6g}",
        regularization=regularization_value,
        dual_condition_number=dual_condition_number,
        slack=slack,
    )


def _minimax_step_regularization(
    A_ineq: np.ndarray,
    b_ineq: np.ndarray,
    *,
    variable_weights: np.ndarray | None = None,
) -> float:
    A_ineq = np.asarray(A_ineq, dtype=float)
    b_ineq = np.asarray(b_ineq, dtype=float)
    if A_ineq.size == 0:
        return 1.0
    if variable_weights is None:
        inverse_weights = np.ones(A_ineq.shape[1], dtype=float)
    else:
        weights = np.asarray(variable_weights, dtype=float)
        inverse_weights = 1.0 / np.maximum(weights, 1e-300)
    weighted_A_t = inverse_weights[:, None] * A_ineq.T
    sensitivity_scale = float(np.max(np.abs(A_ineq @ weighted_A_t)))
    violation_scale = max(float(np.max(np.maximum(-b_ineq, 0.0))), 1e-12)
    if sensitivity_scale <= 0.0 or not np.isfinite(sensitivity_scale):
        return 1.0
    return max(sensitivity_scale / violation_scale, 1e-12)


def _minimax_slack_weight_candidates() -> list[float]:
    return [1.0]


def _edge_constraint_row_indices(
    row_frequencies_hz: Any,
    *,
    edge_frequency_hz: float,
    relative_window: float = 0.02,
) -> np.ndarray:
    freqs = np.asarray(row_frequencies_hz, dtype=float)
    if freqs.size == 0 or edge_frequency_hz <= 0.0:
        return np.array([], dtype=int)
    lower = float(edge_frequency_hz) * max(0.0, 1.0 - float(relative_window))
    indices = np.flatnonzero((freqs >= lower) & (freqs <= float(edge_frequency_hz)))
    return indices.astype(int)


def _solve_minimax_slack_upper_bound_dual_qp(
    A_ineq: np.ndarray,
    b_ineq: np.ndarray,
    *,
    step_regularization: float = 1.0,
    slack_weight: float = 1.0,
    regularization: float = 1e-8,
    variable_weights: np.ndarray | None = None,
) -> PassivityQpResult:
    """Solve min slack_weight*t + 0.5*rho*sum(w_i*x_i^2), A*x <= b + t, t >= 0."""
    A_ineq = np.asarray(A_ineq, dtype=float)
    b_ineq = np.asarray(b_ineq, dtype=float)
    if A_ineq.ndim != 2:
        raise ValueError("A_ineq must be a 2D array")
    if b_ineq.ndim != 1 or b_ineq.shape[0] != A_ineq.shape[0]:
        raise ValueError("b_ineq must be a vector with one entry per constraint")
    if step_regularization <= 0.0 or not np.isfinite(step_regularization):
        raise ValueError("step_regularization must be finite and positive")
    if slack_weight <= 0.0 or not np.isfinite(slack_weight):
        raise ValueError("slack_weight must be finite and positive")
    if variable_weights is None:
        inverse_weights = np.ones(A_ineq.shape[1], dtype=float)
    else:
        weights = np.asarray(variable_weights, dtype=float)
        if weights.ndim != 1 or weights.shape[0] != A_ineq.shape[1]:
            raise ValueError("variable_weights must contain one positive entry per variable")
        if np.any(weights <= 0.0) or not np.all(np.isfinite(weights)):
            raise ValueError("variable_weights must contain finite positive values")
        inverse_weights = 1.0 / weights
    if A_ineq.shape[0] == 0:
        return PassivityQpResult(x=np.zeros(A_ineq.shape[1]), success=True, message="no constraints", slack=0.0)

    weighted_A_t = inverse_weights[:, None] * A_ineq.T
    K = (A_ineq @ weighted_A_t) / float(step_regularization)
    regularization_value = 0.0
    if regularization > 0.0:
        scale = float(np.max(np.abs(K))) if K.size else 0.0
        if scale > 0.0:
            regularization_value = regularization * scale
            K = K + regularization_value * np.eye(K.shape[0])
    dual_condition_number = _safe_condition_number(K)
    result = opt.minimize(
        fun=lambda lmbda: 0.5 * lmbda @ K @ lmbda + b_ineq @ lmbda,
        x0=np.zeros(len(b_ineq)),
        bounds=[(0.0, None)] * len(b_ineq),
        constraints=({"type": "ineq", "fun": lambda lmbda: float(slack_weight) - np.sum(lmbda)},),
        method="SLSQP",
        options={"maxiter": 100, "ftol": 1e-8},
    )
    if not result.success:
        return PassivityQpResult(
            x=np.zeros(A_ineq.shape[1]),
            success=False,
            message=str(result.message),
            regularization=regularization_value,
            dual_condition_number=dual_condition_number,
        )
    x_value = -(inverse_weights * (A_ineq.T @ result.x)) / float(step_regularization)
    slack_value = max(float(np.max(A_ineq @ x_value - b_ineq)), 0.0)
    return PassivityQpResult(
        x=x_value,
        success=True,
        message=str(result.message),
        regularization=regularization_value,
        dual_condition_number=dual_condition_number,
        slack=slack_value,
    )


def _solve_reference_regularized_upper_bound_dual_qp(
    A_ineq: np.ndarray,
    b_ineq: np.ndarray,
    C_ref: np.ndarray,
    d_ref: np.ndarray,
    *,
    reference_weight: float,
    regularization: float = 1e-8,
    variable_weights: np.ndarray | None = None,
) -> PassivityQpResult:
    """Solve weighted min-norm QP with a raw-reference LS term through a small dual."""
    A_ineq = np.asarray(A_ineq, dtype=float)
    b_ineq = np.asarray(b_ineq, dtype=float)
    C_ref = np.asarray(C_ref, dtype=float)
    d_ref = np.asarray(d_ref, dtype=float)
    if A_ineq.ndim != 2:
        raise ValueError("A_ineq must be a 2D array")
    if b_ineq.ndim != 1 or b_ineq.shape[0] != A_ineq.shape[0]:
        raise ValueError("b_ineq must be a vector with one entry per constraint")
    if C_ref.ndim != 2 or C_ref.shape[1] != A_ineq.shape[1]:
        raise ValueError("C_ref must be a 2D matrix with one column per variable")
    if d_ref.ndim != 1 or d_ref.shape[0] != C_ref.shape[0]:
        raise ValueError("d_ref must be a vector with one entry per reference row")
    if reference_weight <= 0.0 or not np.isfinite(reference_weight):
        raise ValueError("reference_weight must be finite and positive")
    if variable_weights is None:
        weights = np.ones(A_ineq.shape[1], dtype=float)
    else:
        weights = np.asarray(variable_weights, dtype=float)
        if weights.ndim != 1 or weights.shape[0] != A_ineq.shape[1]:
            raise ValueError("variable_weights must contain one positive entry per variable")
        if np.any(weights <= 0.0) or not np.all(np.isfinite(weights)):
            raise ValueError("variable_weights must contain finite positive values")
    H = np.diag(weights) + float(reference_weight) * (C_ref.T @ C_ref)
    h = float(reference_weight) * (C_ref.T @ d_ref)
    regularization_value = 0.0
    if regularization > 0.0:
        scale = max(float(np.max(np.abs(H))) if H.size else 0.0, 1.0)
        regularization_value = regularization * scale
        H = H + regularization_value * np.eye(H.shape[0])
    primal_condition_number = _safe_condition_number(H)
    try:
        h_solve = la.solve(H, h, assume_a="pos")
        Hinv_A_t = la.solve(H, A_ineq.T, assume_a="pos")
    except Exception as exc:
        return PassivityQpResult(
            x=np.zeros(A_ineq.shape[1]),
            success=False,
            message=f"reference regularized solve failed: {exc}",
            regularization=regularization_value,
            dual_condition_number=primal_condition_number,
        )
    if A_ineq.shape[0] == 0:
        return PassivityQpResult(
            x=h_solve,
            success=True,
            message="no constraints",
            regularization=regularization_value,
            dual_condition_number=primal_condition_number,
        )
    K = A_ineq @ Hinv_A_t
    dual_linear = b_ineq - A_ineq @ h_solve
    dual_condition_number = _safe_condition_number(K)
    result = opt.minimize(
        fun=lambda lmbda: 0.5 * lmbda @ K @ lmbda + dual_linear @ lmbda,
        x0=np.zeros(len(b_ineq)),
        bounds=[(0.0, None)] * len(b_ineq),
        method="SLSQP",
        options={"maxiter": 100, "ftol": 1e-8},
    )
    if not result.success:
        return PassivityQpResult(
            x=np.zeros(A_ineq.shape[1]),
            success=False,
            message=str(result.message),
            regularization=regularization_value,
            dual_condition_number=dual_condition_number,
        )
    return PassivityQpResult(
        x=h_solve - Hinv_A_t @ result.x,
        success=True,
        message=str(result.message),
        regularization=regularization_value,
        dual_condition_number=dual_condition_number,
    )


def _solve_reference_regularized_upper_bound_nnls(
    A_ineq: np.ndarray,
    b_ineq: np.ndarray,
    C_ref: np.ndarray,
    d_ref: np.ndarray,
    *,
    reference_weight: float,
    regularization: float = 1e-8,
    variable_weights: np.ndarray | None = None,
) -> PassivityQpResult:
    """Reference-regularized upper-bound solve using a nonnegative LS dual."""
    A_ineq = np.asarray(A_ineq, dtype=float)
    b_ineq = np.asarray(b_ineq, dtype=float)
    C_ref = np.asarray(C_ref, dtype=float)
    d_ref = np.asarray(d_ref, dtype=float)
    if A_ineq.ndim != 2:
        raise ValueError("A_ineq must be a 2D array")
    if b_ineq.ndim != 1 or b_ineq.shape[0] != A_ineq.shape[0]:
        raise ValueError("b_ineq must be a vector with one entry per constraint")
    if C_ref.ndim != 2 or C_ref.shape[1] != A_ineq.shape[1]:
        raise ValueError("C_ref must be a 2D matrix with one column per variable")
    if d_ref.ndim != 1 or d_ref.shape[0] != C_ref.shape[0]:
        raise ValueError("d_ref must be a vector with one entry per reference row")
    if reference_weight <= 0.0 or not np.isfinite(reference_weight):
        raise ValueError("reference_weight must be finite and positive")
    if variable_weights is None:
        weights = np.ones(A_ineq.shape[1], dtype=float)
    else:
        weights = np.asarray(variable_weights, dtype=float)
        if weights.ndim != 1 or weights.shape[0] != A_ineq.shape[1]:
            raise ValueError("variable_weights must contain one positive entry per variable")
        if np.any(weights <= 0.0) or not np.all(np.isfinite(weights)):
            raise ValueError("variable_weights must contain finite positive values")

    hessian = np.diag(weights) + float(reference_weight) * (C_ref.T @ C_ref)
    linear = float(reference_weight) * (C_ref.T @ d_ref)
    regularization_value = 0.0
    if regularization > 0.0:
        scale = max(float(np.max(np.abs(hessian))) if hessian.size else 0.0, 1.0)
        regularization_value = float(regularization) * scale
        hessian = hessian + regularization_value * np.eye(hessian.shape[0])
    try:
        unconstrained = la.solve(hessian, linear, assume_a="pos")
        hessian_inverse_a_t = la.solve(hessian, A_ineq.T, assume_a="pos")
    except Exception as exc:
        return PassivityQpResult(
            x=np.zeros(A_ineq.shape[1]),
            success=False,
            message=f"reference regularized NNLS solve failed: {exc}",
            regularization=regularization_value,
            dual_condition_number=_safe_condition_number(hessian),
        )
    if A_ineq.shape[0] == 0:
        return PassivityQpResult(
            x=unconstrained,
            success=True,
            message="no constraints",
            regularization=regularization_value,
            dual_condition_number=_safe_condition_number(hessian),
        )

    dual_gram = A_ineq @ hessian_inverse_a_t
    dual_linear = b_ineq - A_ineq @ unconstrained
    dual_regularization = 0.0
    try:
        lower = la.cholesky(dual_gram, lower=True, check_finite=False)
    except la.LinAlgError:
        scale = max(float(np.max(np.abs(dual_gram))) if dual_gram.size else 0.0, 1.0)
        dual_regularization = float(regularization) * scale
        dual_gram = dual_gram + dual_regularization * np.eye(dual_gram.shape[0])
        try:
            lower = la.cholesky(dual_gram, lower=True, check_finite=False)
        except la.LinAlgError as exc:
            return PassivityQpResult(
                x=np.zeros(A_ineq.shape[1]),
                success=False,
                message=f"reference regularized NNLS dual factorization failed: {exc}",
                regularization=regularization_value + dual_regularization,
                dual_condition_number=_safe_condition_number(dual_gram),
            )
    try:
        rhs = -la.solve_triangular(lower, dual_linear, lower=True, check_finite=False)
        dual, residual_norm = opt.nnls(lower.T, rhs)
    except (la.LinAlgError, ValueError) as exc:
        return PassivityQpResult(
            x=np.zeros(A_ineq.shape[1]),
            success=False,
            message=f"reference regularized NNLS failed: {exc}",
            regularization=regularization_value + dual_regularization,
            dual_condition_number=_safe_condition_number(dual_gram),
        )
    x_value = unconstrained - hessian_inverse_a_t @ dual
    slack = max(float(np.max(A_ineq @ x_value - b_ineq)), 0.0)
    return PassivityQpResult(
        x=x_value,
        success=bool(np.all(np.isfinite(x_value))),
        message=f"reference nnls residual={float(residual_norm):.6g}",
        regularization=regularization_value + dual_regularization,
        dual_condition_number=_safe_condition_number(dual_gram),
        slack=slack,
    )


def _solve_reference_regularized_peak_minimax_dual_qp(
    A_ineq: np.ndarray,
    b_ineq: np.ndarray,
    C_ref: np.ndarray,
    d_ref: np.ndarray,
    *,
    reference_weight: float,
    regularization: float = 1e-8,
    variable_weights: np.ndarray | None = None,
) -> PassivityQpResult:
    """Minimize the worst linearized residual plus the raw-reference quadratic term."""
    A_ineq = np.asarray(A_ineq, dtype=float)
    b_ineq = np.asarray(b_ineq, dtype=float)
    C_ref = np.asarray(C_ref, dtype=float)
    d_ref = np.asarray(d_ref, dtype=float)
    if A_ineq.ndim != 2:
        raise ValueError("A_ineq must be a 2D array")
    if b_ineq.ndim != 1 or b_ineq.shape[0] != A_ineq.shape[0]:
        raise ValueError("b_ineq must be a vector with one entry per constraint")
    if C_ref.ndim != 2 or C_ref.shape[1] != A_ineq.shape[1]:
        raise ValueError("C_ref must be a 2D matrix with one column per variable")
    if d_ref.ndim != 1 or d_ref.shape[0] != C_ref.shape[0]:
        raise ValueError("d_ref must be a vector with one entry per reference row")
    if reference_weight <= 0.0 or not np.isfinite(reference_weight):
        raise ValueError("reference_weight must be finite and positive")
    if variable_weights is None:
        weights = np.ones(A_ineq.shape[1], dtype=float)
    else:
        weights = np.asarray(variable_weights, dtype=float)
        if weights.ndim != 1 or weights.shape[0] != A_ineq.shape[1]:
            raise ValueError("variable_weights must contain one positive entry per variable")
        if np.any(weights <= 0.0) or not np.all(np.isfinite(weights)):
            raise ValueError("variable_weights must contain finite positive values")
    H = np.diag(weights) + float(reference_weight) * (C_ref.T @ C_ref)
    h = float(reference_weight) * (C_ref.T @ d_ref)
    regularization_value = 0.0
    if regularization > 0.0:
        scale = max(float(np.max(np.abs(H))) if H.size else 0.0, 1.0)
        regularization_value = regularization * scale
        H = H + regularization_value * np.eye(H.shape[0])
    primal_condition_number = _safe_condition_number(H)
    try:
        h_solve = la.solve(H, h, assume_a="pos")
        Hinv_A_t = la.solve(H, A_ineq.T, assume_a="pos")
    except Exception as exc:
        return PassivityQpResult(
            x=np.zeros(A_ineq.shape[1]),
            success=False,
            message=f"reference peak-minimax solve failed: {exc}",
            regularization=regularization_value,
            dual_condition_number=primal_condition_number,
        )
    if A_ineq.shape[0] == 0:
        return PassivityQpResult(
            x=h_solve,
            success=True,
            message="no constraints",
            regularization=regularization_value,
            dual_condition_number=primal_condition_number,
            slack=0.0,
        )
    K = A_ineq @ Hinv_A_t
    dual_linear = b_ineq - A_ineq @ h_solve
    dual_condition_number = _safe_condition_number(K)
    result = opt.minimize(
        fun=lambda lmbda: 0.5 * lmbda @ K @ lmbda + dual_linear @ lmbda,
        x0=np.full(len(b_ineq), 1.0 / len(b_ineq), dtype=float),
        bounds=[(0.0, None)] * len(b_ineq),
        constraints=({"type": "eq", "fun": lambda lmbda: np.sum(lmbda) - 1.0},),
        method="SLSQP",
        options={"maxiter": 100, "ftol": 1e-8},
    )
    if not result.success:
        return PassivityQpResult(
            x=np.zeros(A_ineq.shape[1]),
            success=False,
            message=str(result.message),
            regularization=regularization_value,
            dual_condition_number=dual_condition_number,
        )
    x_value = h_solve - Hinv_A_t @ result.x
    peak_slack = float(np.max(A_ineq @ x_value - b_ineq))
    return PassivityQpResult(
        x=x_value,
        success=True,
        message=str(result.message),
        regularization=regularization_value,
        dual_condition_number=dual_condition_number,
        slack=peak_slack,
    )


def _singular_violation_modes(
    U: np.ndarray,
    singular_values: np.ndarray,
    Vh: np.ndarray,
    *,
    epsilon: float,
    max_modes_per_frequency: int = 1,
) -> list[tuple[float, np.ndarray, np.ndarray]]:
    violating_indices = [idx for idx, value in enumerate(singular_values) if float(value) > 1.0 + epsilon]
    violating_indices.sort(key=lambda idx: float(singular_values[idx]), reverse=True)
    modes = []
    for idx in violating_indices[:max_modes_per_frequency]:
        modes.append((float(singular_values[idx]), U[:, idx], Vh[idx, :].conj()))
    return modes


def build_active_mode_residue_sensitivity_system(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
    epsilon: float,
    perturb_constant: bool,
    safety_margin: float = 0.0,
    max_modes_per_frequency: int = 1,
    max_mode_responses: int = 0,
) -> ActiveModeResidueSensitivitySystem:
    """Build first-order upper-bound constraints for active S-parameter modes.

    The variables follow ``_apply_residue_delta``: one real variable per
    real-pole residue and two real variables per conjugate-pair residue.
    """
    if nports < 1:
        raise ValueError("nports must be positive")
    if max_modes_per_frequency < 1:
        raise ValueError("max_modes_per_frequency must be positive")
    if max_mode_responses < 0:
        raise ValueError("max_mode_responses must be non-negative")
    pole_array = np.asarray(poles, dtype=complex).reshape(-1)
    residue_array = np.asarray(residues, dtype=complex)
    constant_array = np.asarray(constant_coeff, dtype=complex).reshape(-1)
    expected_residue_shape = (nports * nports, len(pole_array))
    if residue_array.shape != expected_residue_shape:
        raise ValueError(f"residues shape {residue_array.shape}, expected {expected_residue_shape}")
    if constant_array.shape != (nports * nports,):
        raise ValueError(f"constant_coeff shape {constant_array.shape}, expected {(nports * nports,)}")

    real_poles, complex_pairs = partition_poles(pole_array)
    vars_per_pair = len(real_poles) + (2 * len(complex_pairs))
    full_residue_variable_count = nports * nports * vars_per_pair
    full_constant_variable_count = nports * nports if perturb_constant else 0
    full_variable_count = full_residue_variable_count + full_constant_variable_count
    target_norm = max(0.0, 1.0 - float(epsilon) - float(safety_margin))

    active_modes: list[tuple[float, float, int, np.ndarray, np.ndarray]] = []
    selected_responses: set[int] = set()
    for raw_freq in np.asarray(freqs, dtype=float).reshape(-1):
        freq = float(raw_freq)
        current = _evaluate_s_matrix_at_freq(
            pole_array,
            residue_array,
            constant_array,
            nports=nports,
            freq=freq,
        )
        left_all, singular_values, right_all = la.svd(current)
        active_indices = [
            index for index, sigma in enumerate(singular_values) if float(sigma) > target_norm
        ]
        active_indices.sort(key=lambda index: float(singular_values[index]), reverse=True)
        for mode_index in active_indices[:max_modes_per_frequency]:
            u_vec = left_all[:, mode_index]
            v_vec = right_all[mode_index, :].conj()
            active_modes.append((freq, float(singular_values[mode_index]), mode_index, u_vec, v_vec))
            if max_mode_responses > 0:
                selected_responses.update(
                    _dominant_response_indices_from_singular_vectors(
                        u_vec,
                        v_vec,
                        nports=nports,
                        max_responses=max_mode_responses,
                    )
                )

    if max_mode_responses == 0:
        response_indices = tuple(range(nports * nports))
    else:
        response_indices = tuple(sorted(selected_responses))
    response_to_offset = {response_index: offset for offset, response_index in enumerate(response_indices)}
    residue_variable_count = len(response_indices) * vars_per_pair
    constant_variable_count = len(response_indices) if perturb_constant else 0
    variable_count = residue_variable_count + constant_variable_count
    full_variable_indices: list[int] = []
    for response_index in response_indices:
        start = response_index * vars_per_pair
        full_variable_indices.extend(range(start, start + vars_per_pair))
    if perturb_constant:
        full_variable_indices.extend(
            full_residue_variable_count + response_index for response_index in response_indices
        )

    rows: list[np.ndarray] = []
    bounds: list[float] = []
    frequencies: list[float] = []
    sigmas: list[float] = []
    mode_indices: list[int] = []
    for freq, sigma, mode_index, u_vec, v_vec in active_modes:
        row = np.zeros(variable_count, dtype=float)
        s_value = 1j * 2.0 * np.pi * freq
        for response_index in response_indices:
            i = response_index // nports
            j = response_index % nports
            u_term = np.conj(u_vec[i]) * v_vec[j]
            offset = response_to_offset[response_index] * vars_per_pair
            for variable_index, (_pole_index, pole_value) in enumerate(real_poles):
                row[offset + variable_index] = float(np.real(u_term / (s_value - pole_value)))
            for variable_index, (pole_index_1, pole_index_2, _sigma_p, _omega_p) in enumerate(complex_pairs):
                basis_1 = 1.0 / (s_value - pole_array[pole_index_1])
                basis_2 = 1.0 / (s_value - pole_array[pole_index_2])
                pair_offset = offset + len(real_poles) + (2 * variable_index)
                row[pair_offset] = float(np.real(u_term * (basis_1 + basis_2)))
                row[pair_offset + 1] = float(np.real(u_term * (1j * (basis_1 - basis_2))))
            if perturb_constant:
                row[residue_variable_count + response_to_offset[response_index]] = float(np.real(u_term))
        rows.append(row)
        bounds.append(float(target_norm - sigma))
        frequencies.append(freq)
        sigmas.append(float(sigma))
        mode_indices.append(mode_index)

    A_ineq = np.asarray(rows, dtype=float) if rows else np.empty((0, variable_count), dtype=float)
    b_ineq = np.asarray(bounds, dtype=float)
    return ActiveModeResidueSensitivitySystem(
        A_ineq=A_ineq,
        b_ineq=b_ineq,
        constraint_frequencies_hz=tuple(frequencies),
        constraint_sigmas=tuple(sigmas),
        constraint_mode_indices=tuple(mode_indices),
        real_poles=tuple(real_poles),
        complex_pairs=tuple(complex_pairs),
        response_indices=response_indices,
        full_variable_indices=np.asarray(full_variable_indices, dtype=int),
        full_variable_count=int(full_variable_count),
        residue_variable_count=int(residue_variable_count),
        constant_variable_count=int(constant_variable_count),
        perturb_constant=bool(perturb_constant),
    )


def _select_active_variable_indices(
    A_ineq: np.ndarray,
    max_active_variables: int,
    *,
    variable_weights: np.ndarray | None = None,
) -> np.ndarray:
    if A_ineq.ndim != 2:
        raise ValueError("A_ineq must be a 2D array")
    column_count = A_ineq.shape[1]
    if max_active_variables <= 0 or max_active_variables >= column_count:
        return np.arange(column_count, dtype=int)
    sensitivities = np.max(np.abs(A_ineq), axis=0)
    if variable_weights is not None:
        weights = np.asarray(variable_weights, dtype=float)
        if weights.ndim != 1 or weights.shape[0] != column_count:
            raise ValueError("variable_weights must contain one positive entry per variable")
        sensitivities = sensitivities / np.maximum(weights, 1e-300)
    candidate_indices = np.argpartition(-sensitivities, max_active_variables - 1)[:max_active_variables]
    return np.array(sorted(candidate_indices, key=lambda idx: (-sensitivities[idx], idx)), dtype=int)


def _constant_active_variable_indices(
    A_ineq: np.ndarray,
    max_active_variables: int,
    *,
    n_residue_vars: int,
    n_constant_vars: int,
    variable_weights: np.ndarray | None = None,
) -> np.ndarray:
    if n_constant_vars <= 0:
        return np.array([], dtype=int)
    start = int(n_residue_vars)
    stop = start + int(n_constant_vars)
    if A_ineq.ndim != 2:
        raise ValueError("A_ineq must be a 2D array")
    if stop > A_ineq.shape[1]:
        raise ValueError("constant variable block exceeds matrix width")
    constant_columns = A_ineq[:, start:stop]
    local_weights = None if variable_weights is None else np.asarray(variable_weights, dtype=float)[start:stop]
    local_indices = _select_active_variable_indices(
        constant_columns,
        max_active_variables,
        variable_weights=local_weights,
    )
    return local_indices + start


def _active_variable_budget_candidates(max_active_variables: int, total_variables: int) -> list[int]:
    if total_variables < 1:
        return []
    if max_active_variables <= 0:
        return [0]
    cap = min(max_active_variables, total_variables)
    candidates = [max(1, cap // 4), max(1, cap // 2), cap]
    return sorted(set(candidates))


def _evaluate_passivity_score_at_freqs(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
    epsilon: float,
) -> _PassivityScore:
    max_sigma = 0.0
    violation_count = 0
    residue_cube = residues.reshape((nports, nports, len(poles))) if len(poles) else None
    constant_matrix = constant_coeff.reshape((nports, nports)).astype(complex)
    for freq in freqs:
        s_val = 1j * 2.0 * np.pi * float(freq)
        S_f = constant_matrix.copy()
        if residue_cube is not None:
            for pole_index, pole in enumerate(poles):
                S_f += residue_cube[:, :, pole_index] / (s_val - pole)
        sigma = float(np.max(la.svd(S_f, compute_uv=False)))
        max_sigma = max(max_sigma, sigma)
        if sigma > 1.0 + epsilon:
            violation_count += 1
    return _PassivityScore(violation_count=violation_count, max_sigma=max_sigma)


def _evaluate_s_matrix_at_freq(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freq: float,
) -> np.ndarray:
    residue_cube = residues.reshape((nports, nports, len(poles))) if len(poles) else None
    S_f = constant_coeff.reshape((nports, nports)).astype(complex).copy()
    s_val = 1j * 2.0 * np.pi * float(freq)
    if residue_cube is not None:
        for pole_index, pole in enumerate(poles):
            S_f += residue_cube[:, :, pole_index] / (s_val - pole)
    return S_f


def _evaluate_s_matrices_at_freqs(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
) -> np.ndarray:
    freqs_array = np.asarray(list(freqs), dtype=float).reshape(-1)
    basis = _rational_basis_at_freqs(poles, freqs_array)
    return _evaluate_s_matrices_from_basis(
        residues,
        constant_coeff,
        nports=nports,
        basis=basis,
    )


def _rational_basis_at_freqs(poles: np.ndarray, freqs: Any) -> np.ndarray:
    freqs_array = np.asarray(list(freqs), dtype=float).reshape(-1)
    pole_array = np.asarray(poles, dtype=complex).reshape(-1)
    if freqs_array.size == 0 or pole_array.size == 0:
        return np.zeros((freqs_array.size, pole_array.size), dtype=complex)
    s_values = 1j * 2.0 * np.pi * freqs_array
    return 1.0 / (s_values[:, None] - pole_array[None, :])


def _evaluate_s_matrices_from_basis(
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    basis: np.ndarray,
) -> np.ndarray:
    basis_array = np.asarray(basis, dtype=complex)
    matrices = np.broadcast_to(
        constant_coeff.reshape((nports, nports)).astype(complex),
        (basis_array.shape[0], nports, nports),
    ).copy()
    if basis_array.size == 0 or basis_array.shape[1] == 0:
        return matrices
    residue_cube = residues.reshape((nports, nports, basis_array.shape[1]))
    matrices += np.einsum("fk,ijk->fij", basis_array, residue_cube)
    return matrices


def _singular_sample_at_freq(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freq: float,
    epsilon: float = 1e-6,
    refinement_depth: int = 0,
    source: str = "sample",
) -> dict[str, Any]:
    S_f = _evaluate_s_matrix_at_freq(
        poles,
        residues,
        constant_coeff,
        nports=nports,
        freq=freq,
    )
    sigma = float(np.max(la.svd(S_f, compute_uv=False)))
    return {
        "frequency_hz": float(freq),
        "max_sigma": sigma,
        "violates": bool(sigma > 1.0 + epsilon),
        "refinement_depth": int(refinement_depth),
        "source": source,
    }


def _singular_samples_at_freqs(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
    epsilon: float = 1e-6,
    refinement_depth: int = 0,
    source: str = "sample",
    basis: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    freqs_array = np.asarray(list(freqs), dtype=float).reshape(-1)
    if freqs_array.size == 0:
        return []
    if basis is None:
        matrices = _evaluate_s_matrices_at_freqs(
            poles,
            residues,
            constant_coeff,
            nports=nports,
            freqs=freqs_array,
        )
    else:
        matrices = _evaluate_s_matrices_from_basis(
            residues,
            constant_coeff,
            nports=nports,
            basis=basis,
        )
    singular_values = np.linalg.svd(matrices, compute_uv=False)
    max_sigmas = np.max(singular_values, axis=1)
    return [
        {
            "frequency_hz": float(freq),
            "max_sigma": float(sigma),
            "violates": bool(float(sigma) > 1.0 + epsilon),
            "refinement_depth": int(refinement_depth),
            "source": source,
        }
        for freq, sigma in zip(freqs_array, max_sigmas)
    ]


def _max_sigma_at_freqs(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
) -> tuple[float, float]:
    max_sigma = -np.inf
    max_sigma_freq = 0.0
    for freq in freqs:
        freq_float = float(freq)
        sample = _singular_sample_at_freq(
            poles,
            residues,
            constant_coeff,
            nports=nports,
            freq=freq_float,
        )
        sigma = float(sample["max_sigma"])
        if sigma > max_sigma:
            max_sigma = sigma
            max_sigma_freq = freq_float
    return max_sigma, max_sigma_freq


def _interval_report_sample_frequencies(
    f_start: float,
    f_end: float,
    poles: np.ndarray,
) -> list[float]:
    samples = {float(f_start), float(f_end), (float(f_start) + float(f_end)) / 2.0}
    for pole in poles:
        pole_freq = abs(float(np.imag(pole))) / (2.0 * np.pi)
        if f_start <= pole_freq <= f_end:
            samples.add(pole_freq)
    return sorted(samples)


def _adaptive_passivity_samples(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    intervals: list[tuple[float, float]],
    f_max: float | None,
    epsilon: float,
    max_depth: int = 8,
    curvature_tol: float = 1e-3,
    min_spacing_hz: float = 0.0,
) -> list[dict[str, Any]]:
    samples_by_freq: dict[float, dict[str, Any]] = {}

    def add_sample(freq: float, depth: int, source: str) -> dict[str, Any]:
        freq_float = float(freq)
        if f_max is not None and freq_float > float(f_max):
            freq_float = float(f_max)
        if freq_float < 0.0:
            freq_float = 0.0
        existing = samples_by_freq.get(freq_float)
        if existing is not None and int(existing["refinement_depth"]) <= depth:
            return existing
        sample = _singular_sample_at_freq(
            poles,
            residues,
            constant_coeff,
            nports=nports,
            freq=freq_float,
            epsilon=epsilon,
            refinement_depth=depth,
            source=source,
        )
        samples_by_freq[freq_float] = sample
        return sample

    def refine(start: float, stop: float, depth: int) -> None:
        if stop < start:
            start, stop = stop, start
        if f_max is not None:
            stop = min(stop, float(f_max))
        if stop < 0.0:
            return
        start = max(0.0, start)
        width = stop - start
        if width < 0.0:
            return
        midpoint = (start + stop) / 2.0
        left = add_sample(start, depth, "interval_edge")
        mid = add_sample(midpoint, depth, "interval_midpoint")
        right = add_sample(stop, depth, "interval_edge")

        pole_samples = []
        for pole in poles:
            pole_freq = abs(float(np.imag(pole))) / (2.0 * np.pi)
            if start <= pole_freq <= stop:
                pole_samples.append(add_sample(pole_freq, depth, "pole_frequency"))

        if depth >= max_depth:
            return
        if min_spacing_hz > 0.0 and width <= min_spacing_hz:
            return

        edge_average = 0.5 * (float(left["max_sigma"]) + float(right["max_sigma"]))
        curvature = float(mid["max_sigma"]) - edge_average
        should_refine = (
            curvature > curvature_tol
            or bool(left["violates"])
            or bool(mid["violates"])
            or bool(right["violates"])
            or any(bool(sample["violates"]) for sample in pole_samples)
        )
        if should_refine:
            refine(start, midpoint, depth + 1)
            refine(midpoint, stop, depth + 1)

    for f_start, f_end in intervals:
        refine(float(f_start), float(f_end), 0)

    return [samples_by_freq[freq] for freq in sorted(samples_by_freq)]


def _projection_candidate_passivity_samples(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    intervals: list[tuple[float, float]],
    f_max: float | None,
    epsilon: float,
    reference_freqs: Any | None = None,
    reference_basis: np.ndarray | None = None,
    max_depth: int = 2,
    curvature_tol: float = 1e-3,
) -> list[dict[str, Any]]:
    samples = _adaptive_passivity_samples(
        poles,
        residues,
        constant_coeff,
        nports=nports,
        intervals=intervals,
        f_max=f_max,
        epsilon=epsilon,
        max_depth=max_depth,
        curvature_tol=curvature_tol,
    )
    samples_by_freq = {float(sample["frequency_hz"]): sample for sample in samples}

    if reference_freqs is not None:
        reference_freq_list = []
        for freq in np.asarray(reference_freqs, dtype=float).reshape(-1):
            freq_float = float(freq)
            if f_max is not None and freq_float > float(f_max):
                continue
            if freq_float < 0.0:
                continue
            reference_freq_list.append(freq_float)
        for sample in _singular_samples_at_freqs(
            poles,
            residues,
            constant_coeff,
            nports=nports,
            freqs=reference_freq_list,
            epsilon=epsilon,
            source="reference_grid_holdout",
            basis=reference_basis,
        ):
            freq_float = float(sample["frequency_hz"])
            existing = samples_by_freq.get(freq_float)
            if existing is None or float(sample["max_sigma"]) > float(existing["max_sigma"]):
                samples_by_freq[freq_float] = sample

    return [samples_by_freq[freq] for freq in sorted(samples_by_freq)]


def _candidate_reference_holdout_samples_batch(
    candidates: list[tuple[np.ndarray, np.ndarray]],
    *,
    nports: int,
    freqs: Any,
    epsilon: float,
    basis: np.ndarray,
    chunk_size: int = 128,
) -> list[list[dict[str, Any]]]:
    freqs_array = np.asarray(list(freqs), dtype=float).reshape(-1)
    if not candidates:
        return []
    results: list[list[dict[str, Any]]] = [[] for _ in candidates]
    if freqs_array.size == 0:
        return results
    basis_array = np.asarray(basis, dtype=complex)
    if basis_array.shape[0] != freqs_array.size:
        raise ValueError("basis must have one row per frequency")
    step = max(1, int(chunk_size))
    for start in range(0, freqs_array.size, step):
        stop = min(freqs_array.size, start + step)
        basis_chunk = basis_array[start:stop]
        matrices = np.stack(
            [
                _evaluate_s_matrices_from_basis(
                    residues,
                    constant,
                    nports=nports,
                    basis=basis_chunk,
                )
                for residues, constant in candidates
            ],
            axis=0,
        )
        singular_values = np.linalg.svd(
            matrices.reshape((-1, nports, nports)),
            compute_uv=False,
        )
        max_sigmas = np.max(singular_values, axis=1).reshape((len(candidates), stop - start))
        for candidate_index in range(len(candidates)):
            for freq, sigma in zip(freqs_array[start:stop], max_sigmas[candidate_index]):
                sigma_float = float(sigma)
                results[candidate_index].append(
                    {
                        "frequency_hz": float(freq),
                        "max_sigma": sigma_float,
                        "violates": bool(sigma_float > 1.0 + epsilon),
                        "refinement_depth": 0,
                        "source": "reference_grid_holdout",
                    }
                )
    return results


def _mode_response_magnitudes_from_basis(
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    basis: np.ndarray,
    left_vectors: np.ndarray,
    right_vectors: np.ndarray,
) -> np.ndarray:
    matrices = _evaluate_s_matrices_from_basis(
        residues,
        constant_coeff,
        nports=nports,
        basis=basis,
    )
    left = np.asarray(left_vectors, dtype=complex)
    right = np.asarray(right_vectors, dtype=complex)
    if left.shape != right.shape or left.ndim != 3 or left.shape[0] != matrices.shape[0] or left.shape[2] != nports:
        raise ValueError("left_vectors and right_vectors must have shape (nfreq, nmodes, nports)")
    responses = np.einsum("fmi,fij,fmj->fm", np.conjugate(left), matrices, right)
    return np.abs(responses)


def _dominant_singular_vectors_at_freqs(
    matrices: np.ndarray,
    *,
    mode_count: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    matrix_array = np.asarray(matrices, dtype=complex)
    if matrix_array.ndim != 3 or matrix_array.shape[1] != matrix_array.shape[2]:
        raise ValueError("matrices must have shape (nfreq, nports, nports)")
    count = max(1, min(int(mode_count), matrix_array.shape[1]))
    u_all, sigmas_all, vh_all = np.linalg.svd(matrix_array, full_matrices=False)
    left = np.swapaxes(u_all[:, :, :count], 1, 2)
    right = np.conjugate(vh_all[:, :count, :])
    return sigmas_all[:, :count], left, right


def _screen_projection_candidate_descriptors_by_modes(
    candidates: list[dict[str, Any]],
    *,
    nports: int,
    basis: np.ndarray,
    left_vectors: np.ndarray,
    right_vectors: np.ndarray,
    max_candidates: int,
) -> list[dict[str, Any]]:
    if max_candidates <= 0 or len(candidates) <= max_candidates:
        for candidate in candidates:
            if "mode_screen_max_sigma" not in candidate:
                magnitudes = _mode_response_magnitudes_from_basis(
                    candidate["residues"],
                    candidate["constant"],
                    nports=nports,
                    basis=basis,
                    left_vectors=left_vectors,
                    right_vectors=right_vectors,
                )
                candidate["mode_screen_max_sigma"] = float(np.max(magnitudes)) if magnitudes.size else 0.0
        return candidates
    scored = []
    for index, candidate in enumerate(candidates):
        magnitudes = _mode_response_magnitudes_from_basis(
            candidate["residues"],
            candidate["constant"],
            nports=nports,
            basis=basis,
            left_vectors=left_vectors,
            right_vectors=right_vectors,
        )
        score = float(np.max(magnitudes)) if magnitudes.size else 0.0
        candidate["mode_screen_max_sigma"] = score
        scored.append((score, index, candidate))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [candidate for _score, _index, candidate in scored[: int(max_candidates)]]


def _projection_candidate_passes_cheap_gates(
    candidate: dict[str, Any],
    *,
    max_delta_norm: float | None = None,
    max_response_delta_rms: float | None = None,
    baseline_reference_rms: float | None = None,
    max_reference_rms_increase: float | None = None,
    initial_reference_rms: float | None = None,
    max_reference_rms_total_increase: float | None = None,
    max_reference_rms_per_sigma_improvement: float | None = None,
    late_current_clip_max_reference_rms_per_sigma_improvement: float | None = None,
    late_current_clip_start_iteration: int = 0,
    max_reference_band_sigma_regression: float | None = None,
    active_mode_max_reference_rms_total_increase: float | None = None,
) -> bool:
    return (
        _projection_candidate_reject_reason(
            candidate,
            max_delta_norm=max_delta_norm,
            max_response_delta_rms=max_response_delta_rms,
            baseline_reference_rms=baseline_reference_rms,
            max_reference_rms_increase=max_reference_rms_increase,
            initial_reference_rms=initial_reference_rms,
            max_reference_rms_total_increase=max_reference_rms_total_increase,
            max_reference_rms_per_sigma_improvement=max_reference_rms_per_sigma_improvement,
            late_current_clip_max_reference_rms_per_sigma_improvement=(
                late_current_clip_max_reference_rms_per_sigma_improvement
            ),
            late_current_clip_start_iteration=late_current_clip_start_iteration,
            max_reference_band_sigma_regression=max_reference_band_sigma_regression,
            active_mode_max_reference_rms_total_increase=active_mode_max_reference_rms_total_increase,
        )
        is None
    )


def _is_reference_regularized_active_mode_candidate(candidate: dict[str, Any]) -> bool:
    if candidate.get("strategy") != "active_mode":
        return False
    source_diagnostic = candidate.get("source_diagnostic")
    if not isinstance(source_diagnostic, dict):
        return False
    return source_diagnostic.get("solver") in {
        "reference_regularized_min_norm",
        "reference_regularized_peak_minimax",
        "reference_compensated_min_norm",
    }


def _projection_candidate_reject_reason(
    candidate: dict[str, Any],
    *,
    baseline_max_sigma: float | None = None,
    baseline_violation_count: int | None = None,
    max_sigma_regression: float = 0.0,
    max_delta_norm: float | None = None,
    max_response_delta_rms: float | None = None,
    baseline_reference_rms: float | None = None,
    max_reference_rms_increase: float | None = None,
    initial_reference_rms: float | None = None,
    max_reference_rms_total_increase: float | None = None,
    max_reference_rms_per_sigma_improvement: float | None = None,
    late_current_clip_max_reference_rms_per_sigma_improvement: float | None = None,
    late_current_clip_start_iteration: int = 0,
    max_reference_band_sigma_regression: float | None = None,
    active_mode_max_reference_rms_total_increase: float | None = None,
    post_damping_max_sigma_regression: float | None = None,
    baseline_post_damping_reference_rms: float | None = None,
) -> str | None:
    if max_delta_norm is not None and float(candidate.get("delta_norm", 0.0)) > float(max_delta_norm):
        return "delta_norm_exceeded"
    if (
        max_response_delta_rms is not None
        and float(candidate.get("response_delta_rms", 0.0)) > float(max_response_delta_rms)
    ):
        return "response_delta_rms_exceeded"
    candidate_reference_rms = float(candidate.get("reference_rms", 0.0))
    if (
        _is_reference_regularized_active_mode_candidate(candidate)
        and initial_reference_rms is not None
        and active_mode_max_reference_rms_total_increase is not None
    ):
        if candidate_reference_rms > float(initial_reference_rms) + float(
            active_mode_max_reference_rms_total_increase
        ):
            return "active_mode_reference_rms_total_budget_exceeded"
    if initial_reference_rms is not None and max_reference_rms_total_increase is not None:
        if candidate_reference_rms > float(initial_reference_rms) + float(max_reference_rms_total_increase):
            return "reference_rms_total_budget_exceeded"
    elif (
        baseline_reference_rms is not None
        and max_reference_rms_increase is not None
        and candidate_reference_rms > float(baseline_reference_rms) + float(max_reference_rms_increase)
    ):
        return "reference_rms_regression"
    if (
        max_reference_rms_per_sigma_improvement is not None
        and bool(candidate.get("reference_rms_efficiency_gate", True))
        and baseline_max_sigma is not None
        and baseline_reference_rms is not None
        and "max_sigma" in candidate
    ):
        sigma_improvement = float(baseline_max_sigma) - float(candidate["max_sigma"])
        reference_rms_increase = candidate_reference_rms - float(baseline_reference_rms)
        if sigma_improvement > 0.0 and reference_rms_increase > 0.0:
            rms_per_sigma = reference_rms_increase / sigma_improvement
            if rms_per_sigma > float(max_reference_rms_per_sigma_improvement):
                return "reference_rms_efficiency_exceeded"
    if (
        late_current_clip_max_reference_rms_per_sigma_improvement is not None
        and str(candidate.get("strategy", "")).startswith("current_spectral_clip")
        and int(candidate.get("projection_iteration", 0)) >= int(late_current_clip_start_iteration)
        and baseline_max_sigma is not None
        and baseline_reference_rms is not None
        and "max_sigma" in candidate
    ):
        sigma_improvement = float(baseline_max_sigma) - float(candidate["max_sigma"])
        reference_rms_increase = candidate_reference_rms - float(baseline_reference_rms)
        if sigma_improvement > 0.0 and reference_rms_increase > 0.0:
            rms_per_sigma = reference_rms_increase / sigma_improvement
            candidate["late_current_clip_reference_rms_per_sigma_improvement"] = float(rms_per_sigma)
            if rms_per_sigma > float(late_current_clip_max_reference_rms_per_sigma_improvement):
                return "late_current_clip_reference_rms_efficiency_exceeded"
    if max_reference_band_sigma_regression is not None:
        band_regression = float(candidate.get("reference_band_sigma_regression", 0.0))
        if band_regression > float(max_reference_band_sigma_regression):
            return "reference_band_sigma_regression"
    if (
        baseline_max_sigma is not None
        and baseline_violation_count is not None
        and "max_sigma" in candidate
        and "violation_count" in candidate
    ):
        candidate_sigma = float(candidate["max_sigma"])
        candidate_violations = int(candidate["violation_count"])
        improves_peak = candidate_sigma < float(baseline_max_sigma)
        trades_small_peak_regression = (
            float(max_sigma_regression) > 0.0
            and candidate_sigma <= float(baseline_max_sigma) + float(max_sigma_regression)
            and candidate_violations < int(baseline_violation_count)
        )
        trades_post_damping_rms = (
            post_damping_max_sigma_regression is not None
            and baseline_post_damping_reference_rms is not None
            and "post_damping_reference_rms" in candidate
            and candidate_sigma <= float(baseline_max_sigma) + float(post_damping_max_sigma_regression)
            and float(candidate["post_damping_reference_rms"])
            <= float(baseline_post_damping_reference_rms)
        )
        if not improves_peak and not trades_small_peak_regression and not trades_post_damping_rms:
            return "passivity_not_improved"
    return None


def _projection_candidate_passivity_rank(
    candidate: dict[str, Any],
    *,
    baseline_max_sigma: float,
    baseline_violation_count: int,
    max_sigma_regression: float = 0.0,
) -> tuple[int, float, int]:
    candidate_sigma = float(candidate["max_sigma"])
    candidate_violations = int(candidate["violation_count"])
    if candidate_sigma < float(baseline_max_sigma):
        return (0, candidate_sigma, candidate_violations)
    if (
        float(max_sigma_regression) > 0.0
        and candidate_sigma <= float(baseline_max_sigma) + float(max_sigma_regression)
        and candidate_violations < int(baseline_violation_count)
    ):
        return (1, candidate_sigma, candidate_violations)
    return (2, candidate_sigma, candidate_violations)


def _compact_projection_candidate_diagnostic(
    candidate: dict[str, Any],
    *,
    reject_reason: str | None,
) -> dict[str, Any]:
    keys = (
        "strategy",
        "scale",
        "max_sigma",
        "max_sigma_frequency_hz",
        "violation_count",
        "delta_norm",
        "response_delta_rms",
        "reference_rms",
        "post_damping_reference_rms",
        "post_damping_factor",
        "reference_band_max_sigma",
        "reference_band_sigma_regression",
        "mode_screen_max_sigma",
    )
    diagnostic = {"reject_reason": reject_reason}
    for key in keys:
        if key not in candidate:
            continue
        value = candidate[key]
        if isinstance(value, (np.floating, float)):
            diagnostic[key] = float(value)
        elif isinstance(value, (np.integer, int)):
            diagnostic[key] = int(value)
        else:
            diagnostic[key] = value
    source_diagnostic = candidate.get("source_diagnostic")
    if isinstance(source_diagnostic, dict):
        source_keys = (
            "solver",
            "active_mode_requested_solver",
            "reference_weight",
            "reference_target_scale",
            "active_mode_reference_target_scale",
            "singular_modes",
            "band_singular_modes",
            "band_singular_mode_frequency_count",
            "active_mode_band_singular_frequency_count",
            "reference_row_count",
            "active_variable_count",
            "compressed",
            "full_variable_count",
            "variable_count",
            "response_count",
            "allowed_response_count",
        )
        compact_source: dict[str, Any] = {}
        for key in source_keys:
            if key not in source_diagnostic:
                continue
            value = source_diagnostic[key]
            if isinstance(value, (bool, np.bool_)):
                compact_source[key] = bool(value)
            elif isinstance(value, (np.floating, float)):
                compact_source[key] = float(value)
            elif isinstance(value, (np.integer, int)):
                compact_source[key] = int(value)
            else:
                compact_source[key] = value
        diagnostic["source_diagnostic"] = compact_source
    return diagnostic


def _projection_candidate_rejection_summary(
    candidates: list[dict[str, Any]],
    *,
    baseline_max_sigma: float | None = None,
    baseline_violation_count: int | None = None,
    max_sigma_regression: float = 0.0,
    max_delta_norm: float | None = None,
    max_response_delta_rms: float | None = None,
    baseline_reference_rms: float | None = None,
    max_reference_rms_increase: float | None = None,
    initial_reference_rms: float | None = None,
    max_reference_rms_total_increase: float | None = None,
    max_reference_rms_per_sigma_improvement: float | None = None,
    late_current_clip_max_reference_rms_per_sigma_improvement: float | None = None,
    late_current_clip_start_iteration: int = 0,
    max_reference_band_sigma_regression: float | None = None,
    active_mode_max_reference_rms_total_increase: float | None = None,
    post_damping_max_sigma_regression: float | None = None,
    baseline_post_damping_reference_rms: float | None = None,
) -> dict[str, Any]:
    reasons: dict[str, int] = {}
    accepted_count = 0
    rejected: list[tuple[int, float, int, float, float, dict[str, Any], str]] = []
    for candidate in candidates:
        reason = _projection_candidate_reject_reason(
            candidate,
            baseline_max_sigma=baseline_max_sigma,
            baseline_violation_count=baseline_violation_count,
            max_sigma_regression=max_sigma_regression,
            max_delta_norm=max_delta_norm,
            max_response_delta_rms=max_response_delta_rms,
            baseline_reference_rms=baseline_reference_rms,
            max_reference_rms_increase=max_reference_rms_increase,
            initial_reference_rms=initial_reference_rms,
            max_reference_rms_total_increase=max_reference_rms_total_increase,
            max_reference_rms_per_sigma_improvement=max_reference_rms_per_sigma_improvement,
            late_current_clip_max_reference_rms_per_sigma_improvement=(
                late_current_clip_max_reference_rms_per_sigma_improvement
            ),
            late_current_clip_start_iteration=late_current_clip_start_iteration,
            max_reference_band_sigma_regression=max_reference_band_sigma_regression,
            active_mode_max_reference_rms_total_increase=active_mode_max_reference_rms_total_increase,
            post_damping_max_sigma_regression=post_damping_max_sigma_regression,
            baseline_post_damping_reference_rms=baseline_post_damping_reference_rms,
        )
        if reason is None:
            accepted_count += 1
            continue
        reasons[reason] = reasons.get(reason, 0) + 1
        stage_rank = 0 if reason == "passivity_not_improved" else 1
        rejected.append(
            (
                stage_rank,
                float(candidate.get("max_sigma", math.inf)),
                int(candidate.get("violation_count", 10**9)),
                float(candidate.get("reference_rms", math.inf)),
                float(candidate.get("delta_norm", math.inf)),
                candidate,
                reason,
            )
        )
    best_rejected = None
    if rejected:
        _stage, _sigma, _violations, _reference_rms, _delta_norm, candidate, reason = min(rejected)
        best_rejected = _compact_projection_candidate_diagnostic(candidate, reject_reason=reason)
    return {
        "accepted_candidates": int(accepted_count),
        "rejected_candidates": int(len(candidates) - accepted_count),
        "reasons": dict(sorted(reasons.items())),
        "best_rejected_candidate": best_rejected,
    }


def _projection_candidate_reference_holdout_freqs(
    validation_samples: Any,
    *,
    required_freqs: Any,
    max_reference_points: int,
) -> list[float]:
    selected: dict[float, None] = {}
    for freq in required_freqs:
        selected[float(freq)] = None
    if max_reference_points <= 0:
        return sorted(selected)

    reference_samples = [
        sample
        for sample in validation_samples
        if sample.get("source") == "reference_grid_holdout"
    ]
    reference_samples.sort(key=lambda sample: (-float(sample["max_sigma"]), float(sample["frequency_hz"])))
    for sample in reference_samples[: int(max_reference_points)]:
        selected[float(sample["frequency_hz"])] = None
    return sorted(selected)


def _projection_active_mode_freqs(
    validation_samples: Any,
    *,
    projection_freqs: Any,
    max_reference_points: int,
    selection_mode: str = "top",
    band_sample_count: int = 8,
) -> list[float]:
    if max_reference_points <= 0:
        return sorted(float(freq) for freq in projection_freqs)
    if selection_mode == "reference_bands":
        selected = {float(freq): None for freq in projection_freqs}
        for freq in _projection_frequency_candidates(
            validation_samples,
            max_violation_samples=max_reference_points,
            selection_mode="reference_bands",
            band_sample_count=band_sample_count,
        ):
            selected[float(freq)] = None
        return sorted(selected)
    if selection_mode != "top":
        raise ValueError("active-mode frequency selection must be 'top' or 'reference_bands'")
    return _projection_candidate_reference_holdout_freqs(
        validation_samples,
        required_freqs=projection_freqs,
        max_reference_points=max_reference_points,
    )


def _active_mode_band_singular_mode_freqs(
    validation_samples: Any,
    *,
    max_reference_points: int,
    band_sample_count: int = 1,
) -> list[float]:
    reference_violations = [
        sample
        for sample in validation_samples
        if sample.get("source") == "reference_grid_holdout" and bool(sample.get("violates", False))
    ]
    selected_samples = []
    for band in _reference_violation_bands(reference_violations):
        band_sorted = sorted(band, key=lambda item: (-float(item["max_sigma"]), float(item["frequency_hz"])))
        selected_samples.extend(band_sorted[: max(1, int(band_sample_count))])
    selected_samples.sort(key=lambda item: (-float(item["max_sigma"]), float(item["frequency_hz"])))
    if max_reference_points > 0:
        selected_samples = selected_samples[: int(max_reference_points)]
    return sorted({float(sample["frequency_hz"]) for sample in selected_samples})


def _active_mode_reference_weight_candidates(
    reference_weight: float,
    reference_weight_candidates: Any,
) -> list[float]:
    candidates = tuple(reference_weight_candidates or ())
    if not candidates:
        return [float(reference_weight)]
    weights: list[float] = []
    for candidate in candidates:
        weight = float(candidate)
        if not np.isfinite(weight) or weight < 0.0:
            raise ValueError("active-mode reference weight candidates must be finite and non-negative")
        if weight not in weights:
            weights.append(weight)
    return weights


def _active_mode_solver_candidates(solver: str) -> list[str]:
    if solver == "reference_regularized_hybrid":
        return ["reference_regularized_min_norm", "reference_regularized_peak_minimax"]
    if solver == "reference_compensated_hybrid":
        return ["reference_regularized_min_norm", "reference_compensated_min_norm"]
    return [solver]


def _active_mode_reference_regularization_freqs(
    active_freqs: Any,
    reference_freqs: Any | None,
    *,
    global_reference_points: int = 0,
) -> list[float]:
    selected: dict[float, None] = {}
    for freq in active_freqs:
        selected[float(freq)] = None
    if reference_freqs is not None and int(global_reference_points) > 0:
        reference_array = np.asarray(reference_freqs, dtype=float).reshape(-1)
        if reference_array.size:
            count = min(int(global_reference_points), int(reference_array.size))
            positions = np.linspace(0, reference_array.size - 1, count, dtype=int)
            for position in positions:
                selected[float(reference_array[int(position)])] = None
    return sorted(selected)


def _active_mode_reference_regularization_sample_weights(
    active_freqs: Any,
    active_sample_weights: Any | None,
    regularization_freqs: Any,
) -> list[float]:
    active_list = [float(freq) for freq in active_freqs]
    regularization_list = [float(freq) for freq in regularization_freqs]
    if not regularization_list:
        return []
    if active_sample_weights is None:
        active_weights = np.ones(len(active_list), dtype=float)
    else:
        active_weights = np.asarray(active_sample_weights, dtype=float)
        if active_weights.ndim != 1 or active_weights.shape[0] != len(active_list):
            raise ValueError("active_sample_weights must contain one value per active frequency")
        if np.any(active_weights < 0.0) or not np.all(np.isfinite(active_weights)):
            raise ValueError("active_sample_weights must contain finite non-negative values")
    target_sum = max(float(np.sum(active_weights)), 1e-18)
    default_weight = target_sum / max(1, len(active_list))
    active_weight_by_freq = {
        float(freq): float(weight)
        for freq, weight in zip(active_list, active_weights)
    }
    weights = np.asarray(
        [active_weight_by_freq.get(float(freq), default_weight) for freq in regularization_list],
        dtype=float,
    )
    total = float(np.sum(weights))
    if total <= 0.0 or not np.isfinite(total):
        return [0.0] * len(regularization_list)
    return (weights * (target_sum / total)).tolist()


def _filter_projection_sources_for_late_stage(
    projection_sources: list[tuple[str, np.ndarray, np.ndarray, dict[str, Any]]],
    *,
    projection_iteration: int,
    non_active_stop_iteration: int | None,
) -> list[tuple[str, np.ndarray, np.ndarray, dict[str, Any]]]:
    if non_active_stop_iteration is None:
        return projection_sources
    if int(projection_iteration) < int(non_active_stop_iteration):
        return projection_sources
    return [source for source in projection_sources if source[0] == "active_mode"]


def _projection_candidate_scale_values(
    projection_strategy: str,
    *,
    active_mode_extra_scales: Any = (),
    current_max_sigma: float | None = None,
    active_mode_extra_scales_min_sigma: float = 0.0,
) -> tuple[float, ...]:
    scales = [1.0, 0.5, 0.25, 0.125, 0.0625]
    extra_enabled = (
        current_max_sigma is None
        or float(current_max_sigma) >= float(active_mode_extra_scales_min_sigma)
    )
    if projection_strategy == "active_mode" and extra_enabled:
        for scale in active_mode_extra_scales:
            value = float(scale)
            if value > 0.0:
                scales.append(value)
    return tuple(sorted(set(scales), reverse=True))


def _projection_frequency_candidates(
    validation_samples: Any,
    *,
    max_violation_samples: int,
    include_all_reference_violations: bool = False,
    selection_mode: str = "top",
    band_sample_count: int = 8,
) -> list[float]:
    sorted_violations = [
        sample
        for sample in sorted(validation_samples, key=lambda item: -float(item["max_sigma"]))
        if bool(sample["violates"])
    ]
    if selection_mode not in {"top", "reference_bands"}:
        raise ValueError("projection frequency selection must be 'top' or 'reference_bands'")
    if selection_mode == "reference_bands":
        selected: dict[float, None] = {}
        capped = sorted_violations[:max_violation_samples] if max_violation_samples > 0 else sorted_violations
        for sample in capped:
            selected[float(sample["frequency_hz"])] = None
        reference_violations = [
            sample
            for sample in sorted_violations
            if sample.get("source") == "reference_grid_holdout"
        ]
        for band in _reference_violation_bands(reference_violations):
            band_sorted = sorted(band, key=lambda item: (-float(item["max_sigma"]), float(item["frequency_hz"])))
            for sample in band_sorted[: max(1, int(band_sample_count))]:
                selected[float(sample["frequency_hz"])] = None
        return sorted(selected)
    if not include_all_reference_violations:
        if max_violation_samples > 0:
            sorted_violations = sorted_violations[:max_violation_samples]
        return [float(sample["frequency_hz"]) for sample in sorted_violations]

    selected: dict[float, None] = {}
    capped = sorted_violations[:max_violation_samples] if max_violation_samples > 0 else sorted_violations
    for sample in capped:
        selected[float(sample["frequency_hz"])] = None
    for sample in sorted_violations:
        if sample.get("source") == "reference_grid_holdout":
            selected[float(sample["frequency_hz"])] = None
    return list(selected.keys())


def _reference_violation_bands(reference_violations: Any) -> list[list[dict[str, Any]]]:
    samples = sorted(reference_violations, key=lambda item: float(item["frequency_hz"]))
    if not samples:
        return []
    if len(samples) == 1:
        return [samples]
    gaps = [
        float(samples[index + 1]["frequency_hz"]) - float(samples[index]["frequency_hz"])
        for index in range(len(samples) - 1)
        if float(samples[index + 1]["frequency_hz"]) > float(samples[index]["frequency_hz"])
    ]
    if not gaps:
        return [samples]
    typical_gap = float(np.median(np.asarray(gaps, dtype=float)))
    split_gap = max(typical_gap * 1.5, typical_gap + 1e-12)
    bands: list[list[dict[str, Any]]] = [[samples[0]]]
    for previous, current in zip(samples, samples[1:]):
        gap = float(current["frequency_hz"]) - float(previous["frequency_hz"])
        if gap > split_gap:
            bands.append([])
        bands[-1].append(current)
    return bands


def _reference_band_holdout_ranges(validation_samples: Any) -> list[tuple[float, float, float]]:
    reference_violations = [
        sample
        for sample in validation_samples
        if sample.get("source") == "reference_grid_holdout" and bool(sample.get("violates", False))
    ]
    ranges = []
    for band in _reference_violation_bands(reference_violations):
        freqs = [float(sample["frequency_hz"]) for sample in band]
        max_sigma = max(float(sample["max_sigma"]) for sample in band)
        ranges.append((min(freqs), max(freqs), max_sigma))
    return ranges


def _reference_band_holdout_metrics(
    candidate_samples: Any,
    *,
    bands: Any,
) -> dict[str, float]:
    max_sigma = 0.0
    max_regression = 0.0
    band_count = 0
    for f_start, f_stop, baseline_sigma in bands:
        band_samples = [
            sample
            for sample in candidate_samples
            if sample.get("source") == "reference_grid_holdout"
            and float(f_start) <= float(sample["frequency_hz"]) <= float(f_stop)
        ]
        if not band_samples:
            continue
        band_count += 1
        candidate_sigma = max(float(sample["max_sigma"]) for sample in band_samples)
        max_sigma = max(max_sigma, candidate_sigma)
        max_regression = max(max_regression, candidate_sigma - float(baseline_sigma))
    return {
        "band_count": float(band_count),
        "max_sigma": float(max_sigma),
        "max_regression": float(max_regression),
    }


def _projection_frequency_weights(
    validation_samples: Any,
    projection_freqs: Any,
    *,
    mode: str = "none",
    epsilon: float = 1e-6,
    exponent: float = 1.0,
    floor: float = 1.0,
) -> list[float]:
    freqs = [float(freq) for freq in projection_freqs]
    if mode == "none":
        return [1.0] * len(freqs)
    if mode == "reference_band_equalized":
        weights = [1.0] * len(freqs)
        selected_by_freq = {float(freq): index for index, freq in enumerate(freqs)}
        for band in _reference_violation_bands(
            [
                sample
                for sample in validation_samples
                if sample.get("source") == "reference_grid_holdout" and bool(sample.get("violates", False))
            ]
        ):
            selected_indices = [
                selected_by_freq[float(sample["frequency_hz"])]
                for sample in band
                if float(sample["frequency_hz"]) in selected_by_freq
            ]
            if not selected_indices:
                continue
            weight = 1.0 / float(len(selected_indices))
            for index in selected_indices:
                weights[index] = weight
        return weights
    if mode != "violation_excess":
        raise ValueError(
            "projection weight mode must be 'none', 'violation_excess', or 'reference_band_equalized'"
        )
    sample_by_freq = {float(sample["frequency_hz"]): sample for sample in validation_samples}
    weights = []
    for freq in freqs:
        sample = sample_by_freq.get(freq)
        sigma = 1.0 if sample is None else float(sample["max_sigma"])
        excess = max(0.0, sigma - 1.0 - float(epsilon))
        weights.append(max(float(floor), 1.0 + excess ** float(exponent) / max(float(epsilon), 1e-12)))
    return weights


def _projection_reference_rms_freqs(
    projection_freqs: Any,
    candidate_reference_freqs: Any | None,
    *,
    mode: str,
) -> list[float]:
    if mode == "projection":
        return [float(freq) for freq in projection_freqs]
    if mode != "candidate_validation":
        raise ValueError("projection reference RMS scope must be 'projection' or 'candidate_validation'")
    if candidate_reference_freqs is None:
        return [float(freq) for freq in projection_freqs]
    return [float(freq) for freq in candidate_reference_freqs]


def _adaptive_violation_frequencies_for_enforcement(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    points: list[float],
    epsilon: float,
    max_violation_samples: int,
    f_max: float | None = None,
    max_depth: int = 1,
    curvature_tol: float = 1e-3,
) -> list[tuple[float, float]]:
    intervals = [
        (float(points[idx]), float(points[idx + 1]))
        for idx in range(len(points) - 1)
        if float(points[idx + 1]) >= float(points[idx])
    ]
    if not intervals:
        return []
    samples = _adaptive_passivity_samples(
        poles,
        residues,
        constant_coeff,
        nports=nports,
        intervals=intervals,
        f_max=f_max,
        epsilon=epsilon,
        max_depth=max_depth,
        curvature_tol=curvature_tol,
    )
    violating = [
        (float(sample["frequency_hz"]), float(sample["max_sigma"]))
        for sample in samples
        if bool(sample["violates"])
    ]
    violating.sort(key=lambda item: (-item[1], item[0]))
    if max_violation_samples > 0:
        violating = violating[:max_violation_samples]
    return violating


def _residue_variable_fit_weights(
    poles: np.ndarray,
    *,
    nports: int,
    vars_per_pair: int,
    real_poles: list[tuple[int, float]],
    complex_pairs: list[tuple[int, int, float, float]],
    freqs: Any,
) -> np.ndarray:
    """Estimate each residue variable's full-band response impact for weighted passivity QP."""
    freqs = list(freqs)
    if not freqs:
        return np.ones(nports * nports * vars_per_pair, dtype=float)
    per_pair_weights = np.ones(vars_per_pair, dtype=float)
    n_real = len(real_poles)
    for var_idx, (_pole_idx, val) in enumerate(real_poles):
        basis = []
        for freq in freqs:
            s_val = 1j * 2.0 * np.pi * float(freq)
            basis.append(abs(1.0 / (s_val - val)) ** 2)
        per_pair_weights[var_idx] = math.sqrt(float(np.mean(basis)))

    for var_idx, (_pole_idx1, _pole_idx2, sigma, omega) in enumerate(complex_pairs):
        dx_basis = []
        dy_basis = []
        for freq in freqs:
            s_val = 1j * 2.0 * np.pi * float(freq)
            z1 = 1.0 / (s_val - (sigma + 1j * omega))
            z2 = 1.0 / (s_val - (sigma - 1j * omega))
            dx_basis.append(abs(z1 + z2) ** 2)
            dy_basis.append(abs(-1j * (z1 - z2)) ** 2)
        offset = n_real + 2 * var_idx
        per_pair_weights[offset] = math.sqrt(float(np.mean(dx_basis)))
        per_pair_weights[offset + 1] = math.sqrt(float(np.mean(dy_basis)))

    floor = max(float(np.max(per_pair_weights)) * 1e-12, 1e-30)
    per_pair_weights = np.maximum(per_pair_weights, floor)
    median = float(np.median(per_pair_weights))
    if median > 0.0 and np.isfinite(median):
        per_pair_weights = per_pair_weights / median
    per_pair_weights = np.clip(per_pair_weights, 0.1, 10.0)
    return np.tile(per_pair_weights, nports * nports)


def _normalize_positive_weights(
    values: np.ndarray,
    *,
    floor: float = 1e-12,
    clip: tuple[float, float] = (0.1, 10.0),
) -> np.ndarray:
    weights = np.asarray(values, dtype=float).copy()
    weights[~np.isfinite(weights)] = 1.0
    weights = np.maximum(weights, floor)
    median = float(np.median(weights))
    if median > 0.0 and np.isfinite(median):
        weights = weights / median
    return np.clip(weights, clip[0], clip[1])


def _controllability_gramian_weights(
    A: np.ndarray,
    B: np.ndarray,
    *,
    floor: float = 1e-12,
    clip: tuple[float, float] = (0.1, 10.0),
) -> np.ndarray:
    if A.size == 0:
        return np.ones(0, dtype=float)
    gramian = la.solve_continuous_lyapunov(A, -(B @ B.T))
    diag = np.real(np.diag(gramian))
    return _normalize_positive_weights(diag, floor=floor, clip=clip)


def _model_based_variable_weights(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    vars_per_pair: int,
    real_poles: list[tuple[int, float]],
    complex_pairs: list[tuple[int, int, float, float]],
    perturb_constant: bool,
    perturb_poles: bool,
    constant_weight: float = 1.0,
    pole_weight: float = 1.0,
) -> np.ndarray:
    A, B, _C, _D = real_state_space_realization(poles, residues, constant_coeff, nports)
    state_weights = _controllability_gramian_weights(A, B)
    if len(state_weights) == 0:
        residue_weights = np.ones(nports * nports * vars_per_pair, dtype=float)
    else:
        residue_weights = np.ones(nports * nports * vars_per_pair, dtype=float)
        state_idx = 0
        n_real = len(real_poles)
        for column in range(nports):
            for var_idx, (pole_idx, _val) in enumerate(real_poles):
                active = any(abs(residues[row * nports + column, pole_idx]) > 1e-30 for row in range(nports))
                if not active:
                    continue
                if state_idx < len(state_weights):
                    for row in range(nports):
                        response_idx = row * nports + column
                        residue_weights[response_idx * vars_per_pair + var_idx] = state_weights[state_idx]
                state_idx += 1

            for var_idx, (pole_idx1, pole_idx2, _sigma, _omega) in enumerate(complex_pairs):
                active = any(
                    abs(residues[row * nports + column, pole_idx1]) > 1e-30
                    or abs(residues[row * nports + column, pole_idx2]) > 1e-30
                    for row in range(nports)
                )
                if not active:
                    continue
                dx_weight = state_weights[state_idx] if state_idx < len(state_weights) else 1.0
                dy_weight = state_weights[state_idx + 1] if state_idx + 1 < len(state_weights) else dx_weight
                for row in range(nports):
                    response_idx = row * nports + column
                    offset = response_idx * vars_per_pair + n_real + 2 * var_idx
                    residue_weights[offset] = dx_weight
                    residue_weights[offset + 1] = dy_weight
                state_idx += 2
        residue_weights = _normalize_positive_weights(residue_weights)

    weights_list = [residue_weights]
    if perturb_constant:
        weights_list.append(np.ones(nports * nports, dtype=float) * constant_weight)
    if perturb_poles:
        weights_list.append(np.ones(len(real_poles) + 2 * len(complex_pairs), dtype=float) * pole_weight)
    return np.concatenate(weights_list)


def _variable_fit_weights(
    poles: np.ndarray,
    residues: np.ndarray,
    *,
    nports: int,
    vars_per_pair: int,
    real_poles: list[tuple[int, float]],
    complex_pairs: list[tuple[int, int, float, float]],
    freqs: Any,
    perturb_constant: bool,
    perturb_poles: bool,
    constant_weight: float = 1.0,
    pole_weight: float = 1.0,
) -> np.ndarray:
    freqs = list(freqs)
    n_real = len(real_poles)
    if not freqs:
        res_weights = np.ones(nports * nports * vars_per_pair, dtype=float)
        weights_list = [res_weights]
        if perturb_constant:
            weights_list.append(np.ones(nports * nports, dtype=float) * constant_weight)
        if perturb_poles:
            weights_list.append(np.ones(n_real + 2 * len(complex_pairs), dtype=float) * pole_weight)
        return np.concatenate(weights_list)

    try:
        return _model_based_variable_weights(
            poles,
            residues,
            np.zeros(nports * nports, dtype=complex),
            nports=nports,
            vars_per_pair=vars_per_pair,
            real_poles=real_poles,
            complex_pairs=complex_pairs,
            perturb_constant=perturb_constant,
            perturb_poles=perturb_poles,
            constant_weight=constant_weight,
            pole_weight=pole_weight,
        )
    except Exception:
        pass

    per_pair_weights = np.ones(vars_per_pair, dtype=float)
    for var_idx, (_pole_idx, val) in enumerate(real_poles):
        basis = []
        for freq in freqs:
            s_val = 1j * 2.0 * np.pi * float(freq)
            basis.append(abs(1.0 / (s_val - val)) ** 2)
        per_pair_weights[var_idx] = math.sqrt(float(np.mean(basis)))

    for var_idx, (_pole_idx1, _pole_idx2, sigma, omega) in enumerate(complex_pairs):
        dx_basis = []
        dy_basis = []
        for freq in freqs:
            s_val = 1j * 2.0 * np.pi * float(freq)
            z1 = 1.0 / (s_val - (sigma + 1j * omega))
            z2 = 1.0 / (s_val - (sigma - 1j * omega))
            dx_basis.append(abs(z1 + z2) ** 2)
            dy_basis.append(abs(-1j * (z1 - z2)) ** 2)
        offset = n_real + 2 * var_idx
        per_pair_weights[offset] = math.sqrt(float(np.mean(dx_basis)))
        per_pair_weights[offset + 1] = math.sqrt(float(np.mean(dy_basis)))

    floor = max(float(np.max(per_pair_weights)) * 1e-12, 1e-30)
    per_pair_weights = np.maximum(per_pair_weights, floor)
    median = float(np.median(per_pair_weights))
    if median > 0.0 and np.isfinite(median):
        per_pair_weights = per_pair_weights / median
    per_pair_weights = np.clip(per_pair_weights, 0.1, 10.0)
    residue_weights = np.tile(per_pair_weights, nports * nports)

    weights_list = [residue_weights]

    if perturb_constant:
        weights_list.append(np.ones(nports * nports, dtype=float) * constant_weight)

    if perturb_poles:
        pole_weights = []
        for pole_idx, val in real_poles:
            basis = []
            for freq in freqs:
                s_val = 1j * 2.0 * np.pi * float(freq)
                basis.append(abs(1.0 / (s_val - val)**2) ** 2)
            basis_rms = math.sqrt(float(np.mean(basis)))
            r_scale = float(np.mean(np.abs(residues[:, pole_idx])))
            pole_weights.append(r_scale * basis_rms * pole_weight)

        for pole_idx1, pole_idx2, sigma, omega in complex_pairs:
            sigma_basis = []
            omega_basis = []
            for freq in freqs:
                s_val = 1j * 2.0 * np.pi * float(freq)
                z1_sq = 1.0 / (s_val - (sigma + 1j * omega))**2
                z2_sq = 1.0 / (s_val - (sigma - 1j * omega))**2
                sigma_basis.append(abs(z1_sq + z2_sq)**2)
                omega_basis.append(abs(1j * (z1_sq - z2_sq))**2)
            sigma_rms = math.sqrt(float(np.mean(sigma_basis)))
            omega_rms = math.sqrt(float(np.mean(omega_basis)))
            r_scale = float(np.mean(np.abs(residues[:, pole_idx1])))
            pole_weights.append(r_scale * sigma_rms * pole_weight)
            pole_weights.append(r_scale * omega_rms * pole_weight)

        if pole_weights:
            pole_weights_arr = np.array(pole_weights)
            pole_floor = max(float(np.max(pole_weights_arr)) * 1e-12, 1e-30)
            pole_weights_arr = np.maximum(pole_weights_arr, pole_floor)
            pole_median = float(np.median(pole_weights_arr))
            if pole_median > 0.0:
                pole_weights_arr = pole_weights_arr / pole_median
            pole_weights_arr = np.clip(pole_weights_arr, 0.1, 10.0)
            weights_list.append(pole_weights_arr)

    return np.concatenate(weights_list)


def _base_perturbation_weights(
    *,
    n_residue_vars: int,
    n_constant_vars: int,
    n_pole_vars: int,
    constant_weight: float = 1.0,
    pole_weight: float = 1.0,
) -> np.ndarray | None:
    if n_constant_vars == 0 and n_pole_vars == 0:
        return None
    weights_list = [np.ones(n_residue_vars, dtype=float)]
    if n_constant_vars:
        weights_list.append(np.ones(n_constant_vars, dtype=float) * float(constant_weight))
    if n_pole_vars:
        weights_list.append(np.ones(n_pole_vars, dtype=float) * float(pole_weight))
    weights = np.concatenate(weights_list)
    if np.allclose(weights, 1.0):
        return None
    return weights


def _apply_constant_delta(
    constant_coeff: np.ndarray,
    x_delta: np.ndarray,
    *,
    nports: int,
    offset: int,
    scale: float = 1.0,
) -> np.ndarray:
    updated = constant_coeff.copy()
    updated += scale * x_delta[offset : offset + nports * nports]
    return updated


def _apply_pole_delta(
    poles: np.ndarray,
    x_delta: np.ndarray,
    *,
    real_poles: list[tuple[int, float]],
    complex_pairs: list[tuple[int, int, float, float]],
    offset: int,
    scale: float = 1.0,
) -> np.ndarray:
    updated = poles.copy()
    n_real = len(real_poles)
    for var_idx, (pole_idx, _val) in enumerate(real_poles):
        updated[pole_idx] += scale * x_delta[offset + var_idx]

    for var_idx, (pole_idx1, pole_idx2, _sigma, _omega) in enumerate(complex_pairs):
        ds = scale * x_delta[offset + n_real + 2 * var_idx]
        dw = scale * x_delta[offset + n_real + 2 * var_idx + 1]
        updated[pole_idx1] += ds + 1j * dw
        updated[pole_idx2] += ds - 1j * dw
    return updated


def _apply_residue_delta(
    residues: np.ndarray,
    x_delta: np.ndarray,
    *,
    nports: int,
    vars_per_pair: int,
    n_real: int,
    real_poles: list[tuple[int, float]],
    complex_pairs: list[tuple[int, int, float, float]],
    scale: float = 1.0,
) -> np.ndarray:
    updated = residues.copy()
    for i in range(nports):
        for j in range(nports):
            r_idx = i * nports + j
            offset = r_idx * vars_per_pair

            for var_idx, (pole_idx, _val) in enumerate(real_poles):
                updated[r_idx, pole_idx] += scale * x_delta[offset + var_idx]

            for var_idx, (pole_idx1, pole_idx2, _sigma, _omega) in enumerate(complex_pairs):
                dx = scale * x_delta[offset + n_real + 2 * var_idx]
                dy = scale * x_delta[offset + n_real + 2 * var_idx + 1]
                updated[r_idx, pole_idx1] += dx + 1j * dy
                updated[r_idx, pole_idx2] += dx - 1j * dy
    return updated


def real_state_space_realization(poles, residues, D_coeff, nports):
    """
    Constructs a real state-space realization (A, B, C, D) from rational poles and residues.
    """
    visited = set()
    real_poles = []
    complex_pairs = []
    for idx, p in enumerate(poles):
        if idx in visited:
            continue
        if abs(p.imag) < 1e-15:
            real_poles.append((idx, p.real))
            visited.add(idx)
        else:
            conj_idx = None
            for other_idx, other_p in enumerate(poles):
                if other_idx not in visited and other_idx != idx:
                    if np.isclose(other_p.real, p.real) and np.isclose(other_p.imag, -p.imag):
                        conj_idx = other_idx
                        break
            if conj_idx is not None:
                positive_index = idx if p.imag > 0 else conj_idx
                negative_index = conj_idx if p.imag > 0 else idx
                positive_pole = poles[positive_index]
                complex_pairs.append((positive_index, negative_index, positive_pole.real, positive_pole.imag))
                visited.add(idx)
                visited.add(conj_idx)
            else:
                real_poles.append((idx, p.real))
                visited.add(idx)

    states_per_port = len(real_poles) + 2 * len(complex_pairs)
    nstates = nports * states_per_port

    A = np.zeros((nstates, nstates))
    B = np.zeros((nstates, nports))
    C = np.zeros((nports, nstates))
    D = D_coeff.reshape((nports, nports))

    state_idx = 0
    for j in range(nports):
        for pole_idx, val in real_poles:
            A[state_idx, state_idx] = val
            B[state_idx, j] = 1.0
            for i in range(nports):
                C[i, state_idx] = residues[i * nports + j, pole_idx].real
            state_idx += 1

        for pole_idx1, pole_idx2, sigma, omega in complex_pairs:
            s1 = state_idx
            s2 = state_idx + 1
            state_idx += 2

            A[s1, s1] = sigma
            A[s1, s2] = omega
            A[s2, s1] = -omega
            A[s2, s2] = sigma

            B[s1, j] = 2.0
            # B[s2, j] is 0.0

            for i in range(nports):
                res_val = residues[i * nports + j, pole_idx1]
                C[i, s1] = res_val.real
                C[i, s2] = res_val.imag

    return A, B, C, D


def check_passivity_hamiltonian_s(poles, residues, D_coeff, nports, f_max=None):
    """
    Checks passivity of S-parameter model using Hamiltonian matrix eigenvalues.
    Returns: list of crossover frequencies in Hz.
    """
    A, B, C, D = real_state_space_realization(poles, residues, D_coeff, nports)

    I_port = np.eye(nports)

    D_perturbed = D.copy()
    for i in range(nports):
        for j in range(nports):
            if abs(abs(D_perturbed[i, j]) - 1.0) < 1e-8:
                D_perturbed[i, j] = np.sign(D_perturbed[i, j]) * (1.0 - 1e-7)

    try:
        inv_D_term = la.inv(I_port - D_perturbed.T @ D_perturbed)
        inv_D_term_out = la.inv(I_port - D_perturbed @ D_perturbed.T)
    except la.LinAlgError:
        return []

    M11 = A + B @ inv_D_term @ D_perturbed.T @ C
    M12 = B @ inv_D_term @ B.T
    M21 = -C.T @ inv_D_term_out @ C
    M22 = -A.T - C.T @ D_perturbed @ inv_D_term @ B.T

    H = np.block([
        [M11, M12],
        [M21, M22]
    ])

    eigenvals = la.eigvals(H)

    crossover_omega = []
    for val in eigenvals:
        if abs(val.real) < 1e-4:
            w = abs(val.imag)
            if w > 1e-3:
                crossover_omega.append(w)

    crossover_omega = sorted(list(set(crossover_omega)))

    crossover_freqs_hz = []
    for w in crossover_omega:
        f = w / (2.0 * np.pi)
        if f_max is None or f <= f_max:
            crossover_freqs_hz.append(f)

    return crossover_freqs_hz


def _expand_poles_and_residues(poles, residues):
    poles = np.asarray(poles, dtype=complex)
    residues = np.asarray(residues, dtype=complex)
    if residues.ndim == 1:
        residues = residues.reshape((-1, len(poles)))

    # Check if conjugates are present
    has_conjugates = True
    for p in poles:
        if abs(p.imag) > 1e-15:
            found = False
            for other in poles:
                if np.isclose(other.real, p.real) and np.isclose(other.imag, -p.imag):
                    found = True
                    break
            if not found:
                has_conjugates = False
                break

    if has_conjugates:
        return poles, residues

    expanded_poles = []
    expanded_residues = []
    for idx, p in enumerate(poles):
        expanded_poles.append(p)
        expanded_residues.append(residues[:, idx])
        if abs(p.imag) > 1e-15:
            expanded_poles.append(p.conj())
            expanded_residues.append(residues[:, idx].conj())

    return np.array(expanded_poles), np.column_stack(expanded_residues)


def check_vector_fit_passivity_hamiltonian(
    vector_fit: Any,
    *,
    nports: int,
    epsilon: float = 1e-6,
    f_max: float | None = None,
) -> PassivitySampleReport:
    """
    Checks passivity using Hamiltonian matrix eigenvalues.
    Returns a PassivitySampleReport containing the violation bands.
    """
    poles_orig = np.asarray(getattr(vector_fit, "poles", []), dtype=complex)
    residues_orig = np.asarray(getattr(vector_fit, "residues", []), dtype=complex)
    constant_coeff = np.asarray(getattr(vector_fit, "constant_coeff", []), dtype=complex)

    if residues_orig.size == 0 and len(poles_orig) > 0:
        residues_orig = np.zeros((nports * nports, len(poles_orig)), dtype=complex)
    if constant_coeff.size == 0:
        constant_coeff = np.zeros(nports * nports, dtype=complex)

    poles, residues = _expand_poles_and_residues(poles_orig, residues_orig)

    if residues.size == 0 and len(poles) > 0:
        residues = np.zeros((nports * nports, len(poles)), dtype=complex)
    if constant_coeff.size == 0:
        constant_coeff = np.zeros(nports * nports, dtype=complex)

    crossover_freqs = check_passivity_hamiltonian_s(poles, residues, constant_coeff, nports, f_max)

    f_limit = 100e9
    if len(crossover_freqs) > 0:
        f_limit = max(f_limit, crossover_freqs[-1] * 2.0)
    if f_max is not None:
        f_limit = min(f_limit, f_max)

    points = [0.0] + crossover_freqs + [f_limit]

    violation_bands = []
    report_samples: list[dict[str, Any]] = []

    for i in range(len(points) - 1):
        f_start = points[i]
        f_end = points[i+1]
        interval_samples = _adaptive_passivity_samples(
            poles,
            residues,
            constant_coeff,
            nports=nports,
            intervals=[(float(f_start), float(f_end))],
            f_max=f_max,
            epsilon=epsilon,
            max_depth=2,
            curvature_tol=1e-3,
        )
        report_samples.extend(interval_samples)
        max_sigma = max((float(sample["max_sigma"]) for sample in interval_samples), default=-np.inf)

        if max_sigma > 1.0 + epsilon:
            violation_bands.append([f_start, f_end])

    unique_samples = {float(sample["frequency_hz"]): sample for sample in report_samples}
    for f in crossover_freqs:
        sample = _singular_sample_at_freq(
            poles,
            residues,
            constant_coeff,
            nports=nports,
            freq=float(f) / 2.0,
            epsilon=epsilon,
            source="crossover_half",
        )
        unique_samples[float(sample["frequency_hz"])] = sample

    sample_values = [unique_samples[freq] for freq in sorted(unique_samples)]
    if sample_values:
        max_sample = max(sample_values, key=lambda sample: float(sample["max_sigma"]))
        max_s = float(max_sample["max_sigma"])
        max_s_freq = float(max_sample["frequency_hz"])
    else:
        max_s = 0.0
        max_s_freq = 0.0

    return PassivitySampleReport(
        max_sigma=max_s,
        max_sigma_frequency_hz=max_s_freq,
        violation_bands_hz=violation_bands,
        frequency_points=len(sample_values),
        chunk_size=1,
    )


def partition_poles(poles):
    """
    Partitions complex poles list into real poles and complex conjugate pairs.
    """
    visited = set()
    real_poles = []
    complex_pairs = []
    for idx, p in enumerate(poles):
        if idx in visited:
            continue
        if abs(p.imag) < 1e-15:
            real_poles.append((idx, p.real))
            visited.add(idx)
        else:
            conj_idx = None
            for other_idx, other_p in enumerate(poles):
                if other_idx not in visited and other_idx != idx:
                    if np.isclose(other_p.real, p.real) and np.isclose(other_p.imag, -p.imag):
                        conj_idx = other_idx
                        break
            if conj_idx is not None:
                positive_index = idx if p.imag > 0 else conj_idx
                negative_index = conj_idx if p.imag > 0 else idx
                positive_pole = poles[positive_index]
                complex_pairs.append((positive_index, negative_index, positive_pole.real, positive_pole.imag))
                visited.add(idx)
                visited.add(conj_idx)
            else:
                real_poles.append((idx, p.real))
                visited.add(idx)
    return real_poles, complex_pairs


def _spectral_norm_project_matrix(matrix: np.ndarray, *, target_norm: float) -> np.ndarray:
    U, singular_values, Vh = la.svd(np.asarray(matrix, dtype=complex))
    clipped = np.minimum(singular_values, float(target_norm))
    return (U * clipped[None, :]) @ Vh


def _project_asymptotic_constant_strictly_passive(
    constant_coeff: np.ndarray,
    *,
    nports: int,
    epsilon: float,
    maximum_sigma_to_project: float | None = None,
) -> tuple[np.ndarray, float, float, float]:
    """Project the RFM feedthrough matrix inside the strict passive boundary."""

    constant = np.asarray(constant_coeff, dtype=complex).reshape(nports, nports)
    U, singular_values, Vh = la.svd(constant)
    sigma_before = float(singular_values[0]) if len(singular_values) else 0.0
    strict_margin = max(float(epsilon), 64.0 * np.finfo(float).eps)
    target_norm = max(0.0, 1.0 - strict_margin)
    if sigma_before < 1.0 or (
        maximum_sigma_to_project is not None and sigma_before > maximum_sigma_to_project
    ):
        return constant.reshape(-1).copy(), sigma_before, sigma_before, target_norm

    clipped = np.minimum(singular_values, target_norm)
    projected = (U * clipped[None, :]) @ Vh
    if np.all(constant.imag == 0.0):
        projected = projected.real.astype(complex)
    sigma_after = float(clipped[0]) if len(clipped) else 0.0
    return projected.reshape(-1), sigma_before, sigma_after, target_norm


def _projection_residue_constant_delta(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
    epsilon: float,
    perturb_constant: bool,
    safety_margin: float = 1e-5,
    ridge: float = 1e-10,
    sample_weights: Any | None = None,
    reweight_iterations: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    freq_list = [float(freq) for freq in freqs]
    if not freq_list:
        return residues.copy(), constant_coeff.copy()

    pole_array = np.asarray(poles, dtype=complex)
    residue_array = np.asarray(residues, dtype=complex)
    constant_array = np.asarray(constant_coeff, dtype=complex)
    real_poles, complex_pairs = partition_poles(pole_array)
    n_real = len(real_poles)
    vars_per_response = n_real + 2 * len(complex_pairs) + (1 if perturb_constant else 0)
    if vars_per_response == 0:
        return residue_array.copy(), constant_array.copy()
    if sample_weights is None:
        weight_list = [1.0] * len(freq_list)
    else:
        weight_list = [float(weight) for weight in sample_weights]
        if len(weight_list) != len(freq_list):
            raise ValueError("sample_weights must contain one value per projection frequency")

    target_norm = max(0.0, 1.0 - float(epsilon) - float(safety_margin))
    basis_by_freq: list[np.ndarray] = []
    target_delta_by_freq: list[np.ndarray] = []
    for freq in freq_list:
        s_val = 1j * 2.0 * np.pi * freq
        basis = []
        for _pole_idx, val in real_poles:
            basis.append(1.0 / (s_val - val))
        for _pole_idx1, _pole_idx2, sigma, omega in complex_pairs:
            z1 = 1.0 / (s_val - (sigma + 1j * omega))
            z2 = 1.0 / (s_val - (sigma - 1j * omega))
            basis.append(z1 + z2)
            basis.append(1j * (z1 - z2))
        if perturb_constant:
            basis.append(1.0 + 0.0j)
        basis_by_freq.append(np.asarray(basis, dtype=complex))

        current = _evaluate_s_matrix_at_freq(
            pole_array,
            residue_array,
            constant_array,
            nports=nports,
            freq=freq,
        )
        projected = _spectral_norm_project_matrix(current, target_norm=target_norm)
        target_delta_by_freq.append(projected - current)

    def solve_with_weights(local_weights: list[float]) -> tuple[np.ndarray, np.ndarray]:
        A_rows = []
        B_rows = []
        for basis, target_delta, weight in zip(basis_by_freq, target_delta_by_freq, local_weights):
            row_scale = math.sqrt(max(float(weight), 0.0))
            flat_delta = target_delta.reshape(-1)
            A_rows.append(row_scale * np.real(basis))
            B_rows.append(row_scale * np.real(flat_delta))
            A_rows.append(row_scale * np.imag(basis))
            B_rows.append(row_scale * np.imag(flat_delta))
        A = np.asarray(A_rows, dtype=float)
        B = np.asarray(B_rows, dtype=float)
        if ridge > 0.0:
            scale = max(float(np.max(np.abs(A))) if A.size else 0.0, 1.0)
            A_aug = np.vstack((A, math.sqrt(float(ridge)) * scale * np.eye(vars_per_response)))
            B_aug = np.vstack((B, np.zeros((vars_per_response, nports * nports), dtype=float)))
        else:
            A_aug = A
            B_aug = B
        delta_matrix, *_ = np.linalg.lstsq(A_aug, B_aug, rcond=None)

        candidate_residues = residue_array.copy()
        candidate_constant = constant_array.copy()
        for var_idx, (pole_idx, _val) in enumerate(real_poles):
            candidate_residues[:, pole_idx] += delta_matrix[var_idx, :]
        for var_idx, (pole_idx1, pole_idx2, _sigma, _omega) in enumerate(complex_pairs):
            offset = n_real + 2 * var_idx
            dx = delta_matrix[offset, :]
            dy = delta_matrix[offset + 1, :]
            candidate_residues[:, pole_idx1] += dx + 1j * dy
            candidate_residues[:, pole_idx2] += dx - 1j * dy
        if perturb_constant:
            candidate_constant += delta_matrix[-1, :]
        return candidate_residues, candidate_constant

    best_residues = residue_array.copy()
    best_constant = constant_array.copy()
    best_max_sigma = math.inf
    local_weights = list(weight_list)
    max_reweight_iterations = max(0, int(reweight_iterations))
    for reweight_iteration in range(max_reweight_iterations + 1):
        candidate_residues, candidate_constant = solve_with_weights(local_weights)
        candidate_sigmas = []
        for freq in freq_list:
            candidate = _evaluate_s_matrix_at_freq(
                pole_array,
                candidate_residues,
                candidate_constant,
                nports=nports,
                freq=freq,
            )
            singular_values = la.svd(candidate, compute_uv=False)
            candidate_sigmas.append(float(singular_values[0]) if len(singular_values) else 0.0)
        candidate_max_sigma = max(candidate_sigmas) if candidate_sigmas else 0.0
        if candidate_max_sigma < best_max_sigma:
            best_residues = candidate_residues
            best_constant = candidate_constant
            best_max_sigma = float(candidate_max_sigma)
        if reweight_iteration >= max_reweight_iterations:
            break
        for idx, sigma in enumerate(candidate_sigmas):
            excess = max(0.0, float(sigma) - target_norm)
            if excess <= 0.0:
                continue
            multiplier = min(25.0, 1.0 + excess / max(1e-4, 10.0 * float(epsilon)))
            local_weights[idx] *= multiplier

    return best_residues, best_constant


def _reference_matrix_at_freq(
    *,
    freq: float,
    reference_freqs: Any,
    reference_s: Any,
    nports: int,
) -> np.ndarray:
    reference_freq_array = np.asarray(reference_freqs, dtype=float)
    reference_s_array = np.asarray(reference_s, dtype=complex)
    if reference_freq_array.ndim != 1 or reference_s_array.shape[0] != reference_freq_array.shape[0]:
        raise ValueError("reference_freqs and reference_s must share the frequency axis")
    if reference_s_array.shape[1:] != (nports, nports):
        raise ValueError("reference_s must have shape (nfreq, nports, nports)")

    reference = np.empty((nports, nports), dtype=complex)
    for row in range(nports):
        for column in range(nports):
            series = reference_s_array[:, row, column]
            real = np.interp(float(freq), reference_freq_array, np.real(series))
            imag = np.interp(float(freq), reference_freq_array, np.imag(series))
            reference[row, column] = real + 1j * imag
    return reference


def _reference_projection_residue_constant_delta(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
    reference_freqs: Any,
    reference_s: Any,
    epsilon: float,
    perturb_constant: bool,
    safety_margin: float = 1e-5,
    ridge: float = 1e-10,
    sample_weights: Any | None = None,
    reweight_iterations: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    freq_list = [float(freq) for freq in freqs]
    if not freq_list:
        return residues.copy(), constant_coeff.copy()

    pole_array = np.asarray(poles, dtype=complex)
    residue_array = np.asarray(residues, dtype=complex)
    constant_array = np.asarray(constant_coeff, dtype=complex)
    real_poles, complex_pairs = partition_poles(pole_array)
    n_real = len(real_poles)
    vars_per_response = n_real + 2 * len(complex_pairs) + (1 if perturb_constant else 0)
    if vars_per_response == 0:
        return residue_array.copy(), constant_array.copy()
    if sample_weights is None:
        weight_list = [1.0] * len(freq_list)
    else:
        weight_list = [float(weight) for weight in sample_weights]
        if len(weight_list) != len(freq_list):
            raise ValueError("sample_weights must contain one value per projection frequency")

    target_norm = max(0.0, 1.0 - float(epsilon) - float(safety_margin))
    basis_by_freq: list[np.ndarray] = []
    target_delta_by_freq: list[np.ndarray] = []
    for freq in freq_list:
        s_val = 1j * 2.0 * np.pi * freq
        basis = []
        for _pole_idx, val in real_poles:
            basis.append(1.0 / (s_val - val))
        for _pole_idx1, _pole_idx2, sigma, omega in complex_pairs:
            z1 = 1.0 / (s_val - (sigma + 1j * omega))
            z2 = 1.0 / (s_val - (sigma - 1j * omega))
            basis.append(z1 + z2)
            basis.append(1j * (z1 - z2))
        if perturb_constant:
            basis.append(1.0 + 0.0j)
        basis_by_freq.append(np.asarray(basis, dtype=complex))

        current = _evaluate_s_matrix_at_freq(
            pole_array,
            residue_array,
            constant_array,
            nports=nports,
            freq=freq,
        )
        reference = _reference_matrix_at_freq(
            freq=freq,
            reference_freqs=reference_freqs,
            reference_s=reference_s,
            nports=nports,
        )
        target = _spectral_norm_project_matrix(reference, target_norm=target_norm)
        target_delta_by_freq.append(target - current)

    def solve_with_weights(local_weights: list[float]) -> tuple[np.ndarray, np.ndarray]:
        A_rows = []
        B_rows = []
        for basis, target_delta, weight in zip(basis_by_freq, target_delta_by_freq, local_weights):
            row_scale = math.sqrt(max(float(weight), 0.0))
            flat_delta = target_delta.reshape(-1)
            A_rows.append(row_scale * np.real(basis))
            B_rows.append(row_scale * np.real(flat_delta))
            A_rows.append(row_scale * np.imag(basis))
            B_rows.append(row_scale * np.imag(flat_delta))
        A = np.asarray(A_rows, dtype=float)
        B = np.asarray(B_rows, dtype=float)
        if ridge > 0.0:
            scale = max(float(np.max(np.abs(A))) if A.size else 0.0, 1.0)
            A_aug = np.vstack((A, math.sqrt(float(ridge)) * scale * np.eye(vars_per_response)))
            B_aug = np.vstack((B, np.zeros((vars_per_response, nports * nports), dtype=float)))
        else:
            A_aug = A
            B_aug = B
        delta_matrix, *_ = np.linalg.lstsq(A_aug, B_aug, rcond=None)

        candidate_residues = residue_array.copy()
        candidate_constant = constant_array.copy()
        for var_idx, (pole_idx, _val) in enumerate(real_poles):
            candidate_residues[:, pole_idx] += delta_matrix[var_idx, :]
        for var_idx, (pole_idx1, pole_idx2, _sigma, _omega) in enumerate(complex_pairs):
            offset = n_real + 2 * var_idx
            dx = delta_matrix[offset, :]
            dy = delta_matrix[offset + 1, :]
            candidate_residues[:, pole_idx1] += dx + 1j * dy
            candidate_residues[:, pole_idx2] += dx - 1j * dy
        if perturb_constant:
            candidate_constant += delta_matrix[-1, :]
        return candidate_residues, candidate_constant

    best_residues = residue_array.copy()
    best_constant = constant_array.copy()
    best_max_sigma = math.inf
    local_weights = list(weight_list)
    max_reweight_iterations = max(0, int(reweight_iterations))
    for reweight_iteration in range(max_reweight_iterations + 1):
        candidate_residues, candidate_constant = solve_with_weights(local_weights)
        candidate_sigmas = []
        for freq in freq_list:
            candidate = _evaluate_s_matrix_at_freq(
                pole_array,
                candidate_residues,
                candidate_constant,
                nports=nports,
                freq=freq,
            )
            singular_values = la.svd(candidate, compute_uv=False)
            candidate_sigmas.append(float(singular_values[0]) if len(singular_values) else 0.0)
        candidate_max_sigma = max(candidate_sigmas) if candidate_sigmas else 0.0
        if candidate_max_sigma < best_max_sigma:
            best_residues = candidate_residues
            best_constant = candidate_constant
            best_max_sigma = float(candidate_max_sigma)
        if reweight_iteration >= max_reweight_iterations:
            break
        for idx, sigma in enumerate(candidate_sigmas):
            excess = max(0.0, float(sigma) - target_norm)
            if excess <= 0.0:
                continue
            multiplier = min(25.0, 1.0 + excess / max(1e-4, 10.0 * float(epsilon)))
            local_weights[idx] *= multiplier

    return best_residues, best_constant


def _current_clip_reference_regularized_projection_delta(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
    reference_freqs: Any,
    reference_s: Any,
    epsilon: float,
    perturb_constant: bool,
    reference_weight: float,
    safety_margin: float = 1e-5,
    ridge: float = 1e-10,
    sample_weights: Any | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    freq_list = [float(freq) for freq in freqs]
    if float(reference_weight) <= 0.0:
        return _projection_residue_constant_delta(
            poles,
            residues,
            constant_coeff,
            nports=nports,
            freqs=freq_list,
            epsilon=epsilon,
            perturb_constant=perturb_constant,
            safety_margin=safety_margin,
            ridge=ridge,
            sample_weights=sample_weights,
        )
    if not freq_list:
        return residues.copy(), constant_coeff.copy()

    pole_array = np.asarray(poles, dtype=complex)
    residue_array = np.asarray(residues, dtype=complex)
    constant_array = np.asarray(constant_coeff, dtype=complex)
    real_poles, complex_pairs = partition_poles(pole_array)
    n_real = len(real_poles)
    vars_per_response = n_real + 2 * len(complex_pairs) + (1 if perturb_constant else 0)
    if vars_per_response == 0:
        return residue_array.copy(), constant_array.copy()
    if sample_weights is None:
        weight_list = [1.0] * len(freq_list)
    else:
        weight_list = [float(weight) for weight in sample_weights]
        if len(weight_list) != len(freq_list):
            raise ValueError("sample_weights must contain one value per projection frequency")

    target_norm = max(0.0, 1.0 - float(epsilon) - float(safety_margin))
    A_rows = []
    B_rows = []
    reference_scale = math.sqrt(max(float(reference_weight), 0.0))
    for freq, weight in zip(freq_list, weight_list):
        s_val = 1j * 2.0 * np.pi * freq
        basis = []
        for _pole_idx, val in real_poles:
            basis.append(1.0 / (s_val - val))
        for _pole_idx1, _pole_idx2, sigma, omega in complex_pairs:
            z1 = 1.0 / (s_val - (sigma + 1j * omega))
            z2 = 1.0 / (s_val - (sigma - 1j * omega))
            basis.append(z1 + z2)
            basis.append(1j * (z1 - z2))
        if perturb_constant:
            basis.append(1.0 + 0.0j)
        basis_array = np.asarray(basis, dtype=complex)
        current = _evaluate_s_matrix_at_freq(
            pole_array,
            residue_array,
            constant_array,
            nports=nports,
            freq=freq,
        )
        current_clip_delta = _spectral_norm_project_matrix(current, target_norm=target_norm) - current
        reference_delta = _reference_matrix_at_freq(
            freq=freq,
            reference_freqs=reference_freqs,
            reference_s=reference_s,
            nports=nports,
        ) - current

        row_scale = math.sqrt(max(float(weight), 0.0))
        for target_delta, target_scale in (
            (current_clip_delta, row_scale),
            (reference_delta, row_scale * reference_scale),
        ):
            flat_delta = target_delta.reshape(-1)
            A_rows.append(target_scale * np.real(basis_array))
            B_rows.append(target_scale * np.real(flat_delta))
            A_rows.append(target_scale * np.imag(basis_array))
            B_rows.append(target_scale * np.imag(flat_delta))

    A = np.asarray(A_rows, dtype=float)
    B = np.asarray(B_rows, dtype=float)
    if ridge > 0.0:
        scale = max(float(np.max(np.abs(A))) if A.size else 0.0, 1.0)
        A_aug = np.vstack((A, math.sqrt(float(ridge)) * scale * np.eye(vars_per_response)))
        B_aug = np.vstack((B, np.zeros((vars_per_response, nports * nports), dtype=float)))
    else:
        A_aug = A
        B_aug = B
    delta_matrix, *_ = np.linalg.lstsq(A_aug, B_aug, rcond=None)

    updated_residues = residue_array.copy()
    updated_constant = constant_array.copy()
    for var_idx, (pole_idx, _val) in enumerate(real_poles):
        updated_residues[:, pole_idx] += delta_matrix[var_idx, :]
    for var_idx, (pole_idx1, pole_idx2, _sigma, _omega) in enumerate(complex_pairs):
        offset = n_real + 2 * var_idx
        dx = delta_matrix[offset, :]
        dy = delta_matrix[offset + 1, :]
        updated_residues[:, pole_idx1] += dx + 1j * dy
        updated_residues[:, pole_idx2] += dx - 1j * dy
    if perturb_constant:
        updated_constant += delta_matrix[-1, :]
    return updated_residues, updated_constant


def _active_mode_residue_constant_delta(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
    epsilon: float,
    perturb_constant: bool,
    safety_margin: float = 1e-5,
    variable_weights: np.ndarray | None = None,
    max_active_variables: int | None = None,
    max_mode_responses: int = 0,
    singular_modes: int = 1,
    band_singular_modes: int = 1,
    band_singular_mode_freqs: Any | None = None,
    solver: str = "min_norm",
    target_margin: float = 0.0,
    reference_freqs: Any | None = None,
    reference_s: Any | None = None,
    reference_weight: float = 0.0,
    reference_target_scale: float = 1.0,
    reference_sample_weights: Any | None = None,
    reference_global_points: int = 0,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    freq_list = [float(freq) for freq in freqs]
    pole_array = np.asarray(poles, dtype=complex)
    residue_array = np.asarray(residues, dtype=complex)
    constant_array = np.asarray(constant_coeff, dtype=complex)
    real_poles, complex_pairs = partition_poles(pole_array)
    n_real = len(real_poles)
    vars_per_pair = n_real + 2 * len(complex_pairs)
    n_residue_vars = nports * nports * vars_per_pair
    n_constant_vars = nports * nports if perturb_constant else 0
    n_vars = n_residue_vars + n_constant_vars
    if not freq_list or n_vars == 0:
        return residue_array.copy(), constant_array.copy(), {
            "success": False,
            "constraint_count": 0,
            "message": "no active-mode variables",
            "target_margin": float(max(0.0, float(target_margin))),
        }

    active_target_margin = max(0.0, float(target_margin))
    # NNLS is the production candidate for the sparse RP path.  Build it in
    # compressed response coordinates before the legacy full-width path below.
    # Band-specific extra modes remain on that legacy path until their compact
    # representation is implemented and independently benchmarked.
    no_extra_band_modes = (
        band_singular_mode_freqs is None
        or np.asarray(band_singular_mode_freqs, dtype=float).size == 0
        or int(band_singular_modes) <= int(singular_modes)
    )
    if solver == "nnls" and no_extra_band_modes:
        system = build_active_mode_residue_sensitivity_system(
            pole_array,
            residue_array,
            constant_array,
            nports=nports,
            freqs=freq_list,
            epsilon=epsilon,
            perturb_constant=perturb_constant,
            safety_margin=float(safety_margin) + active_target_margin,
            max_modes_per_frequency=max(1, int(singular_modes)),
            max_mode_responses=max(0, int(max_mode_responses)),
        )
        if system.constraint_count == 0:
            return residue_array.copy(), constant_array.copy(), {
                "success": False,
                "solver": solver,
                "constraint_count": 0,
                "message": "no active violating modes",
                "target_margin": float(active_target_margin),
                "compressed": True,
                **system.diagnostics(),
            }
        local_indices = np.arange(system.variable_count, dtype=int)
        if max_active_variables is not None and 0 < int(max_active_variables) < system.variable_count:
            compressed_weights = (
                None
                if variable_weights is None
                else np.asarray(variable_weights, dtype=float)[system.full_variable_indices]
            )
            local_indices = _select_active_variable_indices(
                system.A_ineq,
                int(max_active_variables),
                variable_weights=compressed_weights,
            )
        active_weights = (
            None
            if variable_weights is None
            else np.asarray(variable_weights, dtype=float)[system.full_variable_indices[local_indices]]
        )
        qp_result = _solve_min_norm_upper_bound_nnls(
            system.A_ineq[:, local_indices],
            system.b_ineq,
            variable_weights=active_weights,
        )
        base_diagnostics = {
            "solver": solver,
            "constraint_count": system.constraint_count,
            "allowed_response_count": len(system.response_indices),
            "active_variable_count": int(len(local_indices)),
            "max_mode_responses": int(max_mode_responses),
            "singular_modes": max(1, int(singular_modes)),
            "target_margin": float(active_target_margin),
            "compressed": True,
            **system.diagnostics(),
        }
        if not qp_result.success:
            return residue_array.copy(), constant_array.copy(), {
                "success": False,
                "message": qp_result.message,
                "dual_condition_number": qp_result.dual_condition_number,
                "dual_regularization": qp_result.regularization,
                **base_diagnostics,
            }
        x_full = np.zeros(n_vars, dtype=float)
        x_full[system.full_variable_indices[local_indices]] = qp_result.x
        updated_residues = _apply_residue_delta(
            residue_array,
            x_full,
            nports=nports,
            vars_per_pair=vars_per_pair,
            n_real=n_real,
            real_poles=real_poles,
            complex_pairs=complex_pairs,
            scale=1.0,
        )
        updated_constant = (
            _apply_constant_delta(
                constant_array,
                x_full,
                nports=nports,
                offset=n_residue_vars,
                scale=1.0,
            )
            if perturb_constant
            else constant_array.copy()
        )
        return updated_residues, updated_constant, {
            "success": True,
            "active_rank": int(np.linalg.matrix_rank(system.A_ineq[:, local_indices])),
            "active_condition_number": _safe_condition_number(system.A_ineq[:, local_indices]),
            "dual_condition_number": qp_result.dual_condition_number,
            "dual_regularization": qp_result.regularization,
            "step_norm": float(np.linalg.norm(x_full)),
            **base_diagnostics,
        }

    target_norm = max(0.0, 1.0 - float(epsilon) - float(safety_margin) - active_target_margin)
    A_rows: list[np.ndarray] = []
    b_values: list[float] = []
    allowed_response_indices: set[int] = set()
    active_singular_modes = max(1, int(singular_modes))
    active_band_singular_modes = max(active_singular_modes, int(band_singular_modes))
    band_singular_mode_freq_set = (
        {float(freq) for freq in np.asarray(band_singular_mode_freqs, dtype=float).reshape(-1)}
        if band_singular_mode_freqs is not None
        else set()
    )
    for freq in freq_list:
        current = _evaluate_s_matrix_at_freq(
            pole_array,
            residue_array,
            constant_array,
            nports=nports,
            freq=freq,
        )
        U, singular_values, Vh = la.svd(current)
        if len(singular_values) == 0:
            continue
        singular_modes_for_freq = (
            active_band_singular_modes if float(freq) in band_singular_mode_freq_set else active_singular_modes
        )
        for mode_idx in range(min(singular_modes_for_freq, len(singular_values))):
            sigma = float(singular_values[mode_idx])
            if sigma <= target_norm:
                continue
            u_vec = U[:, mode_idx]
            v_vec = Vh.conj().T[:, mode_idx]
            if max_mode_responses > 0:
                response_indices = _dominant_response_indices_from_singular_vectors(
                    u_vec,
                    v_vec,
                    nports=nports,
                    max_responses=max_mode_responses,
                )
            else:
                response_indices = list(range(nports * nports))
            allowed_response_indices.update(int(response_idx) for response_idx in response_indices)
            s_val = 1j * 2.0 * np.pi * freq
            row = np.zeros(n_vars, dtype=float)
            for response_idx in response_indices:
                i = response_idx // nports
                j = response_idx % nports
                u_term = np.conj(u_vec[i]) * v_vec[j]
                offset = response_idx * vars_per_pair
                for var_idx, (_pole_idx, val) in enumerate(real_poles):
                    basis = 1.0 / (s_val - val)
                    row[offset + var_idx] = float(np.real(u_term * basis))
                for var_idx, (_pole_idx1, _pole_idx2, sigma_p, omega_p) in enumerate(complex_pairs):
                    z1 = 1.0 / (s_val - (sigma_p + 1j * omega_p))
                    z2 = 1.0 / (s_val - (sigma_p - 1j * omega_p))
                    row[offset + n_real + 2 * var_idx] = float(np.real(u_term * (z1 + z2)))
                    row[offset + n_real + 2 * var_idx + 1] = float(np.real(u_term * (1j * (z1 - z2))))
                if perturb_constant:
                    row[n_residue_vars + response_idx] = float(np.real(u_term))
            A_rows.append(row)
            b_values.append(target_norm - sigma)

    if not A_rows:
        return residue_array.copy(), constant_array.copy(), {
            "success": False,
            "constraint_count": 0,
            "message": "no active violating modes",
            "target_margin": float(active_target_margin),
        }

    A_ineq = np.asarray(A_rows, dtype=float)
    b_ineq = np.asarray(b_values, dtype=float)
    if max_mode_responses > 0:
        allowed_variable_indices: list[int] = []
        for response_idx in sorted(allowed_response_indices):
            start = response_idx * vars_per_pair
            allowed_variable_indices.extend(range(start, start + vars_per_pair))
            if perturb_constant:
                allowed_variable_indices.append(n_residue_vars + response_idx)
        allowed_variable_indices_array = np.asarray(sorted(set(allowed_variable_indices)), dtype=int)
    else:
        allowed_variable_indices_array = np.arange(n_vars, dtype=int)
    if max_active_variables is not None and 0 < int(max_active_variables) < n_vars:
        local_active_indices = _select_active_variable_indices(
            A_ineq[:, allowed_variable_indices_array],
            int(max_active_variables),
            variable_weights=None
            if variable_weights is None
            else np.asarray(variable_weights, dtype=float)[allowed_variable_indices_array],
        )
        active_indices = allowed_variable_indices_array[local_active_indices]
    else:
        active_indices = allowed_variable_indices_array
    active_weights = None if variable_weights is None else np.asarray(variable_weights, dtype=float)[active_indices]
    if solver == "min_norm":
        qp_result = _solve_min_norm_upper_bound_dual_qp(
            A_ineq[:, active_indices],
            b_ineq,
            variable_weights=active_weights,
        )
    elif solver == "nnls":
        qp_result = _solve_min_norm_upper_bound_nnls(
            A_ineq[:, active_indices],
            b_ineq,
            variable_weights=active_weights,
        )
    elif solver == "minimax_slack":
        step_regularization = _minimax_step_regularization(
            A_ineq[:, active_indices],
            b_ineq,
            variable_weights=active_weights,
        )
        qp_result = _solve_minimax_slack_upper_bound_dual_qp(
            A_ineq[:, active_indices],
            b_ineq,
            step_regularization=step_regularization,
            slack_weight=1.0,
            variable_weights=active_weights,
        )
    elif solver in {
        "reference_regularized_min_norm",
        "reference_regularized_nnls",
        "reference_regularized_peak_minimax",
        "reference_compensated_min_norm",
    }:
        if reference_freqs is None or reference_s is None:
            return residue_array.copy(), constant_array.copy(), {
                "success": False,
                "solver": solver,
                "constraint_count": int(A_ineq.shape[0]),
                "allowed_response_count": int(len(allowed_response_indices)),
                "active_variable_count": int(len(active_indices)),
                "message": f"{solver} requires reference_freqs and reference_s",
                "target_margin": float(active_target_margin),
            }
        reference_regularization_freqs = _active_mode_reference_regularization_freqs(
            freq_list,
            reference_freqs,
            global_reference_points=reference_global_points,
        )
        reference_regularization_sample_weights = _active_mode_reference_regularization_sample_weights(
            freq_list,
            reference_sample_weights,
            reference_regularization_freqs,
        )
        C_ref, d_ref = _active_mode_reference_scalar_rows(
            pole_array,
            residue_array,
            constant_array,
            nports=nports,
            freqs=reference_regularization_freqs,
            reference_freqs=reference_freqs,
            reference_s=reference_s,
            variable_indices=active_indices,
            vars_per_pair=vars_per_pair,
            n_residue_vars=n_residue_vars,
            n_vars=n_vars,
            real_poles=real_poles,
            complex_pairs=complex_pairs,
            perturb_constant=perturb_constant,
            target_scale=reference_target_scale,
            sample_weights=reference_regularization_sample_weights,
        )
        if solver == "reference_regularized_peak_minimax":
            qp_result = _solve_reference_regularized_peak_minimax_dual_qp(
                A_ineq[:, active_indices],
                b_ineq,
                C_ref,
                d_ref,
                reference_weight=reference_weight,
                variable_weights=active_weights,
            )
        elif solver == "reference_regularized_nnls":
            qp_result = _solve_reference_regularized_upper_bound_nnls(
                A_ineq[:, active_indices],
                b_ineq,
                C_ref,
                d_ref,
                reference_weight=reference_weight,
                variable_weights=active_weights,
            )
        else:
            qp_result = _solve_reference_regularized_upper_bound_dual_qp(
                A_ineq[:, active_indices],
                b_ineq,
                C_ref,
                d_ref,
                reference_weight=reference_weight,
                variable_weights=active_weights,
            )
    else:
        raise ValueError(
            "active-mode solver must be 'min_norm', 'nnls', 'minimax_slack', "
            "'reference_regularized_min_norm', 'reference_regularized_nnls', "
            "'reference_regularized_peak_minimax', "
            "or 'reference_compensated_min_norm'"
        )
    if not qp_result.success:
        return residue_array.copy(), constant_array.copy(), {
            "success": False,
            "solver": solver,
            "constraint_count": int(A_ineq.shape[0]),
            "allowed_response_count": int(len(allowed_response_indices)),
            "active_variable_count": int(len(active_indices)),
            "message": qp_result.message,
            "target_margin": float(active_target_margin),
            "dual_condition_number": qp_result.dual_condition_number,
            "dual_regularization": qp_result.regularization,
        "reference_weight": float(reference_weight),
        "reference_target_scale": float(reference_target_scale),
        "reference_row_count": int(locals().get("C_ref", np.empty((0, 0))).shape[0]),
        }

    x_full = np.zeros(n_vars, dtype=float)
    x_full[active_indices] = qp_result.x
    updated_residues = _apply_residue_delta(
        residue_array,
        x_full,
        nports=nports,
        vars_per_pair=vars_per_pair,
        n_real=n_real,
        real_poles=real_poles,
        complex_pairs=complex_pairs,
        scale=1.0,
    )
    updated_constant = (
        _apply_constant_delta(
            constant_array,
            x_full,
            nports=nports,
            offset=n_residue_vars,
            scale=1.0,
        )
        if perturb_constant
        else constant_array.copy()
    )
    return updated_residues, updated_constant, {
        "success": True,
        "solver": solver,
        "constraint_count": int(A_ineq.shape[0]),
        "allowed_response_count": int(len(allowed_response_indices)),
        "active_variable_count": int(len(active_indices)),
        "max_mode_responses": int(max_mode_responses),
        "singular_modes": int(active_singular_modes),
        "band_singular_modes": int(active_band_singular_modes),
        "band_singular_mode_frequency_count": int(len(band_singular_mode_freq_set)),
        "target_margin": float(active_target_margin),
        "active_rank": int(np.linalg.matrix_rank(A_ineq[:, active_indices])),
        "active_condition_number": _safe_condition_number(A_ineq[:, active_indices]),
        "dual_condition_number": qp_result.dual_condition_number,
        "dual_regularization": qp_result.regularization,
        "reference_weight": float(reference_weight),
        "reference_target_scale": float(reference_target_scale),
        "reference_weight_mode": "sample_weighted" if reference_sample_weights is not None else "none",
        "reference_global_points": int(max(0, int(reference_global_points))),
        "reference_frequency_count": int(locals().get("reference_regularization_freqs", []).__len__()),
        "reference_row_count": int(locals().get("C_ref", np.empty((0, 0))).shape[0]),
        "slack": qp_result.slack,
        "peak_slack": qp_result.slack if solver == "reference_regularized_peak_minimax" else None,
        "step_norm": float(np.linalg.norm(x_full)),
    }


def _active_mode_reference_rows(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
    reference_freqs: Any,
    reference_s: Any,
    response_indices: Any,
    variable_indices: Any | None = None,
    vars_per_pair: int,
    n_residue_vars: int,
    n_vars: int,
    real_poles: Any,
    complex_pairs: Any,
    perturb_constant: bool,
) -> tuple[np.ndarray, np.ndarray]:
    if variable_indices is None:
        selected_variables = np.arange(n_vars, dtype=int)
    else:
        selected_variables = np.asarray(variable_indices, dtype=int)
        if selected_variables.ndim != 1:
            raise ValueError("variable_indices must be a 1D sequence")
        if np.any(selected_variables < 0) or np.any(selected_variables >= n_vars):
            raise ValueError("variable_indices contains an out-of-range column")

    def variable_coefficient(variable_idx: int, response_idx: int, s_val: complex) -> complex:
        if variable_idx < n_residue_vars:
            if vars_per_pair <= 0:
                return 0.0 + 0.0j
            variable_response_idx = variable_idx // vars_per_pair
            if variable_response_idx != response_idx:
                return 0.0 + 0.0j
            local_idx = variable_idx % vars_per_pair
            if local_idx < len(real_poles):
                _pole_idx, val = real_poles[local_idx]
                return 1.0 / (s_val - val)
            pair_local_idx = local_idx - len(real_poles)
            pair_idx = pair_local_idx // 2
            if pair_idx >= len(complex_pairs):
                return 0.0 + 0.0j
            _pole_idx1, _pole_idx2, sigma_p, omega_p = complex_pairs[pair_idx]
            z1 = 1.0 / (s_val - (sigma_p + 1j * omega_p))
            z2 = 1.0 / (s_val - (sigma_p - 1j * omega_p))
            if pair_local_idx % 2 == 0:
                return z1 + z2
            return 1j * (z1 - z2)
        if not perturb_constant:
            return 0.0 + 0.0j
        constant_response_idx = variable_idx - n_residue_vars
        return 1.0 + 0.0j if constant_response_idx == response_idx else 0.0 + 0.0j

    rows: list[np.ndarray] = []
    targets: list[float] = []
    for freq in freqs:
        freq_float = float(freq)
        current = _evaluate_s_matrix_at_freq(
            poles,
            residues,
            constant_coeff,
            nports=nports,
            freq=freq_float,
        )
        reference = _reference_matrix_at_freq(
            freq=freq_float,
            reference_freqs=reference_freqs,
            reference_s=reference_s,
            nports=nports,
        )
        s_val = 1j * 2.0 * np.pi * freq_float
        for response_idx in response_indices:
            response_idx = int(response_idx)
            row_idx = response_idx // nports
            column_idx = response_idx % nports
            coeff = np.asarray(
                [variable_coefficient(int(variable_idx), response_idx, s_val) for variable_idx in selected_variables],
                dtype=complex,
            )
            delta_target = reference[row_idx, column_idx] - current[row_idx, column_idx]
            rows.append(np.real(coeff))
            targets.append(float(np.real(delta_target)))
            rows.append(np.imag(coeff))
            targets.append(float(np.imag(delta_target)))
    if not rows:
        return np.zeros((0, len(selected_variables)), dtype=float), np.zeros(0, dtype=float)
    return np.asarray(rows, dtype=float), np.asarray(targets, dtype=float)


def _active_mode_reference_scalar_rows(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
    reference_freqs: Any,
    reference_s: Any,
    variable_indices: Any,
    vars_per_pair: int,
    n_residue_vars: int,
    n_vars: int,
    real_poles: Any,
    complex_pairs: Any,
    perturb_constant: bool,
    target_scale: float = 1.0,
    sample_weights: Any | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    selected_variables = np.asarray(variable_indices, dtype=int)
    if selected_variables.ndim != 1:
        raise ValueError("variable_indices must be a 1D sequence")
    if np.any(selected_variables < 0) or np.any(selected_variables >= n_vars):
        raise ValueError("variable_indices contains an out-of-range column")
    freq_list = [float(freq) for freq in freqs]
    if sample_weights is None:
        weight_scales = np.ones(len(freq_list), dtype=float)
    else:
        weights = np.asarray(sample_weights, dtype=float)
        if weights.ndim != 1 or weights.shape[0] != len(freq_list):
            raise ValueError("sample_weights must contain one finite non-negative value per frequency")
        if np.any(weights < 0.0) or not np.all(np.isfinite(weights)):
            raise ValueError("sample_weights must contain finite non-negative values")
        weight_scales = np.sqrt(weights)

    def variable_response_and_basis(variable_idx: int, s_val: complex) -> tuple[int | None, complex]:
        if variable_idx < n_residue_vars:
            if vars_per_pair <= 0:
                return None, 0.0 + 0.0j
            variable_response_idx = variable_idx // vars_per_pair
            local_idx = variable_idx % vars_per_pair
            if local_idx < len(real_poles):
                _pole_idx, val = real_poles[local_idx]
                return int(variable_response_idx), 1.0 / (s_val - val)
            pair_local_idx = local_idx - len(real_poles)
            pair_idx = pair_local_idx // 2
            if pair_idx >= len(complex_pairs):
                return None, 0.0 + 0.0j
            _pole_idx1, _pole_idx2, sigma_p, omega_p = complex_pairs[pair_idx]
            z1 = 1.0 / (s_val - (sigma_p + 1j * omega_p))
            z2 = 1.0 / (s_val - (sigma_p - 1j * omega_p))
            if pair_local_idx % 2 == 0:
                return int(variable_response_idx), z1 + z2
            return int(variable_response_idx), 1j * (z1 - z2)
        if not perturb_constant:
            return None, 0.0 + 0.0j
        constant_response_idx = variable_idx - n_residue_vars
        return int(constant_response_idx), 1.0 + 0.0j

    rows: list[np.ndarray] = []
    targets: list[float] = []
    for freq_index, freq_float in enumerate(freq_list):
        current = _evaluate_s_matrix_at_freq(
            poles,
            residues,
            constant_coeff,
            nports=nports,
            freq=freq_float,
        )
        reference = float(target_scale) * _reference_matrix_at_freq(
            freq=freq_float,
            reference_freqs=reference_freqs,
            reference_s=reference_s,
            nports=nports,
        )
        U, singular_values, Vh = la.svd(current)
        if len(singular_values) == 0:
            continue
        u_vec = U[:, 0]
        v_vec = Vh.conj().T[:, 0]
        s_val = 1j * 2.0 * np.pi * freq_float
        coeffs = []
        for variable_idx in selected_variables:
            response_idx, basis_coeff = variable_response_and_basis(int(variable_idx), s_val)
            if response_idx is None:
                coeffs.append(0.0 + 0.0j)
                continue
            row_idx = response_idx // nports
            column_idx = response_idx % nports
            mode_coeff = np.conj(u_vec[row_idx]) * v_vec[column_idx]
            scalar_coeff = mode_coeff * basis_coeff
            coeffs.append(scalar_coeff)
        delta_target = np.vdot(u_vec, (reference - current) @ v_vec)
        coeff_array = np.asarray(coeffs, dtype=complex)
        scale = float(weight_scales[freq_index])
        rows.append(scale * np.real(coeff_array))
        targets.append(scale * float(np.real(delta_target)))
        rows.append(scale * np.imag(coeff_array))
        targets.append(scale * float(np.imag(delta_target)))
    if not rows:
        return np.zeros((0, len(selected_variables)), dtype=float), np.zeros(0, dtype=float)
    return np.asarray(rows, dtype=float), np.asarray(targets, dtype=float)


def _dominant_response_indices_from_singular_vectors(
    u_vec: np.ndarray,
    v_vec: np.ndarray,
    *,
    nports: int,
    max_responses: int,
) -> list[int]:
    if max_responses <= 0:
        return []
    scores = []
    for row in range(nports):
        for column in range(nports):
            response_idx = row * nports + column
            score = abs(u_vec[row]) * abs(v_vec[column])
            scores.append((float(score), response_idx))
    scores.sort(key=lambda item: (-item[0], item[1]))
    return [response_idx for _score, response_idx in scores[: int(max_responses)]]


def _select_projection_candidate(
    candidates: list[dict[str, Any]],
    *,
    baseline_max_sigma: float,
    baseline_violation_count: int,
    max_sigma_regression: float = 0.0,
    max_delta_norm: float | None = None,
    max_response_delta_rms: float | None = None,
    baseline_reference_rms: float | None = None,
    max_reference_rms_increase: float | None = None,
    initial_reference_rms: float | None = None,
    max_reference_rms_total_increase: float | None = None,
    max_reference_rms_per_sigma_improvement: float | None = None,
    late_current_clip_max_reference_rms_per_sigma_improvement: float | None = None,
    late_current_clip_start_iteration: int = 0,
    max_reference_band_sigma_regression: float | None = None,
    active_mode_max_reference_rms_total_increase: float | None = None,
    post_damping_max_sigma_regression: float | None = None,
    baseline_post_damping_reference_rms: float | None = None,
    selection_metric: str = "passivity",
) -> dict[str, Any] | None:
    if selection_metric not in {"passivity", "post_damping_reference_rms"}:
        raise ValueError("selection_metric must be 'passivity' or 'post_damping_reference_rms'")
    accepted = []
    for candidate in candidates:
        if not _projection_candidate_passes_cheap_gates(
            candidate,
            max_delta_norm=max_delta_norm,
            max_response_delta_rms=max_response_delta_rms,
            baseline_reference_rms=baseline_reference_rms,
            max_reference_rms_increase=max_reference_rms_increase,
            initial_reference_rms=initial_reference_rms,
            max_reference_rms_total_increase=max_reference_rms_total_increase,
            max_reference_rms_per_sigma_improvement=max_reference_rms_per_sigma_improvement,
            late_current_clip_max_reference_rms_per_sigma_improvement=(
                late_current_clip_max_reference_rms_per_sigma_improvement
            ),
            late_current_clip_start_iteration=late_current_clip_start_iteration,
            max_reference_band_sigma_regression=max_reference_band_sigma_regression,
            active_mode_max_reference_rms_total_increase=active_mode_max_reference_rms_total_increase,
        ):
            continue
        if (
            _projection_candidate_reject_reason(
                candidate,
                baseline_max_sigma=baseline_max_sigma,
                baseline_violation_count=baseline_violation_count,
                max_sigma_regression=max_sigma_regression,
                baseline_reference_rms=baseline_reference_rms,
                initial_reference_rms=initial_reference_rms,
                max_reference_rms_per_sigma_improvement=max_reference_rms_per_sigma_improvement,
                late_current_clip_max_reference_rms_per_sigma_improvement=(
                    late_current_clip_max_reference_rms_per_sigma_improvement
                ),
                late_current_clip_start_iteration=late_current_clip_start_iteration,
                max_reference_band_sigma_regression=max_reference_band_sigma_regression,
                active_mode_max_reference_rms_total_increase=active_mode_max_reference_rms_total_increase,
                post_damping_max_sigma_regression=post_damping_max_sigma_regression,
                baseline_post_damping_reference_rms=baseline_post_damping_reference_rms,
            )
            is not None
        ):
            continue
        accepted.append(candidate)
    if not accepted:
        return None
    if selection_metric == "post_damping_reference_rms":
        return min(
            accepted,
            key=lambda candidate: (
                float(candidate.get("post_damping_reference_rms", math.inf)),
                float(candidate.get("reference_rms", math.inf)),
                _projection_candidate_passivity_rank(
                    candidate,
                    baseline_max_sigma=baseline_max_sigma,
                    baseline_violation_count=baseline_violation_count,
                    max_sigma_regression=max_sigma_regression,
                ),
                float(candidate["max_sigma"]),
                int(candidate["violation_count"]),
                float(candidate["delta_norm"]),
            ),
        )
    return min(
        accepted,
        key=lambda candidate: (
            _projection_candidate_passivity_rank(
                candidate,
                baseline_max_sigma=baseline_max_sigma,
                baseline_violation_count=baseline_violation_count,
                max_sigma_regression=max_sigma_regression,
            ),
            float(candidate["max_sigma"]),
            int(candidate["violation_count"]),
            float(candidate.get("reference_rms", 0.0)),
            float(candidate.get("response_delta_rms", 0.0)),
            float(candidate["delta_norm"]),
        ),
    )


def _response_delta_rms_at_freqs(
    poles: np.ndarray,
    residues_before: np.ndarray,
    constant_before: np.ndarray,
    residues_after: np.ndarray,
    constant_after: np.ndarray,
    *,
    nports: int,
    freqs: Any,
    basis: np.ndarray | None = None,
) -> float:
    freqs_array = np.asarray(list(freqs), dtype=float)
    if freqs_array.size == 0:
        return 0.0
    if basis is None:
        before = _evaluate_s_matrices_at_freqs(
            poles,
            residues_before,
            constant_before,
            nports=nports,
            freqs=freqs_array,
        )
        after = _evaluate_s_matrices_at_freqs(
            poles,
            residues_after,
            constant_after,
            nports=nports,
            freqs=freqs_array,
        )
    else:
        before = _evaluate_s_matrices_from_basis(
            residues_before,
            constant_before,
            nports=nports,
            basis=basis,
        )
        after = _evaluate_s_matrices_from_basis(
            residues_after,
            constant_after,
            nports=nports,
            basis=basis,
        )
    flat = np.abs(after - before).reshape(-1)
    return float(np.sqrt(np.mean(np.abs(flat) ** 2)))


def _reference_response_rms_at_freqs(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
    reference_freqs: Any,
    reference_s: Any,
) -> float:
    freqs_array = np.asarray(list(freqs), dtype=float)
    if freqs_array.size == 0:
        return 0.0
    reference = _reference_s_matrices_at_freqs(
        freqs_array,
        reference_freqs=reference_freqs,
        reference_s=reference_s,
        nports=nports,
    )
    return _reference_response_rms_to_matrices(
        poles,
        residues,
        constant_coeff,
        nports=nports,
        freqs=freqs_array,
        reference_matrices=reference,
    )


def _reference_response_rms_to_matrices(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
    reference_matrices: np.ndarray,
    basis: np.ndarray | None = None,
) -> float:
    freqs_array = np.asarray(list(freqs), dtype=float)
    if freqs_array.size == 0:
        return 0.0
    reference = np.asarray(reference_matrices, dtype=complex)
    if reference.shape != (freqs_array.size, nports, nports):
        raise ValueError("reference_matrices must have shape (nfreq, nports, nports)")
    if basis is None:
        fitted = _evaluate_s_matrices_at_freqs(
            poles,
            residues,
            constant_coeff,
            nports=nports,
            freqs=freqs_array,
        )
    else:
        fitted = _evaluate_s_matrices_from_basis(
            residues,
            constant_coeff,
            nports=nports,
            basis=basis,
        )
    flat = np.abs(fitted - reference).reshape(-1)
    return float(np.sqrt(np.mean(np.abs(flat) ** 2)))


def _reference_response_rms_chunked(
    poles: np.ndarray,
    residues: np.ndarray,
    constant_coeff: np.ndarray,
    *,
    nports: int,
    freqs: Any,
    reference_freqs: Any,
    reference_s: Any,
    chunk_size: int = 128,
) -> float:
    freqs_array = np.asarray(list(freqs), dtype=float)
    if freqs_array.size == 0:
        return 0.0
    step = max(1, int(chunk_size))
    error_sum = 0.0
    error_count = 0
    for start in range(0, freqs_array.size, step):
        chunk_freqs = freqs_array[start : start + step]
        reference = _reference_s_matrices_at_freqs(
            chunk_freqs,
            reference_freqs=reference_freqs,
            reference_s=reference_s,
            nports=nports,
        )
        fitted = _evaluate_s_matrices_at_freqs(
            poles,
            residues,
            constant_coeff,
            nports=nports,
            freqs=chunk_freqs,
        )
        diff = np.abs(fitted - reference)
        error_sum += float(np.sum(diff * diff))
        error_count += int(diff.size)
    if error_count == 0:
        return 0.0
    return float(np.sqrt(error_sum / error_count))


def _reference_response_rms_candidates_chunked(
    poles: np.ndarray,
    candidates: list[tuple[np.ndarray, np.ndarray]],
    *,
    nports: int,
    freqs: Any,
    reference_freqs: Any,
    reference_s: Any,
    chunk_size: int = 128,
) -> list[float]:
    freqs_array = np.asarray(list(freqs), dtype=float)
    if not candidates:
        return []
    if freqs_array.size == 0:
        return [0.0 for _residues, _constant in candidates]
    step = max(1, int(chunk_size))
    error_sums = [0.0 for _residues, _constant in candidates]
    error_count = 0
    for start in range(0, freqs_array.size, step):
        chunk_freqs = freqs_array[start : start + step]
        basis = _rational_basis_at_freqs(poles, chunk_freqs)
        reference = _reference_s_matrices_at_freqs(
            chunk_freqs,
            reference_freqs=reference_freqs,
            reference_s=reference_s,
            nports=nports,
        )
        chunk_count = int(reference.size)
        for index, (candidate_residues, candidate_constant) in enumerate(candidates):
            fitted = _evaluate_s_matrices_from_basis(
                candidate_residues,
                candidate_constant,
                nports=nports,
                basis=basis,
            )
            diff = np.abs(fitted - reference)
            error_sums[index] += float(np.sum(diff * diff))
        error_count += chunk_count
    if error_count == 0:
        return [0.0 for _residues, _constant in candidates]
    return [float(np.sqrt(error_sum / error_count)) for error_sum in error_sums]


def _reference_s_matrices_at_freqs(
    freqs: Any,
    *,
    reference_freqs: Any,
    reference_s: Any,
    nports: int,
) -> np.ndarray:
    freqs_array = np.asarray(list(freqs), dtype=float)
    reference_freq_array = np.asarray(reference_freqs, dtype=float)
    reference_s_array = np.asarray(reference_s, dtype=complex)
    if reference_freq_array.ndim != 1 or reference_s_array.shape[0] != reference_freq_array.shape[0]:
        raise ValueError("reference_freqs and reference_s must share the frequency axis")
    if reference_s_array.shape[1:] != (nports, nports):
        raise ValueError("reference_s must have shape (nfreq, nports, nports)")

    reference_flat = reference_s_array.reshape(reference_freq_array.size, nports * nports)
    real = np.vstack(
        [np.interp(freqs_array, reference_freq_array, np.real(reference_flat[:, idx])) for idx in range(nports * nports)]
    ).T
    imag = np.vstack(
        [np.interp(freqs_array, reference_freq_array, np.imag(reference_flat[:, idx])) for idx in range(nports * nports)]
    ).T
    return (real + 1j * imag).reshape(freqs_array.size, nports, nports)


def enforce_passivity_hamiltonian(
    vector_fit: Any,
    *,
    nports: int,
    epsilon: float = 1e-6,
    max_iterations: int = 10,
    f_max: float | None = None,
    max_violation_samples: int = 64,
    max_active_variables: int = 512,
    perturb_constant: bool = False,
    perturb_poles: bool = False,
    constant_only_candidates: bool = False,
    global_damping_fallback: bool = False,
    global_damping_mode: str = "uniform",
    global_damping_selective_min_frequency: float = 5e8,
    global_damping_safety_margin: float = 1e-5,
    spectral_projection_fallback: bool = False,
    spectral_projection_max_delta_norm: float | None = None,
    spectral_projection_max_response_delta_rms: float | None = None,
    spectral_projection_max_sigma_regression: float = 0.0,
    spectral_projection_iterations: int = 1,
    spectral_projection_reweight_iterations: int = 0,
    spectral_projection_reference_freqs: Any | None = None,
    spectral_projection_reference_s: Any | None = None,
    spectral_projection_max_reference_rms_increase: float | None = None,
    spectral_projection_max_reference_rms_total_increase: float | None = None,
    spectral_projection_max_reference_rms_per_sigma_improvement: float | None = None,
    spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement: float | None = None,
    spectral_projection_late_current_clip_start_iteration: int = 0,
    spectral_projection_max_reference_band_sigma_regression: float | None = None,
    spectral_projection_reference_band_holdout_start_iteration: int = 0,
    spectral_projection_include_all_reference_violations: bool = False,
    spectral_projection_weight_mode: str = "none",
    spectral_projection_weight_exponent: float = 1.0,
    spectral_projection_active_mode_candidate: bool = False,
    spectral_projection_active_mode_start_iteration: int = 0,
    spectral_projection_non_active_stop_iteration: int | None = None,
    spectral_projection_active_mode_max_responses: int = 0,
    spectral_projection_active_mode_singular_modes: int = 1,
    spectral_projection_active_mode_band_singular_modes: int = 1,
    spectral_projection_active_mode_band_singular_mode_sample_count: int = 1,
    spectral_projection_active_mode_solver: str = "min_norm",
    spectral_projection_active_mode_target_margin: float = 0.0,
    spectral_projection_active_mode_target_margin_start_iteration: int = 0,
    spectral_projection_active_mode_reference_max_points: int = 0,
    spectral_projection_active_mode_frequency_selection: str = "top",
    spectral_projection_active_mode_reference_weight: float = 0.0,
    spectral_projection_active_mode_reference_weight_mode: str = "none",
    spectral_projection_active_mode_reference_weight_candidates: tuple[float, ...] = (),
    spectral_projection_active_mode_global_reference_points: int = 0,
    spectral_projection_active_mode_max_reference_rms_total_increase: float | None = None,
    spectral_projection_active_mode_extra_scales: tuple[float, ...] = (),
    spectral_projection_active_mode_extra_scales_min_sigma: float = 0.0,
    spectral_projection_current_clip_candidate: bool = False,
    spectral_projection_current_clip_reference_weight: float = 0.0,
    spectral_projection_candidate_reference_max_points: int = 0,
    spectral_projection_frequency_selection: str = "top",
    spectral_projection_band_sample_count: int = 8,
    spectral_projection_reference_rms_scope: str = "projection",
    spectral_projection_reference_rms_chunk_size: int = 0,
    spectral_projection_candidate_selection_metric: str = "passivity",
    spectral_projection_post_damping_selection_start_iteration: int = 0,
    spectral_projection_post_damping_max_sigma_regression: float | None = None,
    spectral_projection_mode_screen_candidates: int = 0,
    spectral_projection_mode_screen_modes: int = 2,
    constant_weight: float = 1.0,
    pole_weight: float = 1.0,
    max_modes_per_frequency: int = 2,
) -> None:
    """
    Enforces passivity of S-parameter model using Hamiltonian crossover checks and SLSQP residue, constant, and pole perturbations.
    """
    poles_orig = np.asarray(getattr(vector_fit, "poles", []), dtype=complex)
    residues_orig = np.asarray(getattr(vector_fit, "residues", []), dtype=complex)
    constant_coeff = np.asarray(getattr(vector_fit, "constant_coeff", []), dtype=complex)

    if residues_orig.size == 0 and len(poles_orig) > 0:
        residues_orig = np.zeros((nports * nports, len(poles_orig)), dtype=complex)
    if constant_coeff.size == 0:
        constant_coeff = np.zeros(nports * nports, dtype=complex)

    poles, residues = _expand_poles_and_residues(poles_orig, residues_orig)

    asymptotic_target = max(
        0.0,
        1.0 - max(float(epsilon), 64.0 * np.finfo(float).eps),
    )

    # Fix an invalid asymptote before the expensive frequency-domain work when
    # no configured repair path can perturb D. Also close the previous
    # tolerance gap in global damping: that fallback triggers above 1+epsilon,
    # while the exported RFM quality gate correctly requires sigma(D) < 1.
    asymptotic_preprojection_available = not (perturb_constant or spectral_projection_fallback)
    if asymptotic_preprojection_available:
        constant_coeff, asymptotic_sigma_before, asymptotic_sigma_after, asymptotic_target = (
            _project_asymptotic_constant_strictly_passive(
                constant_coeff,
                nports=nports,
                epsilon=epsilon,
                maximum_sigma_to_project=(1.0 + epsilon) if global_damping_fallback else None,
            )
        )
        asymptotic_preprojection_enabled = (
            not global_damping_fallback or asymptotic_sigma_before <= 1.0 + epsilon
        )
        asymptotic_constant_projected = (
            asymptotic_sigma_before >= 1.0 and asymptotic_sigma_after < asymptotic_sigma_before
        )
    else:
        constant_matrix = constant_coeff.reshape(nports, nports)
        asymptotic_singular_values = la.svd(constant_matrix, compute_uv=False)
        asymptotic_sigma_before = (
            float(asymptotic_singular_values[0]) if len(asymptotic_singular_values) else 0.0
        )
        asymptotic_sigma_after = asymptotic_sigma_before
        asymptotic_preprojection_enabled = False
        asymptotic_constant_projected = False

    best_residues = residues.copy()
    best_constant = constant_coeff.copy()
    best_poles = poles.copy()
    best_score: _PassivityScore | None = None
    diagnostics: list[dict[str, Any]] = []
    vector_fit.passivity_enforcement_diagnostics = diagnostics
    diagnostics.append(
        {
            "type": "asymptotic_constant_projection",
            "enabled": bool(asymptotic_preprojection_enabled),
            "projected": bool(asymptotic_constant_projected),
            "sigma_before": float(asymptotic_sigma_before),
            "sigma_after": float(asymptotic_sigma_after),
            "target_norm": float(asymptotic_target),
        }
    )

    for iteration in range(max_iterations):
        crossover_freqs = check_passivity_hamiltonian_s(poles, residues, constant_coeff, nports, f_max=f_max)

        f_limit = 100e9
        if len(crossover_freqs) > 0:
            f_limit = max(f_limit, crossover_freqs[-1] * 2.0)
        if f_max is not None:
            f_limit = min(f_limit, f_max)
        points = [0.0] + crossover_freqs + [f_limit]

        violating_freqs = _adaptive_violation_frequencies_for_enforcement(
            poles,
            residues,
            constant_coeff,
            nports=nports,
            points=points,
            epsilon=epsilon,
            max_violation_samples=max_violation_samples,
            f_max=f_max,
            max_depth=1,
            curvature_tol=1e-3,
        )

        if len(violating_freqs) == 0:
            best_residues = residues.copy()
            best_constant = constant_coeff.copy()
            best_poles = poles.copy()
            best_score = _PassivityScore(0, 1.0)
            break

        current_score = _PassivityScore(
            violation_count=len(violating_freqs),
            max_sigma=max(sigma for _freq, sigma in violating_freqs),
        )
        if current_score.is_better_than(best_score):
            best_score = current_score
            best_residues = residues.copy()
            best_constant = constant_coeff.copy()
            best_poles = poles.copy()

        real_poles, complex_pairs = partition_poles(poles)
        n_real = len(real_poles)
        n_complex = len(complex_pairs)
        vars_per_pair = n_real + 2 * n_complex

        n_residue_vars = nports * nports * vars_per_pair
        n_constant_vars = nports * nports if perturb_constant else 0
        n_pole_vars = (n_real + 2 * n_complex) if perturb_poles else 0
        n_vars = n_residue_vars + n_constant_vars + n_pole_vars
        base_qp_weights = _base_perturbation_weights(
            n_residue_vars=n_residue_vars,
            n_constant_vars=n_constant_vars,
            n_pole_vars=n_pole_vars,
            constant_weight=constant_weight,
            pole_weight=pole_weight,
        )

        A_list = []
        b_list = []

        for f_v, sigma_max in violating_freqs:
            s_val = 1j * 2.0 * np.pi * f_v
            S_f = constant_coeff.reshape((nports, nports)).copy().astype(complex)
            for k in range(len(poles)):
                S_f += residues.reshape((nports, nports, len(poles)))[:, :, k] / (s_val - poles[k])

            U, s_values, Vh = la.svd(S_f)
            for sm, u_m, v_m in _singular_violation_modes(
                U,
                s_values,
                Vh,
                epsilon=epsilon,
                max_modes_per_frequency=max_modes_per_frequency,
            ):
                A_row = np.zeros(n_vars)
                b_val = 1.0 - sm

                for i in range(nports):
                    for j in range(nports):
                        r_idx = i * nports + j
                        u_term = u_m[i].conj() * v_m[j]
                        offset = r_idx * vars_per_pair

                        for var_idx, (pole_idx, val) in enumerate(real_poles):
                            z = 1.0 / (s_val - val)
                            A_row[offset + var_idx] = np.real(u_term * z)

                        for var_idx, (pole_idx1, pole_idx2, sigma, omega) in enumerate(complex_pairs):
                            z1 = 1.0 / (s_val - (sigma + 1j * omega))
                            z2 = 1.0 / (s_val - (sigma - 1j * omega))
                            G1 = u_term * z1
                            G2 = u_term * z2
                            A_row[offset + n_real + 2 * var_idx] = np.real(G1 + G2)
                            A_row[offset + n_real + 2 * var_idx + 1] = -np.imag(G1 - G2)

                if perturb_constant:
                    for i in range(nports):
                        for j in range(nports):
                            r_idx = i * nports + j
                            u_term = u_m[i].conj() * v_m[j]
                            A_row[n_residue_vars + r_idx] = np.real(u_term)

                if perturb_poles:
                    pole_offset = n_residue_vars + n_constant_vars
                    # 1. Real poles
                    for var_idx, (pole_idx, val) in enumerate(real_poles):
                        sens = 0.0
                        z_sq = 1.0 / (s_val - val)**2
                        for i in range(nports):
                            for j in range(nports):
                                r_idx = i * nports + j
                                u_term = u_m[i].conj() * v_m[j]
                                R_val = residues[r_idx, pole_idx]
                                sens += np.real(u_term * R_val * z_sq)
                        A_row[pole_offset + var_idx] = sens

                    # 2. Complex pairs
                    for var_idx, (pole_idx1, pole_idx2, sigma, omega) in enumerate(complex_pairs):
                        sens_sigma = 0.0
                        sens_omega = 0.0
                        z1_sq = 1.0 / (s_val - (sigma + 1j * omega))**2
                        z2_sq = 1.0 / (s_val - (sigma - 1j * omega))**2
                        for i in range(nports):
                            for j in range(nports):
                                r_idx = i * nports + j
                                u_term = u_m[i].conj() * v_m[j]
                                R1 = residues[r_idx, pole_idx1]
                                R2 = residues[r_idx, pole_idx2]
                                d_sigma = R1 * z1_sq + R2 * z2_sq
                                d_omega = 1j * (R1 * z1_sq - R2 * z2_sq)
                                sens_sigma += np.real(u_term * d_sigma)
                                sens_omega += np.real(u_term * d_omega)
                        A_row[pole_offset + n_real + 2 * var_idx] = sens_sigma
                        A_row[pole_offset + n_real + 2 * var_idx + 1] = sens_omega

                A_list.append(A_row)
                b_list.append(b_val)

        if not A_list:
            break

        A_ineq = np.array(A_list)
        b_ineq = np.array(b_list)

        sampled_freqs = [freq for freq, _sigma in violating_freqs]
        holdout_freqs = _line_search_eval_frequencies(points, violating_freqs)
        sampled_score = _evaluate_passivity_score_at_freqs(
            poles,
            residues,
            constant_coeff,
            nports=nports,
            freqs=sampled_freqs,
            epsilon=epsilon,
        )
        holdout_score = _evaluate_passivity_score_at_freqs(
            poles,
            residues,
            constant_coeff,
            nports=nports,
            freqs=holdout_freqs,
            epsilon=epsilon,
        )
        variable_fit_weights: np.ndarray | None = None
        accepted_residues = None
        accepted_constant = None
        accepted_poles = None
        accepted_score: _PassivityScore | None = None
        accepted_delta_norm = np.inf
        accepted_priority = 10**9
        selected_diagnostic: dict[str, Any] | None = None

        for active_budget in _active_variable_budget_candidates(max_active_variables, n_vars):
            qp_attempts = [
                (
                    "residue_norm",
                    "hard_bound",
                    None,
                    None,
                    _select_active_variable_indices(A_ineq, active_budget, variable_weights=base_qp_weights),
                    base_qp_weights,
                ),
            ]
            for slack_weight in _minimax_slack_weight_candidates():
                qp_attempts.append(
                    (
                        "residue_norm",
                        "minimax_slack",
                        slack_weight,
                        None,
                        _select_active_variable_indices(A_ineq, active_budget, variable_weights=base_qp_weights),
                        base_qp_weights,
                    )
                )
            if constant_only_candidates and perturb_constant and n_constant_vars > 0:
                constant_active_indices = _constant_active_variable_indices(
                    A_ineq,
                    active_budget,
                    n_residue_vars=n_residue_vars,
                    n_constant_vars=n_constant_vars,
                    variable_weights=base_qp_weights,
                )
                if len(constant_active_indices) > 0:
                    qp_attempts.append(
                        (
                            "constant_only",
                            "hard_bound",
                            None,
                            None,
                            constant_active_indices,
                            base_qp_weights,
                        )
                    )
                    for slack_weight in _minimax_slack_weight_candidates():
                        qp_attempts.append(
                            (
                                "constant_only",
                                "minimax_slack",
                                slack_weight,
                                None,
                                constant_active_indices,
                                base_qp_weights,
                            )
                        )
            if _should_try_fit_weighted_qp(accepted_score):
                if variable_fit_weights is None:
                    variable_fit_weights = _variable_fit_weights(
                        poles=poles,
                        residues=residues,
                        nports=nports,
                        vars_per_pair=vars_per_pair,
                        real_poles=real_poles,
                        complex_pairs=complex_pairs,
                        freqs=holdout_freqs,
                        perturb_constant=perturb_constant,
                        perturb_poles=perturb_poles,
                        constant_weight=constant_weight,
                        pole_weight=pole_weight,
                    )
                qp_attempts.append(
                    (
                        "fit_weighted",
                        "hard_bound",
                        None,
                        None,
                        _select_active_variable_indices(A_ineq, active_budget, variable_weights=variable_fit_weights),
                        variable_fit_weights,
                    )
                )
                for slack_weight in _minimax_slack_weight_candidates():
                    qp_attempts.append(
                        (
                            "fit_weighted",
                            "minimax_slack",
                            slack_weight,
                            None,
                            _select_active_variable_indices(A_ineq, active_budget, variable_weights=variable_fit_weights),
                            variable_fit_weights,
                        )
                    )

            for candidate_priority, (
                weighting_name,
                solver_name,
                slack_weight,
                constraint_indices,
                active_indices,
                qp_weights,
            ) in enumerate(qp_attempts):
                if weighting_name == "fit_weighted" and not _should_try_fit_weighted_qp(accepted_score):
                    continue
                solver_A = A_ineq if constraint_indices is None else A_ineq[constraint_indices, :]
                solver_b = b_ineq if constraint_indices is None else b_ineq[constraint_indices]
                active_matrix = solver_A[:, active_indices]
                active_weights = None if qp_weights is None else qp_weights[active_indices]
                minimax_step_regularization = None
                if solver_name == "minimax_slack":
                    minimax_step_regularization = _minimax_step_regularization(
                        active_matrix,
                        solver_b,
                        variable_weights=active_weights,
                    )
                    qp_result = _solve_minimax_slack_upper_bound_dual_qp(
                        active_matrix,
                        solver_b,
                        step_regularization=minimax_step_regularization,
                        slack_weight=float(slack_weight),
                        variable_weights=active_weights,
                    )
                else:
                    qp_result = _solve_min_norm_upper_bound_dual_qp(
                        active_matrix,
                        solver_b,
                        variable_weights=active_weights,
                    )
                if not qp_result.success:
                    diagnostic = {
                        "iteration": iteration,
                        "active_budget": active_budget,
                        "weighting": weighting_name,
                        "solver": solver_name,
                        "constraint_scope": "all" if constraint_indices is None else "edge",
                        "constraint_count": int(active_matrix.shape[0]),
                        "active_rank": int(np.linalg.matrix_rank(active_matrix)),
                        "active_condition_number": _safe_condition_number(active_matrix),
                        "dual_condition_number": qp_result.dual_condition_number,
                        "dual_regularization": qp_result.regularization,
                        "line_search_accepted": False,
                        "selected_for_iteration": False,
                        "accepted": False,
                        "reject_reason": "qp_failed",
                        "qp_success": False,
                        "qp_message": qp_result.message,
                    }
                    if minimax_step_regularization is not None:
                        diagnostic["minimax_step_regularization"] = float(minimax_step_regularization)
                    if slack_weight is not None:
                        diagnostic["minimax_slack_weight"] = float(slack_weight)
                    if active_weights is not None:
                        diagnostic["active_weight_min"] = float(np.min(active_weights))
                        diagnostic["active_weight_max"] = float(np.max(active_weights))
                    diagnostics.append(diagnostic)
                    continue

                x_opt = np.zeros(n_vars)
                x_opt[active_indices] = qp_result.x
                for scale in (1.0, 0.5, 0.25, 0.125, 0.0625):
                    candidate_residues = _apply_residue_delta(
                        residues,
                        x_opt,
                        nports=nports,
                        vars_per_pair=vars_per_pair,
                        n_real=n_real,
                        real_poles=real_poles,
                        complex_pairs=complex_pairs,
                        scale=scale,
                    )
                    candidate_constant = _apply_constant_delta(
                        constant_coeff,
                        x_opt,
                        nports=nports,
                        offset=n_residue_vars,
                        scale=scale,
                    ) if perturb_constant else constant_coeff

                    candidate_poles = _apply_pole_delta(
                        poles,
                        x_opt,
                        real_poles=real_poles,
                        complex_pairs=complex_pairs,
                        offset=n_residue_vars + n_constant_vars,
                        scale=scale,
                    ) if perturb_poles else poles

                    if perturb_poles and np.any(np.real(candidate_poles) >= 0.0):
                        continue

                    candidate_score = _evaluate_passivity_score_at_freqs(
                        candidate_poles,
                        candidate_residues,
                        candidate_constant,
                        nports=nports,
                        freqs=sampled_freqs,
                        epsilon=epsilon,
                    )
                    candidate_holdout_score = _evaluate_passivity_score_at_freqs(
                        candidate_poles,
                        candidate_residues,
                        candidate_constant,
                        nports=nports,
                        freqs=holdout_freqs,
                        epsilon=epsilon,
                    )

                    candidate_delta_norm_value = _candidate_delta_norm(
                        residues,
                        candidate_residues,
                        constant_coeff,
                        candidate_constant,
                        poles,
                        candidate_poles,
                    )
                    trust_limit = _trust_region_limit(iteration, current_score)

                    candidate_improves_best = _is_candidate_update_better(
                        candidate_score,
                        candidate_delta_norm_value,
                        accepted_score,
                        accepted_delta_norm,
                        candidate_priority=candidate_priority,
                        best_priority=accepted_priority,
                        score_abs_tol=1e-8,
                    )
                    accepted_candidate, validation_diagnostic = _validate_candidate_on_holdout(
                        sampled_score=sampled_score,
                        candidate_score=candidate_score,
                        holdout_score=holdout_score,
                        candidate_holdout_score=candidate_holdout_score,
                        candidate_delta_norm=candidate_delta_norm_value,
                        trust_region_limit=trust_limit,
                        candidate_improves_best=candidate_improves_best,
                    )
                    reject_reason = validation_diagnostic["reject_reason"]

                    diagnostic = _qp_attempt_diagnostic(
                        iteration=iteration,
                        active_budget=active_budget,
                        active_matrix=active_matrix,
                        qp_result=qp_result,
                        A_ineq=A_ineq,
                        b_ineq=b_ineq,
                        x_delta=x_opt,
                        scale=scale,
                        sampled_score=sampled_score,
                        candidate_score=candidate_score,
                        accepted=accepted_candidate,
                        reject_reason=reject_reason,
                        variable_weights=qp_weights,
                    )
                    diagnostic["weighting"] = weighting_name
                    diagnostic["solver"] = solver_name
                    diagnostic["constraint_scope"] = "all" if constraint_indices is None else "edge"
                    diagnostic["constraint_count"] = int(active_matrix.shape[0])
                    diagnostic["candidate_priority"] = int(candidate_priority)
                    if minimax_step_regularization is not None:
                        diagnostic["minimax_step_regularization"] = float(minimax_step_regularization)
                    if slack_weight is not None:
                        diagnostic["minimax_slack_weight"] = float(slack_weight)
                    diagnostic["holdout_max_sigma_before"] = float(holdout_score.max_sigma)
                    diagnostic["holdout_max_sigma_after"] = float(candidate_holdout_score.max_sigma)
                    diagnostic["holdout_improvement"] = float(holdout_score.max_sigma - candidate_holdout_score.max_sigma)
                    diagnostic.update(validation_diagnostic)
                    diagnostics.append(diagnostic)

                    if accepted_candidate:
                        if selected_diagnostic is not None:
                            selected_diagnostic["selected_for_iteration"] = False
                        diagnostic["selected_for_iteration"] = True
                        selected_diagnostic = diagnostic
                        accepted_residues = candidate_residues
                        accepted_constant = candidate_constant
                        accepted_poles = candidate_poles
                        accepted_score = candidate_score
                        accepted_delta_norm = candidate_delta_norm_value
                        accepted_priority = candidate_priority

        if accepted_residues is not None:
            full_line_search = []
            full_trial_models = []
            full_candidate_score: _PassivityScore | None = None
            full_candidate_residues = None
            full_candidate_constant = None
            full_candidate_poles = None
            full_candidate_scale = None
            for full_scale in (1.0, 0.5, 0.25, 0.125, 0.0625):
                trial_residues = residues + full_scale * (accepted_residues - residues)
                trial_constant = constant_coeff + full_scale * (accepted_constant - constant_coeff)
                trial_poles = poles + full_scale * (accepted_poles - poles)
                trial_score = _full_frequency_passivity_score(
                    trial_poles,
                    trial_residues,
                    trial_constant,
                    nports=nports,
                    epsilon=epsilon,
                    f_max=f_max,
                    max_violation_samples=max_violation_samples,
                )
                improves = trial_score.max_sigma < current_score.max_sigma - 1e-10
                full_line_search.append(
                    {
                        "scale": float(full_scale),
                        "max_sigma": float(trial_score.max_sigma),
                        "violation_count": int(trial_score.violation_count),
                        "improves": bool(improves),
                    }
                )
                full_trial_models.append(
                    {
                        "poles": trial_poles,
                        "residues": trial_residues,
                        "constant": trial_constant,
                        "score": trial_score,
                        "scale": float(full_scale),
                        "improves": bool(improves),
                    }
                )
                if improves and trial_score.is_better_than(full_candidate_score):
                    full_candidate_score = trial_score
                    full_candidate_residues = trial_residues
                    full_candidate_constant = trial_constant
                    full_candidate_poles = trial_poles
                    full_candidate_scale = float(full_scale)

            baseline_post_damping_reference_rms = None
            selected_post_damping_reference_rms = None
            if spectral_projection_reference_freqs is not None and spectral_projection_reference_s is not None:
                reference_freq_array = np.asarray(spectral_projection_reference_freqs, dtype=float).reshape(-1)
                rms_chunk_size = max(
                    1,
                    int(spectral_projection_reference_rms_chunk_size)
                    if int(spectral_projection_reference_rms_chunk_size) > 0
                    else 64,
                )
                baseline_damping_factor = _global_damping_factor(
                    max_sigma=float(current_score.max_sigma),
                    epsilon=epsilon,
                    safety_margin=global_damping_safety_margin,
                )
                baseline_post_damping_reference_rms = _reference_response_rms_chunked(
                    poles,
                    residues * baseline_damping_factor,
                    constant_coeff * baseline_damping_factor,
                    nports=nports,
                    freqs=reference_freq_array,
                    reference_freqs=spectral_projection_reference_freqs,
                    reference_s=spectral_projection_reference_s,
                    chunk_size=rms_chunk_size,
                )
                post_damping_models = []
                for trial in full_trial_models:
                    trial_damping_factor = _global_damping_factor(
                        max_sigma=float(trial["score"].max_sigma),
                        epsilon=epsilon,
                        safety_margin=global_damping_safety_margin,
                    )
                    trial["post_damping_factor"] = float(trial_damping_factor)
                    trial["post_damping_residues"] = trial["residues"] * trial_damping_factor
                    trial["post_damping_constant"] = trial["constant"] * trial_damping_factor
                    post_damping_models.append(
                        (trial["post_damping_residues"], trial["post_damping_constant"])
                    )
                if all(np.array_equal(trial["poles"], poles) for trial in full_trial_models):
                    post_damping_rms_values = _reference_response_rms_candidates_chunked(
                        poles,
                        post_damping_models,
                        nports=nports,
                        freqs=reference_freq_array,
                        reference_freqs=spectral_projection_reference_freqs,
                        reference_s=spectral_projection_reference_s,
                        chunk_size=rms_chunk_size,
                    )
                else:
                    post_damping_rms_values = [
                        _reference_response_rms_chunked(
                            trial["poles"],
                            trial["post_damping_residues"],
                            trial["post_damping_constant"],
                            nports=nports,
                            freqs=reference_freq_array,
                            reference_freqs=spectral_projection_reference_freqs,
                            reference_s=spectral_projection_reference_s,
                            chunk_size=rms_chunk_size,
                        )
                        for trial in full_trial_models
                    ]
                for diagnostic, trial, post_rms in zip(
                    full_line_search,
                    full_trial_models,
                    post_damping_rms_values,
                ):
                    trial["post_damping_reference_rms"] = float(post_rms)
                    diagnostic["post_damping_factor"] = float(trial["post_damping_factor"])
                    diagnostic["post_damping_reference_rms"] = float(post_rms)
                eligible_trials = [
                    trial
                    for trial in full_trial_models
                    if trial["improves"]
                    and float(trial["post_damping_reference_rms"])
                    < float(baseline_post_damping_reference_rms) - 1e-12
                ]
                if eligible_trials:
                    selected_trial = min(
                        eligible_trials,
                        key=lambda trial: (
                            float(trial["post_damping_reference_rms"]),
                            float(trial["score"].max_sigma),
                        ),
                    )
                    full_candidate_score = selected_trial["score"]
                    full_candidate_residues = selected_trial["residues"]
                    full_candidate_constant = selected_trial["constant"]
                    full_candidate_poles = selected_trial["poles"]
                    full_candidate_scale = float(selected_trial["scale"])
                    selected_post_damping_reference_rms = float(
                        selected_trial["post_damping_reference_rms"]
                    )
                else:
                    full_candidate_score = None
                    full_candidate_residues = None
                    full_candidate_constant = None
                    full_candidate_poles = None
                    full_candidate_scale = None

            full_frequency_improves = full_candidate_score is not None
            best_full_sigma = (
                float(full_candidate_score.max_sigma)
                if full_candidate_score is not None
                else min(float(item["max_sigma"]) for item in full_line_search)
            )
            best_full_violation_count = (
                int(full_candidate_score.violation_count)
                if full_candidate_score is not None
                else min(
                    int(item["violation_count"])
                    for item in full_line_search
                    if float(item["max_sigma"]) == best_full_sigma
                )
            )
            diagnostics.append(
                {
                    "type": "full_frequency_line_search",
                    "iteration": int(iteration),
                    "max_sigma_before": float(current_score.max_sigma),
                    "max_sigma_after": best_full_sigma,
                    "selected_scale": full_candidate_scale,
                    "baseline_post_damping_reference_rms": baseline_post_damping_reference_rms,
                    "selected_post_damping_reference_rms": selected_post_damping_reference_rms,
                    "accepted": bool(full_frequency_improves),
                    "candidates": full_line_search,
                }
            )
            if selected_diagnostic is not None:
                selected_diagnostic["full_validation_max_sigma_before"] = float(current_score.max_sigma)
                selected_diagnostic["full_validation_max_sigma_after"] = best_full_sigma
                selected_diagnostic["full_validation_violation_count_after"] = best_full_violation_count
                selected_diagnostic["full_frequency_accepted"] = bool(full_frequency_improves)
                selected_diagnostic["full_frequency_selected_scale"] = full_candidate_scale
            if not full_frequency_improves:
                if selected_diagnostic is not None:
                    selected_diagnostic["accepted"] = False
                    selected_diagnostic["selected_for_iteration"] = False
                    selected_diagnostic["reject_reason"] = "full_frequency_regression"
                accepted_residues = None
            else:
                accepted_residues = full_candidate_residues
                accepted_constant = full_candidate_constant
                accepted_poles = full_candidate_poles
                accepted_score = full_candidate_score

        if accepted_residues is None:
            break
        residues = accepted_residues
        if perturb_constant:
            constant_coeff = accepted_constant
        if perturb_poles:
            poles = accepted_poles
        if accepted_score is not None:
            if accepted_score.is_better_than(best_score):
                best_residues = residues.copy()
                best_constant = constant_coeff.copy()
                best_poles = poles.copy()
                best_score = accepted_score

    residues = best_residues
    constant_coeff = best_constant
    poles = best_poles

    validation_f_limit = f_max if f_max is not None else 100e9
    validation_crossovers = check_passivity_hamiltonian_s(
        poles,
        residues,
        constant_coeff,
        nports,
        f_max=f_max,
    )
    validation_points = [0.0] + validation_crossovers + [validation_f_limit]
    validation_intervals = [
        (float(validation_points[idx]), float(validation_points[idx + 1]))
        for idx in range(len(validation_points) - 1)
    ]
    validation_samples = _projection_candidate_passivity_samples(
        poles,
        residues,
        constant_coeff,
        nports=nports,
        intervals=validation_intervals,
        f_max=f_max,
        epsilon=epsilon,
        max_depth=2,
        curvature_tol=1e-3,
        reference_freqs=spectral_projection_reference_freqs
        if spectral_projection_reference_s is not None
        else None,
    )
    if validation_samples:
        validation_max_sample = max(validation_samples, key=lambda item: float(item["max_sigma"]))
        validation_max_sigma = float(validation_max_sample["max_sigma"])
        validation_max_sigma_frequency = float(validation_max_sample["frequency_hz"])
        validation_violation_count = sum(1 for item in validation_samples if bool(item["violates"]))
    else:
        validation_max_sigma = 0.0
        validation_max_sigma_frequency = 0.0
        validation_violation_count = 0

    projection_iteration_count = max(1, int(spectral_projection_iterations))
    initial_projection_reference_rms = None
    for projection_iteration in range(projection_iteration_count):
        if not spectral_projection_fallback or validation_max_sigma <= 1.0 + epsilon:
            break
        reference_band_holdout_enabled = (
            spectral_projection_max_reference_band_sigma_regression is not None
            and projection_iteration >= int(spectral_projection_reference_band_holdout_start_iteration)
        )
        reference_band_holdout_ranges = (
            _reference_band_holdout_ranges(validation_samples)
            if reference_band_holdout_enabled
            else []
        )
        projection_freqs = _projection_frequency_candidates(
            validation_samples,
            max_violation_samples=max_violation_samples,
            include_all_reference_violations=(
                bool(spectral_projection_include_all_reference_violations)
                and spectral_projection_reference_freqs is not None
                and spectral_projection_reference_s is not None
            ),
            selection_mode=spectral_projection_frequency_selection,
            band_sample_count=spectral_projection_band_sample_count,
        )
        projection_weights = _projection_frequency_weights(
            validation_samples,
            projection_freqs,
            mode=spectral_projection_weight_mode,
            epsilon=epsilon,
            exponent=spectral_projection_weight_exponent,
        )
        projection_basis = _rational_basis_at_freqs(poles, projection_freqs)
        if spectral_projection_reference_freqs is not None and spectral_projection_reference_s is not None:
            projected_residues, projected_constant = _reference_projection_residue_constant_delta(
                poles,
                residues,
                constant_coeff,
                nports=nports,
                freqs=projection_freqs,
                reference_freqs=spectral_projection_reference_freqs,
                reference_s=spectral_projection_reference_s,
                epsilon=epsilon,
                perturb_constant=perturb_constant,
                sample_weights=projection_weights,
                reweight_iterations=spectral_projection_reweight_iterations,
            )
            projection_target = "reference"
        else:
            projected_residues, projected_constant = _projection_residue_constant_delta(
                poles,
                residues,
                constant_coeff,
                nports=nports,
                freqs=projection_freqs,
                epsilon=epsilon,
                perturb_constant=perturb_constant,
                sample_weights=projection_weights,
                reweight_iterations=spectral_projection_reweight_iterations,
            )
            projection_target = "current_spectral_clip"
        projection_sources: list[tuple[str, np.ndarray, np.ndarray, dict[str, Any]]] = [
            ("matrix_projection", projected_residues, projected_constant, {})
        ]
        if (
            spectral_projection_current_clip_candidate
            and spectral_projection_reference_freqs is not None
            and spectral_projection_reference_s is not None
        ):
            clip_residues, clip_constant = _projection_residue_constant_delta(
                poles,
                residues,
                constant_coeff,
                nports=nports,
                freqs=projection_freqs,
                epsilon=epsilon,
                perturb_constant=perturb_constant,
                sample_weights=projection_weights,
                reweight_iterations=spectral_projection_reweight_iterations,
            )
            projection_sources.append(("current_spectral_clip", clip_residues, clip_constant, {}))
            if float(spectral_projection_current_clip_reference_weight) > 0.0:
                regularized_clip_residues, regularized_clip_constant = (
                    _current_clip_reference_regularized_projection_delta(
                        poles,
                        residues,
                        constant_coeff,
                        nports=nports,
                        freqs=projection_freqs,
                        reference_freqs=spectral_projection_reference_freqs,
                        reference_s=spectral_projection_reference_s,
                        epsilon=epsilon,
                        perturb_constant=perturb_constant,
                        reference_weight=spectral_projection_current_clip_reference_weight,
                        sample_weights=projection_weights,
                    )
                )
                projection_sources.append(
                    (
                        "current_spectral_clip_reference_regularized",
                        regularized_clip_residues,
                        regularized_clip_constant,
                        {
                            "reference_weight": float(
                                spectral_projection_current_clip_reference_weight
                            )
                        },
                    )
                )
        if (
            spectral_projection_active_mode_candidate
            and projection_iteration >= int(spectral_projection_active_mode_start_iteration)
        ):
            active_mode_freqs = projection_freqs
            if spectral_projection_reference_freqs is not None and spectral_projection_reference_s is not None:
                active_mode_freqs = _projection_active_mode_freqs(
                    validation_samples,
                    projection_freqs=projection_freqs,
                    max_reference_points=spectral_projection_active_mode_reference_max_points,
                    selection_mode=spectral_projection_active_mode_frequency_selection,
                    band_sample_count=spectral_projection_band_sample_count,
                )
            active_mode_band_singular_freqs: list[float] = []
            if (
                int(spectral_projection_active_mode_band_singular_modes)
                > int(spectral_projection_active_mode_singular_modes)
                and spectral_projection_reference_freqs is not None
                and spectral_projection_reference_s is not None
            ):
                active_mode_band_singular_freqs = _active_mode_band_singular_mode_freqs(
                    validation_samples,
                    max_reference_points=spectral_projection_active_mode_reference_max_points,
                    band_sample_count=spectral_projection_active_mode_band_singular_mode_sample_count,
                )
            active_mode_solvers = _active_mode_solver_candidates(spectral_projection_active_mode_solver)
            active_mode_reference_sample_weights = None
            if spectral_projection_active_mode_reference_weight_mode != "none":
                active_mode_reference_sample_weights = _projection_frequency_weights(
                    validation_samples,
                    active_mode_freqs,
                    mode=spectral_projection_active_mode_reference_weight_mode,
                    epsilon=epsilon,
                    exponent=1.0,
                )
            reference_weights = [spectral_projection_active_mode_reference_weight]
            if any(solver in {
                "reference_regularized_min_norm",
                "reference_regularized_peak_minimax",
                "reference_compensated_min_norm",
            } for solver in active_mode_solvers):
                reference_weights = _active_mode_reference_weight_candidates(
                    spectral_projection_active_mode_reference_weight,
                    spectral_projection_active_mode_reference_weight_candidates,
                )
            for active_solver in active_mode_solvers:
                for active_reference_weight in reference_weights:
                    active_target_margin = (
                        max(0.0, float(spectral_projection_active_mode_target_margin))
                        if projection_iteration
                        >= max(0, int(spectral_projection_active_mode_target_margin_start_iteration))
                        else 0.0
                    )
                    active_reference_target_scale = 1.0
                    if active_solver == "reference_compensated_min_norm" and validation_max_sigma > 1.0 + epsilon:
                        active_reference_target_scale = 1.0 / _global_damping_factor(
                            max_sigma=validation_max_sigma,
                            epsilon=epsilon,
                            safety_margin=global_damping_safety_margin,
                        )
                    active_residues, active_constant, active_diagnostic = _active_mode_residue_constant_delta(
                        poles,
                        residues,
                        constant_coeff,
                        nports=nports,
                        freqs=active_mode_freqs,
                        epsilon=epsilon,
                        perturb_constant=perturb_constant,
                        max_active_variables=max_active_variables,
                        max_mode_responses=spectral_projection_active_mode_max_responses,
                        singular_modes=spectral_projection_active_mode_singular_modes,
                        band_singular_modes=spectral_projection_active_mode_band_singular_modes,
                        band_singular_mode_freqs=active_mode_band_singular_freqs,
                        solver=active_solver,
                        target_margin=active_target_margin,
                        reference_freqs=spectral_projection_reference_freqs,
                        reference_s=spectral_projection_reference_s,
                        reference_weight=active_reference_weight,
                        reference_target_scale=active_reference_target_scale,
                        reference_sample_weights=active_mode_reference_sample_weights,
                        reference_global_points=spectral_projection_active_mode_global_reference_points,
                    )
                    active_diagnostic["active_mode_requested_solver"] = spectral_projection_active_mode_solver
                    active_diagnostic["active_mode_target_margin_start_iteration"] = int(
                        spectral_projection_active_mode_target_margin_start_iteration
                    )
                    active_diagnostic["active_mode_frequency_count"] = int(len(active_mode_freqs))
                    active_diagnostic["active_mode_band_singular_frequency_count"] = int(
                        len(active_mode_band_singular_freqs)
                    )
                    active_diagnostic["active_mode_reference_max_points"] = int(
                        spectral_projection_active_mode_reference_max_points
                    )
                    active_diagnostic["active_mode_frequency_selection"] = (
                        spectral_projection_active_mode_frequency_selection
                    )
                    active_diagnostic["active_mode_reference_weight_candidate"] = float(
                        active_reference_weight
                    )
                    active_diagnostic["active_mode_reference_target_scale"] = float(
                        active_reference_target_scale
                    )
                    active_diagnostic["active_mode_reference_weight_mode"] = (
                        spectral_projection_active_mode_reference_weight_mode
                    )
                    active_diagnostic["active_mode_global_reference_points"] = int(
                        spectral_projection_active_mode_global_reference_points
                    )
                    if active_mode_reference_sample_weights is not None:
                        active_diagnostic["active_mode_reference_sample_weight_min"] = float(
                            np.min(active_mode_reference_sample_weights)
                        )
                        active_diagnostic["active_mode_reference_sample_weight_max"] = float(
                            np.max(active_mode_reference_sample_weights)
                        )
                    if active_diagnostic.get("success"):
                        projection_sources.append(
                            ("active_mode", active_residues, active_constant, active_diagnostic)
                        )
        projection_sources = _filter_projection_sources_for_late_stage(
            projection_sources,
            projection_iteration=projection_iteration,
            non_active_stop_iteration=spectral_projection_non_active_stop_iteration,
        )
        candidate_reference_freqs = None
        if spectral_projection_reference_freqs is not None and spectral_projection_reference_s is not None:
            if spectral_projection_candidate_reference_max_points > 0:
                candidate_reference_freqs = _projection_candidate_reference_holdout_freqs(
                    validation_samples,
                    required_freqs=projection_freqs,
                    max_reference_points=spectral_projection_candidate_reference_max_points,
                )
            else:
                candidate_reference_freqs = spectral_projection_reference_freqs
        candidate_reference_basis = None
        if candidate_reference_freqs is not None:
            candidate_reference_basis = _rational_basis_at_freqs(poles, candidate_reference_freqs)
        reference_rms_freqs = _projection_reference_rms_freqs(
            projection_freqs,
            candidate_reference_freqs,
            mode=spectral_projection_reference_rms_scope,
        )
        reference_rms_chunk_size = max(0, int(spectral_projection_reference_rms_chunk_size))
        reference_rms_chunked = (
            reference_rms_chunk_size > 0
            and spectral_projection_reference_freqs is not None
            and spectral_projection_reference_s is not None
        )
        reference_rms_basis = None
        if not reference_rms_chunked:
            reference_rms_basis = _rational_basis_at_freqs(poles, reference_rms_freqs)
        reference_rms_matrices = None
        if (
            not reference_rms_chunked
            and spectral_projection_reference_freqs is not None
            and spectral_projection_reference_s is not None
        ):
            reference_rms_matrices = _reference_s_matrices_at_freqs(
                reference_rms_freqs,
                reference_freqs=spectral_projection_reference_freqs,
                reference_s=spectral_projection_reference_s,
                nports=nports,
            )
        baseline_reference_rms = None
        if reference_rms_chunked:
            baseline_reference_rms = _reference_response_rms_candidates_chunked(
                poles,
                [(residues, constant_coeff)],
                nports=nports,
                freqs=reference_rms_freqs,
                reference_freqs=spectral_projection_reference_freqs,
                reference_s=spectral_projection_reference_s,
                chunk_size=reference_rms_chunk_size,
            )[0]
            if initial_projection_reference_rms is None:
                initial_projection_reference_rms = baseline_reference_rms
        elif reference_rms_matrices is not None:
            baseline_reference_rms = _reference_response_rms_to_matrices(
                poles,
                residues,
                constant_coeff,
                nports=nports,
                freqs=reference_rms_freqs,
                reference_matrices=reference_rms_matrices,
                basis=reference_rms_basis,
            )
            if initial_projection_reference_rms is None:
                initial_projection_reference_rms = baseline_reference_rms
        candidate_descriptors: list[dict[str, Any]] = []
        for projection_strategy, source_residues, source_constant, source_diagnostic in projection_sources:
            for scale in _projection_candidate_scale_values(
                projection_strategy,
                active_mode_extra_scales=spectral_projection_active_mode_extra_scales,
                current_max_sigma=validation_max_sigma,
                active_mode_extra_scales_min_sigma=spectral_projection_active_mode_extra_scales_min_sigma,
            ):
                candidate_residues = residues + scale * (source_residues - residues)
                candidate_constant = constant_coeff + scale * (source_constant - constant_coeff)
                candidate_descriptors.append(
                    candidate := {
                        "strategy": projection_strategy,
                        "projection_iteration": int(projection_iteration),
                        "source_diagnostic": source_diagnostic,
                        "scale": float(scale),
                        "residues": candidate_residues,
                        "constant": candidate_constant,
                        "delta_norm": _candidate_delta_norm(
                            residues,
                            candidate_residues,
                            constant_coeff,
                            candidate_constant,
                            poles,
                            poles,
                        ),
                        "response_delta_rms": _response_delta_rms_at_freqs(
                            poles,
                            residues,
                            constant_coeff,
                            candidate_residues,
                            candidate_constant,
                            nports=nports,
                            freqs=projection_freqs,
                            basis=projection_basis,
                        ),
                    }
                )
                if reference_rms_matrices is not None:
                    candidate["reference_rms"] = _reference_response_rms_to_matrices(
                        poles,
                        candidate_residues,
                        candidate_constant,
                        nports=nports,
                        freqs=reference_rms_freqs,
                        reference_matrices=reference_rms_matrices,
                        basis=reference_rms_basis,
                    )
        if reference_rms_chunked and candidate_descriptors:
            candidate_reference_rms_values = _reference_response_rms_candidates_chunked(
                poles,
                [(candidate["residues"], candidate["constant"]) for candidate in candidate_descriptors],
                nports=nports,
                freqs=reference_rms_freqs,
                reference_freqs=spectral_projection_reference_freqs,
                reference_s=spectral_projection_reference_s,
                chunk_size=reference_rms_chunk_size,
            )
            for candidate, reference_rms in zip(candidate_descriptors, candidate_reference_rms_values):
                candidate["reference_rms"] = reference_rms
        candidate_count_before_screen = len(candidate_descriptors)
        mode_screen_enabled = int(spectral_projection_mode_screen_candidates) > 0
        candidate_count_after_cheap_gates = candidate_count_before_screen
        cheap_gate_rejection_summary = _projection_candidate_rejection_summary(
            candidate_descriptors,
            max_delta_norm=spectral_projection_max_delta_norm,
            max_response_delta_rms=spectral_projection_max_response_delta_rms,
            baseline_reference_rms=baseline_reference_rms,
            max_reference_rms_increase=spectral_projection_max_reference_rms_increase,
            initial_reference_rms=initial_projection_reference_rms,
            max_reference_rms_total_increase=spectral_projection_max_reference_rms_total_increase,
            late_current_clip_max_reference_rms_per_sigma_improvement=(
                spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement
            ),
            late_current_clip_start_iteration=spectral_projection_late_current_clip_start_iteration,
            active_mode_max_reference_rms_total_increase=(
                spectral_projection_active_mode_max_reference_rms_total_increase
            ),
        )
        if mode_screen_enabled and candidate_descriptors:
            candidate_descriptors = [
                candidate
                for candidate in candidate_descriptors
                if _projection_candidate_passes_cheap_gates(
                    candidate,
                    max_delta_norm=spectral_projection_max_delta_norm,
                    max_response_delta_rms=spectral_projection_max_response_delta_rms,
                    baseline_reference_rms=baseline_reference_rms,
                    max_reference_rms_increase=spectral_projection_max_reference_rms_increase,
                    initial_reference_rms=initial_projection_reference_rms,
                    max_reference_rms_total_increase=spectral_projection_max_reference_rms_total_increase,
                    late_current_clip_max_reference_rms_per_sigma_improvement=(
                        spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement
                    ),
                    late_current_clip_start_iteration=spectral_projection_late_current_clip_start_iteration,
                    active_mode_max_reference_rms_total_increase=(
                        spectral_projection_active_mode_max_reference_rms_total_increase
                    ),
                )
            ]
            candidate_count_after_cheap_gates = len(candidate_descriptors)
        if mode_screen_enabled and candidate_descriptors:
            screen_basis = candidate_reference_basis if candidate_reference_basis is not None else projection_basis
            screen_baseline = _evaluate_s_matrices_from_basis(
                residues,
                constant_coeff,
                nports=nports,
                basis=screen_basis,
            )
            _screen_sigmas, screen_left, screen_right = _dominant_singular_vectors_at_freqs(
                screen_baseline,
                mode_count=spectral_projection_mode_screen_modes,
            )
            candidate_descriptors = _screen_projection_candidate_descriptors_by_modes(
                candidate_descriptors,
                nports=nports,
                basis=screen_basis,
                left_vectors=screen_left,
                right_vectors=screen_right,
                max_candidates=spectral_projection_mode_screen_candidates,
            )
        projection_candidates: list[dict[str, Any]] = []
        for candidate in candidate_descriptors:
            candidate_samples = _projection_candidate_passivity_samples(
                poles,
                candidate["residues"],
                candidate["constant"],
                nports=nports,
                intervals=validation_intervals,
                f_max=f_max,
                epsilon=epsilon,
                max_depth=2,
                curvature_tol=1e-3,
                reference_freqs=candidate_reference_freqs,
                reference_basis=candidate_reference_basis,
            )
            if candidate_samples:
                candidate_max_sample = max(candidate_samples, key=lambda item: float(item["max_sigma"]))
                candidate_max_sigma = float(candidate_max_sample["max_sigma"])
                candidate_max_frequency = float(candidate_max_sample["frequency_hz"])
                candidate_violation_count = sum(1 for item in candidate_samples if bool(item["violates"]))
            else:
                candidate_max_sigma = 0.0
                candidate_max_frequency = 0.0
                candidate_violation_count = 0
            candidate["max_sigma"] = float(candidate_max_sigma)
            candidate["max_sigma_frequency_hz"] = float(candidate_max_frequency)
            candidate["violation_count"] = int(candidate_violation_count)
            candidate["samples"] = candidate_samples
            candidate["reference_rms_efficiency_gate"] = bool(
                spectral_projection_max_reference_rms_per_sigma_improvement is not None
                and projection_iteration >= int(spectral_projection_active_mode_start_iteration)
                and candidate.get("strategy") != "active_mode"
            )
            if reference_band_holdout_ranges:
                band_metrics = _reference_band_holdout_metrics(
                    candidate_samples,
                    bands=reference_band_holdout_ranges,
                )
                candidate["reference_band_max_sigma"] = float(band_metrics["max_sigma"])
                candidate["reference_band_sigma_regression"] = float(band_metrics["max_regression"])
            projection_candidates.append(candidate)
        effective_candidate_selection_metric = spectral_projection_candidate_selection_metric
        if (
            spectral_projection_candidate_selection_metric == "post_damping_reference_rms"
            and projection_iteration < int(spectral_projection_post_damping_selection_start_iteration)
        ):
            effective_candidate_selection_metric = "passivity"
        baseline_post_damping_reference_rms = None
        if (
            effective_candidate_selection_metric == "post_damping_reference_rms"
            and projection_candidates
            and spectral_projection_reference_freqs is not None
            and spectral_projection_reference_s is not None
        ):
            post_damping_pairs = []
            baseline_damping_factor = 1.0
            if validation_max_sigma > 1.0 + epsilon:
                baseline_damping_factor = _global_damping_factor(
                    max_sigma=validation_max_sigma,
                    epsilon=epsilon,
                    safety_margin=global_damping_safety_margin,
                )
            post_damping_pairs.append(
                (
                    residues * baseline_damping_factor,
                    constant_coeff * baseline_damping_factor,
                )
            )
            for candidate in projection_candidates:
                damping_factor = 1.0
                if float(candidate.get("max_sigma", 0.0)) > 1.0 + epsilon:
                    damping_factor = _global_damping_factor(
                        max_sigma=float(candidate["max_sigma"]),
                        epsilon=epsilon,
                        safety_margin=global_damping_safety_margin,
                    )
                candidate["post_damping_factor"] = float(damping_factor)
                post_damping_pairs.append(
                    (
                        candidate["residues"] * damping_factor,
                        candidate["constant"] * damping_factor,
                    )
                )
            if reference_rms_chunked:
                post_damping_rms_values = _reference_response_rms_candidates_chunked(
                    poles,
                    post_damping_pairs,
                    nports=nports,
                    freqs=reference_rms_freqs,
                    reference_freqs=spectral_projection_reference_freqs,
                    reference_s=spectral_projection_reference_s,
                    chunk_size=reference_rms_chunk_size,
                )
            elif reference_rms_matrices is not None:
                post_damping_rms_values = [
                    _reference_response_rms_to_matrices(
                        poles,
                        pair_residues,
                        pair_constant,
                        nports=nports,
                        freqs=reference_rms_freqs,
                        reference_matrices=reference_rms_matrices,
                        basis=reference_rms_basis,
                    )
                    for pair_residues, pair_constant in post_damping_pairs
                ]
            else:
                post_damping_rms_values = [
                    float(baseline_reference_rms)
                    if baseline_reference_rms is not None
                    else math.inf,
                    *[
                        float(candidate.get("reference_rms", math.inf))
                        for candidate in projection_candidates
                    ],
                ]
            baseline_post_damping_reference_rms = float(post_damping_rms_values[0])
            for candidate, post_damping_rms in zip(projection_candidates, post_damping_rms_values[1:]):
                candidate["post_damping_reference_rms"] = float(post_damping_rms)
        projection_candidate_rejection_summary = _projection_candidate_rejection_summary(
            projection_candidates,
            baseline_max_sigma=validation_max_sigma,
            baseline_violation_count=validation_violation_count,
            max_sigma_regression=spectral_projection_max_sigma_regression,
            max_delta_norm=spectral_projection_max_delta_norm,
            max_response_delta_rms=spectral_projection_max_response_delta_rms,
            baseline_reference_rms=baseline_reference_rms,
            max_reference_rms_increase=spectral_projection_max_reference_rms_increase,
            initial_reference_rms=initial_projection_reference_rms,
            max_reference_rms_total_increase=spectral_projection_max_reference_rms_total_increase,
            max_reference_rms_per_sigma_improvement=spectral_projection_max_reference_rms_per_sigma_improvement,
            late_current_clip_max_reference_rms_per_sigma_improvement=(
                spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement
            ),
            late_current_clip_start_iteration=spectral_projection_late_current_clip_start_iteration,
            max_reference_band_sigma_regression=(
                spectral_projection_max_reference_band_sigma_regression
                if reference_band_holdout_ranges
                else None
            ),
            active_mode_max_reference_rms_total_increase=(
                spectral_projection_active_mode_max_reference_rms_total_increase
            ),
            post_damping_max_sigma_regression=(
                spectral_projection_post_damping_max_sigma_regression
                if effective_candidate_selection_metric == "post_damping_reference_rms"
                else None
            ),
            baseline_post_damping_reference_rms=baseline_post_damping_reference_rms,
        )
        selected_projection = _select_projection_candidate(
            projection_candidates,
            baseline_max_sigma=validation_max_sigma,
            baseline_violation_count=validation_violation_count,
            max_sigma_regression=spectral_projection_max_sigma_regression,
            max_delta_norm=spectral_projection_max_delta_norm,
            max_response_delta_rms=spectral_projection_max_response_delta_rms,
            baseline_reference_rms=baseline_reference_rms,
            max_reference_rms_increase=spectral_projection_max_reference_rms_increase,
            initial_reference_rms=initial_projection_reference_rms,
            max_reference_rms_total_increase=spectral_projection_max_reference_rms_total_increase,
            max_reference_rms_per_sigma_improvement=spectral_projection_max_reference_rms_per_sigma_improvement,
            late_current_clip_max_reference_rms_per_sigma_improvement=(
                spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement
            ),
            late_current_clip_start_iteration=spectral_projection_late_current_clip_start_iteration,
            max_reference_band_sigma_regression=(
                spectral_projection_max_reference_band_sigma_regression
                if reference_band_holdout_ranges
                else None
            ),
            active_mode_max_reference_rms_total_increase=(
                spectral_projection_active_mode_max_reference_rms_total_increase
            ),
            post_damping_max_sigma_regression=(
                spectral_projection_post_damping_max_sigma_regression
                if effective_candidate_selection_metric == "post_damping_reference_rms"
                else None
            ),
            baseline_post_damping_reference_rms=baseline_post_damping_reference_rms,
            selection_metric=effective_candidate_selection_metric,
        )

        diagnostics.append(
            {
                "type": "spectral_projection_fallback",
                "projection_iteration": int(projection_iteration),
                "projection_target": projection_target,
                "projection_active_mode_candidate": bool(spectral_projection_active_mode_candidate),
                "projection_active_mode_start_iteration": int(
                    spectral_projection_active_mode_start_iteration
                ),
                "projection_non_active_stop_iteration": None
                if spectral_projection_non_active_stop_iteration is None
                else int(spectral_projection_non_active_stop_iteration),
                "projection_active_mode_max_responses": int(spectral_projection_active_mode_max_responses),
                "projection_active_mode_singular_modes": int(
                    spectral_projection_active_mode_singular_modes
                ),
                "projection_active_mode_band_singular_modes": int(
                    spectral_projection_active_mode_band_singular_modes
                ),
                "projection_active_mode_band_singular_mode_sample_count": int(
                    spectral_projection_active_mode_band_singular_mode_sample_count
                ),
                "projection_active_mode_solver": spectral_projection_active_mode_solver,
                "projection_active_mode_reference_max_points": int(
                    spectral_projection_active_mode_reference_max_points
                ),
                "projection_active_mode_frequency_selection": (
                    spectral_projection_active_mode_frequency_selection
                ),
                "projection_active_mode_reference_weight": float(
                    spectral_projection_active_mode_reference_weight
                ),
                "projection_active_mode_reference_weight_mode": (
                    spectral_projection_active_mode_reference_weight_mode
                ),
                "projection_active_mode_reference_weight_candidates": [
                    float(weight)
                    for weight in _active_mode_reference_weight_candidates(
                        spectral_projection_active_mode_reference_weight,
                        spectral_projection_active_mode_reference_weight_candidates,
                    )
                ],
                "projection_active_mode_global_reference_points": int(
                    spectral_projection_active_mode_global_reference_points
                ),
                "projection_current_clip_candidate": bool(spectral_projection_current_clip_candidate),
                "projection_current_clip_reference_weight": float(
                    spectral_projection_current_clip_reference_weight
                ),
                "projection_candidate_reference_max_points": int(
                    spectral_projection_candidate_reference_max_points
                ),
                "projection_candidate_reference_count": None
                if candidate_reference_freqs is None
                else int(len(list(candidate_reference_freqs))),
                "projection_frequency_selection": spectral_projection_frequency_selection,
                "projection_band_sample_count": int(spectral_projection_band_sample_count),
                "projection_reference_rms_scope": spectral_projection_reference_rms_scope,
                "projection_reference_rms_frequency_count": int(len(reference_rms_freqs)),
                "projection_reference_rms_chunk_size": int(reference_rms_chunk_size),
                "projection_candidate_selection_metric": spectral_projection_candidate_selection_metric,
                "projection_effective_candidate_selection_metric": effective_candidate_selection_metric,
                "projection_post_damping_selection_start_iteration": int(
                    spectral_projection_post_damping_selection_start_iteration
                ),
                "projection_post_damping_max_sigma_regression": None
                if spectral_projection_post_damping_max_sigma_regression is None
                else float(spectral_projection_post_damping_max_sigma_regression),
                "projection_mode_screen_candidates": int(spectral_projection_mode_screen_candidates),
                "projection_mode_screen_modes": int(spectral_projection_mode_screen_modes),
                "candidate_count_before_screen": int(candidate_count_before_screen),
                "candidate_count_after_cheap_gates": int(candidate_count_after_cheap_gates),
                "cheap_gate_reject_reasons": cheap_gate_rejection_summary["reasons"],
                "candidate_reject_reasons": projection_candidate_rejection_summary["reasons"],
                "candidate_accepted_count": int(
                    projection_candidate_rejection_summary["accepted_candidates"]
                ),
                "best_rejected_candidate": projection_candidate_rejection_summary[
                    "best_rejected_candidate"
                ],
                "selected_projection_strategy": None
                if selected_projection is None
                else selected_projection.get("strategy"),
                "projection_frequency_count": int(len(projection_freqs)),
                "projection_include_all_reference_violations": bool(
                    spectral_projection_include_all_reference_violations
                ),
                "projection_weight_mode": spectral_projection_weight_mode,
                "projection_weight_exponent": float(spectral_projection_weight_exponent),
                "projection_weight_min": None if not projection_weights else float(min(projection_weights)),
                "projection_weight_max": None if not projection_weights else float(max(projection_weights)),
                "scale": 0.0 if selected_projection is None else float(selected_projection["scale"]),
                "max_sigma_before": float(validation_max_sigma),
                "max_sigma_after": float(validation_max_sigma)
                if selected_projection is None
                else float(selected_projection["max_sigma"]),
                "violation_count_after": int(validation_violation_count)
                if selected_projection is None
                else int(selected_projection["violation_count"]),
                "max_delta_norm": None
                if spectral_projection_max_delta_norm is None
                else float(spectral_projection_max_delta_norm),
                "selected_delta_norm": None if selected_projection is None else float(selected_projection["delta_norm"]),
                "max_response_delta_rms": None
                if spectral_projection_max_response_delta_rms is None
                else float(spectral_projection_max_response_delta_rms),
                "max_sigma_regression": float(spectral_projection_max_sigma_regression),
                "selected_response_delta_rms": None
                if selected_projection is None
                else float(selected_projection["response_delta_rms"]),
                "baseline_reference_rms": None if baseline_reference_rms is None else float(baseline_reference_rms),
                "baseline_post_damping_reference_rms": None
                if baseline_post_damping_reference_rms is None
                else float(baseline_post_damping_reference_rms),
                "max_reference_rms_increase": None
                if spectral_projection_max_reference_rms_increase is None
                else float(spectral_projection_max_reference_rms_increase),
                "max_reference_rms_total_increase": None
                if spectral_projection_max_reference_rms_total_increase is None
                else float(spectral_projection_max_reference_rms_total_increase),
                "max_reference_rms_per_sigma_improvement": None
                if spectral_projection_max_reference_rms_per_sigma_improvement is None
                else float(spectral_projection_max_reference_rms_per_sigma_improvement),
                "late_current_clip_max_reference_rms_per_sigma_improvement": None
                if spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement is None
                else float(spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement),
                "late_current_clip_start_iteration": int(
                    spectral_projection_late_current_clip_start_iteration
                ),
                "max_reference_band_sigma_regression": None
                if spectral_projection_max_reference_band_sigma_regression is None
                else float(spectral_projection_max_reference_band_sigma_regression),
                "reference_band_holdout_start_iteration": int(
                    spectral_projection_reference_band_holdout_start_iteration
                ),
                "reference_band_holdout_count": int(len(reference_band_holdout_ranges)),
                "initial_reference_rms": None
                if initial_projection_reference_rms is None
                else float(initial_projection_reference_rms),
                "selected_reference_rms": None
                if selected_projection is None or "reference_rms" not in selected_projection
                else float(selected_projection["reference_rms"]),
                "selected_post_damping_reference_rms": None
                if selected_projection is None or "post_damping_reference_rms" not in selected_projection
                else float(selected_projection["post_damping_reference_rms"]),
                "selected_reference_band_sigma_regression": None
                if selected_projection is None or "reference_band_sigma_regression" not in selected_projection
                else float(selected_projection["reference_band_sigma_regression"]),
                "selected_mode_screen_max_sigma": None
                if selected_projection is None or "mode_screen_max_sigma" not in selected_projection
                else float(selected_projection["mode_screen_max_sigma"]),
                "selected_source_diagnostic": None
                if selected_projection is None
                else _compact_projection_candidate_diagnostic(
                    selected_projection,
                    reject_reason=None,
                ).get("source_diagnostic"),
                "candidate_count": int(len(projection_candidates)),
                "accepted": selected_projection is not None,
            }
        )
        if selected_projection is None:
            break
        residues = selected_projection["residues"]
        constant_coeff = selected_projection["constant"]
        if spectral_projection_candidate_reference_max_points > 0:
            validation_samples = _projection_candidate_passivity_samples(
                poles,
                residues,
                constant_coeff,
                nports=nports,
                intervals=validation_intervals,
                f_max=f_max,
                epsilon=epsilon,
                max_depth=2,
                curvature_tol=1e-3,
                reference_freqs=spectral_projection_reference_freqs
                if spectral_projection_reference_s is not None
                else None,
            )
            if validation_samples:
                validation_max_sample = max(validation_samples, key=lambda item: float(item["max_sigma"]))
                validation_max_sigma = float(validation_max_sample["max_sigma"])
                validation_max_sigma_frequency = float(validation_max_sample["frequency_hz"])
                validation_violation_count = sum(1 for item in validation_samples if bool(item["violates"]))
            else:
                validation_max_sigma = 0.0
                validation_max_sigma_frequency = 0.0
                validation_violation_count = 0
        else:
            validation_max_sigma = float(selected_projection["max_sigma"])
            validation_max_sigma_frequency = float(selected_projection["max_sigma_frequency_hz"])
            validation_violation_count = int(selected_projection["violation_count"])
            validation_samples = selected_projection["samples"]

    if global_damping_fallback and validation_max_sigma > 1.0 + epsilon:
        if global_damping_mode not in {"uniform", "selective_pole", "optimized_pole"}:
            raise ValueError("global_damping_mode must be 'uniform', 'selective_pole', or 'optimized_pole'")
        validation_max_sigma_before_damping = float(validation_max_sigma)
        cumulative_damping_factor = 1.0
        damping_iterations = 0
        damping_history = []
        validation_max_sigma_after = float(validation_max_sigma)
        for _damping_iteration in range(3):
            if validation_max_sigma <= 1.0 + epsilon:
                break
            damping_factor = _global_damping_factor(
                max_sigma=validation_max_sigma,
                epsilon=epsilon,
                safety_margin=global_damping_safety_margin,
            )
            if damping_factor >= 1.0:
                break
            cumulative_damping_factor *= float(damping_factor)
            damping_iterations += 1
            damping_candidates = [
                ("uniform", residues * damping_factor, constant_coeff * damping_factor),
            ]
            uniform_residues = damping_candidates[0][1]
            uniform_constant = damping_candidates[0][2]
            if global_damping_mode == "selective_pole":
                selective_residues, selective_constant = _apply_selective_pole_damping(
                    poles,
                    residues,
                    constant_coeff,
                    damping_factor=damping_factor,
                    min_frequency_hz=global_damping_selective_min_frequency,
                )
                damping_candidates.insert(0, ("selective_pole", selective_residues, selective_constant))
            elif global_damping_mode == "optimized_pole":
                optimized_freqs = [
                    float(sample["frequency_hz"])
                    for sample in validation_samples
                    if bool(sample.get("violates", False))
                ]
                optimized_residues, optimized_constant, optimized_diagnostic = (
                    _optimized_pole_damping_candidate(
                        poles,
                        residues,
                        constant_coeff,
                        nports=nports,
                        freqs=optimized_freqs,
                        damping_factor=damping_factor,
                        epsilon=epsilon,
                        safety_margin=2e-5,
                        max_beta_scale=4.0,
                    )
                )
                if optimized_diagnostic.get("success"):
                    damping_candidates.insert(0, ("optimized_pole", optimized_residues, optimized_constant))
                    for blend in (0.99, 0.975, 0.95, 0.93, 0.9, 0.75, 0.5, 0.25):
                        damping_candidates.insert(
                            1,
                            (
                                f"optimized_pole_step_{blend:g}",
                                residues + blend * (optimized_residues - residues),
                                constant_coeff + blend * (optimized_constant - constant_coeff),
                            ),
                        )
                    for blend in (0.75, 0.5, 0.25):
                        damping_candidates.insert(
                            1,
                            (
                                f"optimized_pole_blend_{blend:g}",
                                uniform_residues + blend * (optimized_residues - uniform_residues),
                                uniform_constant + blend * (optimized_constant - uniform_constant),
                            ),
                        )

            candidate_results = []

            def evaluate_damping_candidate(
                damping_candidate_mode: str,
                candidate_residues: np.ndarray,
                candidate_constant: np.ndarray,
            ) -> dict[str, Any]:
                candidate_crossovers = check_passivity_hamiltonian_s(
                    poles,
                    candidate_residues,
                    candidate_constant,
                    nports,
                    f_max=f_max,
                )
                candidate_points = [0.0] + candidate_crossovers + [validation_f_limit]
                candidate_intervals = [
                    (float(candidate_points[idx]), float(candidate_points[idx + 1]))
                    for idx in range(len(candidate_points) - 1)
                ]
                candidate_samples = _projection_candidate_passivity_samples(
                    poles,
                    candidate_residues,
                    candidate_constant,
                    nports=nports,
                    intervals=candidate_intervals,
                    f_max=f_max,
                    epsilon=epsilon,
                    max_depth=2,
                    curvature_tol=1e-3,
                    reference_freqs=spectral_projection_reference_freqs
                    if spectral_projection_reference_s is not None
                    else None,
                )
                if candidate_samples:
                    candidate_max_sample = max(candidate_samples, key=lambda item: float(item["max_sigma"]))
                    candidate_max_sigma = float(candidate_max_sample["max_sigma"])
                    candidate_max_sigma_frequency = float(candidate_max_sample["frequency_hz"])
                    candidate_violation_count = sum(1 for item in candidate_samples if bool(item["violates"]))
                else:
                    candidate_max_sigma = 0.0
                    candidate_max_sigma_frequency = 0.0
                    candidate_violation_count = 0
                candidate_reference_rms = math.inf
                if spectral_projection_reference_freqs is not None and spectral_projection_reference_s is not None:
                    reference_freq_array = np.asarray(spectral_projection_reference_freqs, dtype=float).reshape(-1)
                    if int(spectral_projection_reference_rms_chunk_size) > 0:
                        candidate_reference_rms = _reference_response_rms_candidates_chunked(
                            poles,
                            [(candidate_residues, candidate_constant)],
                            nports=nports,
                            freqs=reference_freq_array,
                            reference_freqs=spectral_projection_reference_freqs,
                            reference_s=spectral_projection_reference_s,
                            chunk_size=int(spectral_projection_reference_rms_chunk_size),
                        )[0]
                    else:
                        candidate_reference_matrices = _reference_s_matrices_at_freqs(
                            reference_freq_array,
                            reference_freqs=spectral_projection_reference_freqs,
                            reference_s=spectral_projection_reference_s,
                            nports=nports,
                        )
                        candidate_reference_rms = _reference_response_rms_to_matrices(
                            poles,
                            candidate_residues,
                            candidate_constant,
                            nports=nports,
                            freqs=reference_freq_array,
                            reference_matrices=candidate_reference_matrices,
                            basis=_rational_basis_at_freqs(poles, reference_freq_array),
                        )
                return {
                    "mode": damping_candidate_mode,
                    "residues": candidate_residues,
                    "constant": candidate_constant,
                    "samples": candidate_samples,
                    "intervals": candidate_intervals,
                    "max_sigma": float(candidate_max_sigma),
                    "max_sigma_frequency_hz": float(candidate_max_sigma_frequency),
                    "violation_count": int(candidate_violation_count),
                    "reference_rms": float(candidate_reference_rms),
                }

            for damping_candidate_mode, candidate_residues, candidate_constant in damping_candidates:
                candidate = evaluate_damping_candidate(
                    damping_candidate_mode,
                    candidate_residues,
                    candidate_constant,
                )
                candidate_results.append(candidate)
                if (
                    damping_candidate_mode.startswith("optimized_pole_step_")
                    and float(candidate["max_sigma"]) > 1.0 + epsilon
                ):
                    micro_factor = _global_damping_factor(
                        max_sigma=float(candidate["max_sigma"]),
                        epsilon=epsilon,
                        safety_margin=global_damping_safety_margin,
                    )
                    if micro_factor < 1.0:
                        micro_candidate = evaluate_damping_candidate(
                            f"{damping_candidate_mode}_plus_uniform",
                            candidate_residues * micro_factor,
                            candidate_constant * micro_factor,
                        )
                        micro_candidate["micro_uniform_factor"] = float(micro_factor)
                        candidate_results.append(micro_candidate)

            damping_acceptance_sigma = 1.0 - max(float(epsilon), float(global_damping_safety_margin))
            passive_candidates = [
                candidate
                for candidate in candidate_results
                if int(candidate["violation_count"]) == 0
                and float(candidate["max_sigma"]) <= damping_acceptance_sigma
            ]
            if passive_candidates:
                selected_damping = min(
                    passive_candidates,
                    key=lambda candidate: (
                        float(candidate["reference_rms"]),
                        float(candidate["max_sigma"]),
                    ),
                )
            else:
                selected_damping = min(
                    candidate_results,
                    key=lambda candidate: (
                        float(candidate["max_sigma"]),
                        int(candidate["violation_count"]),
                        float(candidate["reference_rms"]),
                    ),
                )
            residues = selected_damping["residues"]
            constant_coeff = selected_damping["constant"]
            validation_samples = selected_damping["samples"]
            validation_intervals = selected_damping["intervals"]
            validation_max_sigma_after = float(selected_damping["max_sigma"])
            validation_max_sigma_frequency = float(selected_damping["max_sigma_frequency_hz"])
            validation_violation_count = int(selected_damping["violation_count"])
            damping_history.append(
                {
                    "iteration": int(damping_iterations),
                    "damping_factor": float(damping_factor),
                    "cumulative_damping_factor": float(cumulative_damping_factor),
                    "mode": selected_damping["mode"],
                    "max_sigma_after": float(validation_max_sigma_after),
                    "violation_count_after": int(validation_violation_count),
                    "reference_rms_after": float(selected_damping["reference_rms"]),
                    "candidate_modes": [
                        {
                            "mode": candidate["mode"],
                            "max_sigma": float(candidate["max_sigma"]),
                            "violation_count": int(candidate["violation_count"]),
                            "reference_rms": float(candidate["reference_rms"]),
                        }
                        for candidate in candidate_results
                    ],
                }
            )
            validation_max_sigma = validation_max_sigma_after
        diagnostics.append(
            {
                "type": "global_damping_fallback",
                "mode": global_damping_mode,
                "selective_min_frequency_hz": float(global_damping_selective_min_frequency),
                "safety_margin": float(global_damping_safety_margin),
                "damping_factor": float(cumulative_damping_factor),
                "damping_iterations": int(damping_iterations),
                "damping_history": damping_history,
                "max_sigma_before": float(validation_max_sigma_before_damping),
                "max_sigma_after": float(validation_max_sigma_after),
                "accepted": bool(validation_max_sigma_after < validation_max_sigma_before_damping),
            }
        )
        validation_max_sigma = validation_max_sigma_after

    diagnostics.append(
        {
            "type": "final_validation",
            "final_validation_max_sigma": validation_max_sigma,
            "final_validation_max_sigma_frequency_hz": validation_max_sigma_frequency,
            "final_validation_violation_count": int(validation_violation_count),
            "final_validation_sample_count": int(len(validation_samples)),
            "final_validation_passed": bool(validation_violation_count == 0),
        }
    )

    # Update poles in vector_fit
    if perturb_poles:
        if len(poles) != len(poles_orig):
            contracted_poles = np.zeros_like(poles_orig)
            idx_expanded = 0
            for idx in range(len(poles_orig)):
                contracted_poles[idx] = poles[idx_expanded]
                if abs(poles_orig[idx].imag) > 1e-15:
                    idx_expanded += 2
                else:
                    idx_expanded += 1
            vector_fit.poles = contracted_poles
        else:
            vector_fit.poles = poles

    # Update constant_coeff in vector_fit
    if asymptotic_constant_projected or perturb_constant or global_damping_fallback or spectral_projection_fallback:
        vector_fit.constant_coeff = constant_coeff

    # Update residues in vector_fit
    if len(poles) != len(poles_orig):
        contracted_residues = np.zeros_like(residues_orig)
        idx_expanded = 0
        for idx in range(len(poles_orig)):
            contracted_residues[:, idx] = residues[:, idx_expanded]
            if abs(poles_orig[idx].imag) > 1e-15:
                idx_expanded += 2
            else:
                idx_expanded += 1
        vector_fit.residues = contracted_residues
    else:
        vector_fit.residues = residues
