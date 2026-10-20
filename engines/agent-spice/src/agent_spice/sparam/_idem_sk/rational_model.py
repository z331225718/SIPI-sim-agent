"""Rational macromodel: pole-residue representation of a multiport frequency response.

This is the frozen shared interface of the idem_replica engine.  Every other
module (vector fitting, adaptive order search, passivity, SPICE synthesis)
consumes or produces RationalModel objects, so the array layout defined here
must not change without updating INTERFACES.md.

Mathematical form (Foster canonical form, S-parameters):

    S(s) ~= D + sum_{n=1..N} R_n / (s - p_n)          [ + s*E for Y/Z data ]

with s = j*2*pi*f.  D is the direct-coupling (asymptotic) matrix and E the
optional frequency-proportional term used only for admittance/impedance data.

Array layout
------------
poles     : (N,)   complex128, rad/s, Re(p) < 0 for a causal stable model
residues  : (N,P,P) complex128, residues[n] is the P x P residue matrix R_n
d         : (P,P)  complex128, real in practice
e         : (P,P)  complex128 or None

For a real-valued system the poles are real or occur in conjugate pairs, and
the residues obey R(p*) = conj(R(p)).  Use symmetrize() to re-impose that
structure after numerical pole relocation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

__all__ = [
    "RationalModel",
    "cauchy_matrix",
    "conjugate_pairs",
    "symmetrize",
    "real_pole_mask",
]

# Relative tolerance used to decide whether a pole is real.
_REAL_TOL = 1e-10


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def cauchy_matrix(s: np.ndarray, poles: np.ndarray) -> np.ndarray:
    """Return the Cauchy / partial-fraction basis 1 / (s_k - p_n).

    Parameters
    ----------
    s : (F,) complex
        Laplace variables, normally 2j*pi*f.
    poles : (N,) complex

    Returns
    -------
    (F, N) complex128
    """
    s = np.asarray(s, dtype=np.complex128).ravel()
    poles = np.asarray(poles, dtype=np.complex128).ravel()
    return 1.0 / (s[:, None] - poles[None, :])


def real_pole_mask(poles: np.ndarray, tol: float = _REAL_TOL) -> np.ndarray:
    """Boolean mask selecting the (numerically) real poles."""
    poles = np.asarray(poles, dtype=np.complex128).ravel()
    scale = np.maximum(1.0, np.abs(poles))
    return np.abs(poles.imag) <= tol * scale


def conjugate_pairs(poles: np.ndarray, tol: float = 1e-8) -> list:
    """Return index pairs (i, j) of conjugate complex pole pairs.

    Real poles are not reported.  An unmatched complex pole (only possible
    through numerical error) is reported as the pair (i, i).
    """
    poles = np.asarray(poles, dtype=np.complex128).ravel()
    n = poles.size
    used = np.zeros(n, dtype=bool)
    real = real_pole_mask(poles)
    pairs = []
    for i in range(n):
        if used[i] or real[i]:
            continue
        target = np.conj(poles[i])
        dist = np.abs(poles - target)
        dist[used] = np.inf
        dist[i] = np.inf
        j = int(np.argmin(dist))
        if j < n and dist[j] <= tol * max(1.0, abs(poles[i])):
            used[i] = used[j] = True
            pairs.append((i, j))
        else:
            used[i] = True
            pairs.append((i, i))
    return pairs


def symmetrize(poles: np.ndarray, residues: np.ndarray, d: np.ndarray, e=None):
    """Re-impose real-system structure (conjugate pole/residue pairs).

    Poles whose imaginary part is negligible are snapped onto the real axis;
    complex poles are returned as exact conjugate pairs and residues are
    averaged with their conjugate counterpart so that R(p*) = conj(R(p)).

    Returns
    -------
    (poles, residues, d, e) with the same shapes as the inputs.
    """
    poles = np.asarray(poles, dtype=np.complex128).ravel()
    residues = np.asarray(residues, dtype=np.complex128)
    n = poles.size
    new_poles = np.empty(n, dtype=np.complex128)
    new_res = np.empty_like(residues)
    used = np.zeros(n, dtype=bool)

    real = real_pole_mask(poles)
    for i in range(n):
        if used[i]:
            continue
        if real[i]:
            used[i] = True
            new_poles[i] = poles[i].real
            new_res[i] = residues[i].real
            continue
        target = np.conj(poles[i])
        dist = np.abs(poles - target)
        dist[used] = np.inf
        dist[i] = np.inf
        j = int(np.argmin(dist))
        if j < n and not used[j] and dist[j] <= 1e-6 * max(1.0, abs(poles[i])):
            used[i] = used[j] = True
            a = 0.5 * (poles[i].real + poles[j].real)
            b = abs(poles[i].imag) if poles[i].imag >= 0 else abs(poles[j].imag)
            new_poles[i] = a + 1j * b
            new_poles[j] = a - 1j * b
            ri = 0.5 * (residues[i] + np.conj(residues[j]))
            new_res[i] = ri
            new_res[j] = np.conj(ri)
        else:
            used[i] = True
            new_poles[i] = poles[i].real + 1j * abs(poles[i].imag)
            new_res[i] = residues[i]

    # A real-valued system requires S(s*) = conj(S(s)), which holds iff the
    # direct term D is REAL.  It does NOT require D to be symmetric:
    # reciprocity (S = S^T) is a separate, optional projection applied to the
    # DATA, never here.  Taking the real part is therefore the correct
    # projection; averaging with the transpose would silently corrupt any
    # non-reciprocal device.
    d = np.asarray(d, dtype=np.complex128)
    d = d.real.astype(np.complex128)
    if e is not None:
        e = np.asarray(e, dtype=np.complex128)
        e = e.real.astype(np.complex128)
    return new_poles, new_res, d, e


# --------------------------------------------------------------------------- #
# the model
# --------------------------------------------------------------------------- #
@dataclass
class RationalModel:
    """Pole-residue multiport macromodel (see module docstring for layout)."""

    poles: np.ndarray
    residues: np.ndarray
    d: np.ndarray
    e: Optional[np.ndarray] = None
    meta: Optional[dict] = None

    def __post_init__(self) -> None:
        self.poles = np.asarray(self.poles, dtype=np.complex128).ravel()
        self.residues = np.asarray(self.residues, dtype=np.complex128)
        self.d = np.asarray(self.d, dtype=np.complex128)
        if self.residues.ndim != 3:
            raise ValueError(
                "residues must have shape (N,P,P), got %s" % (self.residues.shape,)
            )
        n, p, q = self.residues.shape
        if n != self.poles.size:
            raise ValueError(
                "len(poles)=%d != residues.shape[0]=%d" % (self.poles.size, n)
            )
        if self.d.shape != (p, q):
            raise ValueError("d must have shape %s, got %s" % ((p, q), self.d.shape))
        if self.e is not None:
            self.e = np.asarray(self.e, dtype=np.complex128)
            if self.e.shape != (p, q):
                raise ValueError("e must have shape %s, got %s" % ((p, q), self.e.shape))

    # ------------------------------------------------------------------ #
    # basic properties
    # ------------------------------------------------------------------ #
    @property
    def n_poles(self) -> int:
        """Model order N (number of poles)."""
        return int(self.poles.size)

    @property
    def n_ports(self) -> int:
        """Number of ports P."""
        return int(self.residues.shape[1])

    @property
    def state_dimension(self) -> int:
        """Dimension of the real state-space realisation from to_state_space().

        The realisation is modal: every pole contributes one state per port
        (two per port for a complex pair), i.e. n_ports * n_poles.  This is
        minimal whenever the residue matrices are full rank, which is the usual
        case for distributed multiport structures.
        """
        return int(self.n_ports * self.n_poles)

    def copy(self, **overrides) -> "RationalModel":
        """Return a copy, optionally replacing fields (poles/residues/d/e/meta)."""
        kw = dict(
            poles=self.poles.copy(),
            residues=self.residues.copy(),
            d=self.d.copy(),
            e=None if self.e is None else self.e.copy(),
            meta=dict(self.meta) if self.meta else None,
        )
        kw.update(overrides)
        return RationalModel(**kw)

    # ------------------------------------------------------------------ #
    # evaluation
    # ------------------------------------------------------------------ #
    def evaluate_s(self, s) -> np.ndarray:
        """Evaluate the model at complex Laplace points.

        Parameters
        ----------
        s : (F,) complex or scalar

        Returns
        -------
        (F, P, P) complex128, or (P, P) when s is scalar.
        """
        scalar = np.ndim(s) == 0
        s = np.atleast_1d(np.asarray(s, dtype=np.complex128))
        basis = cauchy_matrix(s, self.poles)              # (F, N)
        resp = np.einsum("fn,npq->fpq", basis, self.residues, optimize=True)
        resp = resp + self.d[None, :, :]
        if self.e is not None:
            resp = resp + s[:, None, None] * self.e[None, :, :]
        return resp[0] if scalar else resp

    def evaluate(self, f) -> np.ndarray:
        """Evaluate the model on a frequency grid (Hz).  Returns (F, P, P)."""
        f = np.atleast_1d(np.asarray(f, dtype=np.float64))
        return self.evaluate_s(2j * np.pi * f)

    # convenience alias matching the wording used in the IdEM help text
    frequency_response = evaluate

    def dc_value(self) -> np.ndarray:
        """Model value at s = 0 (DC), shape (P, P)."""
        return self.evaluate_s(0.0 + 0.0j)

    def asymptotic_value(self) -> np.ndarray:
        """Model value as s -> infinity, i.e. the direct term D."""
        return self.d.copy()

    # ------------------------------------------------------------------ #
    # error metrics
    # ------------------------------------------------------------------ #
    def residuals(self, f, target) -> np.ndarray:
        """Complex error model(f) - target(f), shape (F, P, P)."""
        return self.evaluate(f) - np.asarray(target, dtype=np.complex128)

    def rms_error(self, f, target, relative: bool = True) -> float:
        """RMS error over all frequencies and matrix entries.

        With relative=True the error is normalised by the RMS magnitude of the
        target data, matching the IdEM "RMS relative error" accuracy metric.
        """
        err = self.residuals(f, target)
        rms = float(np.sqrt(np.mean(np.abs(err) ** 2)))
        if not relative:
            return rms
        ref = float(np.sqrt(np.mean(np.abs(np.asarray(target, dtype=np.complex128)) ** 2)))
        return rms / ref if ref > 0 else rms

    def max_abs_error(self, f, target) -> float:
        """Largest element-wise absolute error over the frequency grid."""
        return float(np.max(np.abs(self.residuals(f, target))))

    # ------------------------------------------------------------------ #
    # stability / state space
    # ------------------------------------------------------------------ #
    def is_stable(self, tol: float = 1e-9) -> bool:
        """True when every pole lies in the closed left half-plane."""
        return bool(np.all(self.poles.real < tol))

    def unstable_poles(self, tol: float = 1e-9) -> np.ndarray:
        """Indices of poles with Re(p) >= tol."""
        return np.flatnonzero(self.poles.real >= tol)

    def to_state_space(self):
        """Real modal state-space realisation (A, B, C, D).

        Satisfies S(s) = C (sI - A)^-1 B + D.

        A residue R_n is a full P x P matrix, so one pole needs P states.
        With I_P the P x P identity and M = [[a, b], [-b, a]]:

        * real pole p, residue R  -> A = p*I_P, B = I_P, C = R
        * pair a +- jb, residue R -> A = kron(M, I_P), B = [[I_P],[0]],
          C = [2*Re(R), 2*Im(R)]

        These reproduce R/(s-p) and 2*Re(R/(s-p)) respectively.

        Returns
        -------
        A : (n,n) float64
        B : (n,P) float64
        C : (P,n) float64
        D : (P,P) float64
        """
        P = self.n_ports
        I_P = np.eye(P)
        Z_P = np.zeros((P, P))
        blocks_A = []
        blocks_B = []
        blocks_C = []

        used = np.zeros(self.n_poles, dtype=bool)
        is_real = real_pole_mask(self.poles)
        for i in range(self.n_poles):
            if used[i]:
                continue
            if is_real[i]:
                used[i] = True
                blocks_A.append(self.poles[i].real * I_P)
                blocks_B.append(I_P.copy())
                blocks_C.append(self.residues[i].real)
                continue
            target = np.conj(self.poles[i])
            dist = np.abs(self.poles - target)
            dist[used] = np.inf
            dist[i] = np.inf
            j = int(np.argmin(dist))
            if j < self.n_poles and not used[j] and dist[j] <= 1e-6 * max(1.0, abs(self.poles[i])):
                used[i] = used[j] = True
                a = 0.5 * (self.poles[i].real + self.poles[j].real)
                b = abs(self.poles[i].imag) if self.poles[i].imag != 0 else abs(self.poles[j].imag)
                b = max(b, 1e-12 * max(1.0, abs(a)))
                M = np.array([[a, b], [-b, a]])
                # The identity  2*Re(R/(s-p)) = [2Re(R)(s-a) - 2Im(R)b]/Delta
                # holds for the residue carried by the +j*b pole, so pick that
                # one explicitly: using the -j*b partner flips the Im(R) term.
                R = self.residues[i] if self.poles[i].imag > 0 else self.residues[j]
                blocks_A.append(np.kron(M, I_P))
                blocks_B.append(np.vstack([I_P, Z_P]))
                blocks_C.append(np.concatenate([2.0 * R.real, 2.0 * R.imag], axis=1))
            else:
                used[i] = True
                blocks_A.append(self.poles[i].real * I_P)
                blocks_B.append(I_P.copy())
                blocks_C.append(self.residues[i].real)

        n = sum(b.shape[0] for b in blocks_A)
        A = np.zeros((n, n))
        B = np.zeros((n, P))
        C = np.zeros((P, n))
        r0 = 0
        for Ab, Bb, Cb in zip(blocks_A, blocks_B, blocks_C):
            k = Ab.shape[0]
            A[r0:r0 + k, r0:r0 + k] = Ab
            B[r0:r0 + k, :] = Bb
            C[:, r0:r0 + k] = Cb
            r0 += k
        D = self.d.real.copy()
        return A, B, C, D

    # ------------------------------------------------------------------ #
    def summary(self) -> str:
        """One-line human readable description."""
        n_real = int(np.count_nonzero(real_pole_mask(self.poles)))
        n_cplx = self.n_poles - n_real
        return (
            "RationalModel(ports=%d, poles=%d [%d real + %d complex], "
            "states=%d, stable=%s)"
            % (self.n_ports, self.n_poles, n_real, n_cplx,
               self.state_dimension, self.is_stable())
        )

    def __repr__(self) -> str:
        return self.summary()
