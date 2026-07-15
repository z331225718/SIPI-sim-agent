import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from agent_spice.sparam.fitting import (
    SParamFitConfig,
    _LightweightSNetwork,
    _comparison_frequency_metrics,
    _create_vector_fitting,
    _frequency_fit_weights,
    _select_fit_network,
)
from agent_spice.sparam.native_vf import NativeVectorFitting
from agent_spice.sparam.target_fit import SParamFitTarget, trial_from_fit_result


def test_priority_band_weights_and_sampling_favor_selected_frequency_range():
    network = _LightweightSNetwork(
        f=np.arange(10, dtype=float),
        s=np.zeros((10, 1, 1), dtype=complex),
        z0=np.full((10, 1), 50.0),
    )
    config = SParamFitConfig(
        fit_max_frequency_points=4,
        priority_bands_hz=((7.0, 9.0, 0.01, 1.0),),
        outside_band_weight=0.05,
    )

    weights = _frequency_fit_weights(network.f, config)
    selected = _select_fit_network(network, config)

    np.testing.assert_allclose(weights[:7], 0.05)
    np.testing.assert_allclose(weights[7:], 1.0)
    assert len(selected.f) == 4
    assert sum(value >= 7.0 for value in selected.f) >= 2
    assert selected.f[0] == 0.0
    assert selected.f[-1] == 9.0


def test_priority_band_weights_are_applied_to_native_residue_fit():
    network = _LightweightSNetwork(
        f=np.array([1.0, 2.0, 3.0, 4.0]),
        s=np.zeros((4, 2, 2), dtype=complex),
        z0=np.full((4, 2), 50.0),
    )
    config = SParamFitConfig(
        priority_bands_hz=((3.0, 4.0, 0.01, 2.0),),
        outside_band_weight=0.25,
    )

    vector_fit = _create_vector_fitting(network, config)

    np.testing.assert_allclose(vector_fit.frequency_fit_weights, [0.25, 0.25, 2.0, 2.0])
    assert vector_fit.residue_response_weights.shape == (4, 4)
    np.testing.assert_allclose(vector_fit.residue_response_weights[3], [0.25, 0.25, 2.0, 2.0])


def test_priority_band_report_keeps_global_outside_and_target_rms_separate():
    network = _LightweightSNetwork(
        f=np.array([1.0, 2.0, 3.0, 4.0]),
        s=np.array([1.0, 1.0, 0.1, 0.1], dtype=complex).reshape(4, 1, 1),
        z0=np.full((4, 1), 50.0),
    )
    vector_fit = NativeVectorFitting(network)
    vector_fit.poles = np.empty(0, dtype=complex)
    vector_fit.residues = np.empty((1, 0), dtype=complex)
    vector_fit.constant_coeff = np.zeros(1)
    vector_fit.proportional_coeff = np.zeros(1)
    config = SParamFitConfig(
        priority_bands_hz=((3.0, 4.0, 0.2, 1.0),),
        outside_band_weight=0.1,
    )

    metrics = _comparison_frequency_metrics(network, vector_fit, config)

    assert metrics is not None
    assert metrics["priority_mean_rms_error"] == pytest.approx(0.1)
    assert metrics["outside_mean_rms_error"] == pytest.approx(1.0)
    assert metrics["weighted_mean_rms_error"] < 0.5
    assert metrics["bands"][0]["rms_target"] == pytest.approx(0.2)
    assert metrics["bands"][0]["target_met"] is True


def test_target_order_trial_requires_priority_and_full_band_targets():
    fit_result = SimpleNamespace(
        expanded_model_order=4,
        target_mean_rms_error=0.01,
        comparison_mean_rms_error=0.02,
        pre_enforcement_target_mean_rms_error=0.01,
        pre_enforcement_mean_rms_error=0.02,
        config=SParamFitConfig(priority_bands_hz=((3.0, 4.0, 0.01, 1.0),)),
        frequency_band_metrics=[{"mean_rms_error": 0.01}],
        passivity_max_sigma_before=None,
        passivity_max_sigma_after=None,
        constant_matrix_sigma=None,
        passive_after_enforce=None,
        passivity_enforcement_skip_reason=None,
        fit_frequency_points=10,
        frequency_points=20,
    )

    trial = trial_from_fit_result(
        SParamFitTarget(
            mean_rms=0.03,
            passivity="off",
            max_order=4,
            priority_bands_hz=((3.0, 4.0, 0.01),),
        ),
        fit_result,
        requested_order=4,
    )

    assert trial.target_met is True
    assert trial.final_mean_rms == pytest.approx(0.02)
    assert trial.full_band_rms_target == pytest.approx(0.03)
    assert trial.priority_band_mean_rms_errors == pytest.approx((0.01,))
    assert trial.priority_band_rms_targets == pytest.approx((0.01,))


def test_target_order_trial_rejects_full_band_regression_even_when_priority_band_passes():
    fit_result = SimpleNamespace(
        expanded_model_order=4,
        comparison_mean_rms_error=0.031,
        pre_enforcement_mean_rms_error=0.031,
        config=SParamFitConfig(priority_bands_hz=((3.0, 4.0, 0.01, 1.0),)),
        frequency_band_metrics=[{"mean_rms_error": 0.009}],
        passivity_max_sigma_before=None,
        passivity_max_sigma_after=None,
        constant_matrix_sigma=None,
        passive_after_enforce=None,
        passivity_enforcement_skip_reason=None,
        fit_frequency_points=10,
        frequency_points=20,
    )

    trial = trial_from_fit_result(
        SParamFitTarget(
            mean_rms=0.03,
            passivity="off",
            max_order=4,
            priority_bands_hz=((3.0, 4.0, 0.01),),
        ),
        fit_result,
        requested_order=4,
    )

    assert trial.target_met is False
    assert trial.rejection_reason == "full_band_rms_above_target"


def test_target_order_trial_rejects_priority_band_when_full_band_passes():
    fit_result = SimpleNamespace(
        expanded_model_order=4,
        comparison_mean_rms_error=0.02,
        pre_enforcement_mean_rms_error=0.02,
        config=SParamFitConfig(priority_bands_hz=((3.0, 4.0, 0.01, 1.0),)),
        frequency_band_metrics=[{"mean_rms_error": 0.011}],
        passivity_max_sigma_before=None,
        passivity_max_sigma_after=None,
        constant_matrix_sigma=None,
        passive_after_enforce=None,
        passivity_enforcement_skip_reason=None,
        fit_frequency_points=10,
        frequency_points=20,
    )

    trial = trial_from_fit_result(
        SParamFitTarget(
            mean_rms=0.03,
            passivity="off",
            max_order=4,
            priority_bands_hz=((3.0, 4.0, 0.01),),
        ),
        fit_result,
        requested_order=4,
    )

    assert trial.target_met is False
    assert trial.rejection_reason == "priority_band_rms_above_target"


def test_priority_band_validation_rejects_empty_band():
    with pytest.raises(ValueError, match="contains no frequency samples"):
        _frequency_fit_weights(
            np.array([1.0, 2.0]),
            SParamFitConfig(priority_bands_hz=((3.0, 4.0, 0.01, 1.0),)),
        )


def test_fit_sparam_cli_passes_priority_band_configuration(tmp_path, monkeypatch):
    import agent_spice.cli as cli

    captured = {}

    def fake_target(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            target_met=True,
            selected_trial=SimpleNamespace(requested_order=4, payload=None),
        )

    monkeypatch.setattr(cli, "fit_touchstone_to_spice_target", fake_target)
    result = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "input.s2p"),
            "--priority-band",
            "1e6:2e6:0.003:3",
            "--priority-band",
            "4e6:5e6:0.005",
            "--outside-band-weight",
            "0.2",
        ]
    )

    assert result == 0
    config = captured["config"]
    assert config.priority_bands_hz == (
        (1e6, 2e6, 0.003, 3.0),
        (4e6, 5e6, 0.005, 1.0),
    )
    assert config.outside_band_weight == 0.2
    assert captured["target"].mean_rms == pytest.approx(0.003)
    assert captured["target"].gate_full_band_rms is False
    assert config.priority_band_fit_only is True


def test_fit_sparam_cli_explicit_rms_target_is_full_band_gate(tmp_path, monkeypatch):
    import agent_spice.cli as cli

    captured = {}

    def fake_target(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            target_met=True,
            selected_trial=SimpleNamespace(requested_order=4, payload=None),
        )

    monkeypatch.setattr(cli, "fit_touchstone_to_spice_target", fake_target)
    result = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "input.s2p"),
            "--rms-target",
            "0.002",
            "--priority-band",
            "0:1e7:0.001",
        ]
    )

    assert result == 0
    assert captured["target"].mean_rms == pytest.approx(0.002)
    assert captured["target"].gate_full_band_rms is True
    assert captured["config"].priority_band_fit_only is False


def test_fit_sparam_cli_rejects_priority_band_without_rms_target(tmp_path, capsys):
    import agent_spice.cli as cli

    result = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "input.s2p"),
            "--priority-band",
            "0:1e7",
        ]
    )

    assert result == 1
    assert "F_MIN:F_MAX:RMS_TARGET" in capsys.readouterr().err


def test_priority_only_mode_fits_selected_band_and_postchecks_full_band(tmp_path: Path):
    import agent_spice.cli as cli

    output = tmp_path / "priority-only" / "model.sp"
    result = cli.main(
        [
            "fit-sparam",
            "tests/fixtures/sparam/simple_through.s2p",
            "--output",
            str(output),
            "--priority-band",
            "1e6:1e9:0.2",
            "--passivity",
            "off",
            "--max-order",
            "4",
            "--max-order-step",
            "1",
        ]
    )

    assert result == 0
    report = json.loads((output.parent / "fit_report.json").read_text(encoding="utf-8"))
    assert report["priority_band_fit_mode"] == "priority_only_full_band_postcheck"
    assert report["full_band_rms_target"] is None
    assert report["full_band_rms_blocking"] is False
    assert report["passivity_frequency_scope"] == "zero_to_highest_priority_frequency"
    assert report["passivity_reference_sample_scope"] == "priority_band_samples"
    assert report["full_band_postcheck"] == {
        "blocking": False,
        "calculation_stage": "post_fit",
        "frequency_range_hz": [1e6, 5e9],
        "frequency_points": 5,
        "mean_rms_error": report["comparison_mean_rms_error"],
    }
    assert report["fit_frequency_points"] == 4
    assert report["frequency_points"] == 5
    assert report["frequency_band_metrics"][0]["target_met"] is True
    assert report["comparison_mean_rms_error"] > report["frequency_band_metrics"][0]["rms_target"]


def test_guarded_mode_falls_back_when_priority_candidate_is_worse(tmp_path: Path):
    import agent_spice.cli as cli

    output = tmp_path / "guarded" / "model.sp"
    result = cli.main(
        [
            "fit-sparam",
            "tests/fixtures/sparam/simple_through.s2p",
            "--output",
            str(output),
            "--rms-target",
            "0.2",
            "--priority-band",
            "1e6:1e9:0.2",
            "--passivity",
            "off",
            "--max-order",
            "4",
            "--max-order-step",
            "1",
        ]
    )

    assert result == 0
    report = json.loads((output.parent / "fit_report.json").read_text(encoding="utf-8"))
    selection = report["candidate_selection"]
    assert report["priority_band_fit_mode"] == "baseline_vs_priority_guarded"
    assert report["full_band_rms_target"] == pytest.approx(0.2)
    assert report["full_band_rms_blocking"] is True
    assert report["passivity_frequency_scope"] == "zero_to_full_input_max_frequency"
    assert report["passivity_reference_sample_scope"] == "full_input_samples"
    assert report["full_band_postcheck"] is None
    assert selection["selected_candidate"] == "baseline"
    assert selection["priority_improved_every_band"] is False
    assert (
        selection["priority"]["priority_band_mean_rms_errors"][0]
        > selection["baseline"]["priority_band_mean_rms_errors"][0]
    )
