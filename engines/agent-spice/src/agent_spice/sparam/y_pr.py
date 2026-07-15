"""KYP-certified positive-real enforcement for small proper rational Y models."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import numpy as np


@dataclass(frozen=True)
class EnforcedYModel:
    poles: np.ndarray
    residues: np.ndarray
    constant_coeff: np.ndarray
    proportional_coeff: np.ndarray
    nports: int

    @property
    def network(self) -> SimpleNamespace:
        return SimpleNamespace(nports=self.nports)


@dataclass(frozen=True)
class YPositiveRealCertificate:
    solver: str
    status: str
    state_count: int
    kyp_max_eigenvalue: float
    p_min_eigenvalue: float
    correction_frobenius_norm: float


def _real_scalar_array(values: Any, *, label: str, tolerance: float) -> np.ndarray:
    array = np.asarray(values, dtype=complex)
    scale = max(1.0, float(np.max(np.abs(array)))) if array.size else 1.0
    if not np.isfinite(array).all() or np.max(np.abs(array.imag), initial=0.0) > tolerance * scale:
        raise ValueError(f"KYP Y enforcement requires real {label}")
    return array.real


def _real_y_state_space(model: Any, *, tolerance: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[tuple[str, int, int]]]:
    network = getattr(model, "network", None)
    ports = getattr(network, "nports", None)
    if not isinstance(ports, (int, np.integer)) or isinstance(ports, bool) or ports <= 0:
        raise ValueError("model must provide a positive network.nports")
    ports = int(ports)
    poles = np.asarray(getattr(model, "poles", None), dtype=complex).reshape(-1)
    residues = np.asarray(getattr(model, "residues", None), dtype=complex)
    constant = _real_scalar_array(getattr(model, "constant_coeff", None), label="constant coefficients", tolerance=tolerance).reshape(ports, ports)
    proportional = _real_scalar_array(getattr(model, "proportional_coeff", None), label="proportional coefficients", tolerance=tolerance).reshape(ports, ports)
    if residues.shape != (ports * ports, len(poles)):
        raise ValueError("model has invalid native pole-residue dimensions")
    blocks: list[tuple[str, int, int]] = []
    state_count = sum(ports if pole.imag == 0.0 else 2 * ports for pole in poles)
    a = np.zeros((state_count, state_count), dtype=float)
    b = np.zeros((state_count, ports), dtype=float)
    c = np.zeros((ports, state_count), dtype=float)
    offset = 0
    for index, pole in enumerate(poles):
        if pole.real >= 0.0:
            raise ValueError("KYP Y enforcement requires stable poles")
        residue = residues[:, index].reshape(ports, ports)
        if pole.imag == 0.0:
            real_residue = _real_scalar_array(residue, label="residues at real poles", tolerance=tolerance)
            section = slice(offset, offset + ports)
            a[section, section] = pole.real * np.eye(ports)
            b[section, :] = np.eye(ports)
            c[:, section] = real_residue
            blocks.append(("real", offset, index))
            offset += ports
        elif pole.imag > 0.0:
            section_a = slice(offset, offset + ports)
            section_b = slice(offset + ports, offset + 2 * ports)
            a[section_a, section_a] = pole.real * np.eye(ports)
            a[section_a, section_b] = pole.imag * np.eye(ports)
            a[section_b, section_a] = -pole.imag * np.eye(ports)
            a[section_b, section_b] = pole.real * np.eye(ports)
            b[section_a, :] = 2.0 * np.eye(ports)
            c[:, section_a] = residue.real
            c[:, section_b] = residue.imag
            blocks.append(("complex", offset, index))
            offset += 2 * ports
        else:
            raise ValueError("native model must store only positive-imaginary complex pole representatives")
    return a, b, c, constant, proportional, blocks


def _rank_reduced_real_y_state_space(
    model: Any,
    *,
    tolerance: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[tuple[str, int, int, np.ndarray]]]:
    """Build a real realization with one state per residue rank.

    The native shared-pole representation allocates one state per input port
    even when a residue is rank deficient.  Exact LFT models commonly have
    rank-one residues, so reducing that duplication substantially lowers the
    KYP SDP dimension without changing the transfer function.
    """

    network = getattr(model, "network", None)
    ports = int(getattr(network, "nports", 0))
    if ports <= 0:
        raise ValueError("model must provide a positive network.nports")
    poles = np.asarray(getattr(model, "poles", None), dtype=complex).reshape(-1)
    residues = np.asarray(getattr(model, "residues", None), dtype=complex)
    constant = _real_scalar_array(getattr(model, "constant_coeff", None), label="constant coefficients", tolerance=tolerance).reshape(ports, ports)
    proportional = _real_scalar_array(getattr(model, "proportional_coeff", None), label="proportional coefficients", tolerance=tolerance).reshape(ports, ports)
    if residues.shape != (ports * ports, len(poles)):
        raise ValueError("model has invalid native pole-residue dimensions")

    state_blocks: list[tuple[str, complex, int, np.ndarray, np.ndarray]] = []
    for index, pole in enumerate(poles):
        if pole.real >= 0.0:
            raise ValueError("KYP Y enforcement requires stable poles")
        residue = residues[:, index].reshape(ports, ports)
        if pole.imag == 0.0:
            matrix = _real_scalar_array(residue, label="residues at real poles", tolerance=tolerance)
            left, singular, right = np.linalg.svd(matrix, full_matrices=False)
            cutoff = max(float(singular[0]) if singular.size else 0.0, 1.0) * tolerance
            for rank, value in enumerate(singular):
                if value <= cutoff:
                    continue
                root = float(np.sqrt(value))
                state_blocks.append(("real", pole, index, left[:, rank] * root, right[rank, :] * root))
        elif pole.imag > 0.0:
            left, singular, right = np.linalg.svd(residue, full_matrices=False)
            cutoff = max(float(singular[0]) if singular.size else 0.0, 1.0) * tolerance
            for rank, value in enumerate(singular):
                if value <= cutoff:
                    continue
                root = float(np.sqrt(value))
                state_blocks.append(("complex", pole, index, left[:, rank] * root, right[rank, :] * root))
        else:
            raise ValueError("native model must store only positive-imaginary complex pole representatives")

    if not state_blocks and len(poles):
        # Keep one harmless controllable channel for a D-only model.  It lets
        # the SDP repair a negative conductance while its initial transfer is
        # exactly zero because the output factor is zero.
        first = poles[0]
        if first.imag == 0.0:
            state_blocks.append(("real", first, 0, np.zeros(ports), np.ones(ports)))
        elif first.imag > 0.0:
            state_blocks.append(("complex", first, 0, np.zeros(ports, dtype=complex), np.ones(ports, dtype=complex)))
    states = sum(1 if kind == "real" else 2 for kind, *_ in state_blocks)
    if states == 0:
        raise ValueError("KYP Y enforcement requires at least one stable pole")
    a = np.zeros((states, states), dtype=float)
    b = np.zeros((states, ports), dtype=float)
    c = np.zeros((ports, states), dtype=float)
    blocks: list[tuple[str, int, int, np.ndarray]] = []
    offset = 0
    for kind, pole, index, left, right in state_blocks:
        if kind == "real":
            a[offset, offset] = pole.real
            b[offset, :] = right.real
            c[:, offset] = left.real
            blocks.append((kind, offset, index, b[offset : offset + 1, :].copy()))
            offset += 1
        else:
            a[offset : offset + 2, offset : offset + 2] = ((pole.real, -pole.imag), (pole.imag, pole.real))
            b[offset : offset + 2, :] = np.vstack((right.real, right.imag))
            c[:, offset : offset + 2] = np.column_stack((2.0 * left.real, -2.0 * left.imag))
            blocks.append((kind, offset, index, b[offset : offset + 2, :].copy()))
            offset += 2
    return a, b, c, constant, proportional, blocks


def _balance_kyp_realization(
    a: np.ndarray,
    b: np.ndarray,
    c: np.ndarray,
    blocks: list[tuple[str, int, int, np.ndarray]],
    *,
    omega_scale: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Balance each pole block before the SDP without changing its transfer.

    Native residues can span many orders of magnitude.  The KYP inequality is
    similarity invariant, so apply one scalar per real/complex pole block to
    balance its B and normalized C norms.  Keeping the complex-pair scale
    shared preserves the real 2-by-2 oscillator blocks in ``A``.
    """

    scales = np.ones(a.shape[0], dtype=float)
    c_scaled = c / omega_scale
    for _kind, offset, _index, _b_factor in blocks:
        width = 1 if _kind == "real" else 2
        section = slice(offset, offset + width)
        b_norm = float(np.linalg.norm(b[section, :], ord="fro"))
        c_norm = float(np.linalg.norm(c_scaled[:, section], ord="fro"))
        if b_norm <= np.finfo(float).tiny or c_norm <= np.finfo(float).tiny:
            continue
        factor = float(np.sqrt(b_norm / c_norm))
        # Prevent an otherwise harmless zero/tiny residue from creating an
        # extreme SDP coordinate transform.
        factor = min(1.0e8, max(1.0e-8, factor))
        scales[section] = factor
    return a, b / scales[:, None], c_scaled * scales[None, :], scales


def enforce_y_positive_real_kyp(
    model: Any,
    *,
    margin: float = 1.0e-8,
    max_states: int = 128,
    max_relative_correction: float = 0.05,
    solver: str = "CLARABEL",
    tolerance: float = 1.0e-8,
) -> tuple[EnforcedYModel, YPositiveRealCertificate]:
    """Correct C/D through a continuous-frequency KYP LMI.

    This is intentionally limited to real, stable, proper models with a small
    dense state count.  Unlike a sampled clipping heuristic, a successful LMI
    supplies a KYP certificate for positive realness over the full frequency
    axis under the realization assumptions.
    """

    try:
        import cvxpy as cp
    except ImportError as exc:  # pragma: no cover - installation contract
        raise RuntimeError("Y positive-real enforcement requires the optional cvxpy dependency") from exc
    if not np.isfinite(margin) or margin <= 0.0:
        raise ValueError("margin must be finite and positive")
    if not np.isfinite(max_relative_correction) or max_relative_correction < 0.0:
        raise ValueError("max_relative_correction must be finite and non-negative")
    a, b, c0, d0, e0, blocks = _rank_reduced_real_y_state_space(model, tolerance=tolerance)
    ports = d0.shape[0]
    states = a.shape[0]
    if states == 0 or states > max_states:
        raise ValueError(f"KYP Y enforcement supports 1..{max_states} dense states; got {states}")
    e_scale = max(float(np.max(np.abs(e0))), np.finfo(float).tiny)
    if np.max(np.abs(e0 - e0.T)) > tolerance * e_scale:
        raise ValueError("KYP Y enforcement requires a symmetric proportional matrix")
    if float(np.min(np.linalg.eigvalsh(0.5 * (e0 + e0.T)))) < -tolerance * e_scale:
        raise ValueError("KYP Y enforcement requires a positive-semidefinite proportional matrix")
    # A feasible certificate means the original fit is already continuous-time
    # positive real.  Preserve it exactly instead of running a correction SDP.
    # Normalize the Laplace variable.  KYP is invariant under s'=s/omega,
    # while the normalization avoids SDP matrices that mix 1e9 pole entries
    # with 1e-2 Siemens feedthroughs.
    omega_scale = max(1.0, float(np.max(np.abs(np.linalg.eigvals(a)))))
    a_scaled, b_scaled, c0_scaled, state_scales = _balance_kyp_realization(
        a / omega_scale,
        b,
        c0,
        blocks,
        omega_scale=omega_scale,
    )
    p_check = cp.Variable((states, states), symmetric=True)
    kyp_check = cp.bmat(
        (
            (a_scaled.T @ p_check + p_check @ a_scaled, p_check @ b_scaled - c0_scaled.T),
            (b_scaled.T @ p_check - c0_scaled, -(d0 + d0.T)),
        )
    )
    check_problem = cp.Problem(cp.Minimize(0), [p_check >> margin * np.eye(states), kyp_check << -margin * np.eye(states + ports)])
    check_problem.solve(solver=solver)
    if check_problem.status in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE} and p_check.value is not None:
        p_value = np.asarray(p_check.value, dtype=float)
        kyp_value = np.block(
            [
                [a_scaled.T @ p_value + p_value @ a_scaled, p_value @ b_scaled - c0_scaled.T],
                [b_scaled.T @ p_value - c0_scaled, -(d0 + d0.T)],
            ]
        )
        kyp_max = float(np.max(np.linalg.eigvalsh(0.5 * (kyp_value + kyp_value.T))))
        p_min = float(np.min(np.linalg.eigvalsh(0.5 * (p_value + p_value.T))))
        certificate_tolerance = max(1.0e-7, 10.0 * margin)
        if kyp_max <= certificate_tolerance and p_min >= -certificate_tolerance:
            original = EnforcedYModel(
                np.asarray(getattr(model, "poles"), dtype=complex).reshape(-1).copy(),
                np.asarray(getattr(model, "residues"), dtype=complex).copy(),
                d0.reshape(-1).copy(),
                e0.reshape(-1).astype(complex),
                ports,
            )
            return original, YPositiveRealCertificate(solver, str(check_problem.status), states, kyp_max, p_min, 0.0)
    p = cp.Variable((states, states), symmetric=True)
    c = cp.Variable((ports, states))
    d = cp.Variable((ports, ports))
    kyp = cp.bmat(
        (
            (a_scaled.T @ p + p @ a_scaled, p @ b_scaled - c.T),
            (b_scaled.T @ p - c, -(d + d.T)),
        )
    )
    c_scale = max(1.0e-12, float(np.linalg.norm(c0_scaled, ord="fro")))
    d_scale = max(1.0, float(np.linalg.norm(d0, ord="fro")))
    constraints = [p >> margin * np.eye(states), kyp << -margin * np.eye(states + ports)]
    problem = cp.Problem(cp.Minimize(cp.sum_squares((c - c0) / c_scale) + cp.sum_squares((d - d0) / d_scale)), constraints)
    problem.solve(solver=solver)
    if problem.status not in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE} or p.value is None or c.value is None or d.value is None:
        raise ValueError(f"KYP Y enforcement did not produce a certificate (status={problem.status})")
    p_value = np.asarray(p.value, dtype=float)
    c_value = np.asarray(c.value, dtype=float)
    d_value = np.asarray(d.value, dtype=float)
    kyp_value = np.block(
        [
            [a_scaled.T @ p_value + p_value @ a_scaled, p_value @ b_scaled - c_value.T],
            [b_scaled.T @ p_value - c_value, -(d_value + d_value.T)],
        ]
    )
    kyp_max = float(np.max(np.linalg.eigvalsh(0.5 * (kyp_value + kyp_value.T))))
    p_min = float(np.min(np.linalg.eigvalsh(0.5 * (p_value + p_value.T))))
    certificate_tolerance = max(1.0e-7, 10.0 * margin)
    if kyp_max > certificate_tolerance or p_min < -certificate_tolerance:
        raise ValueError("KYP solver result failed the numerical certificate audit")
    poles = np.asarray(getattr(model, "poles"), dtype=complex).reshape(-1).copy()
    residues = np.zeros_like(np.asarray(getattr(model, "residues"), dtype=complex))
    for kind, offset, index, b_factor in blocks:
        width = 1 if kind == "real" else 2
        c_original = c_value[:, offset : offset + width] * omega_scale / state_scales[offset]
        if kind == "real":
            residues[:, index] += (c_original @ b_factor).reshape(-1)
        else:
            real = c_original[:, :1]
            imag = c_original[:, 1:2]
            residues[:, index] += (0.5 * (real - 1j * imag) @ (b_factor[:1, :] + 1j * b_factor[1:2, :])).reshape(-1)
    correction = float(
        np.sqrt(
            np.linalg.norm((c_value - c0_scaled) * omega_scale / state_scales[None, :], ord="fro") ** 2
            + np.linalg.norm(d_value - d0, ord="fro") ** 2
        )
    )
    baseline = max(1.0, float(np.sqrt(np.linalg.norm(c0, ord="fro") ** 2 + np.linalg.norm(d0, ord="fro") ** 2)))
    if correction > max_relative_correction * baseline:
        raise ValueError(
            "KYP Y enforcement requires an excessive correction "
            f"({correction / baseline:.6g} relative; limit={max_relative_correction:.6g})"
        )
    enforced = EnforcedYModel(poles, residues, d_value.reshape(-1), e0.reshape(-1).astype(complex), ports)
    certificate = YPositiveRealCertificate(
        solver=solver,
        status=str(problem.status),
        state_count=states,
        kyp_max_eigenvalue=kyp_max,
        p_min_eigenvalue=p_min,
        correction_frobenius_norm=correction,
    )
    return enforced, certificate
