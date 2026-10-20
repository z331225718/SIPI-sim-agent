"""Tests for the merged adaptive Adding/Skimming search mode.

The default ``native-idem-fast-v1`` ladder is covered by the pre-existing
sparam tests; here we pin the new opt-in backend:

* the adapter keeps the native stored-pole convention and absolute-target
  semantics;
* the merged mode delivers the same product contract as the ladder
  (post-enforcement RMS target, ``max_sigma <= 1 + epsilon``, artifacts,
  report fields);
* the CLI switch selects the backend and forwards the adaptive options;
* the default CLI still uses the ladder.
"""

from pathlib import Path
import json

import numpy as np
import pytest

from agent_spice.sparam.adaptive_search import (
    ADAPTIVE_SEARCH_BACKEND_VERSION,
    AdaptiveSearchConfig,
    discover_poles,
)
from agent_spice.sparam.fitting import (
    SParamFitConfig,
    fit_touchstone_to_spice_adaptive,
)
from agent_spice.sparam.target_fit import SParamFitTarget

PASSIVITY_EPSILON = 1e-6


def _rc_one_port(frequencies=None, resistance=50.0, capacitance=1e-12, z0=50.0):
    """Passive 1-port series-RC S data that is exactly representable by a 2-pole model."""

    if frequencies is None:
        frequencies = np.geomspace(1e6, 1e10, 61)
    impedance = resistance + 1.0 / (1j * 2.0 * np.pi * frequencies * capacitance)
    return np.asarray(frequencies, dtype=float), ((impedance - z0) / (impedance + z0)).reshape(-1, 1, 1)


def _write_touchstone_one_port(path: Path, frequencies: np.ndarray, s_values: np.ndarray) -> Path:
    lines = ["# Hz S RI R 50"]
    for frequency, value in zip(frequencies, s_values.reshape(-1), strict=True):
        lines.append(f"{frequency:.6e} {value.real:.12e} {value.imag:.12e}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# configuration and adapter
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "changes",
    [
        {"target_mean_rms": 0.0},
        {"target_mean_rms": float("nan")},
        {"min_order": 0},
        {"max_order": 2, "min_order": 4},
        {"order_step": 0},
        {"target_margin": 0.0},
        {"target_margin": 1.5},
        {"init_pole_damping": 0.0},
        {"seed_probe_subsample": 0},
    ],
)
def test_adaptive_search_config_rejects_invalid_values(changes):
    kwargs = {"target_mean_rms": 1e-3}
    kwargs.update(changes)
    with pytest.raises(ValueError):
        AdaptiveSearchConfig(**kwargs)


def test_discover_poles_returns_stable_native_convention_poles():
    frequencies, s_values = _rc_one_port()
    config = AdaptiveSearchConfig(
        target_mean_rms=1e-3,
        min_order=2,
        max_order=20,
        order_step=4,
    )
    result = discover_poles(frequencies, s_values, config)

    poles = np.asarray(result.poles)
    assert poles.size == result.order == result.real_pole_count + 2 * result.complex_pair_count
    assert np.all(poles.real < 0.0)
    # Native convention: one positive-imaginary representative per conjugate pair.
    assert not np.any(poles.imag < 0.0)
    assert result.real_pole_count + result.complex_pair_count == poles.size
    # Absolute target semantics: relative target is derived from rms(|S|).
    reference = float(np.sqrt(np.mean(np.abs(s_values) ** 2)))
    assert result.rms_abs_input == pytest.approx(reference, rel=1e-12)
    assert result.target_relative_rms == pytest.approx(1e-3 / reference, rel=1e-12)
    assert np.isfinite(result.absolute_rms)
    assert result.absolute_rms <= 1e-3
    assert 0.0 < result.elapsed_seconds <= 120.0
    assert result.history
    assert result.history[0]["phase"] == "initialization"


# --------------------------------------------------------------------------- #
# model bridge used by the fast passivity backend
# --------------------------------------------------------------------------- #


def test_replica_model_bridge_round_trip_preserves_response(tmp_path: Path):
    import skrf as rf

    from agent_spice.sparam.adaptive_search import (
        apply_replica_model_to_native_vector_fit,
        native_vector_fit_to_replica_model,
    )
    from agent_spice.sparam.artifacts import evaluate_fitted_s
    from agent_spice.sparam.native_vf import NativeVectorFitting

    frequencies, s_values = _rc_one_port()
    touchstone = _write_touchstone_one_port(tmp_path / "rc.s1p", frequencies, s_values)
    network = rf.Network(str(touchstone))
    vector_fit = NativeVectorFitting(network)
    vector_fit.max_iterations = 1
    vector_fit.vector_fit(
        n_poles_real=1,
        n_poles_cmplx=1,
        init_pole_spacing="lin",
        parameter_type="s",
        fit_constant=True,
        fit_proportional=False,
        enforce_dc=False,
    )
    native_response = evaluate_fitted_s(vector_fit, network.f)

    replica_model = native_vector_fit_to_replica_model(vector_fit)
    replica_response = replica_model.evaluate(np.asarray(network.f))
    assert np.allclose(replica_response, native_response, rtol=1e-12, atol=1e-12)

    round_trip = NativeVectorFitting(network)
    round_trip.network = network
    apply_replica_model_to_native_vector_fit(replica_model, round_trip)
    round_trip_response = evaluate_fitted_s(round_trip, network.f)
    assert np.allclose(round_trip_response, native_response, rtol=1e-12, atol=1e-12)


# --------------------------------------------------------------------------- #
# end-to-end merged pipeline on a passive network
# --------------------------------------------------------------------------- #


def test_adaptive_fit_delivers_native_contract_and_artifacts(tmp_path: Path):
    frequencies, s_values = _rc_one_port()
    touchstone = _write_touchstone_one_port(tmp_path / "rc.s1p", frequencies, s_values)
    result = fit_touchstone_to_spice_adaptive(
        touchstone,
        tmp_path / "rc.sp",
        target=SParamFitTarget(
            mean_rms=1e-2,
            passivity="enforce",
            max_order=20,
            max_order_step=4,
            passivity_epsilon=PASSIVITY_EPSILON,
        ),
        config=SParamFitConfig(use_lightweight_network=True),
        search=AdaptiveSearchConfig(
            target_mean_rms=1e-2,
            min_order=2,
            max_order=20,
            order_step=4,
        ),
        report_path=tmp_path / "fit_report.json",
        html_report_path=tmp_path / "fit_report.html",
        fitted_touchstone_path=tmp_path / "rc_fitted.s1p",
        log_path=tmp_path / "fit.log",
    )

    assert result.target_met is True
    assert result.stop_reason == "target_met"
    assert result.selected_trial is not None
    selected = result.selected_trial
    assert selected.final_mean_rms is not None and selected.final_mean_rms <= 1e-2
    assert selected.final_max_sigma is not None
    assert selected.final_max_sigma <= 1.0 + PASSIVITY_EPSILON
    assert selected.effective_order == selected.requested_order == selected.payload.expanded_model_order

    assert (tmp_path / "rc.sp").is_file()
    assert (tmp_path / "rc_fitted.s1p").is_file()
    assert (tmp_path / "fit_report.html").is_file()
    payload = json.loads((tmp_path / "fit_report.json").read_text(encoding="utf-8"))
    assert payload["search_mode"] == "adaptive"
    assert payload["search_backend"] == ADAPTIVE_SEARCH_BACKEND_VERSION
    adaptive = payload["adaptive_search"]
    assert adaptive["backend_version"] == ADAPTIVE_SEARCH_BACKEND_VERSION
    assert adaptive["passivity_backend"] == "idem-replica"
    assert adaptive["native_enforce_dc"] is False
    assert len(adaptive["attempts"]) == len(result.trials)
    assert adaptive["attempts"][0]["pole_search"]["order"] == selected.requested_order
    assert payload["selected_effective_order"] == selected.requested_order
    assert payload.get("order_trials")
    assert "adaptive-search attempt=0" in (tmp_path / "fit.log").read_text(encoding="utf-8")


def test_adaptive_fit_rejects_priority_band_requests(tmp_path: Path):
    frequencies, s_values = _rc_one_port()
    touchstone = _write_touchstone_one_port(tmp_path / "rc.s1p", frequencies, s_values)
    with pytest.raises(ValueError, match="priority band"):
        fit_touchstone_to_spice_adaptive(
            touchstone,
            tmp_path / "rc.sp",
            target=SParamFitTarget(
                mean_rms=1e-2,
                passivity="off",
                max_order=20,
                gate_full_band_rms=False,
                priority_bands_hz=((1e9, 2e9, 1e-2),),
            ),
            search=AdaptiveSearchConfig(target_mean_rms=1e-2, max_order=20, order_step=4),
        )


def test_adaptive_fit_requires_matching_search_target(tmp_path: Path):
    frequencies, s_values = _rc_one_port()
    touchstone = _write_touchstone_one_port(tmp_path / "rc.s1p", frequencies, s_values)
    with pytest.raises(ValueError, match="target_mean_rms"):
        fit_touchstone_to_spice_adaptive(
            touchstone,
            tmp_path / "rc.sp",
            target=SParamFitTarget(mean_rms=1e-2, passivity="off", max_order=20),
            search=AdaptiveSearchConfig(target_mean_rms=1e-3, max_order=20, order_step=4),
        )


# --------------------------------------------------------------------------- #
# passivity backend switch
# --------------------------------------------------------------------------- #


def test_native_fit_config_passivity_backend_defaults_to_native():
    assert SParamFitConfig().passivity_backend == "native"


def test_passivity_hamiltonian_rejects_unknown_backend():
    from agent_spice.sparam.passivity import enforce_passivity_hamiltonian

    class _Dummy:
        network = None

    with pytest.raises(ValueError, match="passivity backend"):
        enforce_passivity_hamiltonian(_Dummy(), nports=1, backend="not-a-backend")


# --------------------------------------------------------------------------- #
# CLI surface
# --------------------------------------------------------------------------- #


class _FakeQualityReport:
    status = "PASS"
    blocking_reasons: list = []
    warnings: list = []


def _fake_search_result():
    from types import SimpleNamespace

    payload = SimpleNamespace(quality_report=_FakeQualityReport())
    return SimpleNamespace(
        target_met=True,
        selected_trial=SimpleNamespace(requested_order=8, payload=payload),
    )


def test_cli_search_mode_adaptive_forwards_options(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    recorded: dict = {}

    def fake_adaptive(touchstone_path, output_path, *, target, config, search, refine_iterations, **kwargs):
        recorded["search"] = search
        recorded["target"] = target
        recorded["refine_iterations"] = refine_iterations
        recorded["kwargs"] = kwargs
        return _fake_search_result()

    def unexpected_ladder(*args, **kwargs):
        raise AssertionError("default ladder backend must not run in adaptive mode")

    monkeypatch.setattr(cli, "fit_touchstone_to_spice_adaptive", fake_adaptive)
    monkeypatch.setattr(cli, "fit_touchstone_to_spice_target", unexpected_ladder)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s2p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--rms-target",
            "0.001",
            "--passivity",
            "enforce",
            "--max-order",
            "60",
            "--search-mode",
            "adaptive",
            "--adaptive-order-step",
            "6",
            "--adaptive-min-order",
            "8",
            "--adaptive-target-margin",
            "0.8",
            "--adaptive-init-pole-damping",
            "0.07",
            "--adaptive-refine-iterations",
            "1",
            "--no-adaptive-seed-probe",
            "--no-adaptive-sk-weighting",
            "--report",
            str(tmp_path / "fit_report.json"),
            "--html-report",
            str(tmp_path / "fit_report.html"),
            "--log",
            str(tmp_path / "fit.log"),
        ]
    )

    assert exit_code == 0
    search = recorded["search"]
    assert isinstance(search, AdaptiveSearchConfig)
    assert search.target_mean_rms == pytest.approx(0.001)
    assert search.max_order == 60
    assert search.min_order == 8
    assert search.order_step == 6
    assert search.target_margin == pytest.approx(0.8)
    assert search.init_pole_damping == pytest.approx(0.07)
    assert search.seed_probe is False
    assert search.sk_weighting is False
    assert recorded["refine_iterations"] == 1
    assert recorded["target"].passivity == "enforce"
    assert recorded["kwargs"]["report_path"] == tmp_path / "fit_report.json"
    assert recorded["kwargs"]["fitted_touchstone_path"] is not None


def test_cli_search_mode_default_stays_on_ladder(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    recorded: dict = {}

    def fake_ladder(touchstone_path, output_path, **kwargs):
        recorded["called"] = True
        return _fake_search_result()

    def unexpected_adaptive(*args, **kwargs):
        raise AssertionError("adaptive backend must not run without --search-mode adaptive")

    monkeypatch.setattr(cli, "fit_touchstone_to_spice_target", fake_ladder)
    monkeypatch.setattr(cli, "fit_touchstone_to_spice_adaptive", unexpected_adaptive)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s2p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--rms-target",
            "0.001",
        ]
    )

    assert exit_code == 0
    assert recorded["called"] is True


def test_cli_adaptive_rejects_priority_band(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    def unexpected_adaptive(*args, **kwargs):
        raise AssertionError("priority bands must be rejected before the backend runs")

    monkeypatch.setattr(cli, "fit_touchstone_to_spice_adaptive", unexpected_adaptive)
    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s2p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--rms-target",
            "0.001",
            "--priority-band",
            "1000000:2000000000:0.001",
            "--search-mode",
            "adaptive",
        ]
    )
    assert exit_code == 1
