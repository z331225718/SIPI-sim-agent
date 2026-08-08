from pathlib import Path
import json

import numpy as np
import pytest

import scripts.sparam_passivity_source_attribution as attribution


def test_source_attribution_writes_auditable_summary(tmp_path: Path, monkeypatch):
    touchstone = tmp_path / "Test16.s91p"
    touchstone.write_text("placeholder", encoding="utf-8")
    idem_model = tmp_path / "idem_order8.mod.h5"
    idem_model.write_text("placeholder", encoding="utf-8")
    native_order10 = tmp_path / "native_order10.npz"
    native_order10.write_text("placeholder", encoding="utf-8")
    native_order17 = tmp_path / "native_order17.npz"
    native_order17.write_text("placeholder", encoding="utf-8")
    output_dir = tmp_path / "source-attribution"

    monkeypatch.setattr(
        attribution,
        "load_raw_touchstone",
        lambda path: attribution.RawTouchstone(
            path=Path(path),
            freqs_hz=np.array([1.0, 2.0, 3.0]),
            s=np.zeros((3, 1, 1), dtype=complex),
            nports=1,
        ),
    )
    monkeypatch.setattr(
        attribution,
        "load_idem_poles",
        lambda path: np.array([-1.0 + 0.0j, -2.0 + 0.0j]),
    )
    monkeypatch.setattr(
        attribution,
        "load_native_model_arrays",
        lambda path: attribution.VectorFitArrays(
            poles=np.array([-1.0 + 0.0j]),
            residues=np.array([[0.1 + 0.0j]]),
            constant_coeff=np.array([0.2 + 0.0j]),
        ),
    )

    def fake_fixed_pole_fit(raw, poles, *, parameter_type, fit_max_frequency_points, rcond, enforce_dc):
        assert enforce_dc is False
        constant = np.array([0.99 + 0.0j]) if len(poles) == 2 else np.array([1.01 + 0.0j])
        return attribution.FitCaseModel(
            poles=np.asarray(poles, dtype=complex),
            residues=np.zeros((1, len(poles)), dtype=complex),
            constant_coeff=constant,
            fit_points=len(raw.freqs_hz),
            mean_rms=0.001 if len(poles) == 2 else 0.003,
            rank=len(poles) + 1,
            condition_number=12.0,
        )

    monkeypatch.setattr(attribution, "fit_fixed_pole_residues", fake_fixed_pole_fit)

    def fake_enforce(model, raw, **kwargs):
        assert kwargs["spectral_projection_active_mode_band_singular_modes"] == 2
        assert kwargs["spectral_projection_active_mode_band_singular_mode_sample_count"] == 3
        assert kwargs["spectral_projection_active_mode_reference_weight"] == 0.1
        assert kwargs["spectral_projection_non_active_stop_iteration"] == 7
        assert kwargs["global_damping_safety_margin"] == 1e-7
        enforced = model.copy()
        enforced.constant_coeff = np.array([0.99 + 0.0j])
        enforced.diagnostics = [
            {
                "type": "global_damping_fallback",
                "max_sigma_before": 1.002,
                "max_sigma_after": 0.99,
                "damping_factor": 0.998,
            },
            {"type": "final_validation", "final_validation_passed": True},
            {"type": "source_attribution_runtime", "elapsed_seconds": 12.5, "peak_memory_mb": 345.0},
        ]
        return enforced

    monkeypatch.setattr(attribution, "enforce_promoted_passivity", fake_enforce)

    summary = attribution.run_source_attribution(
        touchstone_path=touchstone,
        idem_order8_model_path=idem_model,
        native_order10_model_path=native_order10,
        native_high_order_model_path=native_order17,
        output_dir=output_dir,
    )

    summary_path = output_dir / "summary.json"
    assert summary_path.exists()
    written = json.loads(summary_path.read_text(encoding="utf-8"))
    assert written == summary
    assert [case["case"] for case in summary["cases"]] == [
        "idem_order8_poles_our_residue_ls",
        "native_order10_poles_our_residue_ls",
        "native_high_order_poles_our_residue_ls",
        "native_order10_poles_current_residues_control",
    ]
    assert summary["cases"][0]["pre_enforcement"]["fit_points"] == 3
    assert summary["cases"][0]["post_enforcement"]["max_sigma"] == 0.99
    required = summary["cases"][0]["required_metrics"]
    assert required["pre_enforcement_mean_rms"] == pytest.approx(0.001)
    assert required["pre_enforcement_max_sigma"] == pytest.approx(0.99)
    assert required["pre_damping_max_sigma"] == pytest.approx(1.002)
    assert required["final_max_sigma"] == pytest.approx(0.99)
    assert required["final_mean_rms"] == pytest.approx(0.99)
    assert required["damping_factor"] == pytest.approx(0.998)
    assert required["wall_time_seconds"] == pytest.approx(12.5)
    assert required["peak_memory_mb"] == pytest.approx(345.0)
    assert summary["promoted_passivity_profile"]["band_representative_count"] == 3
    assert summary["decision"]["next_branch"] == "Task 4"
    note = (output_dir / "benchmark_note.md").read_text(encoding="utf-8")
    assert "Decision: **Task 4**" in note
    assert "Pre-damping sigma" in note
    assert "idem_order8_poles_our_residue_ls" in note


def test_full_conjugate_poles_are_normalized_to_half_pair_basis():
    full = np.array(
        [
            -1.0 + 0.0j,
            -2.0 + 3.0j,
            -2.0 - 3.0j,
            -4.0 + 5.0j,
            -4.0 - 5.0j,
        ]
    )

    half = attribution._half_pair_representatives(full)

    assert set(half) == {-1.0 + 0.0j, -2.0 + 3.0j, -4.0 + 5.0j}


def test_half_pair_normalization_keeps_nearby_distinct_poles():
    poles = np.array([-1.0e10 + 2.0e10j, -1.000005e10 + 2.0e10j])

    half = attribution._half_pair_representatives(poles)

    assert len(half) == 2


def test_decide_root_cause_detects_enforcement_formulation_stall():
    cases = [
        {
            "case": name,
            "pre_enforcement": {"mean_rms": 0.003, "max_sigma": 1.02},
            "post_enforcement": {"max_sigma": 1.0022},
        }
        for name in (
            "idem_order8_poles_our_residue_ls",
            "native_order10_poles_our_residue_ls",
            "native_high_order_poles_our_residue_ls",
            "native_order10_poles_current_residues_control",
        )
    ]

    decision = attribution.decide_root_cause(cases, target_mean_rms=0.002, low_sigma=1.001)

    assert decision["interpretation"] == "Final enforcement formulation is the blocker"
    assert decision["next_branch"] == "Task 5"


def test_decide_root_cause_treats_tiny_idem_excess_as_pole_placement_signal():
    cases = [
        {
            "case": "idem_order8_poles_our_residue_ls",
            "pre_enforcement": {"mean_rms": 0.00089444, "max_sigma": 1.002174253},
            "post_enforcement": {"mean_rms": 0.000909128, "max_sigma": 0.999998394},
            "required_metrics": {"damping_factor": None},
        },
        {
            "case": "native_order10_poles_our_residue_ls",
            "pre_enforcement": {"mean_rms": 0.003210012, "max_sigma": 1.046432673},
            "post_enforcement": {"mean_rms": 0.004223465, "max_sigma": 0.9999989},
            "required_metrics": {"damping_factor": 0.997799114},
        },
        {
            "case": "native_high_order_poles_our_residue_ls",
            "pre_enforcement": {"mean_rms": 0.043893958, "max_sigma": 2.379686446},
            "post_enforcement": {"mean_rms": 0.06910016, "max_sigma": 0.9999989},
            "required_metrics": {"damping_factor": 0.422978773},
        },
    ]

    decision = attribution.decide_root_cause(cases)

    assert decision["interpretation"] == "Native pole placement is the main blocker"
    assert decision["next_branch"] == "Task 4"
    assert "without global damping" in decision["evidence"]


def test_vector_fit_arrays_uses_half_complex_pair_convention() -> None:
    pole = np.array([-1.0 + 10.0j])
    residue = np.array([[2.0 + 3.0j]])
    model = attribution.VectorFitArrays(
        poles=pole,
        residues=residue,
        constant_coeff=np.array([0.5 + 0.0j]),
    )

    freqs = np.array([1.0])
    s_axis = 2j * np.pi * freqs
    expected = (
        0.5
        + residue[0, 0] / (s_axis[0] - pole[0])
        + np.conj(residue[0, 0]) / (s_axis[0] - np.conj(pole[0]))
    )

    assert model.get_model_response(0, 0, freqs=freqs)[0] == pytest.approx(expected)
