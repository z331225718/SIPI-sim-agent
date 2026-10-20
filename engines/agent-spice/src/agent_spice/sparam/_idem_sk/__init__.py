"""Vendored pole-discovery core of the ``idem_replica`` IdEM replica (MIT).

This subpackage is a **verbatim, unmodified** snapshot of four `.py` files from
the clean-room IdEM replica research project (byte-identical to upstream commit
``28b76dc``), used as an opt-in pole-discovery + fast passivity backend by
:mod:`agent_spice.sparam.adaptive_search`.  The residues, DC handling, the
authoritative passivity audit, reports and product artifacts all come from our
own native pipeline; nothing here participates in the default
``native-idem-fast-v1`` fit path.

Provenance and licence: see ``VENDOR.md`` and ``LICENSE`` in this directory.
"""

from .adaptive import AdaptiveConfig, AdaptiveFitter
from .passivity import (
    enforce_asymptotic_passivity,
    enforce_passivity,
    passivity_violation,
    scan_grid,
    singular_values,
)
from .rational_model import RationalModel
from .vector_fitting import VFConfig, VectorFitter, canonical_poles, stabilise_poles

__all__ = [
    "AdaptiveConfig",
    "AdaptiveFitter",
    "RationalModel",
    "VFConfig",
    "VectorFitter",
    "canonical_poles",
    "enforce_asymptotic_passivity",
    "enforce_passivity",
    "passivity_violation",
    "scan_grid",
    "singular_values",
    "stabilise_poles",
]
