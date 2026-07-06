from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import scipy.linalg as la
import scipy.optimize as opt




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
    poles = np.asarray(getattr(vector_fit, "poles", []), dtype=complex)
    residues = np.asarray(getattr(vector_fit, "residues", []), dtype=complex)
    constant_coeff = np.asarray(getattr(vector_fit, "constant_coeff", []), dtype=complex)

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
) -> None:
    """
    Enforces passivity of S-parameter model using Hamiltonian crossover checks and SLSQP residue perturbation.
    """
    poles = np.asarray(getattr(vector_fit, "poles", []), dtype=complex)
    residues = np.asarray(getattr(vector_fit, "residues", []), dtype=complex)
    constant_coeff = np.asarray(getattr(vector_fit, "constant_coeff", []), dtype=complex)

    if residues.size == 0 and len(poles) > 0:
        residues = np.zeros((nports * nports, len(poles)), dtype=complex)
    if constant_coeff.size == 0:
        constant_coeff = np.zeros(nports * nports, dtype=complex)

    real_poles, complex_pairs = partition_poles(poles)
    n_real = len(real_poles)
    n_complex = len(complex_pairs)
    vars_per_pair = n_real + 2 * n_complex
    n_vars = nports * nports * vars_per_pair

    for iteration in range(max_iterations):
        crossover_freqs = check_passivity_hamiltonian_s(poles, residues, constant_coeff, nports)

        f_limit = 100e9
        if len(crossover_freqs) > 0:
            f_limit = max(f_limit, crossover_freqs[-1] * 2.0)
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
            break

        A_list = []
        b_list = []

        for f_v, sigma_max in violating_freqs:
            s_val = 1j * 2.0 * np.pi * f_v
            S_f = constant_coeff.reshape((nports, nports)).copy().astype(complex)
            for k in range(len(poles)):
                S_f += residues.reshape((nports, nports, len(poles)))[:, :, k] / (s_val - poles[k])

            U, s_values, Vh = la.svd(S_f)
            for m, sm in enumerate(s_values):
                if sm > 1.0 + epsilon:
                    u_m = U[:, m]
                    v_m = Vh[m, :].conj()

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

                    A_list.append(A_row)
                    b_list.append(b_val)

        if not A_list:
            break

        A_ineq = np.array(A_list)
        b_ineq = np.array(b_list)

        res = opt.minimize(
            fun=lambda x: 0.5 * np.sum(x**2),
            x0=np.zeros(n_vars),
            jac=lambda x: x,
            constraints=[{'type': 'ineq', 'fun': lambda x: b_ineq - A_ineq @ x, 'jac': lambda x: -A_ineq}],
            method='SLSQP',
            options={'maxiter': 100, 'ftol': 1e-8}
        )

        if not res.success:
            break

        x_opt = res.x
        for i in range(nports):
            for j in range(nports):
                r_idx = i * nports + j
                offset = r_idx * vars_per_pair

                for var_idx, (pole_idx, val) in enumerate(real_poles):
                    residues[r_idx, pole_idx] += x_opt[offset + var_idx]

                for var_idx, (pole_idx1, pole_idx2, sigma, omega) in enumerate(complex_pairs):
                    dx = x_opt[offset + n_real + 2 * var_idx]
                    dy = x_opt[offset + n_real + 2 * var_idx + 1]
                    residues[r_idx, pole_idx1] += dx + 1j * dy
                    residues[r_idx, pole_idx2] += dx - 1j * dy

    vector_fit.residues = residues


