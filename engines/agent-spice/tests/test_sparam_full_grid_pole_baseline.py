from pathlib import Path

import numpy as np

import scripts.sparam_full_grid_pole_baseline as baseline
from scripts.sparam_passivity_source_attribution import FitCaseModel, RawTouchstone


IDEM_TEST_POLES = np.array(
    [
        -2.0 * np.pi * 1.0e6,
        -2.0 * np.pi * 4.0e6,
        -2.0 * np.pi * 20.0e6 + 1j * 2.0 * np.pi * 1.4e9,
        -2.0 * np.pi * 25.0e6 + 1j * 2.0 * np.pi * 1.9e9,
    ],
    dtype=complex,
)


def fake_raw(*, points: int) -> RawTouchstone:
    return RawTouchstone(
        path=Path("Test16.s91p"),
        freqs_hz=np.linspace(1.0e6, 3.0e9, points),
        s=np.zeros((points, 1, 1), dtype=complex),
        nports=1,
    )


def fake_model(*, fit_points: int) -> FitCaseModel:
    return FitCaseModel(
        poles=np.array(
            [
                -2.0 * np.pi * 1.0e6,
                -2.0 * np.pi * 4.0e6,
                -2.0 * np.pi * 20.0e6 + 1j * 2.0 * np.pi * 1.4e9,
                -2.0 * np.pi * 25.0e6 + 1j * 2.0 * np.pi * 1.9e9,
                -2.0 * np.pi * 30.0e6 + 1j * 2.0 * np.pi * 2.3e9,
            ],
            dtype=complex,
        ),
        residues=np.zeros((1, 5), dtype=complex),
        constant_coeff=np.zeros(1, dtype=complex),
        fit_points=fit_points,
        fit_elapsed_seconds=12.5,
        pole_relocation_history=[],
    )


def fake_refit(raw, poles, *, parameter_type, fit_max_frequency_points, rcond):
    assert parameter_type == "s"
    assert fit_max_frequency_points is None
    assert rcond is None
    return fake_model(fit_points=len(raw.freqs_hz))


def fake_measure(model, raw):
    return {
        "mean_rms": 0.0019,
        "max_sigma": 1.009,
        "evaluation_frequency_points": len(raw.freqs_hz),
    }


def test_baseline_runs_256_and_full_grid(monkeypatch, tmp_path):
    seen = []

    def fake_build(raw, recipe):
        seen.append(recipe.fit_max_frequency_points)
        return fake_model(fit_points=256 if recipe.fit_max_frequency_points == 256 else 611)

    monkeypatch.setattr(baseline, "load_raw_touchstone", lambda path: fake_raw(points=611))
    monkeypatch.setattr(baseline, "build_native_model", fake_build)
    monkeypatch.setattr(baseline, "load_idem_poles", lambda path: IDEM_TEST_POLES)
    monkeypatch.setattr(baseline, "fit_fixed_pole_residues", fake_refit)
    monkeypatch.setattr(baseline, "measure_model", fake_measure)

    result = baseline.run_full_grid_pole_baseline(
        touchstone_path=tmp_path / "Test16.s91p",
        idem_model_path=tmp_path / "model.mod.h5",
        output_dir=tmp_path / "out",
    )

    assert seen == [256, None]
    assert result["cases"]["native_256"]["training_frequency_points"] == 256
    assert result["cases"]["native_full_grid"]["training_frequency_points"] == 611
    assert result["reference_grid"]["evaluation_frequency_points"] == 611


def test_baseline_preserves_trained_metrics_and_uses_idem_only_as_oracle(monkeypatch, tmp_path):
    raw = fake_raw(points=611)
    trained = fake_model(fit_points=256)
    seen_refit_poles = []

    def fake_refit_with_tracking(raw_arg, poles, **kwargs):
        seen_refit_poles.append(np.asarray(poles, dtype=complex))
        return fake_model(fit_points=len(raw_arg.freqs_hz))

    def distinct_measure(model, raw_arg):
        return {
            "mean_rms": 0.001 if model.fit_points == 256 else 0.002,
            "max_sigma": 1.009,
        }

    monkeypatch.setattr(baseline, "load_raw_touchstone", lambda path: raw)
    monkeypatch.setattr(baseline, "build_native_model", lambda raw_arg, recipe: trained)
    monkeypatch.setattr(baseline, "load_idem_poles", lambda path: IDEM_TEST_POLES)
    monkeypatch.setattr(baseline, "fit_fixed_pole_residues", fake_refit_with_tracking)
    monkeypatch.setattr(baseline, "measure_model", distinct_measure)

    result = baseline.run_full_grid_pole_baseline(
        touchstone_path=tmp_path / "Test16.s91p",
        idem_model_path=tmp_path / "model.mod.h5",
        output_dir=tmp_path / "out",
    )

    case = result["cases"]["native_256"]
    assert case["trained_model_metrics"]["mean_rms"] == 0.001
    assert case["full_grid_residue_refit_metrics"]["mean_rms"] == 0.002
    assert sum(np.array_equal(poles, trained.poles) for poles in seen_refit_poles) == 2
    assert sum(np.array_equal(poles, IDEM_TEST_POLES) for poles in seen_refit_poles) == 1
    assert result["idem_oracle"]["full_grid_residue_refit_metrics"]["mean_rms"] == 0.002
    assert result["oracle_policy"] == "IdEM poles are oracle-only and were not supplied to native fitting."


def test_full_grid_gate_requires_accuracy_passivity_and_order():
    assert baseline.decide_full_grid_baseline(
        mean_rms=0.0019,
        max_sigma=1.009,
        effective_order=10,
    )["stop_before_d11"] is True
    assert baseline.decide_full_grid_baseline(
        mean_rms=0.0021,
        max_sigma=1.009,
        effective_order=10,
    )["stop_before_d11"] is False
