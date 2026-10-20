"""Frequency-domain vector fitting (FDVF) with Sanathanan-Koerner iteration.

This module implements the engine CST Studio Suite ships as IdEM
(idemmp_fitting.exe): an iterated Sanathanan-Koerner linearisation of the
Foster canonical form

    S(s) ~= D + sum_n R_n / (s - p_n)          (+ s*E for Y/Z data)

with a SHARED pole set for the whole P x P matrix (IdEM splits=none) and
per-entry residues / direct term.  s = 2j*pi*f with f in Hz and poles in rad/s.

One SK step -- VectorFitter.relocate_poles
------------------------------------------
1. Fix the current poles and build REAL basis functions so that the whole
   least-squares problem is real (a real LAPACK path can be used):

       real pole  p     ->  phi_k(s) = 1 / (s - p)
       pair  a +- jb    ->  phi_1 = (s - a) / ((s - a)^2 + b^2)
                            phi_2 = -b      / ((s - a)^2 + b^2)

   A conjugate pair contributes two basis columns and two poles, so
   n_basis == n_poles.  With real coefficients these reproduce exactly the
   contribution of the conjugate pole pair, with R = (c1 + 1j*c2)/2 on the
   +j*b pole -- the same convention RationalModel.to_state_space() uses.

2. For every matrix entry (i, j) solve the linearised SK condition

       sum_k c_k,ij phi_k(s) + d_ij - S_ij(s) * sum_k ktilde_k phi_k(s) ~= S_ij(s)

   where the constant term of sigma is normalised to 1 (this removes the rank
   deficiency of the classical VF system, INTERFACES.md requirement 3).
   ktilde is SHARED by every entry -- that is what makes the pole set common.
   Real and imaginary parts of every equation are stacked into one
   overdetermined real system; the block of N shared unknowns is eliminated
   with a QR factorisation of the per-entry local block, so the final
   least-squares problem is only N columns wide and stays well conditioned for
   8 ports / 40 poles without ever materialising a huge dense matrix.

3. The zeros of sigma(s) = 1 + sum_k ktilde_k phi_k(s) are the next pole set.
   They are the eigenvalues of A_sigma - B_sigma @ C_sigma with D_sigma = 1,
   assembled in real modal form from the SAME basis order:

       A_sigma blocks : [p]                    /  [[a, b], [-b, a]]
       B_sigma        : [1]                    /  [[1], [0]]
       C_sigma        : the fitted ktilde row

4. Poles with Re(p) > 0 are reflected to -Re(p) when enforce_stability is set
   (IdEM allowUnstablePoles=false), and the returned pole vector is always
   canonicalised with idem_replica.core.rational_model.symmetrize, i.e. it
   contains exact conjugate pairs plus real poles, so
   RationalModel.to_state_space() stays valid.

Frequency normalisation
-----------------------
Internally the Laplace variable is normalised, shat = s / w_scale with
w_scale = 2*pi*exp(mean(log f)) (geometric mean of the band).  Basis columns,
poles and coefficients are therefore O(1), which is what keeps the
least-squares system well conditioned over four decades of frequency.  Poles
and residues are converted back at the interface, so callers only ever see
rad/s and absolute residues.

Initial pole seeding (measured, not guessed)
-------------------------------------------
initial_poles(kind=...) delegates to pole_frequency_grid: 'log' (geometric over
the band), 'lin' (arithmetic over the band), 'quantile' (empirical quantiles of
the measured grid) and the DEFAULT 'auto', which is that same density-matched
quantile rule.  The default is data adaptive on purpose: on a log-uniform grid
the quantiles ARE geometric, while on a grid whose point density varies by
orders of magnitude (the 30-port PDN sweep 5power_30port_wocap: 25 points per
decade below 10 MHz but 300 in the last decade) the poles follow the data
instead of the decades.

A grid heuristic is not enough, though.  Measured on that PDN sweep at N=78,
relative RMS after 4 SK steps: 6.42e-3 with 'lin', 1.28e-2 with the
density-matched seed, 6.87e-2 with 'log' (and worse with log/quantile blends:
2.7e-2 and 3.8e-2).  The winner depends on the data, not on the grid shape, so
fit() MEASURES instead of guessing: unless VFConfig.seed_probe is off it gives
the caller's pole set and the standard seedings _SEED_PROBE_KINDS a couple of SK
steps each on a sub-sampled grid, scores them by relative RMS, and continues
from the winner (VectorFitter.select_initial_poles; AdaptiveFitter calls the
same helper once per fit).  VFConfig.seed_probe=False restores the previous
behaviour exactly, and the probe always includes the caller's own poles, so it
can only improve on what it was handed.

Weighting
---------
Two independent weights multiply every equation:

* the user weight -- the weights argument, shape (F,), (P,P) or (F,P,P), times
  VFConfig.response_weights (IdEM weights.responses);
* the SK weight 1/|sigma(s)| carried over from the previous pole relocation
  (Sanathanan-Koerner).  It is state of the fitter: a relocation call reuses it
  only when it is handed exactly the pole set that closed the previous
  conversion.

VFConfig.weighting selects the frequency weighting of the error norm:

* 'none'      -- unit weight, plain SK;
* 'relative'  -- 1 / max(|S_ij|, weight_rel_threshold * max_f |S_ij|) ** weight_alpha,
  i.e. IdEM's weights.frequency.relative (alpha = 1 gives uniform relative
  error, weight_rel_threshold is IdEM's relativeThreshold);
* 'absolute'  -- no per-entry normalisation: the supplied weights are used
  verbatim as absolute weights (IdEM's explicit <absolute><point/> list).
  Without an explicit weights argument this coincides with 'none'.

Deviations / extensions relative to INTERFACES.md
-------------------------------------------------
* VFConfig carries two extra optional fields with defaults (convergence_tol,
  sk_weighting) -- purely additive; the documented fields keep their names,
  types and defaults.
* compute_residues returns the documented (residues, d) tuple; when
  include_e_term=True the fitted s*E matrix is exposed as VectorFitter.e_
  because the frozen signature has no third slot.
* initial_poles() defaults to kind='auto' (data-density matched seeding)
  instead of the 'log' written in INTERFACES.md section 2.  The explicit
  'log'/'lin' values keep exactly their previous meaning, and 'quantile' is a
  new additive value.
* fit() returns the best model visited by the iteration (lowest relative RMS
  against the data) instead of unconditionally the last one.  The SK/Levy
  iteration is not guaranteed to descend in the true unweighted error - when
  some sigma zeros fall in the right half plane the reflected pole set is no
  longer a set of sigma zeros and the iteration can cycle (observed on a real
  long-delay channel: relative RMS 7.96e-4 after the first step, drifting to
  1.5e-3 and never settling).  For well-posed problems the last iteration is
  already the best, so nothing changes there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from .rational_model import (
    RationalModel,
    conjugate_pairs,
    real_pole_mask,
    symmetrize,
)

__all__ = [
    "VFConfig",
    "VectorFitter",
    "band_centre_omega",
    "canonical_poles",
    "modal_layout",
    "pole_frequency_grid",
    "real_basis_matrix",
    "stabilise_poles",
]

#: Relative floor applied to |sigma| when forming the SK weight 1/|sigma|.
_SK_FLOOR_REL = 1e-8   # legacy alias of VFConfig.sk_weight_floor
_TINY = 1e-300

#: Maximum number of right-hand sides per batched least-squares call.  The
#: entries of one weight group are solved in blocks of this size, which bounds
#: the (2F, K) work block for very large port counts without recomputing the
#: shared factorisation more than necessary.
_LSTSQ_MAX_COLS = 1024
#: Byte budget for one block of the batched relocation projection (each entry
#: contributes a (2F, N) real block, so the block size follows from F and N).
_RELOC_BLOCK_BYTES = 16 * 1024 * 1024
#: Largest condition number of the normal-equations matrix G for which the fast
#: 'gram' path is trusted.  cond(G) = cond(Z)^2, so 1e9 corresponds to cond(Z)
#: ~3e4: the 30-port PDN sweep sits at cond(Z)=1.8e4 and works well, while an
#: 8-port synthetic round trip at cond(Z)=1.7e14 would produce garbage.
_GRAM_COND_MAX = 1e9

#: Above this many bytes for the stacked (2*F*P*P, N) matrix, the exact solve is
#: done with a streaming QR that folds in one block at a time, so peak memory is
#: O(N^2) instead of O(F*P^2*N).  Below it the matrix is materialised, which keeps
#: the historical path bitwise reproducible.  512 MB was chosen so every file in
#: the local corpus keeps the old behaviour (the 30-port case needs 930 MB at
#: N=78 ... ) - raise it if bitwise reproduction of a larger case matters more
#: than memory.
_STACK_MATERIALISE_BYTES = 512 * 1024 * 1024
#: Fraction of the matrix entries whose accumulated Gram is used to decide, up
#: front, whether the normal-equations path is trustworthy.  Measured on the
#: 30-port PDN sweep at N=78, the 1/16 subset reproduces cond(G_full) to within
#: a factor of 1.5 at every order (2.2e8 vs 3.4e8; 3.2e13 vs 3.2e13; 2.4e13 vs
#: 2.5e13; 1.4e15 vs 1.9e15), which is all the decision needs - and it costs 1/16
#: of the pass instead of the whole pass plus a re-run.
_GRAM_PROBE_FRACTION = 16

#: Candidate seedings compared by the automatic seed probe of fit() and
#: select_initial_poles().  Measured on the 30-port PDN sweep at N=78 (relative
#: RMS after 3 SK iterations): 'lin' 6.4e-3, 'auto' (data quantiles) 1.3e-2,
#: 'log' 6.9e-2 - the ranking is data dependent, so it is measured, not guessed.
_SEED_PROBE_KINDS = ("lin", "auto", "log")


def _positive_frequencies(f: np.ndarray) -> np.ndarray:
    """Sorted positive frequencies; raises when the sweep has none."""
    f = np.asarray(f, dtype=np.float64).ravel()
    if f.size < 2:
        raise ValueError("at least two frequency points are required")
    if not np.all(np.isfinite(f)):
        raise ValueError("f must be finite")
    fpos = np.sort(f[f > 0.0])
    if fpos.size == 0:
        raise ValueError("at least one positive frequency is required")
    return fpos


def pole_frequency_grid(f: np.ndarray, n_pairs: int, kind: str = "auto") -> np.ndarray:
    """Angular frequencies (rad/s) for n_pairs conjugate starting poles.

    kind='log'
        geometric spacing over [w_min, w_max] - the classic vector-fitting seed.
    kind='lin'
        arithmetic spacing over [w_min, w_max] - what the reference pipeline
        (scikit-rf VectorFitting, init_pole_spacing='lin') uses.
    kind='auto' (default) / kind='quantile'
        empirical quantiles of the measured frequency grid: every pole then
        carries the same number of data points, so the pole density follows the
        measurement density instead of the decades.  On a log-uniform grid this
        IS 'log' spacing; on a grid whose point density varies by orders of
        magnitude (a PDN sweep with 25 points per decade below 10 MHz and 300
        points in the last decade) the poles follow the data instead of the
        decades.  'auto' and 'quantile' are the same rule; the alias exists so
        that callers can be explicit.

        A density-matched seed is not automatically the best seed - on the
        30-port PDN sweep 'lin' beats it 2x.  That is why fit() does not rely on
        a heuristic: it measures _SEED_PROBE_KINDS on the data (see
        VectorFitter.select_initial_poles).

    The spacing is in angular frequency; the caller applies the damping.
    """
    fpos = _positive_frequencies(f)
    w0 = float(2.0 * np.pi * fpos[0])
    w1 = float(2.0 * np.pi * fpos[-1])
    if w1 <= w0:
        w1 = w0 * 4.0
    n = int(n_pairs)
    if n < 1:
        raise ValueError("n_pairs must be >= 1")
    if kind == "lin":
        return np.linspace(w0, w1, n)
    if kind == "log":
        return np.geomspace(w0, w1, n)
    if kind in ("quantile", "auto"):
        q = (np.arange(n) + 0.5) / float(n)
        return np.maximum(2.0 * np.pi * np.quantile(fpos, q), w0)
    raise ValueError(
        "kind must be 'auto', 'log', 'lin' or 'quantile', got %r" % (kind,)
    )


def band_centre_omega(f: np.ndarray, kind: str = "auto") -> float:
    """Angular frequency used for the single real pole of an odd pole count."""
    fpos = _positive_frequencies(f)
    if kind == "lin":
        return float(2.0 * np.pi * 0.5 * (fpos[0] + fpos[-1]))
    if kind == "log":
        return float(2.0 * np.pi * np.sqrt(fpos[0] * fpos[-1]))
    if kind in ("quantile", "auto"):
        return float(2.0 * np.pi * np.quantile(fpos, 0.5))
    raise ValueError(
        "kind must be 'auto', 'log', 'lin' or 'quantile', got %r" % (kind,)
    )


# --------------------------------------------------------------------------- #
# pole / basis helpers
# --------------------------------------------------------------------------- #
def canonical_poles(poles: np.ndarray) -> np.ndarray:
    """Return poles as exact real values and exact conjugate pairs.

    Delegates to idem_replica.core.rational_model.symmetrize (with a dummy
    residue array) so that every code path produces the pole structure
    RationalModel.to_state_space() requires.
    """
    p = np.asarray(poles, dtype=np.complex128).ravel()
    if p.size == 0:
        raise ValueError("poles must not be empty")
    dummy_res = np.zeros((p.size, 1, 1), dtype=np.complex128)
    dummy_d = np.zeros((1, 1), dtype=np.complex128)
    out, _, _, _ = symmetrize(p, dummy_res, dummy_d)
    return out


def stabilise_poles(poles: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """Reflect poles with Re(p) > 0 onto -Re(p).

    IdEM's outOfBand.allowUnstablePoles default is false; this is that switch.
    Poles sitting exactly on the imaginary axis are nudged to a tiny negative
    real part so the result is strictly stable (Re(p) < 0).
    """
    p = np.asarray(poles, dtype=np.complex128).ravel()
    re = p.real.copy()
    flip = re > 0.0
    if np.any(flip):
        re = np.where(flip, -re, re)
    on_axis = re == 0.0
    if np.any(on_axis):
        re = np.where(on_axis, -eps * np.maximum(1.0, np.abs(p)), re)
    return re + 1j * p.imag


def modal_layout(poles: np.ndarray) -> List[tuple]:
    """Split poles into real blocks and conjugate pairs, in basis order.

    Returns a list of ('real', i) and ('pair', ip, im, a, b) tuples where ip
    indexes the pole with the positive imaginary part.  The order of the list
    defines the column order of real_basis_matrix() and the state order of the
    sigma realisation, so all of them stay consistent.

    Raises ValueError if a complex pole has no conjugate partner (call
    canonical_poles() first).
    """
    p = np.asarray(poles, dtype=np.complex128).ravel()
    real = real_pole_mask(p)
    pairs = conjugate_pairs(p)
    partner = {}
    for i, j in pairs:
        if i != j:
            partner[i] = j
    used = np.zeros(p.size, dtype=bool)
    layout: List[tuple] = []
    for i in range(p.size):
        if used[i]:
            continue
        if real[i]:
            used[i] = True
            layout.append(("real", i))
            continue
        j = partner.get(i)
        if j is None or used[j]:
            raise ValueError(
                "complex pole %d has no conjugate partner; poles must be "
                "canonicalised first (see canonical_poles)" % i
            )
        ip, im = (i, j) if p[i].imag > 0 else (j, i)
        a = 0.5 * (p[i].real + p[j].real)
        b = abs(p[ip].imag)
        if b <= 0.0:
            b = abs(p[im].imag)
        used[i] = used[j] = True
        layout.append(("pair", ip, im, a, b))
    return layout


def real_basis_matrix(s: np.ndarray, poles: np.ndarray):
    """Real basis functions evaluated at the Laplace points s.

    Returns (Phi, layout) with Phi of shape (F, N) complex128, one column per
    pole (two per conjugate pair), in modal_layout() order.  The coefficients
    of these basis functions are REAL.
    """
    s = np.asarray(s, dtype=np.complex128).ravel()
    p = np.asarray(poles, dtype=np.complex128).ravel()
    layout = modal_layout(p)
    phi = np.empty((s.size, p.size), dtype=np.complex128)
    k = 0
    for blk in layout:
        if blk[0] == "real":
            phi[:, k] = 1.0 / (s - p[blk[1]].real)
            k += 1
        else:
            _, _ip, _im, a, b = blk
            den = (s - a) ** 2 + b * b
            phi[:, k] = (s - a) / den
            phi[:, k + 1] = -b / den
            k += 2
    return phi, layout


def _sigma_modal(layout, poles, ktilde):
    """Real modal realisation (A, B, C) of sigma(s) = 1 + sum k phi_k(s)."""
    n = poles.size
    A = np.zeros((n, n), dtype=np.float64)
    B = np.zeros((n, 1), dtype=np.float64)
    C = np.zeros((1, n), dtype=np.float64)
    row = 0
    for blk in layout:
        if blk[0] == "real":
            A[row, row] = poles[blk[1]].real
            B[row, 0] = 1.0
            C[0, row] = ktilde[row]
            row += 1
        else:
            _, _ip, _im, a, b = blk
            A[row, row] = a
            A[row, row + 1] = b
            A[row + 1, row] = -b
            A[row + 1, row + 1] = a
            B[row, 0] = 1.0
            C[0, row] = ktilde[row]
            C[0, row + 1] = ktilde[row + 1]
            row += 2
    return A, B, C


def _frequency_scale(f: np.ndarray) -> float:
    """Geometric-mean angular frequency of the band (internal normalisation)."""
    f = np.asarray(f, dtype=np.float64).ravel()
    pos = f[f > 0.0]
    if pos.size == 0:
        return 1.0
    return float(2.0 * np.pi * np.exp(np.mean(np.log(pos))))


def _pole_deviation(old: np.ndarray, new: np.ndarray) -> float:
    """Largest relative movement between two matched pole sets."""
    old = np.asarray(old, dtype=np.complex128).ravel()
    new = np.asarray(new, dtype=np.complex128).ravel()
    if old.size != new.size or new.size == 0:
        return np.inf
    used = np.zeros(old.size, dtype=bool)
    worst = 0.0
    for p in new:
        scale = np.maximum(np.maximum(np.abs(old), abs(p)), _TINY)
        d = np.abs(old - p) / scale
        d[used] = np.inf
        k = int(np.argmin(d))
        if not np.isfinite(d[k]):
            return np.inf
        used[k] = True
        if d[k] > worst:
            worst = float(d[k])
    return worst


def _constrained_lstsq(A, b, c, g):
    """min ||A x - b||_2 subject to the exact hard constraint c^T x = g.

    Null-space parameterisation: x = x0 + Z t with c^T x0 = g and Z spanning
    the null space of c^T, so the constraint holds to machine precision.
    """
    c = np.asarray(c, dtype=np.float64).ravel()
    denom = float(c @ c)
    if denom <= 0.0:
        raise ValueError("degenerate DC constraint row")
    x0 = c * (float(g) / denom)
    _u, _s, vt = np.linalg.svd(c.reshape(1, -1), full_matrices=True)
    Z = vt[1:].T
    t = np.linalg.lstsq(A @ Z, b - A @ x0, rcond=None)[0]
    return x0 + Z @ t


def _entry_weight_groups(Wflat: np.ndarray):
    """Group matrix entries that share a bitwise-identical weight vector.

    Returns (indices, weights) pairs, where indices are the flat (i*P + j) entry
    positions and weights is the shared (F,) column.  The batched solvers build
    ONE design matrix per group, so the common case - no weights at all, or a
    single per-frequency weight vector - collapses P*P solves into one.
    """
    n_cols = Wflat.shape[1]
    if n_cols <= 1 or np.array_equal(Wflat, Wflat[:, :1]):
        # fast path: one weight vector for the whole matrix (no weights at all,
        # or a single per-frequency vector) - no hashing of P*P columns
        return [(np.arange(n_cols, dtype=np.intp), Wflat[:, 0])]
    order = {}
    for k in range(n_cols):
        order.setdefault(Wflat[:, k].tobytes(), []).append(k)
    return [(np.asarray(idx, dtype=np.intp), Wflat[:, idx[0]])
            for idx in order.values()]


def _lstsq_many(A: np.ndarray, B: np.ndarray, max_cols: int = _LSTSQ_MAX_COLS) -> np.ndarray:
    """Least squares for a block of right-hand sides: min ||A X - B||.

    B is 2-D with one column per right-hand side, so LAPACK factorises A once
    and applies it to the whole block.  That is the same LAPACK path (gelsd) the
    per-entry calls used, which is why the results are unchanged to machine
    precision rather than merely close.
    """
    if B.shape[1] == 0:
        return np.empty((A.shape[1], 0), dtype=np.float64)
    if B.shape[1] <= max_cols:
        return np.linalg.lstsq(A, B, rcond=None)[0]
    X = np.empty((A.shape[1], B.shape[1]), dtype=np.float64)
    for s in range(0, B.shape[1], max_cols):
        sl = slice(s, min(B.shape[1], s + max_cols))
        X[:, sl] = np.linalg.lstsq(A, B[:, sl], rcond=None)[0]
    return X


def _constrained_lstsq_many(A, B, c, g, max_cols: int = _LSTSQ_MAX_COLS) -> np.ndarray:
    """Column-wise hard-constrained least squares.

    Solves min ||A x_k - b_k|| subject to c^T x_k = g_k for every column k, with
    the null-space parameterisation of _constrained_lstsq but sharing the
    factorisation of A (and of c) across all right-hand sides.
    """
    c = np.asarray(c, dtype=np.float64).ravel()
    denom = float(c @ c)
    if denom <= 0.0:
        raise ValueError("degenerate DC constraint row")
    k = B.shape[1]
    g = np.broadcast_to(np.asarray(g, dtype=np.float64).ravel(), (k,))
    X0 = np.outer(c, g / denom)
    _u, _s, vt = np.linalg.svd(c.reshape(1, -1), full_matrices=True)
    Z = vt[1:].T
    T = _lstsq_many(A @ Z, B - A @ X0, max_cols)
    return X0 + Z @ T


# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #
@dataclass
class VFConfig:
    """Configuration of the FDVF / Sanathanan-Koerner engine.

    Attributes
    ----------
    n_iter_initial : int
        SK iterations used before any order growth (IdEM iterations.initial).
    n_iter_final : int
        SK iterations used in finalisation (IdEM iterations.final).
        VectorFitter.fit() uses n_iter_initial + n_iter_final relocations when
        n_iter is not given.
    enforce_stability : bool
        Reflect poles with Re(p) > 0 (IdEM allowUnstablePoles=false).
    weighting : {'none', 'relative', 'absolute'}
        Frequency weighting of the error norm, see the module docstring.
    weight_alpha : float
        Exponent of the relative weighting.
    weight_rel_threshold : float
        Floor of the relative weighting, relative to the largest magnitude of
        the response (IdEM weights.frequency.relative.relativeThreshold).
    response_weights : (P,P) array or None
        Per-entry weights (IdEM weights.responses).
    convergence_tol : float
        Stop iterating when the largest relative pole movement drops below
        this value (extension, default 1e-10).
    sk_weighting : bool
        Apply the 1/|sigma(s)| Sanathanan-Koerner weight (extension, default
        True; turning it off gives a plain Levy iteration).
    sk_weight_floor : float
        Relative floor on |sigma| before inverting it, i.e. the SK weight is
        capped at 1/floor.  Default 1e-8 (uncapped).  This knob exists because
        the 1/|sigma| term genuinely IS unstable at high order, but raising it
        is NOT a win overall.  Both measurements are recorded so the next
        person does not have to redo them.

        FIXED-ORDER chain, N=82, 6 relocations, lin seed, per-step absolute RMS
        (IdEM order-82 reference 7.8984e-04):

            1e-8   1.060392e-03  last/best 1.53  DIVERGING after step 3
            1e-4   9.979906e-04  last/best 1.04  marginal
            1e-3   9.979947e-04  last/best 1.01  stable
            1e-2   9.979967e-04  last/best 1.08  stable
            1e-1   1.015650e-03  last/best 1.09  too loose
            off    9.805100e-04  last/best 1.04  marginal

        On that chain the clamp looks like a clean ~6% win.  It is not.  On the
        MATCHED ADAPTIVE run - the path that matters - with
        AdaptiveConfig(target_tol=5.738395e-03, min_order=4, order_step=8,
        max_order=100) on the 30-port PDN sweep:

            1e-8 (default)      order 82  8.858903e-04  75.3 s
            1e-3                order 80  9.834561e-04  58.7 s
            1e-2                order 80  9.834307e-04  59.4 s
            sk_weighting=False  order 80  9.834227e-04  59.0 s

        Every variant that tames the weighting lands on the SAME ~9.834e-04,
        i.e. 11% WORSE.  The strong 1/|sigma| reweighting, which diverges on a
        long fixed-order chain, is precisely what drives the adding search to a
        better pole set pass by pass.  Hence the uncapped default.  If you are
        tempted to raise it, measure BOTH paths - the fixed-order number alone
        is actively misleading here.
    seed_probe : bool
        fit() measures a few candidate seedings on the data and keeps the best
        one instead of trusting the pole array it was handed (extension,
        default True).  This is what makes the seeding independent of a user
        guessing 'log' vs 'lin'; set it to False for the fastest possible run
        or when the starting poles are chosen deliberately.
    seed_probe_iters : int
        SK iterations run per candidate seed during the probe (default 2).
    seed_probe_subsample : int
        The probe runs on every N-th frequency point (default 16) to keep its
        cost a small fraction of the full fit; 1 uses the whole grid.
        Measured on the 30-port PDN sweep (P=30, F=826, N=78), the probe cost
        for the three candidates is 32 s at 4, 15 s at 8 and 3.4 s at 16, and
        the ranking lin < auto < log is identical in all three cases.
    sigma_solve : {'auto', 'gram', 'stacked'}
        How the reduced sigma system is assembled and solved in
        relocate_poles.  'gram' accumulates the normal equations
        G = sum Z_e^T Z_e, h = sum Z_e^T b_e and never materialises the
        (2*F*P*P, N) stacked matrix - 930 MB at P=30, F=826, N=78, whose SVD
        dominated the relocation.  'stacked' keeps the stacked least-squares
        solve, which is BITWISE reproducible against pre-batching builds.

        'auto' (default) tries 'gram' and falls back to 'stacked' when cond(G)
        exceeds _GRAM_COND_MAX, because normal equations square the condition
        number: the 30-port PDN sweep has cond(Z)=1.8e4 / cond(G)=3.4e8 and is
        solved accurately (residual equal to the stacked solve to 1.2e-16,
        coefficients to 2.2e-11, one relocation moves the model error by
        ~5e-10), while an 8-port synthetic round trip at cond(Z)=1.7e14 would
        give a 100% wrong coefficient vector - it correctly falls back.

        The SK iteration amplifies even the tiny 'gram' change, so the final
        relative RMS of a fitted model can move in the 1e-5 range (measured:
        9.2e-05 on the 30-port order-78 fit).  Use 'stacked' when published
        numbers must be reproduced bit for bit.
    """

    n_iter_initial: int = 3
    n_iter_final: int = 1
    enforce_stability: bool = True
    weighting: str = "none"
    weight_alpha: float = 1.0
    weight_rel_threshold: float = 1e-6
    response_weights: Optional[np.ndarray] = None
    convergence_tol: float = 1e-10
    sk_weighting: bool = True
    sk_weight_floor: float = 1e-8
    sk_weight_persist: bool = False
    init_pole_damping: float = 0.05
    # ^ damping of the STARTING poles: alpha = -damping * omega.  Measured on
    #   the 30-port PDN sweep at the matched target (IdEM reference 8.11577e-04
    #   at order 82), adaptive search, absolute RMS:
    #       0.01 (old default)   order 83   8.796902e-04   29.2 s
    #       0.05                 order 82   8.233855e-04   30.4 s   <- best
    #       0.10                 order 83   9.625227e-04   30.5 s
    #       0.34                 order 82   8.323637e-04   30.3 s
    #   i.e. 6.4% better for the same cost, cutting the matched-order gap to
    #   IdEM from 8.4% to 1.5%.  The response is not monotone, so this was
    #   verified for regressions rather than assumed: the local 2-port corpus is
    #   unchanged to 4 significant figures and all four files stay <= 1e-3, and
    #   at fixed orders 4/10/18/42 the result still beats IdEM (by 27.7 / 19.5 /
    #   8.1 / 16.3%).  IdEM@BT@s own initial pair is far more damped than ours was
    #   (0.339 at order 4 against 0.101), which is what pointed here.
    seed_probe: bool = True
    seed_probe_iters: int = 2
    seed_probe_subsample: int = 16
    sigma_solve: str = "auto"

    def __post_init__(self) -> None:
        if self.weighting not in ("none", "relative", "absolute"):
            raise ValueError(
                "weighting must be 'none', 'relative' or 'absolute', got %r"
                % (self.weighting,)
            )
        if self.weight_alpha < 0.0:
            raise ValueError("weight_alpha must be >= 0")
        if self.weight_rel_threshold <= 0.0:
            raise ValueError("weight_rel_threshold must be > 0")
        if self.response_weights is not None:
            rw = np.asarray(self.response_weights, dtype=np.float64)
            if rw.ndim != 2 or rw.shape[0] != rw.shape[1] or rw.shape[0] == 0:
                raise ValueError("response_weights must be a square (P,P) matrix")
            self.response_weights = rw
        if int(self.seed_probe_iters) < 1:
            raise ValueError("seed_probe_iters must be >= 1")
        if int(self.seed_probe_subsample) < 1:
            raise ValueError("seed_probe_subsample must be >= 1")
        if self.sigma_solve not in ("auto", "gram", "stacked"):
            raise ValueError(
                "sigma_solve must be 'auto', 'gram' or 'stacked', got %r"
                % (self.sigma_solve,)
            )


# --------------------------------------------------------------------------- #
# the fitter
# --------------------------------------------------------------------------- #
class VectorFitter:
    """Sanathanan-Koerner / FDVF pole relocation and residue solve."""

    def __init__(self, config: Optional[VFConfig] = None) -> None:
        self.config: VFConfig = VFConfig() if config is None else config
        #: fitted s*E matrix of the last include_e_term=True residue solve
        #: (the frozen return type is only (residues, d)).
        self.e_: Optional[np.ndarray] = None
        #: diagnostics of the most recent fit()
        self.n_iterations_: int = 0
        self.converged_: bool = False
        self.pole_history_: List[float] = []
        self.rms_history_: List[float] = []
        self.best_iteration_: int = -1
        #: seeding diagnostics of the most recent fit() / select_initial_poles()
        self.seed_kind_: Optional[str] = None
        self.seed_probe_report_: List[dict] = []
        #: sticky performance hint: cond(G) was too large for the fast path
        self._sigma_stack_only_: bool = False
        self._sk_weight: Optional[np.ndarray] = None
        self._sk_poles: Optional[np.ndarray] = None
        self._sk_f: Optional[np.ndarray] = None

    # ------------------------------------------------------------------ #
    # input handling
    # ------------------------------------------------------------------ #
    @staticmethod
    def _prepare(f, s_data):
        f = np.asarray(f, dtype=np.float64).ravel()
        S = np.asarray(s_data, dtype=np.complex128)
        if S.ndim != 3 or S.shape[1] != S.shape[2]:
            raise ValueError("s_data must have shape (F,P,P), got %s" % (S.shape,))
        if S.shape[0] != f.size:
            raise ValueError(
                "len(f)=%d does not match s_data.shape[0]=%d" % (f.size, S.shape[0])
            )
        if f.size < 2:
            raise ValueError("at least two frequency points are required")
        if not np.all(np.isfinite(f)):
            raise ValueError("f must be finite")
        if not np.all(np.isfinite(S)):
            raise ValueError("s_data must be finite")
        if f.size > 1 and np.any(np.diff(f) < 0.0):
            order = np.argsort(f)
            f = f[order]
            S = S[order]
        return f, S

    def _entry_weights(self, f, S, weights) -> np.ndarray:
        """(F,P,P) real per-equation weights (user weights only, no SK part)."""
        cfg = self.config
        F, P, _ = S.shape
        W = np.ones((F, P, P), dtype=np.float64)
        if weights is not None:
            w = np.asarray(weights, dtype=np.float64)
            if w.shape == (F,):
                W = W * w[:, None, None]
            elif w.shape == (P, P):
                W = W * w[None, :, :]
            elif w.shape == (F, P, P):
                W = W * w
            else:
                raise ValueError(
                    "weights must have shape (F,), (P,P) or (F,P,P); got %s"
                    % (w.shape,)
                )
        if cfg.response_weights is not None:
            rw = np.asarray(cfg.response_weights, dtype=np.float64)
            if rw.shape != (P, P):
                raise ValueError(
                    "response_weights must have shape (%d,%d), got %s"
                    % (P, P, rw.shape)
                )
            W = W * rw[None, :, :]
        if np.any(W < 0.0):
            raise ValueError("weights must be non-negative")
        if cfg.weighting == "relative":
            mag = np.abs(S)
            scale = np.maximum(mag.max(axis=0, keepdims=True), _TINY)
            floor = np.maximum(cfg.weight_rel_threshold * scale, _TINY)
            W = W / np.power(np.maximum(mag, floor), cfg.weight_alpha)
        # 'absolute' / 'none': supplied weights are used verbatim
        return W

    def _sk_weights(self, f, poles) -> np.ndarray:
        """Sanathanan-Koerner weight 1/|sigma| of the previous relocation."""
        if not self.config.sk_weighting:
            return np.ones(f.size, dtype=np.float64)
        cfg = self.config
        if (
            self._sk_weight is not None
            and self._sk_f is not None
            and self._sk_f.size == f.size
            and np.array_equal(self._sk_f, f)
            and self._sk_weight.size == f.size
        ):
            # The 1/|sigma| weight is a function of FREQUENCY, not of the pole
            # count, so it could in principle be carried across an order change.
            # By default it is reused only when the pole set is bit-identical,
            # which means it never survives an adding pass: the order grows, the
            # size check fails, and the weight resets to one.
            #
            # sk_weight_persist=True carries it across the growth instead.
            # MEASURED, and it is WORSE: on the 30-port PDN sweep with the
            # matched target, persisting gives 9.692410e-04 against 8.796902e-04
            # for resetting - a 10.2% regression.  Resetting the weight when the
            # order changes is the correct behaviour; this knob is kept only so
            # the experiment does not have to be repeated.
            if cfg.sk_weight_persist:
                return self._sk_weight
            if self._sk_poles is not None and self._sk_poles.size == poles.size:
                scale = np.maximum(np.abs(self._sk_poles), _TINY)
                drift = np.max(np.abs(self._sk_poles - poles) / scale)
                if drift <= 1e-14:
                    return self._sk_weight
        return np.ones(f.size, dtype=np.float64)

    def _reset_sk(self) -> None:
        self._sk_weight = None
        self._sk_poles = None
        self._sk_f = None

    # ------------------------------------------------------------------ #
    # SK pole relocation
    # ------------------------------------------------------------------ #
    def relocate_poles(self, f, s_data, poles, weights=None) -> np.ndarray:
        """One Sanathanan-Koerner step. Returns the NEW poles (same length)."""
        cfg = self.config
        f, S = self._prepare(f, s_data)
        F, P, _ = S.shape
        w_scale = _frequency_scale(f)

        poles = canonical_poles(np.asarray(poles, dtype=np.complex128))
        N = poles.size
        phat = poles / w_scale
        shat = (2j * np.pi * f) / w_scale
        phi, layout = real_basis_matrix(shat, phat)

        W = self._entry_weights(f, S, weights)
        W = W * self._sk_weights(f, poles)[:, None, None]

        rows = 2 * F
        Sflat = S.reshape(F, P * P)
        Wflat = W.reshape(F, P * P)

        # Two ways to solve the reduced system min ||Z k - b||, where Z is the
        # vertical stack of the per-entry blocks:
        #
        #   'gram'    accumulate G = sum Z_e^T Z_e (N x N) and h = sum Z_e^T b_e
        #             and solve that.  The (2*F*P*P, N) stacked matrix - 930 MB
        #             at P=30, F=826, N=78 - is never materialised and its 4.2 s
        #             SVD is replaced by an N x N solve.  Normal equations square
        #             the condition number, so this is only used when cond(G) is
        #             small enough for the answer to be trustworthy.
        #   'stacked' the old stacked least-squares solve.  Bitwise reproducible
        #             against pre-batching builds and safe for any conditioning.
        #
        # 'auto' (default) tries 'gram' and falls back to 'stacked' when cond(G)
        # says the squared conditioning would destroy the solution.  Measured on
        # the 30-port PDN sweep (cond(Z)=1.8e4, cond(G)=3.4e8): residual equal to
        # 1.2e-16 relative, coefficients equal to 2.2e-11, one relocation moves
        # the model error by ~5e-10.  Measured on an 8-port synthetic round trip
        # (cond(Z)=1.7e14, cond(G)=7.0e17): the normal-equations solution is
        # garbage (100% coefficient error, 9% worse residual) - hence the guard.
        #: which branch the sigma solve actually took, for diagnostics and tests:
        #: "gram" | "stacked-materialised" | "stacked-streamed"
        self.sigma_mode_ = None
        mode = cfg.sigma_solve
        if mode == "auto":
            # once a fit has shown the normal equations are unsafe here, stay on
            # the exact path for the rest of that fit (a performance hint only)
            mode = "stacked" if self._sigma_stack_only_ else "gram"
        ktilde = None
        if mode == "gram":
            self.sigma_mode_ = "gram"
            gram = np.zeros((N, N), dtype=np.float64)
            rhs = np.zeros(N, dtype=np.float64)
            probe_until = max(1, int(P * P) // _GRAM_PROBE_FRACTION)
            seen = 0
            # The conditioning is decided from a cheap 1/16 subset of the
            # entries, so a bad decision costs 1/16 of a pass instead of a whole
            # pass plus a re-run (which is what made the first version of this
            # guard slower than never trying: cond(G) jumps from 3.4e8 at the
            # first SK step to 3e13 by the second on the 30-port sweep).
            blocks = self._projection_blocks(Sflat, Wflat, phi, rows, N, P)
            for sel, Zblock, bblock in blocks:
                gram += Zblock.T @ Zblock
                rhs += Zblock.T @ bblock
                seen += int(sel.size)
                if seen >= probe_until:
                    sv = np.linalg.svd(gram, compute_uv=False)
                    if sv[-1] <= 0.0 or sv[0] / sv[-1] > _GRAM_COND_MAX:
                        mode = "stacked"
                        self._sigma_stack_only_ = True
                    break
            if mode == "gram":
                for _sel, Zblock, bblock in blocks:      # generator kept its place
                    gram += Zblock.T @ Zblock
                    rhs += Zblock.T @ bblock
                sv = np.linalg.svd(gram, compute_uv=False)
                if cfg.sigma_solve == "auto" and (
                    sv[-1] <= 0.0 or sv[0] / sv[-1] > _GRAM_COND_MAX
                ):
                    mode = "stacked"                     # probe underestimated
                    self._sigma_stack_only_ = True
                else:
                    ktilde = np.linalg.lstsq(gram, rhs, rcond=None)[0]
        if mode == "stacked":
            n_unknown_rows = rows * P * P
            if n_unknown_rows * N * 8 <= _STACK_MATERIALISE_BYTES:
                # Small enough to materialise: keep the historical path, which
                # is bitwise reproducible against pre-batching builds.
                Z_stack = np.empty((n_unknown_rows, N), dtype=np.float64)
                b_stack = np.empty(n_unknown_rows, dtype=np.float64)
                row_offsets = np.arange(rows)
                for sel, Zblock, bblock in self._projection_blocks(
                    Sflat, Wflat, phi, rows, N, P
                ):
                    rsel = (sel[:, None] * rows + row_offsets[None, :]).ravel()
                    Z_stack[rsel] = Zblock
                    b_stack[rsel] = bblock
                ktilde = np.linalg.lstsq(Z_stack, b_stack, rcond=None)[0]
                self.sigma_mode_ = "stacked-materialised"
            else:
                # Too big to materialise - 2*F*P^2*N*8 bytes is 9.6 GB at
                # P=166, F=542, N=40, which is what made the 163/166-port files
                # look infeasible.  Accumulate the same least-squares problem
                # with a STREAMING QR instead: keep an (N, N) triangular factor
                # R and a transformed right-hand side z, and fold each block in
                # with  [R; Z_b] = Q_b R_new ,  z <- (Q_b^T [z; b_b])[:N].
                # The final solve R k = z is the exact least-squares solution of
                # the full stacked system, with the same conditioning as the
                # materialised path (cond(Z), not cond(Z)^2 as in the Gram path),
                # but only O(N^2) memory instead of O(F*P^2*N).
                R_fac = np.zeros((N, N), dtype=np.float64)
                z_rhs = np.zeros(N, dtype=np.float64)
                for _sel, Zblock, bblock in self._projection_blocks(
                    Sflat, Wflat, phi, rows, N, P
                ):
                    M = np.vstack([R_fac, Zblock])
                    v = np.concatenate([z_rhs, bblock])
                    Q, R_new = np.linalg.qr(M, mode="reduced")
                    R_fac = R_new
                    z_rhs = Q.T @ v
                ktilde = np.linalg.lstsq(R_fac, z_rhs, rcond=None)[0]
                self.sigma_mode_ = "stacked-streamed"
        if not np.all(np.isfinite(ktilde)):
            return poles  # degenerate system: keep the current pole set

        A_s, B_s, C_s = _sigma_modal(layout, phat, ktilde)
        new_hat = np.linalg.eigvals(A_s - B_s @ C_s)
        if cfg.enforce_stability:
            new_hat = stabilise_poles(new_hat)
        new_poles = canonical_poles(new_hat) * w_scale

        if cfg.sk_weighting:
            sigma = np.abs(1.0 + phi @ ktilde)
            floor = max(cfg.sk_weight_floor * float(sigma.max()), _TINY)
            self._sk_weight = 1.0 / np.maximum(sigma, floor)
        else:
            self._sk_weight = np.ones(F, dtype=np.float64)
        self._sk_poles = new_poles.copy()
        self._sk_f = f.copy()
        return new_poles

    @staticmethod
    def _projection_blocks(Sflat, Wflat, phi, rows, N, P):
        """Yield (entries, Zblock, bblock) for every block of matrix entries.

        One QR per distinct weight vector (the local design matrix depends only
        on the poles, the grid and that weight vector), then the sigma block of
        each entry is projected with it.  The b projection stays per entry: it is
        cheap (one gemv pair each) and keeping it unbatched is what makes
        b_stack bit-for-bit identical to the pre-batching loop.
        """
        block = max(1, int(_RELOC_BLOCK_BYTES // max(1, rows * N * 8)))
        n_freq = phi.shape[0]
        for idx, w in _entry_weight_groups(Wflat):
            loc = np.empty((n_freq, N + 1), dtype=np.complex128)
            loc[:, :N] = phi * w[:, None]
            loc[:, N] = w
            A = np.vstack([loc.real, loc.imag])
            Q, _R = np.linalg.qr(A, mode="reduced")
            for start in range(0, idx.size, block):
                sel = idx[start:start + block]
                C = sel.size
                Sw = Sflat[:, sel] * w[:, None]                  # (F,C)
                Zc = -Sw[:, :, None] * phi[:, None, :]           # (F,C,N)
                Zt = Zc.transpose(1, 0, 2)                       # (C,F,N)
                Zmat = np.concatenate([Zt.real, Zt.imag], axis=1)  # (C,2F,N)
                Z2 = Zmat.transpose(1, 0, 2).reshape(rows, C * N)  # (2F,C*N)
                Z2 -= Q @ (Q.T @ Z2)                             # project per entry column
                Zblock = Z2.reshape(rows, C, N).transpose(1, 0, 2)
                Zblock = Zblock.reshape(rows * C, N)             # entry-major rows
                bmat = np.vstack([Sw.real, Sw.imag])             # (2F,C)
                bblock = np.empty((C, rows), dtype=np.float64)
                for c in range(C):
                    bc = bmat[:, c]
                    bblock[c] = bc - Q @ (Q.T @ bc)
                yield sel, Zblock, bblock.reshape(rows * C)

    # ------------------------------------------------------------------ #
    # automatic seed selection (measured, not guessed)
    # ------------------------------------------------------------------ #
    def _probe_grid(self, f, subsample=None, n_poles=None):
        """Indices of the (sub-sampled) frequency grid used to score seeds.

        The probe only has to rank the candidates, so a thin grid is enough -
        but not thinner than n_poles/2 points, otherwise the per-entry probe
        system (2*F rows against N+1 local unknowns) stops being meaningful.
        Cost scales with the number of probe points, which is what keeps the
        probe at a few percent of a full fit on large problems.
        """
        step = int(self.config.seed_probe_subsample if subsample is None else subsample)
        step = max(1, step)
        target = max(8, int(n_poles) // 2) if n_poles else 8
        if f.size // step < target:
            step = max(1, f.size // target)
        idx = np.arange(0, f.size, step)
        if idx.size < 8:
            idx = np.arange(f.size)
        return idx

    def _probe_seed(self, poles, fs, Ss, n_iter):
        """Relative RMS reached by one candidate seed after n_iter SK steps.

        The probe runs on a private VectorFitter, so the SK state of self is
        untouched.  (Sharing it would be wrong anyway: the SK weight is a
        per-frequency vector defined on the probe grid, not on the full grid.)
        """
        probe = VectorFitter(self.config)
        p = canonical_poles(np.asarray(poles, dtype=np.complex128))
        for _ in range(max(1, int(n_iter))):
            p = probe.relocate_poles(fs, Ss, p)
        res, d = probe.compute_residues(fs, Ss, p)
        err = float(RationalModel(poles=p, residues=res, d=d).rms_error(fs, Ss))
        return err, p

    def _probe_candidates(self, candidates, fs, Ss, n_iter):
        """Score candidate seeds; return the winning kind's ORIGINAL seed.

        The probe grid is deliberately thin, so the pole set it warms up is a
        coarse object: using it to start the full fit measurably hurts (measured
        on the 30-port PDN sweep, relative RMS 7.26e-3 instead of 6.42e-3 for
        the same 'lin' kind).  The probe therefore only decides WHICH kind to
        use, and the full fit always starts from that kind's own seed.  Both
        pole sets are kept in the report for inspection.
        """
        report = []
        best_err = np.inf
        best_raw = None
        best_kind = None
        for kind, poles in candidates:
            err, warmed = self._probe_seed(poles, fs, Ss, n_iter)
            if not np.isfinite(err):
                err = np.inf          # a degenerate candidate never wins
            report.append(
                {"kind": kind, "error": err, "seed": np.asarray(poles).copy(),
                 "poles": warmed}
            )
            if err < best_err:
                best_err, best_raw, best_kind = err, poles, kind
        if best_raw is None:          # every candidate degenerate: keep the first
            best_kind, best_raw = candidates[0][0], candidates[0][1]
        report.sort(key=lambda row: row["error"])
        self.seed_kind_ = best_kind
        self.seed_probe_report_ = report
        return np.asarray(best_raw, dtype=np.complex128).copy(), best_kind, report

    def select_initial_poles(
        self,
        f,
        s_data,
        n_poles: int,
        *,
        damping: Optional[float] = None,
        kinds=None,
        n_iter_probe: Optional[int] = None,
        subsample: Optional[int] = None,
    ):
        """Pick the starting poles by MEASURING candidate seedings on the data.

        Each candidate kind from pole_frequency_grid ('lin', 'auto', 'log' by
        default) is given seed_probe_iters Sanathanan-Koerner steps on a
        sub-sampled copy of the sweep and scored by relative RMS; the winner is
        returned.  A heuristic on the frequency grid is not enough: measured on
        the 30-port PDN sweep 5power_30port_wocap at N=78 the same engine
        reaches 6.4e-3 with 'lin', 1.3e-2 with data-density 'auto' and 6.9e-2
        with 'log', so the ranking has to be measured.

        Parameters
        ----------
        f, s_data : the sweep (same shapes as everywhere else)
        n_poles   : number of poles (odd -> one real pole appended)
        damping   : initial pole damping; None uses VFConfig.init_pole_damping
                    (passing it through rather than hard-coding a default here
                    is what makes that config field actually take effect on the
                    default seed-probe path)
        kinds     : iterable of kinds to try, default _SEED_PROBE_KINDS
        n_iter_probe, subsample : override VFConfig.seed_probe_iters /
                    seed_probe_subsample for this call

        Returns
        -------
        (poles, report): poles is the winning kind's own seed (not the pole set
        the thin probe grid warmed up - see _probe_candidates); report is a list
        of {'kind', 'error', 'seed', 'poles'} dicts sorted by error, best first.
        """
        f, S = self._prepare(f, s_data)
        n = int(n_poles)
        kinds = tuple(_SEED_PROBE_KINDS if kinds is None else kinds)
        iters = int(self.config.seed_probe_iters if n_iter_probe is None else n_iter_probe)
        idx = self._probe_grid(f, subsample, n_poles=n)
        fs, Ss = f[idx], S[idx]
        cands = [(k, self.initial_poles(f, n, damping=damping, kind=k)) for k in kinds]
        poles, _kind, report = self._probe_candidates(cands, fs, Ss, iters)
        return poles, report

    def _seed_for_fit(self, f, S, poles):
        """Best of the caller's poles and the standard seedings."""
        if not self.config.seed_probe:
            self.seed_kind_ = "given"
            self.seed_probe_report_ = []
            return poles
        cands = [("given", poles)]
        for kind in _SEED_PROBE_KINDS:
            cand = self.initial_poles(f, poles.size, kind=kind)
            far = all(
                float(np.max(np.abs(cand - c[1]) / np.maximum(np.abs(c[1]), _TINY))) > 1e-12
                for c in cands
            )
            if far:
                cands.append((kind, cand))
        idx = self._probe_grid(f, n_poles=poles.size)
        best, _kind, _report = self._probe_candidates(
            cands, f[idx], S[idx], self.config.seed_probe_iters
        )
        return best

    # ------------------------------------------------------------------ #
    # residue solve
    # ------------------------------------------------------------------ #
    def compute_residues(
        self,
        f,
        s_data,
        poles,
        weights=None,
        enforce_dc: bool = False,
        dc_value=None,
        include_e_term: bool = False,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Fixed poles -> (residues (N,P,P), d (P,P)).

        Solves S_ij(s) ~= d_ij + sum_k c_k,ij phi_k(s) (+ s*e_ij) in the real
        basis for every entry.  With enforce_dc the exact row
        d_ij + sum_k c_k,ij phi_k(0) = dc_value[i,j] is added as a hard
        constraint (null-space elimination, satisfied to machine precision).
        When dc_value is None the DC value of the unconstrained solution is
        pinned instead.

        include_e_term adds the s*E term of Y/Z data; the fitted matrix is
        exposed as self.e_ because the frozen signature returns only
        (residues, d).
        """
        cfg = self.config
        f, S = self._prepare(f, s_data)
        F, P, _ = S.shape
        w_scale = _frequency_scale(f)

        poles = canonical_poles(np.asarray(poles, dtype=np.complex128))
        if cfg.enforce_stability:
            poles = canonical_poles(stabilise_poles(poles))
        N = poles.size
        phat = poles / w_scale
        shat = (2j * np.pi * f) / w_scale
        phi, layout = real_basis_matrix(shat, phat)
        W = self._entry_weights(f, S, weights)

        if enforce_dc and dc_value is not None:
            dc_arr = np.asarray(dc_value, dtype=np.complex128)
            if dc_arr.ndim == 0:
                dc_arr = np.full((P, P), dc_arr)
            if dc_arr.shape != (P, P):
                raise ValueError(
                    "dc_value must be a (P,P) matrix or a scalar, got %s"
                    % (dc_arr.shape,)
                )
        else:
            dc_arr = None

        # DC row in coefficient space: phi_k(0) (real for a real system), the
        # constant 1, and 0 for the s*E column.
        phi0 = real_basis_matrix(np.zeros(1, dtype=np.complex128), phat)[0][0].real

        coeffs_flat = np.zeros((N, P * P), dtype=np.float64)
        d_flat = np.zeros(P * P, dtype=np.float64)
        e_flat = None
        if include_e_term:
            e_flat = np.zeros(P * P, dtype=np.float64)

        crow = None
        if enforce_dc:
            crow = np.concatenate([phi0, [1.0], [0.0] if include_e_term else []])
        dc_flat = None
        if dc_arr is not None:
            dc_flat = np.asarray(dc_arr, dtype=np.complex128).reshape(P * P)

        # Entries with the same weight vector have the SAME real design matrix
        # (it depends only on the poles, the grid and the weights), so they share
        # one least-squares factorisation and are solved as one block of
        # right-hand sides.  Without weights this is a single solve for all P*P
        # entries instead of P*P solves - the same LAPACK path, same numbers.
        Sflat = S.reshape(F, P * P)
        Wflat = W.reshape(F, P * P)
        for idx, w in _entry_weight_groups(Wflat):
            Sw = Sflat[:, idx] * w[:, None]                     # (F,K)
            cols = [phi * w[:, None], w[:, None]]
            if include_e_term:
                cols.append(shat[:, None] * w[:, None])
            Ablock = np.hstack(cols)
            A = np.vstack([Ablock.real, Ablock.imag])           # (2F,M)
            B = np.vstack([Sw.real, Sw.imag])                   # (2F,K)
            if enforce_dc:
                if dc_flat is None:
                    X = _lstsq_many(A, B)
                    g = crow @ X                                # (K,)
                else:
                    g = dc_flat[idx].real
                X = _constrained_lstsq_many(A, B, crow, g)
            else:
                X = _lstsq_many(A, B)
            coeffs_flat[:, idx] = X[:N]
            d_flat[idx] = X[N]
            if include_e_term:
                e_flat[idx] = X[N + 1]

        coeffs = coeffs_flat.reshape(N, P, P)
        d_out = d_flat.reshape(P, P)
        e_out = None if e_flat is None else e_flat.reshape(P, P)

        # real basis coefficients -> complex residues at the poles
        residues = np.zeros((N, P, P), dtype=np.complex128)
        k = 0
        for blk in layout:
            if blk[0] == "real":
                residues[blk[1]] = w_scale * coeffs[k]
                k += 1
            else:
                _kind, ip, im, _a, _b = blk
                R = 0.5 * w_scale * (coeffs[k] + 1j * coeffs[k + 1])
                residues[ip] = R
                residues[im] = np.conj(R)
                k += 2

        d_c = d_out.astype(np.complex128)
        e_c = None if e_out is None else e_out / w_scale
        self.e_ = None if e_c is None else e_c.copy()
        poles, residues, d_c, e_c = symmetrize(poles, residues, d_c, e_c)
        return residues, d_c

    # ------------------------------------------------------------------ #
    # full fit
    # ------------------------------------------------------------------ #
    def fit(self, f, s_data, poles, n_iter: Optional[int] = None) -> RationalModel:
        """Iterate relocate+residue until the poles stop moving; return model.

        Unless VFConfig.seed_probe is off, the starting poles are first chosen
        by measurement: the caller's pole array and the standard seedings
        (_SEED_PROBE_KINDS) are each given seed_probe_iters SK steps on a
        sub-sampled grid, scored by relative RMS, and the best one is used.  A
        user therefore does not have to know whether 'log' or 'lin' suits the
        data - on the 30-port PDN sweep that choice is worth a factor of 10.
        Diagnostics: seed_kind_ and seed_probe_report_.

        The iteration is followed by a residue solve at every visited pole set
        and the best model (lowest relative RMS error against the data) is
        returned.  This matters on hard data: the SK/Levy iteration is not
        guaranteed to descend in the true unweighted error, and when some
        sigma zeros fall in the right half plane the reflected (pole-flipped)
        set is no longer a set of sigma zeros, so the iteration can cycle
        instead of converging.  Returning the best model makes the result
        monotone in the acceptance metric without changing anything for
        well-posed problems, where the last iteration is already the best.

        Diagnostics: n_iterations_, converged_, pole_history_ (relative pole
        movement per iteration), rms_history_ (relative RMS per iteration),
        best_iteration_.
        """
        cfg = self.config
        f, S = self._prepare(f, s_data)
        poles = canonical_poles(np.asarray(poles, dtype=np.complex128))
        if n_iter is None:
            n_iter = max(1, int(cfg.n_iter_initial) + int(cfg.n_iter_final))
        n_iter = int(n_iter)
        if n_iter < 1:
            raise ValueError("n_iter must be >= 1")

        self._reset_sk()
        poles = self._seed_for_fit(f, S, poles)
        history: List[float] = []
        rms_history: List[float] = []
        converged = False
        used = 0
        best_poles = poles
        best_res = None
        best_d = None
        best_err = np.inf
        best_iter = -1
        for it in range(n_iter):
            new_poles = self.relocate_poles(f, S, poles)
            dev = _pole_deviation(poles, new_poles)
            history.append(float(dev))
            poles = new_poles
            used = it + 1
            res_it, d_it = self.compute_residues(f, S, poles)
            err_it = float(RationalModel(poles=poles, residues=res_it, d=d_it).rms_error(f, S))
            rms_history.append(err_it)
            if err_it < best_err:
                best_err = err_it
                best_poles = poles.copy()
                best_res = res_it
                best_d = d_it
                best_iter = it
            if dev < cfg.convergence_tol:
                converged = True
                break

        if best_res is None:  # cannot happen: the loop always runs at least once
            best_res, best_d = self.compute_residues(f, S, best_poles)
        model = RationalModel(poles=best_poles, residues=best_res, d=best_d)
        model.meta = {
            "algorithm": "FDVF/SK (shared poles, splits=none)",
            "n_sk_iterations": used,
            "converged": bool(converged),
            "pole_deviation_history": history,
            "rms_history": rms_history,
            "best_iteration": best_iter,
            "rms_error": float(model.rms_error(f, S)),
            "weighting": cfg.weighting,
            "enforce_stability": bool(cfg.enforce_stability),
            "seed_kind": self.seed_kind_,
            "seed_probe": [
                {"kind": row["kind"], "error": row["error"]}
                for row in self.seed_probe_report_
            ],
        }
        self.n_iterations_ = used
        self.converged_ = bool(converged)
        self.pole_history_ = history
        self.rms_history_ = rms_history
        self.best_iteration_ = best_iter
        return model

    # ------------------------------------------------------------------ #
    # initial poles
    # ------------------------------------------------------------------ #
    def initial_poles(
        self, f, n_poles: int, *, damping: Optional[float] = None,
        kind: str = "auto"
    ) -> np.ndarray:
        """Deterministic starting poles on the jw axis, damped.

        n_poles // 2 conjugate pairs are placed over the band with
        alpha = -damping * omega; when n_poles is odd one real pole is appended
        near the centre of the band.  damping == 0 falls back to
        alpha = -1e-3 * omega so that no pole is exactly imaginary.  The result
        is a set of exact conjugate pairs.

        kind selects the pole frequencies (see pole_frequency_grid):

          'auto'     (default) data-density matched seeding: geometric blend of
                     'log' and the empirical quantiles of the measured grid.
                     The user never has to guess log vs lin.
          'log'      geometric spacing over the band (the classic VF seed).
          'lin'      arithmetic spacing over the band (the reference pipeline's
                     init_pole_spacing='lin').
          'quantile' pure empirical quantiles of the measured grid.

        The band runs from the smallest POSITIVE frequency to the largest, so a
        Touchstone sweep that starts at DC (f = 0) is handled natively.
        """
        f = np.asarray(f, dtype=np.float64).ravel()
        if f.size < 2:
            raise ValueError("at least two frequency points are required")
        if damping is None:
            damping = float(self.config.init_pole_damping)
        n = int(n_poles)
        if n < 1:
            raise ValueError("n_poles must be >= 1")
        n_pairs = n // 2
        if n_pairs > 0:
            ws = pole_frequency_grid(f, n_pairs, kind=kind)
        else:
            _positive_frequencies(f)  # same validation as the pair path
            ws = np.empty(0, dtype=np.float64)
        alphas = -float(damping) * ws if damping != 0.0 else -1e-3 * ws

        poles = np.empty(2 * n_pairs, dtype=np.complex128)
        poles[0::2] = alphas + 1j * ws
        poles[1::2] = alphas - 1j * ws
        if n % 2:
            w_c = band_centre_omega(f, kind=kind)
            a_c = -float(damping) * w_c if damping != 0.0 else -1e-3 * w_c
            poles = np.concatenate([poles, np.array([a_c + 0.0j])])
        return poles
