"""Configuration of the merged adaptive Adding/Skimming search backend.

This module is deliberately dependency-free (standard library only) so that it
can be imported by the leading API surface for type annotations and argument
validation **without** loading the vendored pole-discovery engine.  The heavy
adapter lives in :mod:`agent_spice.sparam.adaptive_search`; it re-exports
:class:`AdaptiveSearchConfig` for backwards compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class AdaptiveSearchConfig:
    """Order-search settings for the merged Adding/Skimming backend.

    Parameters
    ----------
    target_mean_rms:
        Absolute full-band mean S-RMS bar the search aims below (IdEM/our
        ``--rms-target`` semantics), before passivity enforcement.
    max_order:
        Maximum effective model order (real poles + 2 per complex pair) the
        search may grow to.
    min_order:
        Starting order of the cumulative search.
    order_step:
        Poles added per adding pass; odd values are rounded up to the next even
        number because poles are inserted as conjugate pairs.
    target_margin:
        Fraction of ``target_mean_rms`` handed to the order search as its raw
        relative target.  ``1.0`` asks for exactly the bar, ``0.75`` adds
        headroom for the residue refit + passivity enforcement.
    init_pole_damping:
        Starting-pole damping ratio (``alpha = -damping * omega``).  The
        upstream sweep measured 0.05 as the best value on the 30-port PDN.
    seed_probe / seed_probe_iters / seed_probe_subsample:
        Measured best-of-``lin``/``auto``/``log`` seeding on a strided probe
        grid (upstream default: on, 2 SK steps, every 16th point).
    sk_weighting:
        Sanathanan-Koerner ``1/|sigma|`` reweighting inside the vendored
        engine (upstream default on; the adaptive path is what it was tuned
        for, unlike our fixed-order ladder).
    enforce_dc:
        Pin the DC point *during the search's residue solve*.  Off by default:
        the delivered model is re-solved by the native residue solve anyway,
        and the merged mode reports the delivered DC error separately.
    """

    target_mean_rms: float
    max_order: int = 100
    min_order: int = 4
    order_step: int = 8
    target_margin: float = 1.0
    init_pole_damping: float = 0.05
    seed_probe: bool = True
    seed_probe_iters: int = 2
    seed_probe_subsample: int = 16
    sk_weighting: bool = True
    enforce_dc: bool = False

    def __post_init__(self) -> None:
        if not math.isfinite(self.target_mean_rms) or self.target_mean_rms <= 0.0:
            raise ValueError("target_mean_rms must be finite and > 0")
        if int(self.min_order) < 1:
            raise ValueError("min_order must be >= 1")
        if int(self.max_order) < int(self.min_order):
            raise ValueError("max_order must be >= min_order")
        if int(self.order_step) < 1:
            raise ValueError("order_step must be >= 1")
        if not math.isfinite(self.target_margin) or not 0.0 < self.target_margin <= 1.0:
            raise ValueError("target_margin must be in (0, 1]")
        if not math.isfinite(self.init_pole_damping) or self.init_pole_damping <= 0.0:
            raise ValueError("init_pole_damping must be finite and > 0")
        if int(self.seed_probe_iters) < 1:
            raise ValueError("seed_probe_iters must be >= 1")
        if int(self.seed_probe_subsample) < 1:
            raise ValueError("seed_probe_subsample must be >= 1")


__all__ = ["AdaptiveSearchConfig"]
