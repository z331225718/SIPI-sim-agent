"""Passivity assessment and enforcement for rational macromodels.

Passivity of a scattering macromodel means

    sigma_max( S(j*w) ) <= 1     for every real frequency w,

which is equivalent to the model being a bounded-real (unitary-bounded)
function.  A stable but non-passive model can produce unstable behaviour when
it is terminated with an arbitrary passive network, so IdEM (and this replica)
always checks and, when needed, repairs passivity before exporting a netlist.

Two complementary tests are implemented:

* frequency sweep - sample sigma_max(S(jw)) on a dense grid of real frequencies
  (singular_values, passivity_violation, violating_bands).
* Hamiltonian test - transform the state-space realisation into the Hamiltonian
  matrix H whose purely imaginary eigenvalues are exactly the frequencies where
  sigma_max = 1 (hamiltonian_matrix, hamiltonian_violations).  When
  ||D||_2 < 1 and A is stable the test is necessary *and* sufficient.

Enforcement follows the IdEM passivity-enforcement work flow:

1. asymptotic term first (enforce_asymptotic_passivity) - SVD truncate the
   direct term D so that sigma_max(D) <= 1 - margin and re-solve the residues so
   that the model still reproduces the original response (this is IdEM's
   AsymptoticPassivityMargin, default 0.001);
2. frequency-domain repair (enforce_passivity) - at every violating frequency
   the right singular vector v of S(jw) defines the linear constraint

       Re( v^H dS(jw) v ) <= target - sigma_max(S(jw)),

   with dS(s) = sum_n dR_n/(s - p_n), which is linear in the residue
   perturbation.  The smallest correction satisfying all constraints is the
   solution of a minimum-norm quadratic program, solved here with Hildreth's
   dual coordinate-descent method (the Hessian is the identity, so every
   coordinate update is exact and no linear system has to be inverted - which
   matters because the constraint rows span many orders of magnitude);
3. the perturbation is symmetrised (symmetrize) so the model stays real and
   to_state_space() remains valid, then the dense grid is re-scanned and the
   loop is repeated.  If the constrained solve stalls, a guaranteed residue
   shrink line search is used as a fallback, so the returned model is passive.

Enforcement details (and where this deviates from INTERFACES.md)

* constraint direction.  The note in INTERFACES.md uses v^H dS v with v the
  right singular vector.  The gradient of a singular value is
  Re(u^H dS v) with u and v the LEFT and RIGHT singular vectors; the two agree
  only when S is normal.  Using v^H dS v on a real fitted multiport produces a
  constraint that is not the gradient of sigma_max at all (measured: the peak
  grew instead of shrinking).  This module uses u^H dS v.
* degenerate singular values.  When two singular values are (nearly) equal -
  typical for a matched through connection - pushing the largest one down pushes
  its twin up, so constraining only sigma_max is first-order blind.  Every
  singular value above the target is therefore constrained.
* constraint level.  INTERFACES.md writes the right-hand side as
  '1 + margin - sigma_max'.  A model repaired to exactly 1 + margin would still
  violate sigma_max <= 1, so the margin is placed *below* one: the target level
  is 1 - margin (0.999 for the default margin = 1e-3).
* only the residues are perturbed.  The direct term has different physical units
  (residues are O(1e10) for a GHz model), so including dD in the same ||.||^2
  norm lets an arbitrarily small dD dominate the objective and silently break
  the asymptotic bound.  D is handled by the SVD clamp only.
* the corrections are projected onto the conjugate-symmetric residue subspace
  before solving, so that symmetrize() does not have to project (and thereby
  destroy) the correction afterwards.
* the objective is the absolute residue norm, weighted by the per-pole response
  sensitivity h_n = mean_f |1/(jw_f - p_n)|^2 over the fitted grid (the diagonal
  of the response-change Gram).  The full Gram is numerically singular
  (condition number ~1e280 for poles spread over decades), so only its diagonal
  is used.  Weighting each pole block by 1/||R_n||^2 (the relative norm) was
  also measured and is worse for the fitted accuracy: it forces the correction
  onto the few large residues that carry the coarse response.

Measured cost.  Enforcement removes the violation, and the price is a response
change that cannot be smaller than the violation depth itself (a first-order
bound: |u^H dS v| <= ||dS||_F at the violating frequency).  Measured on a fitted
2-port S-model of the local benchmark corpus, response change / violation depth:

    violation 1.0e-3 -> response change 4.0e-3   (rms x1.00)
    violation 2.5e-3 -> response change 6.9e-3   (rms x1.01)
    violation 5.0e-3 -> response change 1.2e-2   (rms x1.01)
    violation 7.3e-3 -> response change 1.6e-2   (rms x1.02)
    violation 2.0e-2 -> response change 4.0e-2   (rms x1.08)

Models that are already passive inside their fitted band are returned untouched
(see the early out in enforce_passivity).

Measured on the local benchmark corpus (fit -> enforce, dense grids):

    file                      ports order  violation   rms cost  dS/violation
    channel_16ghz_3db.s2p     2     38     5.39e-02    x14.7     1.16
    channel_gen5_highloss.s4p 4     18     2.10e-01    x1.00     0.45
    line_long.s2p             2     14     0.00e+00    x1.00     no-op
    line_short.s2p            2      8     0.00e+00    x1.00     no-op
    test_filter.s2p           2     12     0.00e+00    x1.00     no-op

The rms cost is proportional to the violation being removed, not to the fit
error: for these models the rms increase is about 0.2 x the response change and
the response change about 1.2 x the violation, i.e. rms_after is roughly
rms_before + 0.25 * violation.  A very accurate fit (rms 9e-4) with a large
violation (5e-2) therefore pays a large *relative* price even though the
absolute response movement is only ~1.2 x the overshoot it removes.

All frequency arguments are in Hz and the Laplace variable is s = 2j*pi*f.
"""

from __future__ import annotations

import warnings

import numpy as np

from .rational_model import (
    RationalModel,
    cauchy_matrix,
    conjugate_pairs,
    real_pole_mask,
    symmetrize,
)

__all__ = [
    "singular_values",
    "passivity_violation",
    "violating_bands",
    "enforce_asymptotic_passivity",
    "hamiltonian_matrix",
    "hamiltonian_eigenvalues",
    "hamiltonian_violations",
    "count_unpaired_complex_poles",
    "enforce_passivity",
    "scan_grid",
]

# Evaluation is chunked to bound the peak memory of the (F, P, P) responses.
_CHUNK = 512

# Default parameters of the constrained residue perturbation.
_MAX_SWEEPS = 2000
_FEAS_TOL = 1e-12
# Line search over the nominal correction.  1.0 first (the minimum-norm step),
# then backtracking halves and, finally, an over-relaxed step (the symmetrisation
# of a non-symmetric correction can lose up to a factor two).
_STEP_SCALES = (0.0625, 0.125, 0.1875, 0.25, 0.375, 0.5, 0.75, 1.0, 1.5, 2.0)
_SHRINK_ALPHAS = (0.05, 0.1, 0.25, 0.5, 0.75, 1.0)
# Per-iteration damping of the requested reduction: the singular-value
# constraint is only first order accurate, so when the violation is large at
# most this fraction of the excess over the target is demanded per iteration
# (the excess is then removed geometrically instead of overshooting).  Once the
# relative excess drops below _DAMPING_REL the full target is requested again,
# which makes the tail of the iteration converge in one or two steps.
_DAMPING = 0.5
_DAMPING_REL = 0.02
# The singular-value constraint is a first-order (linearised) model.  Requesting
# a large relative reduction in one go makes the underlying quadratic program
# infeasible in practice and its dual diverges, so the per-iteration demand is
# capped at this fraction of the current sigma_max.
_MAX_REL_STEP = 0.05
# Bisection steps of the final "least perturbation" polish.
_POLISH_STEPS = 12
# Relative slack used when checking "sigma_max <= target" (the asymptotic clamp
# sets the largest singular value of D exactly to the target).
_LEVEL_TOL = 1e-12


# --------------------------------------------------------------------------- #
# frequency sweep assessment
# --------------------------------------------------------------------------- #
def scan_grid(f, n_min: int = 2000, per_decade: int = 100,
              decades_below: float = 0.0, sub_dc_decades: float = 2.0,
              max_points: int = 20000) -> np.ndarray:
    """Dense log-spaced grid over the *enforcement band* defined by f.

    The band is [f_lo, f_hi] with f_hi = max(f) and f_lo = min positive sample:

    * when the data starts above DC, the band edge is extended by
      decades_below below the lowest sample (a guard band);
    * when the data includes DC (min(f) <= 0) the interval between DC and the
      first positive sample belongs to the model band, so the grid starts
      sub_dc_decades below that first sample and DC itself is included.

    There is deliberately NO extension above f_hi.  The high frequency limit of
    the model is the direct term D, whose passivity is enforced separately and
    exactly by enforce_asymptotic_passivity; beyond the fitted band a rational
    model is unconstrained by data, and enforcing passivity in that region would
    perturb the model for an artefact of the extrapolation.  Callers that do
    want out-of-band enforcement can simply pass a wider f.

    Parameters
    ----------
    f : (F,) array_like, Hz
    n_min : int
        Minimum number of points of the returned grid.
    per_decade : int
        Points per decade used for the log-spaced part.
    decades_below : float
        Guard band (decades) below the lowest sample when min(f) > 0.
    sub_dc_decades : float
        Coverage (decades) below the first positive sample when the data
        includes DC.
    max_points : int
        Hard cap on the grid size.
    """
    f = np.asarray(f, dtype=np.float64).ravel()
    if f.size == 0:
        raise ValueError("scan_grid: empty frequency vector")
    pos = f[f > 0.0]
    if pos.size == 0:
        # Degenerate input (DC only): fall back to a linear sweep.
        return np.unique(np.concatenate(([0.0], np.linspace(0.0, 1.0, max(n_min, 2)))))
    f_lo, f_hi = float(pos.min()), float(pos.max())
    if float(f.min()) <= 0.0:
        lo = f_lo * 10.0 ** (-abs(sub_dc_decades))
    else:
        lo = f_lo * 10.0 ** (-abs(decades_below))
    hi = f_hi
    n_dec = float(np.log10(hi / lo))
    n = int(min(max_points, max(int(n_min), int(per_decade * n_dec) + 1)))
    grid = np.logspace(np.log10(lo), np.log10(hi), n)
    parts = [grid, pos]
    if np.any(f <= 0.0):
        parts.append(np.array([0.0]))
    return np.unique(np.concatenate(parts))


def singular_values(model: RationalModel, f) -> np.ndarray:
    """Singular values of S(j*2*pi*f), shape (F, P), descending.

    sv[:, 0] is therefore sigma_max at every frequency.
    """
    f = np.atleast_1d(np.asarray(f, dtype=np.float64)).ravel()
    p = model.n_ports
    out = np.empty((f.size, p), dtype=np.float64)
    for a in range(0, f.size, _CHUNK):
        b = min(f.size, a + _CHUNK)
        out[a:b] = np.linalg.svd(model.evaluate(f[a:b]), compute_uv=False)
    return out


def _sigma_max_scan(model: RationalModel, f) -> np.ndarray:
    """sigma_max(S(jw)) on the grid f (1-D float array)."""
    f = np.atleast_1d(np.asarray(f, dtype=np.float64)).ravel()
    out = np.empty(f.size, dtype=np.float64)
    for a in range(0, f.size, _CHUNK):
        b = min(f.size, a + _CHUNK)
        sv = np.linalg.svd(model.evaluate(f[a:b]), compute_uv=False)
        out[a:b] = sv[:, 0] if sv.ndim == 2 else sv
    return out


def passivity_violation(model: RationalModel, f) -> float:
    """max(0, max_f sigma_max(S(jw)) - 1).

    Zero means 'no violation detected on this grid'; the Hamiltonian test is the
    definitive check.
    """
    smax = _sigma_max_scan(model, f)
    if smax.size == 0:
        return 0.0
    return float(max(0.0, float(smax.max()) - 1.0))


def _crossing(f, sv, i_in, i_out, thr):
    """Frequency where sv crosses thr between grid points i_in / i_out."""
    f0, f1 = float(f[i_out]), float(f[i_in])
    y0, y1 = float(sv[i_out]), float(sv[i_in])
    if f0 <= 0.0 or f1 <= 0.0 or y1 == y0:
        return f1
    t = (thr - y0) / (y1 - y0)
    t = min(max(t, 0.0), 1.0)
    x = np.log10(f0) + t * (np.log10(f1) - np.log10(f0))
    return float(10.0 ** x)


def violating_bands(model: RationalModel, f, margin: float = 0.0) -> list:
    """Frequency bands where sigma_max(S(jw)) > 1 + margin.

    Returns a list of dictionaries (sorted by frequency) with the keys
    f_start, f_stop (interpolated crossing frequencies), f_peak, sigma_max
    (value at the peak) and the grid indices i_start, i_stop, i_peak.
    """
    f = np.atleast_1d(np.asarray(f, dtype=np.float64)).ravel()
    if f.size == 0:
        return []
    sv = singular_values(model, f)[:, 0]
    thr = 1.0 + float(margin)
    mask = sv > thr
    bands = []
    i = 0
    while i < f.size:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j + 1 < f.size and mask[j + 1]:
            j += 1
        k = i + int(np.argmax(sv[i:j + 1]))
        f_start = _crossing(f, sv, i, i - 1, thr) if i > 0 else float(f[i])
        f_stop = _crossing(f, sv, j, j + 1, thr) if j + 1 < f.size else float(f[j])
        bands.append({
            "f_start": f_start,
            "f_stop": f_stop,
            "f_peak": float(f[k]),
            "sigma_max": float(sv[k]),
            "i_start": int(i),
            "i_stop": int(j),
            "i_peak": int(k),
        })
        i = j + 1
    return bands


# --------------------------------------------------------------------------- #
# asymptotic (direct term) passivity
# --------------------------------------------------------------------------- #
def _pole_grid(model: RationalModel, n: int = 400) -> np.ndarray:
    """A log-spaced frequency grid (Hz) derived from the pole locations."""
    if model.n_poles == 0:
        return None
    mag = np.abs(model.poles.imag)
    if not np.any(mag > 0.0):
        mag = np.abs(model.poles.real)
    mag = mag[mag > 0.0]
    if mag.size == 0:
        return None
    lo, hi = float(mag.min()) / 100.0, float(mag.max()) * 100.0
    n = int(min(4000, max(int(n), int(40 * np.log10(hi / lo)) + 1)))
    return np.logspace(np.log10(lo), np.log10(hi), n)


def enforce_asymptotic_passivity(model: RationalModel,
                                 margin: float = 1e-6) -> RationalModel:
    """SVD-truncate the direct term D so that sigma_max(D) <= 1 - margin.

    Steps (INTERFACES.md section 4.1):

    1. (A, B, C, D) = model.to_state_space();
    2. D = U S V^H, clamp S to 1 - margin and rebuild D;
    3. re-solve the residues against the *original* model response on a
       pole-derived grid so that the truncated model still reproduces the
       original frequency behaviour as closely as possible.  The candidate with
       the smaller maximum deviation (residues kept vs. residues re-solved) is
       returned;
    4. the pole set is untouched, hence the model stays stable.

    The returned model carries meta['asymptotic_passivity_margin'].
    """
    margin = float(margin)
    if not (0.0 <= margin < 1.0):
        raise ValueError("margin must be in [0, 1)")

    meta = dict(model.meta) if model.meta else {}
    meta["asymptotic_passivity_margin"] = margin

    _, _, _, d = model.to_state_space()
    target = 1.0 - margin
    u, sv, vh = np.linalg.svd(d)
    if sv.size == 0 or float(sv[0]) <= target:
        # Nothing to do - the asymptotic term is already passive.
        return model.copy(meta=meta)

    sv_clamped = np.minimum(sv, target)
    d_new = ((u * sv_clamped) @ vh).real

    cand_keep = model.copy(d=d_new, meta=meta)
    if model.n_poles == 0:
        return cand_keep

    fg = _pole_grid(model)
    if fg is None:
        return cand_keep
    s = 2j * np.pi * fg
    s_orig = model.evaluate(fg)

    # Candidate B: re-solve the residues for the new (clamped) direct term.
    rhs = s_orig - d_new[None, :, :]
    if model.e is not None:
        rhs = rhs - s[:, None, None] * model.e[None, :, :]
    basis = cauchy_matrix(s, model.poles)                       # (F, N)
    p = model.n_ports
    sol, *_ = np.linalg.lstsq(basis, rhs.reshape(fg.size, p * p), rcond=None)
    poles_s, res_s, d_s, e_s = symmetrize(
        model.poles, sol.reshape(model.n_poles, p, p), d_new, model.e
    )
    cand_fit = RationalModel(poles_s, res_s, d_s, e_s, meta=meta)

    def _deviation(cand):
        return float(np.max(np.abs(cand.evaluate(fg) - s_orig)))

    dev_keep, dev_fit = _deviation(cand_keep), _deviation(cand_fit)
    best = cand_fit if dev_fit <= dev_keep else cand_keep
    if not best.is_stable():
        warnings.warn("enforce_asymptotic_passivity produced unstable poles; "
                      "falling back to the original pole set")
        return model.copy(d=d_new, meta=meta)
    out_meta = dict(best.meta) if best.meta else {}
    out_meta["asymptotic_residue_resolve"] = bool(dev_fit <= dev_keep)
    out_meta["asymptotic_deviation"] = float(min(dev_keep, dev_fit))
    return best.copy(meta=out_meta)


# --------------------------------------------------------------------------- #
# Hamiltonian test
# --------------------------------------------------------------------------- #
def count_unpaired_complex_poles(model: RationalModel) -> int:
    """Number of complex poles that have no conjugate partner in the pole set.

    RationalModel.to_state_space() realises an unpaired complex pole as a real
    pole and silently drops its imaginary part, so such a model cannot be used
    for the Hamiltonian test (or for any state-space based passivity check).
    Vector fitting always returns exact conjugate pairs (symmetrize), so this
    only shows up for hand-built or corrupted models.
    """
    poles = model.poles
    n = poles.size
    if n == 0:
        return 0
    is_real = real_pole_mask(poles)
    used = np.zeros(n, dtype=bool)
    unpaired = 0
    for i in range(n):
        if used[i] or is_real[i]:
            continue
        dist = np.abs(poles - np.conj(poles[i]))
        dist[used] = np.inf
        dist[i] = np.inf
        j = int(np.argmin(dist))
        if j < n and not used[j] and dist[j] <= 1e-6 * max(1.0, abs(poles[i])):
            used[i] = used[j] = True
        else:
            used[i] = True
            unpaired += 1
    return unpaired


def hamiltonian_matrix(model: RationalModel) -> np.ndarray:
    """Real 2n x 2n Hamiltonian matrix of the model state space.

    n = model.state_dimension.  With (A, B, C, D) from model.to_state_space(),
    R = I - D^T D and S = I - D D^T::

        H = [[ A + B R^-1 D^T C ,  +B R^-1 B^T ],
             [ -C^T S^-1 C      ,  -A^T - C^T D R^-1 B^T ]]

    The eigenvalues of H are the zeros of det( I - S(-s)^T S(s) ), i.e. the
    frequencies where sigma_max(S(jw)) = 1.  Derivation: the series connection
    S(-s)^T S(s) is the system

        A_t = [[A, 0], [-C^T C, -A^T]],  B_t = [[B], [-C^T D]],
        C_t = [D^T C, B^T],              D_t = D^T D

    whose zeros (D_t invertible in det(C_t (sI-A_t)^-1 B_t + D) = 0) are the
    eigenvalues of A_t - B_t (I - D_t)^-1 C_t; substituting D_t = D^T D and
    using (I - D D^T)^-1 = I + D (I - D^T D)^-1 D^T gives exactly the matrix
    above.

    NOTE / DEVIATION FROM INTERFACES.md: section 4 quotes the commonly seen
    form with the opposite signs on all four correction terms
    (A - B R^-1 D^T C / -B R^-1 B^T / +C^T S^-1 C / -A^T + C^T D R^-1 B^T).
    That form is only equivalent for D = 0 (the two are then related by the
    similarity diag(I, -I)); for D != 0 it predicts wrong crossover
    frequencies.  Example: the scalar model S(s) = 2/(s+1) + 0.3 crosses
    |S| = 1 at w = 2.1712 while the INTERFACES form gives w = 1.4412 - the form
    used here reproduces 2.1712 exactly.  The correct form was also verified
    numerically against det(I - S(-jw)^H S(jw)) on random multiport systems
    (residual < 1e-12).

    The formulation requires sigma_max(D) < 1 (otherwise R and S are singular);
    a ValueError is raised in that case - run enforce_asymptotic_passivity first.
    A warning is issued when the model is unstable, since the test is only valid
    for stable A.
    """
    a, b, c, d = model.to_state_space()
    sv = np.linalg.svd(d, compute_uv=False)
    if sv.size and float(sv[0]) >= 1.0:
        raise ValueError(
            "hamiltonian_matrix requires sigma_max(D) < 1, got %.6g; call "
            "enforce_asymptotic_passivity(model, margin) first" % float(sv[0])
        )
    if not model.is_stable():
        warnings.warn("hamiltonian_matrix: the model has unstable poles, the "
                      "Hamiltonian passivity test is not reliable")
    n_unpaired = count_unpaired_complex_poles(model)
    if n_unpaired:
        warnings.warn("hamiltonian_matrix: %d complex pole(s) have no conjugate "
                      "partner; to_state_space() realises them as real poles and "
                      "drops their imaginary part, so H does not describe this "
                      "model.  Re-run symmetrize()/the fit before the test."
                      % n_unpaired)

    p = d.shape[0]
    eye = np.eye(p)
    r = eye - d.T @ d
    s_mat = eye - d @ d.T
    r_inv = np.linalg.inv(r)
    s_inv = np.linalg.inv(s_mat)
    b_r = b @ r_inv
    h11 = a + b_r @ d.T @ c                     # A + B R^-1 D^T C
    h12 = b_r @ b.T                             # B R^-1 B^T
    h21 = -(c.T @ s_inv @ c)                    # -C^T S^-1 C
    h22 = -a.T - (c.T @ d) @ r_inv @ b.T        # -A^T - C^T D R^-1 B^T
    return np.block([[h11, h12], [h21, h22]])


def hamiltonian_eigenvalues(model: RationalModel) -> np.ndarray:
    """All eigenvalues of the Hamiltonian matrix (complex128)."""
    return np.linalg.eigvals(hamiltonian_matrix(model))


def _band_limits(f_band):
    if f_band is None:
        return None, None
    arr = np.asarray(f_band, dtype=np.float64).ravel()
    if arr.size != 2:
        raise ValueError("f_band must be None or a (f_min, f_max) pair in Hz")
    return float(arr[0]), float(arr[1])


def hamiltonian_violations(model: RationalModel, f_band=None, *,
                           rel_tol: float = 1e-6,
                           abs_tol: float | None = None,
                           exclude_dc: bool = True) -> np.ndarray:
    """Crossover frequencies (Hz) from purely imaginary Hamiltonian eigenvalues.

    Every purely imaginary eigenvalue +/- j*w of H is a frequency where
    sigma_max(S(jw)) = 1; the model is non-passive iff at least one such
    eigenvalue exists.  f_band = (f_min, f_max) restricts the returned
    frequencies (Hz) to the band of interest.

    Eigenvalues are accepted as purely imaginary when
    |Re(lambda)| <= tol with tol = rel_tol * max(1, |lambda|_max) (or abs_tol
    when given); eigenvalues with |Im(lambda)| <= tol (in particular the DC
    eigenvalue lambda = 0) are skipped when exclude_dc.  The default rel_tol of
    1e-6 is calibrated for the state-space realisations produced by
    RationalModel.to_state_space(): measured relative real parts of genuine
    crossover pairs are ~1e-15, while non-crossover complex eigenvalues are
    separated from the axis by the model damping.
    """
    ev = hamiltonian_eigenvalues(model)
    if ev.size == 0:
        return np.zeros(0)
    scale = max(1.0, float(np.max(np.abs(ev))))
    tol = float(abs_tol) if abs_tol is not None else rel_tol * scale
    keep = np.abs(ev.real) <= tol
    w = np.abs(ev[keep].imag)
    if exclude_dc:
        w = w[w > tol]
    f_hz = w / (2.0 * np.pi)
    f_lo, f_hi = _band_limits(f_band)
    if f_lo is not None:
        f_hz = f_hz[(f_hz >= f_lo) & (f_hz <= f_hi)]
    if f_hz.size == 0:
        return np.zeros(0)
    f_hz = np.sort(f_hz)
    # Merge numerically duplicated crossover frequencies.
    merged = [f_hz[0]]
    for v in f_hz[1:]:
        if v > merged[-1] * (1.0 + 1e-6) + 1e-9:
            merged.append(v)
    return np.asarray(merged, dtype=np.float64)


# --------------------------------------------------------------------------- #
# constrained residue perturbation
# --------------------------------------------------------------------------- #
def _select_constraints(f, smax, level, per_band: int = 16,
                        max_constraints: int = 400) -> np.ndarray:
    """Grid indices used as passivity constraints (peaks + spread per band)."""
    idx = np.flatnonzero(smax > level)
    if idx.size == 0:
        return np.zeros(0, dtype=int)
    splits = np.flatnonzero(np.diff(idx) > 1)
    runs = [r for r in np.split(idx, splits + 1) if r.size]
    runs.sort(key=lambda r: -float(smax[r].max()))
    sel = []
    for r in runs:
        if r.size <= per_band:
            sel.extend(int(i) for i in r)
        else:
            pos = np.unique(np.linspace(0, r.size - 1, per_band).round().astype(int))
            sel.extend(int(r[i]) for i in pos)
        if len(sel) >= max_constraints:
            break
    sel = np.unique(np.asarray(sel, dtype=int))
    if sel.size > max_constraints:
        order = np.argsort(-smax[sel])
        sel = np.sort(sel[order[:max_constraints]])
    return sel


def _symmetrize_coefficients(poles, coeffs):
    """Project coefficients onto the conjugate-symmetric residue subspace.

    The perturbation must keep the model real (R(p*) = conj(R(p)), real residues
    on real poles), otherwise symmetrize() projects the correction afterwards and
    the first-order prediction of the constraint is lost.  The subspace S of
    admissible perturbations is real-linear and conjugation invariant, and the
    minimum-norm solution of the constraint set is a combination of the
    conjugated coefficient vectors.  Projecting the coefficients onto S (with
    the real inner product Re sum(A*X), i.e. exactly the averaging rule used by
    symmetrize) therefore guarantees that the solver returns an element of S:
    the predicted and the achieved response change then coincide.
    """
    out = np.array(coeffs, dtype=np.complex128)
    for i in np.flatnonzero(real_pole_mask(poles)):
        out[..., i, :, :] = out[..., i, :, :].real
    for i, j in conjugate_pairs(poles):
        if i == j:
            continue
        avg = 0.5 * (out[..., i, :, :] + np.conj(out[..., j, :, :]))
        out[..., i, :, :] = avg
        out[..., j, :, :] = np.conj(avg)
    return out


def _response_sensitivity(model: RationalModel, grid):
    """Per-pole diagonal of the response-change Gram matrix, symmetrised.

    Changing the residue of pole n by dR_n moves the response by
    dR_n / (jw_f - p_n) on every frequency of the metric grid, so the mean
    squared response movement caused by that pole is
    h_n = mean_f |1/(jw_f - p_n)|^2.  Minimising sum_n h_n ||dR_n||^2 instead of
    sum_n ||dR_n||^2 keeps the correction away from the poles that radiate into
    the whole band and biases it towards the poles that act locally - which is
    what keeps the fitted accuracy intact.  The full Gram matrix is numerically
    singular (condition numbers beyond 1e100 for poles spread over decades), so
    only its diagonal is used.  Conjugate partners get the same weight, which
    keeps the metric invariant under the real-system pairing.

    Returns None when the grid is unusable (the solver then falls back to the
    plain residue norm).
    """
    if grid is None:
        return None
    grid = np.asarray(grid, dtype=np.float64).ravel()
    n = model.n_poles
    if n == 0 or grid.size < 2:
        return None
    phi = cauchy_matrix(2j * np.pi * grid, model.poles)            # (F,N)
    h = np.mean(np.abs(phi) ** 2, axis=0)
    for i, j in conjugate_pairs(model.poles):
        if i != j:
            h[i] = h[j] = 0.5 * (h[i] + h[j])
    if not np.all(np.isfinite(h)) or np.any(h <= 0.0):
        return None
    return h


def _solve_perturbation(model: RationalModel, fk, target,
                        metric_grid=None, max_sweeps: int = _MAX_SWEEPS):
    """Minimum-norm residue correction satisfying the local passivity constraints.

    At every constraint frequency f_k the right singular vector v_k of S(jw_k)
    with sigma_max > target gives the (first order) constraint

        Re( v_k^H dS(jw_k) v_k ) <= target_k - sigma_max(S(jw_k)),
        dS(s) = sum_n dR_n / (s - p_n),

    which is linear in the unknown residue corrections.  Minimising
    ||dR||_F^2 subject to those inequalities is a quadratic program with an
    identity Hessian; it is solved here through its dual with Hildreth's
    coordinate-descent method.  Only the residues are perturbed - the direct
    term has different physical units, so including it in the same norm would
    let an arbitrary small ||dD|| dominate the objective.  The direct term is
    handled separately by enforce_asymptotic_passivity.

    Parameters
    ----------
    fk : (K,) array_like, Hz
        Frequencies carrying a constraint.
    target : float or (K,) array_like
        Requested sigma_max level at each constraint frequency.

    Returns (X, info) with the complex residue correction X of shape (N, P, P)
    and a diagnostics dictionary.  X is None when the constraint set is empty.
    """
    fk = np.atleast_1d(np.asarray(fk, dtype=np.float64)).ravel()
    n, p = model.n_poles, model.n_ports
    k = int(fk.size)
    if k == 0 or n == 0:
        return None, {"constraints": 0}
    resp = model.evaluate(fk)                                  # (K,P,P)
    u, sv, vh = np.linalg.svd(resp, full_matrices=False)
    smax = sv[:, 0]
    target = np.asarray(target, dtype=np.float64).ravel()
    if target.size == 1:
        target = np.full(k, float(target[0]))
    elif target.size != k:
        raise ValueError("target must be a scalar or have one entry per frequency")

    # First order perturbation of a singular value:
    #     sigma_i(S + dS) = sigma_i(S) + Re( u_i^H dS v_i ) + O(||dS||^2)
    # with u_i / v_i the LEFT / RIGHT singular vectors.  For a non-normal S (the
    # generic case for a fitted multiport) u_i != v_i, and using v_i^H dS v_i -
    # as in the INTERFACES.md note - is not the gradient of sigma_i at all.
    # Every singular value that still exceeds the target is constrained: when
    # two singular values are (nearly) degenerate - e.g. a matched through
    # connection with sigma_1 = sigma_2 - constraining only the largest one is
    # first-order blind, because pushing it down pushes its twin up.
    rows_a, rows_b = [], []
    for a in range(k):
        for b in range(p):
            if sv[a, b] > target[a]:
                rows_a.append(a)
                rows_b.append(b)
    if not rows_a:
        return None, {"constraints": 0}
    rows_a = np.asarray(rows_a, dtype=int)
    rows_b = np.asarray(rows_b, dtype=int)
    ul = u[rows_a, :, rows_b]                                   # (Kc,P)
    v = np.conj(vh[rows_a, rows_b, :])                          # (Kc,P)
    sig = sv[rows_a, rows_b]
    h = target[rows_a] - sig                                    # (Kc,)
    fkc = fk[rows_a]

    # M = outer(conj(u), v) so that u^H X v = sum_ab M[a,b] X[a,b].
    m = np.einsum("ka,kb->kab", np.conj(ul), v)
    s = 2j * np.pi * fkc
    w = m[:, None, :, :] / (s[:, None] - model.poles[None, :])[:, :, None, None]
    # Restrict the problem to perturbations that keep the model real: the
    # minimum-norm solution then lies in the conjugate-symmetric subspace and
    # symmetrize() no longer has to project (and destroy) the correction.
    w = _symmetrize_coefficients(model.poles, w)

    # Diagonal response-change metric: h_n = mean_f |1/(jw_f - p_n)|^2.
    h_metric = _response_sensitivity(model, metric_grid)

    wf = w.reshape(w.shape[0], -1)
    if h_metric is None:
        q = np.real(wf @ wf.conj().T)                          # (Kc,Kc) Gram
    else:
        scale = np.sqrt(np.repeat(h_metric, p * p))
        wfs = wf / scale[None, :]
        q = np.real(wfs @ wfs.conj().T)                        # weighted Gram
    diag = np.diag(q).copy()
    diag[diag <= 0.0] = np.finfo(float).tiny

    # Hildreth dual coordinate descent:
    #   min 0.5 lam^T Q lam + h^T lam  s.t. lam >= 0,  x = -G^T lam
    # with the residual r = G x = -Q lam maintained incrementally.
    kc = int(rows_a.size)
    lam = np.zeros(kc)
    r = np.zeros(kc)
    converged = False
    sweeps = 0
    for sweeps in range(1, int(max_sweeps) + 1):
        max_delta = 0.0
        for j in range(kc):
            delta = lam[j] + (r[j] - h[j]) / diag[j]
            if delta < 0.0:
                delta = 0.0
            delta -= lam[j]
            if delta != 0.0:
                lam[j] += delta
                r -= delta * q[:, j]
                max_delta = max(max_delta, abs(delta))
        if float(np.max(r - h)) <= _FEAS_TOL:
            converged = True
            break
        if max_delta <= 1e-15 * max(1.0, float(np.max(np.abs(lam)))):
            break

    x = -np.einsum("k,knpq->npq", lam, np.conj(w))
    if h_metric is not None:
        # x = -H^-1 G^T lam with the diagonal metric H = diag(h_n)
        x = x / h_metric[:, None, None]
    info = {
        "constraints": kc,
        "frequencies": k,
        "sweeps": int(sweeps),
        "converged": bool(converged),
        "max_violation": float(np.max(r - h)),
        "sigma_max": float(smax.max()),
        "correction": float(np.linalg.norm(x)),
        "response_metric": h_metric is not None,
    }
    return x, info


def _apply_perturbation(model: RationalModel, x) -> RationalModel:
    """Apply a residue correction and re-impose the real-system structure."""
    poles, res, d, e = symmetrize(
        model.poles, model.residues + x, model.d, model.e
    )
    meta = dict(model.meta) if model.meta else None
    return RationalModel(poles, res, d, e, meta=meta)


def _clamp_direct_term(model: RationalModel, target: float) -> RationalModel:
    """SVD-clamp the direct term of an existing model (poles/residues untouched)."""
    d = np.asarray(model.d, dtype=np.complex128).real
    sv = np.linalg.svd(d, compute_uv=False)
    if sv.size == 0 or float(sv[0]) <= target:
        return model
    u, s, vh = np.linalg.svd(d)
    d_new = ((u * np.minimum(s, target)) @ vh).real.astype(np.complex128)
    return model.copy(d=d_new)


def _shrink_to_level(model: RationalModel, grid, level):
    """Guaranteed fallback: scale the residues down until sigma_max <= level.

    With the direct term clamped to the target level, alpha = 1 (residues
    removed) always satisfies the bound, so this cannot fail for a model whose
    asymptotic term is passive.  A coarse scan locates a working scale and a
    short bisection then minimises it, so the fallback perturbs the model as
    little as possible.
    """
    tol = level * (1.0 + _LEVEL_TOL)

    def works(alpha):
        cand = model.copy(residues=model.residues * (1.0 - alpha))
        return cand, float(_sigma_max_scan(cand, grid).max()) <= tol

    hi = None
    for alpha in _SHRINK_ALPHAS:
        cand, ok = works(alpha)
        if ok:
            hi = alpha
            break
    if hi is None:
        return None
    lo = 0.0
    best = cand
    for _ in range(8):
        mid = 0.5 * (lo + hi)
        if mid <= lo:
            break
        trial, ok = works(mid)
        if ok:
            hi, best = mid, trial
        else:
            lo = mid
    return best


def _response_deviation(a: RationalModel, b: RationalModel, f) -> float:
    """Maximum absolute difference of the two responses on f (chunked)."""
    dev = 0.0
    for i in range(0, f.size, _CHUNK):
        j = min(f.size, i + _CHUNK)
        dev = max(dev, float(np.max(np.abs(a.evaluate(f[i:j]) - b.evaluate(f[i:j])))))
    return dev


def enforce_passivity(model: RationalModel, f, *, margin: float = 1e-3,
                      max_iter: int = 20, perturb_d: bool = True,
                      verbose: bool = False) -> RationalModel:
    """Remove passivity violations by a minimum-norm residue perturbation.

    Parameters
    ----------
    model : RationalModel
    f : (F,) array_like, Hz
        Fitted frequency grid.  A dense scan grid (>= 2000 points, plus two
        decades on each side) is generated from it with scan_grid.
    margin : float
        Safety margin: the model is driven to sigma_max <= 1 - margin on the
        enforcement band (IdEM default PassivityMargin is 1e-4 and the
        asymptotic margin 1e-3; 1e-3 is used here as the combined default).
    max_iter : int
        Maximum number of repair / re-scan iterations.
    perturb_d : bool
        When True (default) the direct term is clamped first with
        enforce_asymptotic_passivity (SVD truncation of D).  The frequency
        domain repair itself always perturbs residues only.
    verbose : bool
        Print one line per iteration.

    Returns
    -------
    RationalModel
        A model with stable poles, sigma_max <= 1 - margin on the enforcement
        band and meta['passivity_margin'], meta['passivity_iterations'],
        meta['passivity_max_sigma'], meta['passivity_deviation'] set.
        meta['passivity_noop'] is True when the input model was already passive
        and is returned unchanged.

    Notes
    -----
    The enforcement band is derived from f (see scan_grid): the fitted band
    plus, when the data include DC, the sub-DC interval.  A rational model is
    unconstrained by data outside its band, so out-of-band extrapolation
    artefacts (which are common and can be violent) are not chased; the
    high-frequency limit is covered exactly by the asymptotic clamp.  Pass a
    wider f to enforce over a wider band.
    """
    f = np.atleast_1d(np.asarray(f, dtype=np.float64)).ravel()
    if f.size == 0:
        raise ValueError("enforce_passivity: empty frequency vector")
    margin = float(margin)
    if not (0.0 < margin < 1.0):
        raise ValueError("margin must be in (0, 1)")
    if model.e is not None:
        warnings.warn("enforce_passivity implements S-parameter passivity "
                      "(sigma_max <= 1); this model carries an s*E term, so the "
                      "result is only an approximation of Y/Z passivity")

    grid = scan_grid(f)
    level = 1.0 - margin
    level_tol = level * (1.0 + _LEVEL_TOL)

    # ------------------------------------------------------------------ #
    # Early out: never touch a model that is already passive.  Enforcing the
    # safety margin on a compliant model would silently move the answer, which
    # is worse than no enforcement at all.
    # ------------------------------------------------------------------ #
    current_smax = _sigma_max_scan(model, grid)
    if float(current_smax.max()) <= 1.0:
        meta = dict(model.meta) if model.meta else {}
        meta["passivity_margin"] = margin
        meta["passivity_iterations"] = 0
        meta["passivity_max_sigma"] = float(current_smax.max())
        meta["passivity_deviation"] = 0.0
        meta["passivity_noop"] = True
        return model.copy(meta=meta)

    cur = model.copy()
    if perturb_d:
        cur = enforce_asymptotic_passivity(cur, margin=margin)
    elif float(np.linalg.svd(cur.d, compute_uv=False)[0]) >= 1.0:
        warnings.warn("perturb_d=False and sigma_max(D) >= 1: the asymptotic "
                      "term alone violates passivity and cannot be repaired "
                      "without touching D")

    best = cur
    best_smax = _sigma_max_scan(best, grid)
    iterations = 0
    # Frequency samples used by the response-change metric of the solver: the
    # fitted grid, i.e. exactly where the model accuracy is measured.  The
    # sub-band and out-of-band extrapolation regions are left free, which is
    # what allows a violation that sits outside the fitted band to be removed
    # without touching the fitted response.
    metric_grid = f

    for it in range(int(max_iter)):
        if float(best_smax.max()) <= level_tol:
            break
        sel = _select_constraints(grid, best_smax, level)
        if sel.size == 0:
            break
        sig = best_smax[sel]
        # Damped per-iteration target (see _DAMPING): large excesses are removed
        # geometrically, small ones in a single full step.
        excess = sig - level
        rel = excess / np.maximum(sig, np.finfo(float).tiny)
        demand = np.minimum(_DAMPING * excess, _MAX_REL_STEP * sig)
        demand = np.where(rel <= _DAMPING_REL, excess, demand)
        target = np.maximum(level, sig - demand)
        x, info = _solve_perturbation(best, grid[sel], target,
                                      metric_grid=metric_grid)
        if x is None:
            break
        iterations = it + 1
        # Line search over the nominal (minimum response change) correction.
        # Scales are tried from the smallest one: the first that removes every
        # violation on the dense grid wins, i.e. the model is perturbed as
        # little as possible.  When no scale succeeds the largest reduction
        # found is used and the loop re-linearises.
        cand, cand_smax, cand_scale = None, None, None
        for scale in _STEP_SCALES:
            trial = _apply_perturbation(best, scale * x)
            trial_smax = _sigma_max_scan(trial, grid)
            if cand_smax is None or trial_smax.max() < cand_smax.max():
                cand, cand_smax, cand_scale = trial, trial_smax, scale
            if trial_smax.max() <= level_tol:
                cand, cand_smax, cand_scale = trial, trial_smax, scale
                break
        if cand is None:
            break
        if verbose:
            print("[passivity] iter %2d: constraints=%3d metric=%s sweeps=%4d "
                  "conv=%s step=%.3f sigma_max %.6f -> %.6f (target %.6f)"
                  % (it + 1, info["constraints"], info["response_metric"],
                     info["sweeps"], info["converged"], cand_scale,
                     float(best_smax.max()), float(cand_smax.max()), level))
        if float(cand_smax.max()) < float(best_smax.max()) - 1e-14 * max(1.0, level):
            best, best_smax = cand, cand_smax
        else:
            break

    # ------------------------------------------------------------------ #
    # Polish: scale the whole accepted correction back as far as passivity
    # allows (bisection on the perturbation fraction).  The returned model is
    # then the least perturbed passive model this iteration found, instead of
    # the first one that happened to satisfy the constraint.
    # ------------------------------------------------------------------ #
    if iterations:
        delta = best.residues - cur.residues
        if np.linalg.norm(delta) > 0.0:
            lo_t, hi_t = 0.0, 1.0
            polish_model, polish_smax = best, best_smax
            for _ in range(_POLISH_STEPS):
                mid_t = 0.5 * (lo_t + hi_t)
                if mid_t <= lo_t:
                    break
                trial = cur.copy(residues=cur.residues + mid_t * delta)
                trial_smax = _sigma_max_scan(trial, grid)
                if float(trial_smax.max()) <= level_tol:
                    hi_t = mid_t
                    polish_model, polish_smax = trial, trial_smax
                else:
                    lo_t = mid_t
            best, best_smax = polish_model, polish_smax
            if verbose:
                print("[passivity] polish: keeping %.1f%% of the correction"
                      % (100.0 * hi_t))

    # Safety net: the residue perturbation never touches the direct term, but
    # symmetrize() re-projects D onto the real matrices, so re-assert the
    # asymptotic bound before the final check.
    if perturb_d:
        clamped = _clamp_direct_term(best, level)
        if clamped is not best:
            best = clamped
            best_smax = _sigma_max_scan(best, grid)

    if float(best_smax.max()) > level_tol:
        shrunk = _shrink_to_level(best, grid, level)
        if shrunk is not None:
            if verbose:
                print("[passivity] constrained solve stalled; using the residue "
                      "shrink fallback")
            best = shrunk
            best_smax = _sigma_max_scan(best, grid)
        elif perturb_d:
            warnings.warn("passivity could not be fully enforced: max sigma_max "
                          "= %.6g > %.6g" % (float(best_smax.max()), level))

    if not best.is_stable():
        warnings.warn("enforce_passivity produced unstable poles; returning the "
                      "input model unchanged")
        best = model.copy()
        best_smax = _sigma_max_scan(best, grid)

    meta = dict(best.meta) if best.meta else {}
    meta["passivity_margin"] = margin
    meta["passivity_iterations"] = int(iterations)
    meta["passivity_max_sigma"] = float(best_smax.max())
    meta["passivity_deviation"] = _response_deviation(model, best, grid)
    return best.copy(meta=meta)
