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
    return accepted_score is None


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
                p_comp = p if p.imag > 0 else other_p
                complex_pairs.append((idx, conj_idx, p_comp.real, p_comp.imag))
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

    for i in range(len(points) - 1):
        f_start = points[i]
        f_end = points[i+1]
        f_mid = (f_start + f_end) / 2.0

        s_val = 1j * 2.0 * np.pi * f_mid
        S_mid = constant_coeff.reshape((nports, nports)).copy().astype(complex)
        for k in range(len(poles)):
            S_mid += residues.reshape((nports, nports, len(poles)))[:, :, k] / (s_val - poles[k])

        sigmas = la.svd(S_mid, compute_uv=False)
        max_sigma = float(np.max(sigmas))

        if max_sigma > 1.0 + epsilon:
            violation_bands.append([f_start, f_end])

    max_s = -np.inf
    max_s_freq = 0.0

    sample_freqs = sorted(list(set(points + [f / 2.0 for f in crossover_freqs])))
    for f in sample_freqs:
        s_val = 1j * 2.0 * np.pi * f
        S_f = constant_coeff.reshape((nports, nports)).copy().astype(complex)
        for k in range(len(poles)):
            S_f += residues.reshape((nports, nports, len(poles)))[:, :, k] / (s_val - poles[k])
        sigmas = la.svd(S_f, compute_uv=False)
        curr_max = float(np.max(sigmas))
        if curr_max > max_s:
            max_s = curr_max
            max_s_freq = f

    return PassivitySampleReport(
        max_sigma=max_s,
        max_sigma_frequency_hz=max_s_freq,
        violation_bands_hz=violation_bands,
        frequency_points=len(crossover_freqs),
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
                p_comp = p if p.imag > 0 else other_p
                complex_pairs.append((idx, conj_idx, p_comp.real, p_comp.imag))
                visited.add(idx)
                visited.add(conj_idx)
            else:
                real_poles.append((idx, p.real))
                visited.add(idx)
    return real_poles, complex_pairs


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
    constant_weight: float = 1.0,
    pole_weight: float = 1.0,
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

    best_residues = residues.copy()
    best_constant = constant_coeff.copy()
    best_poles = poles.copy()
    best_score: _PassivityScore | None = None
    diagnostics: list[dict[str, Any]] = []
    vector_fit.passivity_enforcement_diagnostics = diagnostics

    for iteration in range(max_iterations):
        crossover_freqs = check_passivity_hamiltonian_s(poles, residues, constant_coeff, nports, f_max=f_max)

        f_limit = 100e9
        if len(crossover_freqs) > 0:
            f_limit = max(f_limit, crossover_freqs[-1] * 2.0)
        if f_max is not None:
            f_limit = min(f_limit, f_max)
        points = [0.0] + crossover_freqs + [f_limit]

        violating_freqs = []
        for i in range(len(points) - 1):
            f_start = points[i]
            f_end = points[i+1]
            grid = np.linspace(f_start, f_end, 5)
            max_sigma_val = -np.inf
            max_f = f_start
            for f in grid:
                s_val = 1j * 2.0 * np.pi * f
                S_f = constant_coeff.reshape((nports, nports)).copy().astype(complex)
                for k in range(len(poles)):
                    S_f += residues.reshape((nports, nports, len(poles)))[:, :, k] / (s_val - poles[k])
                sigmas = la.svd(S_f, compute_uv=False)
                curr_max = float(np.max(sigmas))
                if curr_max > max_sigma_val:
                    max_sigma_val = curr_max
                    max_f = f
            if max_sigma_val > 1.0 + epsilon:
                violating_freqs.append((max_f, max_sigma_val))

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

        if max_violation_samples > 0 and len(violating_freqs) > max_violation_samples:
            violating_freqs = sorted(violating_freqs, key=lambda item: item[1], reverse=True)[:max_violation_samples]

        real_poles, complex_pairs = partition_poles(poles)
        n_real = len(real_poles)
        n_complex = len(complex_pairs)
        vars_per_pair = n_real + 2 * n_complex

        n_residue_vars = nports * nports * vars_per_pair
        n_constant_vars = nports * nports if perturb_constant else 0
        n_pole_vars = (n_real + 2 * n_complex) if perturb_poles else 0
        n_vars = n_residue_vars + n_constant_vars + n_pole_vars

        A_list = []
        b_list = []

        for f_v, sigma_max in violating_freqs:
            s_val = 1j * 2.0 * np.pi * f_v
            S_f = constant_coeff.reshape((nports, nports)).copy().astype(complex)
            for k in range(len(poles)):
                S_f += residues.reshape((nports, nports, len(poles)))[:, :, k] / (s_val - poles[k])

            U, s_values, Vh = la.svd(S_f)
            for sm, u_m, v_m in _singular_violation_modes(U, s_values, Vh, epsilon=epsilon):
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
                    _select_active_variable_indices(A_ineq, active_budget),
                    None,
                ),
            ]
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
                        _select_active_variable_indices(A_ineq, active_budget, variable_weights=variable_fit_weights),
                        variable_fit_weights,
                    )
                )

            for candidate_priority, (weighting_name, active_indices, qp_weights) in enumerate(qp_attempts):
                if weighting_name == "fit_weighted" and not _should_try_fit_weighted_qp(accepted_score):
                    continue
                active_matrix = A_ineq[:, active_indices]
                active_weights = None if qp_weights is None else qp_weights[active_indices]
                qp_result = _solve_min_norm_upper_bound_dual_qp(
                    active_matrix,
                    b_ineq,
                    variable_weights=active_weights,
                )
                if not qp_result.success:
                    diagnostic = {
                        "iteration": iteration,
                        "active_budget": active_budget,
                        "weighting": weighting_name,
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

                    residue_diff = np.linalg.norm(candidate_residues - residues)
                    constant_diff = np.linalg.norm(candidate_constant - constant_coeff) if perturb_constant else 0.0
                    pole_diff = np.linalg.norm(candidate_poles - poles) if perturb_poles else 0.0
                    candidate_delta_norm = float(residue_diff + constant_diff + pole_diff)

                    candidate_improves_sample = candidate_score.is_better_than(sampled_score)
                    candidate_preserves_holdout = candidate_holdout_score.max_sigma <= holdout_score.max_sigma + 1e-10
                    candidate_improves_best = _is_candidate_update_better(
                        candidate_score,
                        candidate_delta_norm,
                        accepted_score,
                        accepted_delta_norm,
                        candidate_priority=candidate_priority,
                        best_priority=accepted_priority,
                        score_abs_tol=1e-8,
                    )
                    accepted_candidate = candidate_improves_sample and candidate_preserves_holdout and candidate_improves_best
                    reject_reason = None
                    if not candidate_improves_sample:
                        reject_reason = "no_sampled_improvement"
                    elif not candidate_preserves_holdout:
                        reject_reason = "holdout_regression"
                    elif not candidate_improves_best:
                        reject_reason = "worse_than_selected_candidate"

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
                    diagnostic["candidate_priority"] = int(candidate_priority)
                    diagnostic["holdout_max_sigma_before"] = float(holdout_score.max_sigma)
                    diagnostic["holdout_max_sigma_after"] = float(candidate_holdout_score.max_sigma)
                    diagnostic["holdout_improvement"] = float(holdout_score.max_sigma - candidate_holdout_score.max_sigma)
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
                        accepted_delta_norm = candidate_delta_norm
                        accepted_priority = candidate_priority

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
    if perturb_constant:
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
