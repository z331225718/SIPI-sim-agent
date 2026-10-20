"""IdEM-style adaptive order refinement: Adding, Skimming and Finalization.

This module replicates the order-adaptation layer of CST Studio Suite's IdEM
(idemmp_fitting.exe).  Its XML defaults (OptionsFittingSchema.xsd) map field
for field onto AdaptiveConfig:

    iterations {initial, postadding, final}      -> VFConfig.n_iter_initial,
                                                    AdaptiveConfig.n_iter_postadding,
                                                    VFConfig.n_iter_final
    errorControl {stagnation, nBackSteps}        -> stagnation_alpha, n_back_steps
    skimming {relativeTolerance,
              finalRelativeTolerance,
              absoluteTolerance}                 -> skimming_tol,
                                                    final_skimming_tol,
                                                    (absoluteTolerance is not
                                                     used; kept in the XML only)
    accuracy {target, guaranteed}                -> target_tol, guaranteed_accuracy
    order {min, increment, max}                  -> min_order, order_step, max_order

The four pass names IdEM prints are reproduced literally in history[].phase:
'initialization', 'first adding pass', 'adding-skimming pass', 'finalization'.

Algorithm
---------
initialization
    min_order poles from VectorFitter.initial_poles, then n_iter_initial
    Sanathanan-Koerner iterations and a residue solve.

adding pass
    While the relative RMS error is above target_tol and the order is below
    max_order, order_step poles are ADDED per pass (IdEM order.increment, the
    help table's Nadd).  The count is rounded up to an even number internally,
    because new poles are always inserted as conjugate pairs: with the default
    order_step=2 exactly one pair is added per pass, so the order grows by 2
    each time.  The pairs are placed at the largest-residual frequencies, i.e.
    where ||S_fit(f_k) - S_data(f_k)||_F is largest, with
    alpha = -damping * 2*pi*f_k.  This is a HARD relocation: the new poles sit
    at the frequencies that are actually wrong, not on a generic grid (a
    frequency already occupied by a pole is skipped).  n_iter_postadding SK
    iterations follow, then a residue solve.

skimming (from the second growth pass onwards, hence the IdEM name
'adding-skimming pass')
    Each pole is scored by its energy contribution

        E_n = ||R_n||_F / |Re(p_n)|

    and poles with E_n < skimming_tol * mean(E) are treated as spurious.  They
    are removed and replaced by fresh damped poles at the largest-residual
    frequencies, so the order is preserved and never falls below min_order.
    Complex poles are always removed and re-inserted as whole conjugate pairs.

stagnation
    The last n_back_steps relative errors are compared; when the relative
    improvement over that window drops below stagnation_alpha the order growth
    stops (IdEM's noise-floor detector).  The pass index is published as
    AdaptiveFitter.stagnation_pass_ and flagged in history[].

finalization
    n_iter_final SK iterations, then final skimming: the lowest-energy pole is
    removed tentatively and the removal is kept only when the relative error
    grows by less than final_skimming_tol; candidates are retried until no pole
    can be removed (never below min_order).  The fit always ends with
    VectorFitter.compute_residues so every entry of the P x P matrix is
    consistent with the final pole set.

Seeding: the two paths measure different things (task-6 / task-9)
---------------------------------------------------------------
The starting poles are measured on the data, not guessed, but what has to be
measured depends on how the poles are used:

* fixed-order paths (VectorFitter.fit, AdaptiveFitter.fit_fixed_order) probe
  'lin' / 'auto' / 'log' with a couple of SK steps at the target order on a
  sub-sampled grid and keep the best (VectorFitter.select_initial_poles).  On the
  30-port PDN sweep that is worth a factor of 10: 'lin' 6.42e-3 against 'log'
  6.87e-2 at N=78.
* the growing path (AdaptiveFitter.fit) shortlists with that same cheap probe
  and then runs a SHORT GROWTH for the two best kinds, because a seed that wins
  at min_order need not win the grown fit.  Measured on the 19-port PDN sweep
  (P=19, F=826, min_order=8, order_step=8, target=1e-2): the fixed-order probe
  prefers 'auto' at every order and every grid resolution tried (orders 8, 24 and
  64; 52 and 826 probe points), yet the grown fit ends at 8.3073e-03 from 'auto'
  against 6.8263e-03 from 'lin' - 22% worse - and the two trajectories only cross
  at order 24, which no single-order probe can see.  The short growth run
  reproduces the crossing (auto 6.06e-02 vs lin 4.81e-02 at order 24) and costs
  ~10 s on a ~100 s fit.  See _GROWTH_PROBE_STEPS / _GROWTH_PROBE_MARGIN and
  AdaptiveFitter.growth_probe_scores_.

VFConfig.seed_probe=False switches both paths back to plain initial_poles().

Extensions relative to INTERFACES.md section 3 (all additive)
-------------------------------------------------------------
* history[] entries carry three extra keys, 'improvement', 'stagnated' and
  'n_rejected' (None/False/0 outside the growth loop), next to the documented
  pass/phase/order/rms_error/n_added/n_skimmed.  n_rejected counts poles
  relocated by the outOfBand.rejectPoles rule, which is kept separate from the
  skimming removals reported in n_skimmed.
* AdaptiveFitter.fit_fixed_order() implements IdEM's order.type=fixed path
  (the CLI maps -order N onto it): a fixed pole count, no Adding/Skimming, but
  the initial and final SK iterations and the final residue solve are kept.
* reject_poles_factor (IdEM outOfBand.rejectPoles) is honoured: when set to a
  factor q, poles whose natural frequency 2*pi*|p| leaves
  [f_pos_min/q, f_max*q] are rejected and relocated to high-residual
  frequencies.
* guaranteed_accuracy is used as IdEM uses it: a fit whose final error is
  worse than accuracy.guaranteed publishes a warning (AdaptiveFitter.warning_).
* The returned model carries a meta dict with the pass/order/error summary.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import List, Optional

import numpy as np

from .rational_model import RationalModel, conjugate_pairs, real_pole_mask
from .vector_fitting import VFConfig, VectorFitter, canonical_poles, stabilise_poles

__all__ = ["AdaptiveConfig", "AdaptiveFitter", "pole_energies", "pole_mix"]

#: Phase labels, identical to the strings IdEM prints.
PHASE_INITIALIZATION = "initialization"
PHASE_FIRST_ADDING = "first adding pass"
PHASE_ADDING_SKIMMING = "adding-skimming pass"
PHASE_FINALIZATION = "finalization"

#: Damping of a pole pair inserted at a high-residual frequency.
#:
#: Inserted poles land on the worst-fitting frequencies, which for a
#: delay-dominated channel are the lowest ones, where the data grid is coarse
#: relative to the frequency.  An under-damped pair then rings BETWEEN samples,
#: where nothing constrains it: measured on channel_16ghz_3db.s2p, 1% damping
#: leaves a passivity violation of 0.94 that enforce_passivity() can only repair
#: by destroying the fit (relative RMS 9.27e-4 -> 7.65e-1), while 2% damping
#: gives 2.7e-2 and 4.2e-2 after enforcement; 3% and 5% are comparable.  The
#: value is a documented tuning constant, not an algorithmic choice.
_ADD_DAMPING = 0.02
#: Relative frequency separation required between two inserted poles.
_DUPLICATE_REL = 1e-3

#: Minimum separation between frequencies chosen for pole INSERTION, as a
#: fraction of the band span divided by the number of poles being added.
#: The _DUPLICATE_REL guard alone is relative and therefore far too weak on a
#: wide-band grid: at 280 MHz it permits a 280 kHz gap while the grid spacing
#: there is ~2 MHz, so "mutually separated" was a no-op and the top-K rule put
#: every new pole inside a single error peak.  Measured on the 30-port PDN
#: sweep after initialization: the 12 largest residuals were ALL at 270-292 MHz
#: (a single peak), while the error energy was spread 43% in 100-500 MHz, 18%
#: in 0.5-1 GHz and 24% in 1-2 GHz.  IdEM spreads its added poles across the
#: band instead (order-10 poles at 178 / 634 / 1098 / 1467 MHz), and that is
#: why its adding search improves on its own fixed-order fits far more than
#: ours does.  Set to 0.0 for the previous behaviour.
_ADD_SEPARATION_FRACTION = 1.0

#: Residual peaks below this fraction of the fitted band are represented by ONE
#: real pole instead of a two-state conjugate pair.
#:
#: DEFAULT 0.0 = pairs everywhere.  Measured on the 30-port PDN sweep at the
#: matched target, INSERTING real poles at low-frequency peaks is worse than the
#: pair-only search (see the task-11 experiment table), which agrees with the
#: Lead's independent result that real-pole SEEDING is worse at 6/12/20 real
#: poles (x1.17, x1.09, x1.37).  IdEM's real poles are an outcome of its
#: relocation/skimming, not something it inserts on residual peaks.
_REAL_POLE_MAX_FRACTION = 0.0
#: Hard cap on real poles as a share of the order.  IdEM sits at 12/82 = 0.15,
#: so 0.2 leaves room to beat it without letting the search turn into a
#: real-pole-only fit.
_REAL_POLE_MAX_SHARE = 0.2
_TINY = 1e-300

#: Growth-path seed selection (task-9).  The fixed-order probe scores a seed by
#: a couple of SK steps at ONE order, but this engine GROWS the order, and a
#: seed that wins at min_order need not win at the final order.  Measured on the
#: 19-port PDN sweep 5power_19port_withcap (P=19, F=826, min_order=8,
#: order_step=8): the fixed-order probe prefers 'auto' at every order and every
#: grid resolution tried (order 8/24/64, 52 and 826 probe points), yet the grown
#: fit ends at 8.3073e-03 from 'auto' against 6.8263e-03 from 'lin' - 22% worse.
#: The two trajectories cross at order 24 ('lin' 4.81e-02 vs 'auto' 6.13e-02).
#: The growing path therefore shortlists with the cheap probe and then runs a
#: SHORT GROWTH (min_order + _GROWTH_PROBE_STEPS * order_step) for the two best
#: kinds, scoring the quantity the adaptive loop actually lives with.
_GROWTH_PROBE_STEPS = 2
#: When the cheap probe already separates the two best kinds by this factor, the
#: short growth runs are skipped (the fixed-order ranking is trustworthy there).
_GROWTH_PROBE_MARGIN = 2.0


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def pole_mix(poles) -> dict:
    """Summarise a pole set: real vs complex, resonance and damping histograms.

    Reported per adaptive pass (history[]['pole_mix']) so our allocation can be
    compared directly with IdEM's trajectory: IdEM order 82 = 12 real + 35 pairs
    with pair resonances 0.09-2.17 GHz, median damping 0.043-0.051.
    """
    poles = np.asarray(poles, dtype=np.complex128).ravel()
    real = real_pole_mask(poles)
    pairs = poles[~real & (poles.imag > 0.0)]
    res_hz = np.abs(pairs) / (2.0 * np.pi)
    damping = -pairs.real / np.maximum(np.abs(pairs), _TINY)

    def _stat(values, fn):
        return float(fn(values)) if values.size else float("nan")

    return {
        "n_poles": int(poles.size),
        "n_real": int(np.count_nonzero(real)),
        "n_pairs": int(pairs.size),
        "real_abs_min": _stat(np.abs(poles[real]), np.min),
        "real_abs_max": _stat(np.abs(poles[real]), np.max),
        "pair_res_min": _stat(res_hz, np.min),
        "pair_res_median": _stat(res_hz, np.median),
        "pair_res_max": _stat(res_hz, np.max),
        "damping_min": _stat(damping, np.min),
        "damping_median": _stat(damping, np.median),
        "damping_max": _stat(damping, np.max),
        "n_pairs_below_10mhz": int(np.count_nonzero(res_hz < 1e7)),
        "n_pairs_10_100mhz": int(np.count_nonzero((res_hz >= 1e7) & (res_hz < 1e8))),
        "n_pairs_100mhz_1ghz": int(np.count_nonzero((res_hz >= 1e8) & (res_hz < 1e9))),
        "n_pairs_above_1ghz": int(np.count_nonzero(res_hz >= 1e9)),
    }


def pole_energies(poles, residues) -> np.ndarray:
    """IdEM skimming metric E_n = ||R_n||_F / |Re(p_n)| for every pole.

    Parameters
    ----------
    poles : (N,) complex
    residues : (N,P,P) complex

    Returns
    -------
    (N,) float64
    """
    p = np.asarray(poles, dtype=np.complex128).ravel()
    r = np.asarray(residues, dtype=np.complex128)
    if r.ndim != 3 or r.shape[0] != p.size:
        raise ValueError("residues must have shape (N,P,P) matching the poles")
    fro = np.sqrt(np.sum(np.abs(r) ** 2, axis=(1, 2)))
    real = np.abs(p.real)
    floor = _TINY * np.maximum(1.0, np.abs(p))
    return fro / np.maximum(real, floor)


def _partner_indices(poles) -> dict:
    """Map every complex pole index onto its conjugate partner index.

    The mapping is symmetrical (i -> j and j -> i): conjugate_pairs() reports
    each pair once, and a one-sided map silently let a pole be removed without
    its partner, which breaks the conjugate structure RationalModel requires.
    """
    out = {}
    for i, j in conjugate_pairs(np.asarray(poles, dtype=np.complex128)):
        if i != j:
            out[i] = j
            out[j] = i
    return out


# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #
@dataclass
class AdaptiveConfig:
    """IdEM order-adaptation settings (see the module docstring for the XML map).

    Attributes
    ----------
    target_tol : float
        Stop adding poles once the relative RMS error reaches this value
        (IdEM accuracy.target).
    guaranteed_accuracy : float
        Error the fit is expected to reach; a final error above it raises the
        AdaptiveFitter.warning_ flag (IdEM accuracy.guaranteed).
    min_order, max_order : int
        Bounds on the number of poles (IdEM order.min / order.max).
    order_step : int
        Number of poles ADDED per adding pass (IdEM order.increment / Nadd).
        Odd values are rounded up to the next even number, because poles are
        inserted as conjugate pairs; order_step=2 therefore adds one pair per
        pass and the order grows by 2.  The insertion points are the
        order_step/2 largest-residual frequencies.
    skimming_tol : float
        Relative energy threshold gamma of the skimming test
        E_n < gamma * mean(E) (IdEM skimming.relativeTolerance).
    final_skimming_tol : float
        Allowed relative error growth for a finalization removal (IdEM
        skimming.finalRelativeTolerance).
    stagnation_alpha : float
        Minimum relative improvement over n_back_steps (IdEM
        errorControl.stagnation).
    n_back_steps : int
        Length of the stagnation window (IdEM errorControl.nBackSteps).
    enable_adding, enable_skimming, enable_final_skimming : bool
        Individual stage switches.
    n_iter_postadding : int
        SK iterations after every adding pass (IdEM iterations.postadding).
    reject_poles_factor : float or None
        Out-of-band pole rejection factor (IdEM outOfBand.rejectPoles).
    enforce_dc : bool
        Pin the DC value during every residue solve.
    vf_config : VFConfig or None
        Configuration handed to the internal VectorFitter (defaults to
        VFConfig(), i.e. IdEM's iterations.initial=3 / iterations.final=1).
    """

    target_tol: float = 1e-3
    guaranteed_accuracy: float = 0.1
    min_order: int = 4
    max_order: int = 40
    order_step: int = 2
    skimming_tol: float = 1e-3
    final_skimming_tol: float = 1e-3
    stagnation_alpha: float = 0.05
    n_back_steps: int = 3
    enable_adding: bool = True
    enable_skimming: bool = True
    enable_final_skimming: bool = True
    n_iter_postadding: int = 1
    reject_poles_factor: Optional[float] = None
    enforce_dc: bool = False
    vf_config: Optional[VFConfig] = None

    def __post_init__(self) -> None:
        if self.min_order < 1:
            raise ValueError("min_order must be >= 1")
        if self.max_order < self.min_order:
            raise ValueError("max_order must be >= min_order")
        if self.order_step < 1:
            raise ValueError("order_step must be >= 1")
        if self.n_back_steps < 1:
            raise ValueError("n_back_steps must be >= 1")
        if self.target_tol <= 0.0:
            raise ValueError("target_tol must be > 0")
        if self.reject_poles_factor is not None and self.reject_poles_factor <= 1.0:
            raise ValueError("reject_poles_factor must be > 1 when given")
        if self.vf_config is not None and not isinstance(self.vf_config, VFConfig):
            raise ValueError("vf_config must be a VFConfig instance")


# --------------------------------------------------------------------------- #
# the adaptive fitter
# --------------------------------------------------------------------------- #
class AdaptiveFitter:
    """IdEM Adding/Skimming adaptive order search on top of VectorFitter."""

    def __init__(self, config: Optional[AdaptiveConfig] = None) -> None:
        self.config: AdaptiveConfig = AdaptiveConfig() if config is None else config
        self.vf_config: VFConfig = (
            VFConfig() if self.config.vf_config is None else self.config.vf_config
        )
        self.fitter: VectorFitter = VectorFitter(self.vf_config)

        self._history: List[dict] = []
        self._f: Optional[np.ndarray] = None
        self._S: Optional[np.ndarray] = None
        self._f_floor: float = 1.0

        #: True when the stagnation detector stopped the order growth.
        self.stagnated_: bool = False
        #: Pass index (history[] index) at which stagnation fired, or None.
        self.stagnation_pass_: Optional[int] = None
        #: Set when the final error is worse than config.guaranteed_accuracy.
        self.warning_: Optional[str] = None
        #: Diagnostics of the last fit().
        self.order_: int = 0
        self.rms_error_: float = float("nan")
        self.n_adding_passes_: int = 0
        self.n_skimmed_: int = 0
        self.model_: Optional[RationalModel] = None
        #: Seeding diagnostics of the last fit: which candidate kind won the
        #: measured seed probe, the full probe report and what the probe cost.
        self.seed_kind_: Optional[str] = None
        self.seed_probe_report_: List[dict] = []
        self.seed_probe_seconds_: float = 0.0
        #: kind -> relative RMS of the short growth run (growing path only)
        self.growth_probe_scores_: dict = {}

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    @property
    def history(self) -> List[dict]:
        """One dict per pass: pass, phase, order, rms_error, n_added, n_skimmed.

        Additive keys: n_rejected, improvement, stagnated.
        """
        return list(self._history)

    def fit(self, f, s_data, poles=None) -> RationalModel:
        """Run initialization, adding/skimming passes and finalization.

        Returns the final RationalModel (all poles stable, residues consistent
        for every matrix entry).
        """
        cfg = self.config
        self._reset(f, s_data)

        # ------------------------------------------------ initialization
        if poles is None:
            poles = self._seed_poles(max(1, int(cfg.min_order)), growth=True)
        else:
            poles = self._canonical(poles)
        poles = self._iterate(poles, self.vf_config.n_iter_initial)
        model, err = self._solve(poles)
        poles = model.poles
        if cfg.reject_poles_factor is not None:
            # IdEM's outOfBand.rejectPoles also applies to the starting set.
            poles, n_out = self._enforce_band(poles, self._residual_norms(model))
            if n_out:
                model, err = self._solve(poles)
                poles = model.poles
        self._record(0, PHASE_INITIALIZATION, poles.size, err, 0, 0, poles=poles)

        # ------------------------------------------------ adding / skimming
        errors = [err]
        pass_index = 1
        while (
            err > cfg.target_tol
            and poles.size < cfg.max_order
            and cfg.enable_adding
        ):
            room = cfg.max_order - poles.size
            # IdEM order.increment is the number of poles ADDED per round;
            # round up to a whole number of conjugate pairs.
            step = int(cfg.order_step)
            step += step % 2
            n_new = min(step, room)
            n_new -= n_new % 2
            if n_new < 2:
                break

            residuals = self._residual_norms(model)
            poles, n_added = self._insert_poles(poles, residuals, n_new)
            poles = self._iterate(poles, cfg.n_iter_postadding)
            n_skimmed = 0

            residuals = self._residual_norms(model)
            poles, n_rejected = self._enforce_band(poles, residuals)
            model, err = self._solve(poles)
            poles = model.poles
            if cfg.enable_skimming and pass_index >= 2:
                residuals = self._residual_norms(model)
                trial_poles, n_skimmed = self._skim(poles, model, residuals)
                if n_skimmed:
                    # A skim is only accepted when it does not damage the fit:
                    # poles whose removal costs more than skimming_tol of
                    # relative accuracy were not spurious after all.
                    trial_model, trial_err = self._solve(trial_poles)
                    if trial_err <= err * (1.0 + cfg.skimming_tol):
                        poles, model, err = trial_model.poles, trial_model, trial_err
                    else:
                        n_skimmed = 0
                self.n_skimmed_ += n_skimmed
                model, err = self._solve(poles)
                poles = model.poles

            phase = (
                PHASE_FIRST_ADDING if pass_index == 1 else PHASE_ADDING_SKIMMING
            )
            self._record(pass_index, phase, poles.size, err, n_added, n_skimmed,
                         n_rejected, poles=poles)
            self.n_adding_passes_ += 1
            errors.append(err)

            improvement = None
            stagnated = False
            if len(errors) > cfg.n_back_steps:
                previous = errors[-1 - cfg.n_back_steps]
                if previous > 0.0:
                    improvement = float((previous - err) / previous)
                else:
                    improvement = 0.0
                stagnated = bool(improvement < cfg.stagnation_alpha)
                self._history[-1]["improvement"] = improvement
                self._history[-1]["stagnated"] = stagnated
                if stagnated:
                    self.stagnated_ = True
                    self.stagnation_pass_ = pass_index
                    break
            pass_index += 1

        # ------------------------------------------------ finalization
        poles = self._iterate(poles, self.vf_config.n_iter_final)
        model, err = self._solve(poles)
        poles = model.poles
        n_final = 0
        if cfg.enable_final_skimming:
            poles, model, err, n_final = self._final_skim(poles, model, err)
        # Always finish with a residue solve on the final pole set.
        model, err = self._solve(poles)
        self._record(
            self._history[-1]["pass"] + 1, PHASE_FINALIZATION, poles.size, err, 0,
            n_final, poles=poles,
        )
        self.n_skimmed_ += n_final

        if err > cfg.guaranteed_accuracy:
            self.warning_ = (
                "final relative RMS error %.3e is worse than "
                "accuracy.guaranteed=%.3e" % (err, cfg.guaranteed_accuracy)
            )
        self._finish(model, err)
        return model

    def fit_fixed_order(self, f, s_data, order: int, poles=None) -> RationalModel:
        """Fixed-order fit: no Adding/Skimming, but the SK iterations stay.

        Mirrors IdEM's order.type=fixed / command line '-order N' path: the
        pole count is exactly 'order' (or len(poles) when an explicit pole set
        is given), iterations.initial and iterations.final SK steps are run and
        the fit ends with a residue solve.
        """
        cfg = self.config
        self._reset(f, s_data)
        if poles is None:
            n = int(order)
            if n < 1:
                raise ValueError("order must be >= 1")
            poles = self._seed_poles(n)
        else:
            poles = self._canonical(poles)
            if int(order) > 0 and int(order) != poles.size:
                raise ValueError(
                    "order=%d does not match the %d poles given" % (order, poles.size)
                )
        poles = self._iterate(poles, self.vf_config.n_iter_initial)
        poles = self._iterate(poles, self.vf_config.n_iter_final)
        model, err = self._solve(poles)
        self._record(0, PHASE_FINALIZATION, poles.size, err, 0, 0, poles=poles)
        if err > cfg.guaranteed_accuracy:
            self.warning_ = (
                "final relative RMS error %.3e is worse than "
                "accuracy.guaranteed=%.3e" % (err, cfg.guaranteed_accuracy)
            )
        self._finish(model, err)
        return model

    # ------------------------------------------------------------------ #
    # internals: inputs and diagnostics
    # ------------------------------------------------------------------ #
    def _seed_poles(self, n: int, *, growth: bool = False) -> np.ndarray:
        """Starting poles: the measured best of the candidate seedings.

        VectorFitter.select_initial_poles() gives every candidate kind
        ('lin', 'auto', 'log') a few SK steps on a sub-sampled grid and keeps
        the best relative RMS, which is what makes the seeding independent of
        the data (on the 30-port PDN sweep the same engine reaches 6.4e-3 with
        'lin' but 6.9e-2 with 'log').

        With growth=True (AdaptiveFitter.fit, which GROWS the order) the choice
        is made by a short GROWTH run instead: a seed that wins a fixed-order
        probe need not win the grown fit - see _GROWTH_PROBE_STEPS for the
        measured 22% counter-example.  The cheap probe still shortlists.

        The probe runs ONCE per fit, never per adding pass; its cost is
        published as seed_probe_seconds_.  With VFConfig.seed_probe=False this
        is exactly VectorFitter.initial_poles().
        """
        n = max(1, int(n))
        t0 = time.perf_counter()
        if not self.vf_config.seed_probe:
            poles = self.fitter.initial_poles(self._f, n)
            self.seed_kind_ = "auto"
            self.seed_probe_report_ = []
        elif growth:
            poles = self._growth_seed_poles(n)
        else:
            poles, report = self.fitter.select_initial_poles(self._f, self._S, n)
            self.seed_kind_ = self.fitter.seed_kind_
            self.seed_probe_report_ = report
        self.seed_probe_seconds_ = time.perf_counter() - t0
        return poles

    def _growth_seed_poles(self, n: int) -> np.ndarray:
        """Choose the growing path's seed by a SHORT GROWTH run.

        Stage 1 is the cheap fixed-order probe (select_initial_poles), which
        shortlists the candidate kinds.  Stage 2, only when the two best kinds
        are within _GROWTH_PROBE_MARGIN of each other, replaces that fixed-order
        ranking with a real (short) adaptive growth per candidate, capped at
        min_order + _GROWTH_PROBE_STEPS * order_step.  That is the quantity the
        adaptive loop goes on to optimise, and on the 19-port PDN sweep it is
        the difference between 8.3073e-03 ('auto', what the fixed-order probe
        picks) and 6.8263e-03 ('lin'); the two trajectories only cross at
        order 24, which no single-order probe can see.
        """
        poles, report = self.fitter.select_initial_poles(self._f, self._S, n)
        # the report is sorted best-first, so its head is the fixed-order winner
        self.seed_kind_ = report[0]["kind"] if report else self.fitter.seed_kind_
        self.seed_probe_report_ = report
        self.growth_probe_scores_ = {}
        if len(report) < 2 or not np.isfinite(report[0]["error"]):
            return poles                      # nothing measurable to compare
        if report[1]["error"] > _GROWTH_PROBE_MARGIN * report[0]["error"]:
            return poles                      # the cheap probe clearly separates
        step = max(2, int(self.config.order_step))
        horizon = n + _GROWTH_PROBE_STEPS * step
        if horizon > int(self.config.max_order):
            horizon = int(self.config.max_order)
        if horizon <= n:
            return poles                      # no room to grow: nothing to probe
        for row in report[:2]:
            probe_cfg = replace(
                self.config,
                max_order=horizon,
                target_tol=_TINY,              # grow all the way to the horizon
                enable_final_skimming=False,
            )
            probe = AdaptiveFitter(probe_cfg)
            model = probe.fit(self._f, self._S, poles=row["seed"])
            self.growth_probe_scores_[row["kind"]] = float(
                model.rms_error(self._f, self._S)
            )
        best = min(self.growth_probe_scores_, key=self.growth_probe_scores_.get)
        for row in report:
            if row["kind"] == best:
                self.seed_kind_ = best
                return row["seed"]
        return poles

    def _reset(self, f, s_data) -> None:
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
        if not np.all(np.isfinite(f)) or not np.all(np.isfinite(S)):
            raise ValueError("f and s_data must be finite")
        self._f, self._S = f, S
        pos = f[f > 0.0]
        self._f_floor = float(pos.min()) if pos.size else 1.0
        self._history = []
        self.stagnated_ = False
        self.stagnation_pass_ = None
        self.warning_ = None
        self.n_adding_passes_ = 0
        self.n_skimmed_ = 0
        self.order_ = 0
        self.rms_error_ = float("nan")
        self.model_ = None
        self.seed_kind_ = None
        self.seed_probe_report_ = []
        self.seed_probe_seconds_ = 0.0
        self.growth_probe_scores_ = {}

    def _record(self, index, phase, order, err, n_added, n_skimmed,
                n_rejected: int = 0, poles=None) -> None:
        self._history.append(
            {
                "pass": int(index),
                "phase": phase,
                "order": int(order),
                "rms_error": float(err),
                "n_added": int(n_added),
                "n_skimmed": int(n_skimmed),
                "n_rejected": int(n_rejected),
                "improvement": None,
                "stagnated": False,
                # task-11 instrumentation: what the pass actually allocated
                "pole_mix": None if poles is None else pole_mix(poles),
            }
        )

    def _canonical(self, poles):
        poles = canonical_poles(np.asarray(poles, dtype=np.complex128).ravel())
        if self.vf_config.enforce_stability:
            poles = canonical_poles(stabilise_poles(poles))
        return poles

    def _residual_norms(self, model) -> np.ndarray:
        """(F,) Frobenius norm of the residual at every frequency."""
        return np.linalg.norm(model.residuals(self._f, self._S), axis=(1, 2))

    def _solve(self, poles):
        """Residue solve at the fixed pole set -> (RationalModel, relative RMS).

        The poles are canonicalised first, and model.poles is the authoritative
        pole set afterwards: the residues returned by compute_residues belong to
        the canonicalised poles (symmetrize averages the two members of a pair),
        so every caller must continue from model.poles.
        """
        poles = self._canonical(poles)
        residues, d = self.fitter.compute_residues(
            self._f, self._S, poles, enforce_dc=self.config.enforce_dc
        )
        model = RationalModel(poles=poles, residues=residues, d=d)
        return model, float(model.rms_error(self._f, self._S))

    def _iterate(self, poles, n_iter: int):
        """n_iter Sanathanan-Koerner pole relocations, best pole set wins.

        The SK/Levy iteration is not guaranteed to descend in the true
        (unweighted) error: when some sigma zeros fall in the right half plane
        the reflected pole set is not the set of sigma zeros any more and the
        iteration can cycle.  VectorFitter.fit() answers that by returning the
        best model it visited; the adaptive passes need the same guarantee,
        otherwise a pass can hand a worse pole set to the next one.  The
        relocation chain itself is untouched - each relocate_poles call still
        receives the pole set the previous call returned, so the 1/|sigma| SK
        weight is chained as designed - and the winner is chosen by the same
        relative RMS metric the adaptive loop optimises.
        """
        n_iter = max(0, int(n_iter))
        current = self._canonical(poles)
        if n_iter == 0:
            return current
        _, best_err = self._solve(current)
        best_poles = current
        for _ in range(n_iter):
            current = self.fitter.relocate_poles(self._f, self._S, current)
            current = self._canonical(current)
            _, err = self._solve(current)
            if err < best_err:
                best_poles, best_err = current, err
        return best_poles

    def _finish(self, model, err) -> None:
        self.order_ = int(model.n_poles)
        self.rms_error_ = float(err)
        self.model_ = model
        model.meta = {
            "algorithm": "IdEM adaptive adding/skimming",
            "order": int(model.n_poles),
            "rms_error": float(err),
            "target_tol": self.config.target_tol,
            "n_adding_passes": int(self.n_adding_passes_),
            "n_skimmed": int(self.n_skimmed_),
            "stagnated": bool(self.stagnated_),
            "stagnation_pass": self.stagnation_pass_,
            "guaranteed_accuracy": self.config.guaranteed_accuracy,
            "warning": self.warning_,
            "phases": [h["phase"] for h in self._history],
        }

    # ------------------------------------------------------------------ #
    # internals: adding
    # ------------------------------------------------------------------ #
    def _pick_frequencies(self, residuals, count: int, avoid=None) -> np.ndarray:
        """Indices of the 'count' largest-residual, mutually separated points.

        Frequencies within _DUPLICATE_REL of a frequency in 'avoid' (the
        natural frequencies of poles that are already in the model) are never
        returned: inserting a second pole where one already sits is what makes
        the pole set degenerate.  The mutual-separation guard is relaxed when
        the grid is too coarse to satisfy it.
        """
        order = np.argsort(np.asarray(residuals, dtype=np.float64))[::-1]
        avoid = (
            None
            if avoid is None
            else np.asarray(avoid, dtype=np.float64).ravel()
        )

        def blocked(fk: float) -> bool:
            if avoid is None or avoid.size == 0:
                return False
            return bool(
                np.any(np.abs(avoid - fk) <= _DUPLICATE_REL * np.maximum(avoid, fk))
            )

        # Band-aware separation floor.  _DUPLICATE_REL alone is relative, so on
        # a wide-band grid it permits gaps far smaller than the sample spacing
        # and the top-K pick collapses into one peak; see the constant docstring.
        f = self._f
        span = float(f.max() - f.min()) if f.size else 0.0
        min_sep = _ADD_SEPARATION_FRACTION * span / max(2 * int(count), 1)

        chosen: List[int] = []
        for k in order:
            fk = self._f[k]
            if blocked(fk):
                continue
            if all(
                abs(fk - self._f[j])
                > max(_DUPLICATE_REL * max(fk, self._f[j], self._f_floor), min_sep)
                for j in chosen
            ):
                chosen.append(int(k))
            if len(chosen) >= count:
                break
        if len(chosen) < count:  # relax the separation guard, keep 'avoid'
            for k in order:
                fk = self._f[k]
                if int(k) in chosen or blocked(fk):
                    continue
                chosen.append(int(k))
                if len(chosen) >= count:
                    break
        return np.asarray(chosen[:count], dtype=int)

    def _new_poles(self, residuals, n_new: int, avoid=None, max_real=None) -> np.ndarray:
        """Fresh poles at the largest-residual frequencies.

        A damped conjugate pair (alpha = -_ADD_DAMPING * 2*pi*f_k, +-j*2*pi*f_k)
        is the default.  A residual peak below _REAL_POLE_MAX_FRACTION of the
        fitted band is represented by ONE real pole instead: a pair parked where
        the response has no resonance spends two states doing a real pole's job.
        IdEM carries 12 real poles and 35 pairs at order 82 while this engine
        used to insert pairs only - see _REAL_POLE_MAX_FRACTION.  At most n_new
        poles are produced and frequencies too close to a pole in 'avoid' are
        skipped.
        """
        n_new = int(n_new)
        if n_new < 1:
            return np.empty(0, dtype=np.complex128)
        idx = self._pick_frequencies(residuals, n_new, avoid=avoid)
        if idx.size == 0:
            return np.empty(0, dtype=np.complex128)
        w = 2.0 * np.pi * np.maximum(self._f[idx], self._f_floor)
        real_below = _REAL_POLE_MAX_FRACTION * 2.0 * np.pi * float(self._f.max())
        if max_real is None:
            max_real = n_new
        max_real = max(0, int(max_real))
        out: List[complex] = []
        budget = int(n_new)
        n_real = 0
        for wk in w:
            if budget <= 0:
                break
            if wk <= real_below and n_real < max_real:
                # a real pole acts at its own magnitude, so it goes ON the peak
                out.append(-max(wk, _TINY))
                budget -= 1
                n_real += 1
            elif budget >= 2:
                a = -_ADD_DAMPING * wk
                out.extend([a + 1j * wk, a - 1j * wk])
                budget -= 2
            else:
                # odd leftover: exactly the pre-task-11 behaviour (a heavily
                # damped single pole), so disabling the real-pole branch above
                # reproduces the old search bit for bit.
                out.append(-_ADD_DAMPING * wk)
                budget -= 1
                n_real += 1
        return np.asarray(out, dtype=np.complex128)

    def _pole_frequencies(self, poles) -> np.ndarray:
        """Natural frequencies (Hz) of a pole set, for the avoid list."""
        return np.abs(np.asarray(poles, dtype=np.complex128)) / (2.0 * np.pi)

    def _insert_poles(self, poles, residuals, n_new: int):
        """Hard relocation: keep the poles and add fresh ones where it hurts.

        Returns (poles, n_added) so the caller records what actually happened.
        """
        n_real_now = int(np.count_nonzero(real_pole_mask(poles)))
        room_real = int(np.ceil(_REAL_POLE_MAX_SHARE * (poles.size + n_new))) - n_real_now
        fresh = self._new_poles(
            residuals, n_new, avoid=self._pole_frequencies(poles),
            max_real=max(0, room_real),
        )
        if fresh.size == 0:
            return poles, 0
        return self._canonical(np.concatenate([poles, fresh])), int(fresh.size)

    # ------------------------------------------------------------------ #
    # internals: skimming and out-of-band rejection
    # ------------------------------------------------------------------ #
    def _skim(self, poles, model, residuals):
        """Drop spurious poles and replace them at high-residual frequencies.

        Selection works on whole units (a conjugate pair or a single real pole)
        so a pair can never be split, and the replacements are fresh damped
        poles at the largest-residual frequencies: the order is preserved and
        the pole count never falls below min_order.
        """
        cfg = self.config
        poles = np.asarray(poles, dtype=np.complex128).ravel()
        energies = pole_energies(poles, model.residues)
        threshold = cfg.skimming_tol * float(np.mean(energies))
        partners = _partner_indices(poles)

        seen = set()
        units = []
        for i in range(poles.size):
            if i in seen:
                continue
            j = partners.get(i)
            if j is None:
                seen.add(i)
                units.append((float(energies[i]), [i]))
            else:
                seen.add(i)
                seen.add(j)
                units.append((float(min(energies[i], energies[j])), [i, j]))
        units.sort(key=lambda u: u[0])

        max_remove = poles.size - int(cfg.min_order)
        drop: List[int] = []
        for energy, idxs in units:
            if energy >= threshold:
                break
            if len(drop) + len(idxs) > max_remove:
                break
            drop.extend(idxs)
        if not drop:
            return poles, 0

        dropped = set(drop)
        keep = np.array([i for i in range(poles.size) if i not in dropped], dtype=int)
        fresh = self._new_poles(
            residuals, len(drop), avoid=self._pole_frequencies(poles[keep])
        )
        out = self._canonical(np.concatenate([poles[keep], fresh]))
        return out, len(drop)

    def _enforce_band(self, poles, residuals):
        """Reject poles whose natural frequency leaves the fitting band."""
        factor = self.config.reject_poles_factor
        if factor is None:
            return poles, 0
        w = 2.0 * np.pi * self._f
        lo = 2.0 * np.pi * self._f_floor / float(factor)
        hi = 2.0 * np.pi * float(self._f.max()) * float(factor)
        poles = np.asarray(poles, dtype=np.complex128).ravel()
        nat = np.abs(poles)
        bad = np.flatnonzero((nat < lo) | (nat > hi))
        if bad.size == 0:
            return poles, 0
        partners = _partner_indices(poles)
        drop = set()
        for k in bad:
            drop.add(int(k))
            if int(k) in partners:
                drop.add(int(partners[k]))
        if len(drop) > poles.size - int(self.config.min_order):
            return poles, 0
        keep = np.array([i for i in range(poles.size) if i not in drop], dtype=int)
        fresh = self._new_poles(
            residuals, len(drop), avoid=self._pole_frequencies(poles[keep])
        )
        return self._canonical(np.concatenate([poles[keep], fresh])), len(drop)

    # ------------------------------------------------------------------ #
    # internals: finalization
    # ------------------------------------------------------------------ #
    def _final_skim(self, poles, model, err):
        """Remove the lowest-energy pole while the error barely grows."""
        cfg = self.config
        removed = 0
        trials = 0
        max_trials = 8 * max(1, poles.size)
        while poles.size > int(cfg.min_order) and trials < max_trials:
            energies = pole_energies(poles, model.residues)
            partners = _partner_indices(poles)
            accepted = False
            for k in np.argsort(energies):
                k = int(k)
                drop = [k]
                if k in partners:
                    drop.append(partners[k])
                drop = sorted(set(drop))
                if len(drop) > poles.size - int(cfg.min_order):
                    continue
                trial_poles = np.delete(poles, drop)
                trial_model, trial_err = self._solve(trial_poles)
                trials += 1
                growth = (trial_err - err) / err if err > 0.0 else np.inf
                if growth < cfg.final_skimming_tol:
                    poles, model, err = trial_model.poles, trial_model, trial_err
                    removed += len(drop)
                    accepted = True
                    break
                if trials >= max_trials:
                    break
            if not accepted:
                break
        return poles, model, err, removed
