"""Exact state-space bilinear transforms for proper rational multiports."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import numpy as np


@dataclass(frozen=True)
class RationalSModel:
    """RFM-compatible canonical S pole-residue model produced by a rational LFT."""

    poles: np.ndarray
    residues: np.ndarray
    constant_coeff: np.ndarray
    proportional_coeff: np.ndarray
    nports: int

    @property
    def network(self) -> SimpleNamespace:
        return SimpleNamespace(nports=self.nports)


def _native_dimensions(model: Any, *, allow_proportional: bool = False) -> tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    network = getattr(model, "network", None)
    ports = getattr(network, "nports", None)
    if not isinstance(ports, (int, np.integer)) or isinstance(ports, bool) or ports <= 0:
        raise ValueError("model must provide a positive network.nports")
    poles = np.asarray(getattr(model, "poles", None), dtype=complex).reshape(-1)
    residues = np.asarray(getattr(model, "residues", None), dtype=complex)
    constant = np.asarray(getattr(model, "constant_coeff", None), dtype=complex).reshape(-1)
    proportional = np.asarray(getattr(model, "proportional_coeff", None), dtype=complex).reshape(-1)
    count = int(ports) ** 2
    if residues.shape != (count, len(poles)) or constant.size != count or proportional.size != count:
        raise ValueError("model has invalid native pole-residue dimensions")
    if not np.isfinite(poles).all() or not np.isfinite(residues).all() or not np.isfinite(constant).all() or not np.isfinite(proportional).all():
        raise ValueError("model has non-finite pole-residue coefficients")
    if np.any(poles.real >= 0.0):
        raise ValueError("exact Y-to-S transform requires stable Y poles")
    if not allow_proportional and np.any(np.abs(proportional) > 1.0e-14):
        raise ValueError("exact RFM Y-to-S transform currently requires a proper Y model (zero proportional term)")
    return int(ports), poles, residues, constant.reshape(int(ports), int(ports)), proportional


def _expanded_state_space(model: Any, *, allow_proportional: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return complex state-space matrices for native canonical pole-residue data."""

    ports, poles, residues, constant, proportional = _native_dimensions(model, allow_proportional=allow_proportional)
    expanded_poles: list[complex] = []
    expanded_residues: list[np.ndarray] = []
    for index, pole in enumerate(poles):
        residue = residues[:, index].reshape(ports, ports)
        expanded_poles.append(complex(pole))
        expanded_residues.append(residue)
        if pole.imag > 0.0:
            expanded_poles.append(complex(pole.conjugate()))
            expanded_residues.append(residue.conjugate())
        elif pole.imag < 0.0:
            raise ValueError("native model must store only positive-imaginary complex pole representatives")
    states_per_input = len(expanded_poles)
    a = np.kron(np.eye(ports, dtype=complex), np.diag(np.asarray(expanded_poles, dtype=complex)))
    b = np.zeros((ports * states_per_input, ports), dtype=complex)
    c = np.zeros((ports, ports * states_per_input), dtype=complex)
    for input_port in range(ports):
        state_slice = slice(input_port * states_per_input, (input_port + 1) * states_per_input)
        b[state_slice, input_port] = 1.0
        for state, residue in enumerate(expanded_residues):
            c[:, state_slice.start + state] = residue[:, input_port]
    return a, b, c, constant, proportional.reshape(ports, ports)


def _canonicalize_state_space(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray, *, tolerance: float) -> RationalSModel:
    poles, vectors = np.linalg.eig(a)
    inverse_vectors = np.linalg.inv(vectors)
    output_vectors = c @ vectors
    input_vectors = inverse_vectors @ b
    ports = d.shape[0]
    entries: list[tuple[complex, np.ndarray]] = []
    used = np.zeros(len(poles), dtype=bool)
    for index, pole in enumerate(poles):
        if used[index]:
            continue
        scale = max(1.0, abs(pole))
        if abs(pole.imag) <= tolerance * scale:
            used[index] = True
            residue = np.outer(output_vectors[:, index], input_vectors[index, :])
            entries.append((complex(pole.real, 0.0), residue.real.astype(complex)))
            continue
        distances = np.abs(poles - pole.conjugate())
        distances[used] = np.inf
        partner = int(np.argmin(distances))
        if used[partner] or abs(poles[partner] - pole.conjugate()) > tolerance * scale:
            raise ValueError("Y-to-S state-space poles are not conjugate paired; refusing non-real RFM")
        positive, negative = (index, partner) if pole.imag > 0.0 else (partner, index)
        used[positive] = used[negative] = True
        entries.append((complex(poles[positive]), np.outer(output_vectors[:, positive], input_vectors[positive, :])))
    entries.sort(key=lambda item: (item[0].imag > 0.0, item[0].imag, item[0].real))
    canonical_poles = np.asarray([item[0] for item in entries], dtype=complex)
    residues = np.stack([item[1].reshape(-1) for item in entries], axis=1)
    if np.any(canonical_poles.real >= tolerance):
        raise ValueError("Y-to-S LFT produced an unstable S model")
    if np.max(np.abs(d.imag)) > tolerance * max(1.0, float(np.max(np.abs(d.real)))):
        raise ValueError("Y-to-S LFT produced a complex S feedthrough; model is not real RFM compatible")
    for index, pole in enumerate(canonical_poles):
        if pole.imag == 0.0 and np.max(np.abs(residues[:, index].imag)) > tolerance * max(1.0, float(np.max(np.abs(residues[:, index].real)))):
            raise ValueError("Y-to-S LFT produced complex residues at a real pole")
    return RationalSModel(
        poles=canonical_poles,
        residues=residues,
        constant_coeff=d.real.reshape(-1),
        proportional_coeff=np.zeros(ports * ports, dtype=complex),
        nports=ports,
    )


def exact_y_to_s_rational(model: Any, z0: float, *, tolerance: float = 1.0e-8) -> RationalSModel:
    """Apply the exact proper-rational LFT ``S=(I-z0Y)(I+z0Y)^-1``.

    This is a state-space algebraic transform, not a sampled conversion followed
    by vector fitting.  It deliberately rejects non-proper Y models because
    the current RFM target cannot represent their descriptor/feedthrough form.
    """

    if not np.isfinite(z0) or z0 <= 0.0:
        raise ValueError("z0 must be a finite positive real value")
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("tolerance must be finite and positive")
    a, b, c, d, _ = _expanded_state_space(model)
    identity = np.eye(d.shape[0], dtype=complex)
    try:
        f = np.linalg.solve(identity + z0 * d, identity)
    except np.linalg.LinAlgError as exc:
        raise ValueError("Y-to-S LFT has singular I+z0D feedthrough") from exc
    a_s = a - b @ f @ (z0 * c)
    b_s = b @ f
    c_s = -z0 * c - (identity - z0 * d) @ f @ (z0 * c)
    d_s = (identity - z0 * d) @ f
    return _canonicalize_state_space(a_s, b_s, c_s, d_s, tolerance=tolerance)


def exact_y_to_s_descriptor_rational(
    model: Any,
    z0: float,
    *,
    tolerance: float = 1.0e-8,
    max_descriptor_condition: float = 1.0e8,
) -> RationalSModel:
    """Apply the exact descriptor LFT for ``Y=D+sE+C(sI-A)^-1B``.

    This preserves a positive-definite proportional ``E`` term instead of
    approximating it with additional poles.  Singular ``E`` needs descriptor
    index reduction and is deliberately rejected rather than pseudo-inverted.
    """

    if not np.isfinite(z0) or z0 <= 0.0:
        raise ValueError("z0 must be a finite positive real value")
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("tolerance must be finite and positive")
    if not np.isfinite(max_descriptor_condition) or max_descriptor_condition <= 1.0:
        raise ValueError("max_descriptor_condition must be finite and > 1")
    a, b, c, d, e = _expanded_state_space(model, allow_proportional=True)
    scale = max(1.0, float(np.max(np.abs(e))))
    if np.max(np.abs(e.imag)) > tolerance * scale or np.max(np.abs(e - e.T.conjugate())) > tolerance * scale:
        raise ValueError("descriptor Y-to-S requires a real symmetric proportional matrix")
    e_real = e.real
    eigenvalues = np.linalg.eigvalsh(e_real)
    if eigenvalues[0] <= tolerance * max(float(abs(eigenvalues[-1])), np.finfo(float).tiny):
        raise ValueError("descriptor Y-to-S requires a positive-definite proportional matrix; singular E needs index reduction")
    e_s = np.block([[np.eye(a.shape[0], dtype=complex), np.zeros((a.shape[0], d.shape[0]), dtype=complex)], [np.zeros((d.shape[0], a.shape[0]), dtype=complex), z0 * e_real]])
    condition = float(np.linalg.cond(e_s))
    if not np.isfinite(condition) or condition > max_descriptor_condition:
        raise ValueError(f"descriptor Y-to-S pencil is ill-conditioned (cond(E_s)={condition:.12g})")
    identity = np.eye(d.shape[0], dtype=complex)
    a_s = np.block([[a, b], [-z0 * c, -(identity + z0 * d)]])
    b_s = np.vstack((np.zeros((a.shape[0], d.shape[0]), dtype=complex), identity))
    c_s = np.hstack((np.zeros((d.shape[0], a.shape[0]), dtype=complex), 2.0 * identity))
    d_s = -identity
    return _canonicalize_state_space(np.linalg.solve(e_s, a_s), np.linalg.solve(e_s, b_s), c_s, d_s, tolerance=tolerance)
