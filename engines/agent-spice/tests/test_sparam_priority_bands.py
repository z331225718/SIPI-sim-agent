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
        priority_bands_hz=((7.0, 9.0, 1.0),),
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
        priority_bands_hz=((3.0, 4.0, 2.0),),
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
        priority_bands_hz=((3.0, 4.0, 1.0),),
        outside_band_weight=0.1,
    )

    metrics = _comparison_frequency_metrics(network, vector_fit, config)

    assert metrics is not None
    assert metrics["priority_mean_rms_error"] == pytest.approx(0.1)
    assert metrics["outside_mean_rms_error"] == pytest.approx(1.0)
    assert metrics["weighted_mean_rms_error"] < 0.5


def test_target_order_trial_uses_priority_target_metric_when_available():
    fit_result = SimpleNamespace(
        expanded_model_order=4,
        target_mean_rms_error=0.01,
        comparison_mean_rms_error=0.2,
        pre_enforcement_target_mean_rms_error=0.01,
        passivity_max_sigma_before=None,
        passivity_max_sigma_after=None,
        constant_matrix_sigma=None,
        passive_after_enforce=None,
        passivity_enforcement_skip_reason=None,
        fit_frequency_points=10,
        frequency_points=20,
    )

    trial = trial_from_fit_result(
        SParamFitTarget(mean_rms=0.02, passivity="off", max_order=4),
        fit_result,
        requested_order=4,
    )

    assert trial.target_met is True
    assert trial.final_mean_rms == pytest.approx(0.01)


def test_priority_band_validation_rejects_empty_band():
    with pytest.raises(ValueError, match="contains no frequency samples"):
        _frequency_fit_weights(
            np.array([1.0, 2.0]),
            SParamFitConfig(priority_bands_hz=((3.0, 4.0, 1.0),)),
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
            "--rms-target",
            "0.01",
            "--priority-band",
            "1e6:2e6:3",
            "--priority-band",
            "4e6:5e6",
            "--outside-band-weight",
            "0.2",
        ]
    )

    assert result == 0
    config = captured["config"]
    assert config.priority_bands_hz == ((1e6, 2e6, 3.0), (4e6, 5e6, 1.0))
    assert config.outside_band_weight == 0.2
