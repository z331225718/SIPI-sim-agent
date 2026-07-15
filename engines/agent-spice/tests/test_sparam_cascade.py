import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from agent_spice.sparam.artifacts import write_fitted_touchstone
from agent_spice.sparam.cascade import (
    CascadeBlockSpec,
    CascadeFitConfig,
    _CascadeBlockState,
    _apply_scales,
    _base_coefficients,
    _evaluate_scales,
    _find_adjustment,
    fit_sparam_cascade,
)
from agent_spice.sparam.fitting import SParamFitConfig, _FitExecution, _LightweightSNetwork
from agent_spice.sparam.native_vf import NativeVectorFitting
from agent_spice.sparam.target_fit import SParamFitTarget


def _active_through_state(tmp_path: Path, name: str) -> _CascadeBlockState:
    freqs = np.array([1.0e6, 1.0e7, 1.0e8])
    s = np.zeros((len(freqs), 2, 2), dtype=complex)
    s[:, 0, 1] = 1.01
    s[:, 1, 0] = 1.01
    z0 = np.full((len(freqs), 2), 50.0)
    touchstone = tmp_path / f"{name}.s2p"
    write_fitted_touchstone(touchstone, freqs, s, z0)
    network = _LightweightSNetwork(f=freqs, s=s, z0=z0, name=name)
    vector_fit = NativeVectorFitting(network)
    vector_fit.poles = np.empty(0, dtype=complex)
    vector_fit.residues = np.empty((4, 0), dtype=complex)
    vector_fit.constant_coeff = np.array([0.0, 1.01, 1.01, 0.0])
    vector_fit.proportional_coeff = np.zeros(4)
    result = SimpleNamespace(config=SParamFitConfig())
    execution = _FitExecution(result=result, network=network, vector_fit=vector_fit)
    target = SParamFitTarget(mean_rms=0.05, passivity="enforce", max_order=4)
    directory = tmp_path / name
    return _CascadeBlockState(
        spec=CascadeBlockSpec(name, touchstone, target.mean_rms, target.max_order),
        target=target,
        search_result=None,
        execution=execution,
        directory=directory,
        spice_path=directory / f"{name}.sp",
        report_path=directory / "fit_report.json",
        html_report_path=directory / "fit_report.html",
        log_path=directory / "fit.log",
        fitted_touchstone_path=directory / f"{name}_fitted.s2p",
        rfm_path=directory / f"{name}.rfm",
        rfm_wrapper_path=directory / f"{name}_rfm_wrapper.sp",
    )


def test_cascade_adjustment_finds_minimal_block_contraction(tmp_path: Path):
    states = [_active_through_state(tmp_path, "a"), _active_through_state(tmp_path, "b")]
    config = CascadeFitConfig(
        rms_target=0.05,
        cascade_rms_target=0.05,
        cascade_samples=21,
        cascade_passivity_epsilon=1e-8,
        adjustment_iterations=16,
        minimum_scale=0.9,
    )
    freqs = np.geomspace(1.0e6, 1.0e8, 21)

    scales, diagnostics = _find_adjustment(states, freqs, config)

    assert scales is not None
    assert any(scale < 1.0 for scale in scales)
    assert diagnostics
    assert all(item["cascade_rms_target"] == pytest.approx(0.05) for item in diagnostics)
    assert any(item["cascade_rms_target_met"] is True for item in diagnostics)
    base = _base_coefficients(states)
    _apply_scales(states, base, scales)
    metrics, block_rms, _ = _evaluate_scales(states, base, scales, freqs, config)
    assert metrics["max_sigma"] <= 1.0 + config.cascade_passivity_epsilon
    assert all(item["target_met"] for item in block_rms)


def test_fit_sparam_cascade_writes_block_and_chain_artifacts(tmp_path: Path):
    manifest = Path("tests/fixtures/sparam/cascade_two_through.json")
    output_root = tmp_path / "cascade"

    payload = fit_sparam_cascade(
        manifest,
        output_root,
        config=CascadeFitConfig(
            rms_target=0.2,
            cascade_rms_target=1.0,
            max_order=4,
            cascade_samples=21,
        ),
    )

    assert payload["status"] == "PASS"
    assert payload["blocking_reasons"] == []
    assert payload["cascade_rms_target"] == pytest.approx(1.0)
    assert payload["cascade_rms_target_blocking"] is True
    assert payload["cascade_rms_target_met"] is True
    assert payload["cascade_refit"]["stop_reason"] == "initial_target_met"
    assert payload["cascade_refit"]["iterations"] == []
    assert payload["cascade_order"] == ["first", "second"]
    assert payload["evaluation_scope"] == "intersection_only_no_extrapolation"
    assert Path(payload["cascade_touchstone_path"]).is_file()
    assert (output_root / "cascade_report.json").is_file()
    for block in payload["blocks"]:
        assert Path(block["spice_path"]).is_file()
        assert Path(block["fitted_touchstone_path"]).is_file()
        assert Path(block["rfm_path"]).is_file()
        assert Path(block["rfm_wrapper_path"]).is_file()


def test_cascade_rms_target_blocks_delivery_when_final_chain_misses(tmp_path: Path):
    payload = fit_sparam_cascade(
        Path("tests/fixtures/sparam/cascade_two_through.json"),
        tmp_path / "cascade-rms-fail",
        config=CascadeFitConfig(
            rms_target=0.2,
            cascade_rms_target=1e-12,
            max_order=4,
            cascade_samples=21,
        ),
    )

    assert payload["status"] == "FAIL"
    assert payload["reason"] == "cascade_rms_target_not_met"
    assert payload["blocking_reasons"] == ["cascade_rms_target_not_met"]
    assert payload["cascade_rms_target_met"] is False
    assert payload["cascade_mean_rms_error"] > payload["cascade_rms_target"]
    assert payload["cascade_refit"]["stop_reason"] == "no_refittable_blocks"
    assert payload["cascade_refit"]["iterations"]


def test_cascade_rms_target_refits_high_impact_blocks_until_met(tmp_path: Path):
    payload = fit_sparam_cascade(
        Path("tests/fixtures/sparam/cascade_two_through.json"),
        tmp_path / "cascade-rms-refit",
        config=CascadeFitConfig(
            rms_target=0.2,
            cascade_rms_target=0.1,
            cascade_refit_max_iterations=8,
            max_order=6,
            cascade_samples=21,
        ),
    )

    refit = payload["cascade_refit"]
    assert payload["status"] == "PASS"
    assert payload["cascade_rms_target_met"] is True
    assert refit["enabled"] is True
    assert refit["initial_mean_rms_error"] > payload["cascade_rms_target"]
    assert refit["final_mean_rms_error"] <= payload["cascade_rms_target"]
    assert refit["stop_reason"] == "target_met"
    assert any(item["accepted"] for item in refit["iterations"])
    rejected = [item for item in refit["iterations"] if not item["accepted"]]
    assert all(item["restored_previous_artifacts"] is True for item in rejected)
    assert all(item["rejection_reason"] is not None for item in rejected)
    assert any(
        item["candidate_selected_order"] > item["contributions"][0]["current_order"]
        for item in refit["iterations"]
        if item["accepted"]
    )
    assert all(Path(item["history_path"]).is_dir() for item in refit["iterations"])
    assert sum(block["cascade_refit_count"] for block in payload["blocks"]) == sum(
        1 for item in refit["iterations"] if item["accepted"]
    )
    assert max(block["selected_order"] for block in payload["blocks"]) > 3


def test_zero_cascade_refit_budget_keeps_rms_gate_but_skips_refit(tmp_path: Path):
    payload = fit_sparam_cascade(
        Path("tests/fixtures/sparam/cascade_two_through.json"),
        tmp_path / "cascade-rms-no-refit",
        config=CascadeFitConfig(
            rms_target=0.2,
            cascade_rms_target=0.1,
            cascade_refit_max_iterations=0,
            max_order=6,
            cascade_samples=21,
        ),
    )

    assert payload["status"] == "FAIL"
    assert payload["cascade_rms_target_met"] is False
    assert payload["cascade_refit"]["stop_reason"] == "max_iterations_reached"
    assert payload["cascade_refit"]["iterations"] == []


def test_priority_only_cascade_postchecks_full_band_without_blocking(tmp_path: Path):
    payload = fit_sparam_cascade(
        Path("tests/fixtures/sparam/cascade_two_through.json"),
        tmp_path / "cascade-priority-only",
        config=CascadeFitConfig(
            rms_target=0.2,
            max_order=4,
            cascade_samples=21,
            priority_bands_hz=((1e6, 1e9, 0.2, 1.0),),
            gate_full_band_rms=False,
            priority_band_fit_only=True,
        ),
    )

    assert payload["status"] == "PASS"
    assert payload["evaluation_scope"] == "priority_band_union_only_no_extrapolation"
    assert payload["cascade_rms_target"] is None
    assert payload["cascade_rms_target_blocking"] is False
    assert payload["cascade_rms_target_met"] is None
    assert payload["cascade_refit"]["enabled"] is False
    assert payload["cascade_refit"]["stop_reason"] == "target_not_set"
    assert payload["full_band_postcheck"]["blocking"] is False
    assert payload["full_band_postcheck"]["frequency_range_hz"] == [1e6, 5e9]
    assert all(block["full_band_rms_target"] is None for block in payload["blocks"])


@pytest.mark.parametrize(
    "overrides",
    [
        {"priority_band_fit_only": True},
        {"gate_full_band_rms": False},
    ],
)
def test_cascade_config_rejects_incomplete_priority_only_mode(overrides):
    with pytest.raises(ValueError):
        CascadeFitConfig(rms_target=0.01, **overrides)


@pytest.mark.parametrize("target", [0.0, -1.0, math.inf, math.nan])
def test_cascade_config_rejects_invalid_cascade_rms_target(target):
    with pytest.raises(ValueError):
        CascadeFitConfig(rms_target=0.01, cascade_rms_target=target)


def test_cascade_config_rejects_negative_refit_iteration_limit():
    with pytest.raises(ValueError):
        CascadeFitConfig(
            rms_target=0.01,
            cascade_refit_max_iterations=-1,
        )


def test_fit_sparam_cascade_cli_builds_public_configuration(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    captured = {}

    def fake_fit(manifest, output_root, *, config, report_path=None):
        captured.update(
            manifest=manifest,
            output_root=output_root,
            config=config,
            report_path=report_path,
        )
        return {"status": "PASS"}

    monkeypatch.setattr(cli, "fit_sparam_cascade", fake_fit)
    manifest = tmp_path / "chain.json"
    result = cli.main(
        [
            "fit-sparam-cascade",
            str(manifest),
            "--rms-target",
            "0.01",
            "--priority-band",
            "1e6:2e6:0.005:4",
            "--cascade-samples",
            "101",
            "--cascade-rms-target",
            "0.02",
            "--cascade-refit-iterations",
            "5",
            "--reference-impedance",
            "75",
        ]
    )

    assert result == 0
    assert captured["manifest"] == manifest
    assert captured["output_root"] == manifest.with_name("chain_fit")
    assert captured["config"].priority_bands_hz == ((1e6, 2e6, 0.005, 4.0),)
    assert captured["config"].cascade_samples == 101
    assert captured["config"].cascade_rms_target == pytest.approx(0.02)
    assert captured["config"].cascade_refit_max_iterations == 5
    assert captured["config"].reference_impedance_ohm == 75.0


def test_fit_sparam_cascade_cli_uses_priority_only_mode_without_full_band_target(
    tmp_path: Path,
    monkeypatch,
):
    import agent_spice.cli as cli

    captured = {}

    def fake_fit(manifest, output_root, *, config, report_path=None):
        captured["config"] = config
        return {"status": "PASS"}

    monkeypatch.setattr(cli, "fit_sparam_cascade", fake_fit)
    result = cli.main(
        [
            "fit-sparam-cascade",
            str(tmp_path / "chain.json"),
            "--priority-band",
            "0:1e7:0.001",
        ]
    )

    assert result == 0
    assert captured["config"].rms_target == 0.001
    assert captured["config"].gate_full_band_rms is False
    assert captured["config"].priority_band_fit_only is True
