"""Adaptive Adding/Skimming pole discovery (merged IdEM-replica backend).

This module is the single adapter between the vendored
:mod:`agent_spice.sparam._idem_sk` pole-discovery core and our production
S-parameter fit pipeline.  It answers exactly one question:

    Given a Touchstone measurement, at which shared poles should the native
    residue solve be performed?

The order search is the ``idem_replica`` Adding/Skimming algorithm (the
mechanism that measured ~60x faster than our order ladder on the 30-port PDN
corpus).  Everything downstream stays native: the D/DC-constrained residue
solve, the strictly passive enforcement (``max_sigma <= 1 + epsilon``), the
quality report, the JSON/HTML report and the SPICE/Touchstone/RFM artifacts.
This keeps our signoff contract intact while replacing the weak link, which the
project retrospective identified as pole discovery / search efficiency.

Semantics that matter:

* ``AdaptiveSearchConfig.target_mean_rms`` is an **absolute** mean S-RMS bar,
  matching IdEM and ``fit-sparam --rms-target``.  The vendored engine's
  ``target_tol`` is *relative*; the conversion is
  ``target_tol = target_mean_rms / rms(|S|_input)``.
* ``target_margin`` < 1 asks the search for headroom below the absolute bar so
  that passivity enforcement cannot push the delivered model over it.
* The returned poles use our native stored-pole convention: real poles plus
  one positive-imaginary representative per conjugate pair, in rad/s.  The
  replica's canonical form stores both members of each pair; the adapter
  reduces it.

The default fit path never imports this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import Any

import numpy as np

from ._idem_sk import AdaptiveConfig, AdaptiveFitter, VFConfig
from .adaptive_config import AdaptiveSearchConfig


#: Bumped whenever the vendored snapshot or the adapter mapping changes.
ADAPTIVE_SEARCH_BACKEND_VERSION = "idem-replica-sk-v1"


@dataclass
class AdaptivePoleSearchResult:
    """Outcome of one adaptive pole-discovery run."""

    poles: np.ndarray
    order: int
    absolute_rms: float
    relative_rms: float
    target_relative_rms: float
    rms_abs_input: float
    history: list[dict[str, Any]] = field(default_factory=list)
    seed_kind: str | None = None
    seed_probe_seconds: float = 0.0
    elapsed_seconds: float = 0.0
    backend_version: str = ADAPTIVE_SEARCH_BACKEND_VERSION
    config: AdaptiveSearchConfig | None = None

    @property
    def real_pole_count(self) -> int:
        return int(np.count_nonzero(np.abs(np.asarray(self.poles).imag) <= 1e-10))

    @property
    def complex_pair_count(self) -> int:
        return int(np.asarray(self.poles).size - self.real_pole_count)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend_version,
            "order": int(self.order),
            "real_pole_count": int(self.real_pole_count),
            "complex_pair_count": int(self.complex_pair_count),
            "absolute_rms": float(self.absolute_rms),
            "relative_rms": float(self.relative_rms),
            "target_relative_rms": float(self.target_relative_rms),
            "rms_abs_input": float(self.rms_abs_input),
            "seed_kind": self.seed_kind,
            "seed_probe_seconds": float(self.seed_probe_seconds),
            "elapsed_seconds": float(self.elapsed_seconds),
            "history": list(self.history),
        }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    return value


def _native_poles_from_model(model: Any) -> tuple[np.ndarray, int]:
    """Reduce the replica's canonical pole set to our stored-pole convention."""

    poles = np.asarray(model.poles, dtype=complex).reshape(-1)
    if poles.size == 0:
        raise ValueError("adaptive pole search returned no poles")
    if not np.all(np.isfinite(poles)):
        raise ValueError("adaptive pole search returned non-finite poles")
    tolerance = 1e-10 * np.maximum(1.0, np.abs(poles))
    real_mask = np.abs(poles.imag) <= tolerance
    real_poles = poles[real_mask].real.astype(complex)
    complex_poles = poles[~real_mask]
    positive = complex_poles[complex_poles.imag > 0.0]
    negative = complex_poles[complex_poles.imag < 0.0]
    if positive.size != negative.size:
        raise ValueError(
            "adaptive pole search returned an unpaired complex pole set "
            f"({positive.size} positive vs {negative.size} negative)"
        )
    native_poles = np.concatenate([real_poles, positive])
    order = int(real_poles.size + 2 * positive.size)
    if order != int(model.n_poles):
        raise ValueError(
            f"adaptive pole accounting mismatch: reduced order {order} != engine order {model.n_poles}"
        )
    if np.any(native_poles.real >= 0.0):
        raise ValueError("adaptive pole search returned an unstable pole")
    return native_poles, order


def discover_poles(
    frequencies_hz: Any,
    s_matrix: Any,
    config: AdaptiveSearchConfig,
    *,
    rms_abs_input: float | None = None,
) -> AdaptivePoleSearchResult:
    """Run the merged Adding/Skimming search and return native-convention poles.

    Parameters
    ----------
    frequencies_hz:
        One-dimensional frequency grid in Hz (as stored in the Touchstone file).
    s_matrix:
        ``(F, P, P)`` complex S data on that grid.
    config:
        Search settings.  ``target_mean_rms`` is absolute.
    rms_abs_input:
        Optional pre-computed ``sqrt(mean(|S|^2))``; computed when omitted.
    """

    frequencies = np.asarray(frequencies_hz, dtype=float).ravel()
    data = np.asarray(s_matrix, dtype=complex)
    if frequencies.size < 4:
        raise ValueError("adaptive pole search needs at least four frequency points")
    if data.ndim != 3 or data.shape[0] != frequencies.size or data.shape[1] != data.shape[2]:
        raise ValueError("s_matrix must have shape (frequency, port, port) matching frequencies_hz")
    if not np.all(np.isfinite(frequencies)) or not np.all(np.isfinite(data)):
        raise ValueError("frequencies_hz and s_matrix must be finite")
    if frequencies.size > 1 and np.any(np.diff(frequencies) <= 0.0):
        raise ValueError("frequencies_hz must be strictly increasing")

    reference = (
        float(rms_abs_input)
        if rms_abs_input is not None
        else float(np.sqrt(np.mean(np.abs(data) ** 2)))
    )
    if not math.isfinite(reference) or reference <= 0.0:
        raise ValueError("input S-parameter RMS must be finite and > 0")
    relative_target = float(config.target_margin) * float(config.target_mean_rms) / reference
    if not math.isfinite(relative_target) or relative_target <= 0.0:
        raise ValueError("derived relative target must be finite and > 0")

    vector_fit_config = VFConfig(
        init_pole_damping=float(config.init_pole_damping),
        seed_probe=bool(config.seed_probe),
        seed_probe_iters=int(config.seed_probe_iters),
        seed_probe_subsample=int(config.seed_probe_subsample),
        sk_weighting=bool(config.sk_weighting),
    )
    adaptive_config = AdaptiveConfig(
        target_tol=relative_target,
        min_order=int(config.min_order),
        max_order=int(config.max_order),
        order_step=int(config.order_step),
        enforce_dc=bool(config.enforce_dc),
        vf_config=vector_fit_config,
    )

    started = time.perf_counter()
    fitter = AdaptiveFitter(adaptive_config)
    model = fitter.fit(frequencies, data)
    elapsed = time.perf_counter() - started

    fitted = np.asarray(model.evaluate(frequencies), dtype=complex)
    absolute_rms = float(np.sqrt(np.mean(np.abs(fitted - data) ** 2)))
    relative_rms = absolute_rms / reference
    native_poles, order = _native_poles_from_model(model)
    return AdaptivePoleSearchResult(
        poles=native_poles,
        order=order,
        absolute_rms=absolute_rms,
        relative_rms=relative_rms,
        target_relative_rms=relative_target,
        rms_abs_input=reference,
        history=[_json_safe(item) for item in fitter.history],
        seed_kind=getattr(fitter, "seed_kind_", None),
        seed_probe_seconds=float(getattr(fitter, "seed_probe_seconds_", 0.0)),
        elapsed_seconds=elapsed,
        config=config,
    )


# --------------------------------------------------------------------------- #
# Model bridging for the fast IdEM-replica passivity enforcement
# --------------------------------------------------------------------------- #
#
# The native ``NativeVectorFitting`` stores one positive-imaginary representative
# per conjugate pair and a ``(ports*ports, poles)`` residue matrix; the vendored
# replica stores both members of every pair and a ``(poles, ports, ports)``
# residue tensor.  These two helpers convert between the layouts losslessly so
# the fast Hildreth-QP enforcement can run on a native model and its result can
# be written back into the native object.


def _vector_fit_port_count(vector_fit: Any) -> int:
    network = getattr(vector_fit, "network", None)
    ports = getattr(network, "nports", None)
    if isinstance(ports, (int, np.integer)) and not isinstance(ports, (bool, np.bool_)) and int(ports) > 0:
        return int(ports)
    constant = np.asarray(getattr(vector_fit, "constant_coeff", None), dtype=complex).reshape(-1)
    root = int(round(np.sqrt(constant.size)))
    if root <= 0 or root * root != constant.size:
        raise ValueError("native vector-fit coefficients do not describe a square S-matrix")
    return root


def native_vector_fit_to_replica_model(vector_fit: Any) -> Any:
    """Convert a native ``NativeVectorFitting`` into the vendored model type."""

    from ._idem_sk import RationalModel as ReplicaRationalModel

    ports = _vector_fit_port_count(vector_fit)
    poles = np.asarray(getattr(vector_fit, "poles", None), dtype=complex).reshape(-1)
    residues = np.asarray(getattr(vector_fit, "residues", None), dtype=complex)
    constant = np.asarray(getattr(vector_fit, "constant_coeff", None), dtype=complex).reshape(-1)
    if poles.size == 0:
        raise ValueError("native vector fit has no poles")
    if residues.shape != (ports * ports, poles.size):
        raise ValueError("native vector-fit residues must have shape (ports*ports, poles)")
    if constant.size != ports * ports:
        raise ValueError("native vector-fit constant coefficients have invalid length")

    full_poles: list[complex] = []
    full_residues: list[np.ndarray] = []
    for index, pole in enumerate(poles):
        entry = residues[:, index].reshape(ports, ports)
        tolerance = 1e-10 * max(1.0, abs(pole))
        if abs(pole.imag) <= tolerance:
            full_poles.append(complex(float(pole.real), 0.0))
            full_residues.append(entry)
        else:
            full_poles.extend((complex(pole), complex(np.conj(pole))))
            full_residues.extend((entry, np.conj(entry)))
    model = ReplicaRationalModel(
        poles=np.asarray(full_poles, dtype=complex),
        residues=np.asarray(full_residues, dtype=complex),
        d=np.asarray(constant, dtype=complex).reshape(ports, ports),
    )
    return model


def apply_replica_model_to_native_vector_fit(model: Any, vector_fit: Any) -> None:
    """Write a vendored model back into a native ``NativeVectorFitting`` object."""

    ports = int(model.n_ports)
    poles = np.asarray(model.poles, dtype=complex).reshape(-1)
    residues = np.asarray(model.residues, dtype=complex)
    if residues.shape != (poles.size, ports, ports):
        raise ValueError("replica residues must have shape (poles, ports, ports)")
    tolerance = 1e-10 * np.maximum(1.0, np.abs(poles))
    real_mask = np.abs(poles.imag) <= tolerance
    positive = (~real_mask) & (poles.imag > 0.0)
    selected = np.flatnonzero(real_mask | positive)
    if selected.size == 0:
        raise ValueError("replica model returned no poles")
    native_poles = poles[selected].astype(complex)
    native_residues = np.stack(
        [residues[index].reshape(ports * ports) for index in selected],
        axis=1,
    )
    vector_fit.poles = native_poles
    vector_fit.residues = native_residues
    vector_fit.constant_coeff = np.asarray(model.d, dtype=complex).reshape(ports * ports)
    vector_fit.proportional_coeff = np.zeros(ports * ports, dtype=complex)


def enforce_passivity_with_idem_replica(
    vector_fit: Any,
    *,
    nports: int,
    epsilon: float,
    f_max: float | None = None,
) -> dict[str, Any]:
    """Fast Hildreth-QP residue enforcement from the vendored IdEM replica.

    The enforcement target is ``sigma_max <= 1 - margin`` with
    ``margin = max(epsilon, 1e-7)``, i.e. strictly *below* unity, so the native
    Hamiltonian audit that runs afterwards (with its own ``1 + epsilon``
    contract) has headroom.  The delivered RMS change is small because the
    replica QP moves residues by the minimum-norm amount.
    """

    from ._idem_sk import enforce_passivity as replica_enforce_passivity
    from ._idem_sk import passivity_violation as replica_passivity_violation

    if int(nports) <= 0:
        raise ValueError("nports must be positive")
    if not math.isfinite(float(epsilon)) or float(epsilon) <= 0.0:
        raise ValueError("epsilon must be finite and > 0")
    network = getattr(vector_fit, "network", None)
    frequencies = np.asarray(getattr(network, "f", None), dtype=float).ravel()
    if frequencies.size == 0:
        raise ValueError("passivity enforcement needs the fitted frequency grid")

    model = native_vector_fit_to_replica_model(vector_fit)
    if model.n_ports != int(nports):
        raise ValueError("nports does not match the model port count")
    margin = max(float(epsilon), 1e-7)
    enforced = replica_enforce_passivity(model, frequencies, margin=margin, max_iter=20)
    apply_replica_model_to_native_vector_fit(enforced, vector_fit)
    violation = float(replica_passivity_violation(enforced, frequencies))
    meta = dict(enforced.meta or {})
    meta["backend"] = "idem-replica"
    meta["requested_margin"] = margin
    meta["fitted_grid_violation"] = violation
    return meta


__all__ = [
    "ADAPTIVE_SEARCH_BACKEND_VERSION",
    "AdaptivePoleSearchResult",
    "AdaptiveSearchConfig",
    "apply_replica_model_to_native_vector_fit",
    "discover_poles",
    "enforce_passivity_with_idem_replica",
    "native_vector_fit_to_replica_model",
]
