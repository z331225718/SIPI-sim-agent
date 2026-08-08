import json
import inspect

import numpy as np
import pytest

import agent_spice.sparam.passivity as passivity
from agent_spice.sparam.passivity import (
    AsymptoticCompensationResult,
    _PassivityScore,
    _active_variable_budget_candidates,
    _active_mode_reference_regularization_freqs,
    _active_mode_reference_regularization_sample_weights,
    _adaptive_passivity_samples,
    _adaptive_violation_frequencies_for_enforcement,
    _apply_dc_preserving_uniform_damping,
    _apply_selective_pole_damping,
    _optimized_pole_damping_candidate,
    _optimized_pole_damping_global_energy_weights,
    _best_passivity_snapshot,
    _constant_active_variable_indices,
    _controllability_gramian_weights,
    _global_damping_factor,
    _line_search_eval_frequencies,
    _qp_attempt_diagnostic,
    _is_candidate_update_better,
    _evaluate_passivity_score_at_freqs,
    _edge_constraint_row_indices,
    _merge_reference_grid_violation_frequencies,
    _minimax_slack_weight_candidates,
    _residue_variable_fit_weights,
    _should_try_fit_weighted_qp,
    _select_active_variable_indices,
    _minimax_step_regularization,
    _solve_minimax_slack_upper_bound_dual_qp,
    _solve_min_norm_upper_bound_dual_qp,
    _singular_violation_modes,
    sample_streaming_singular_values,
    sample_vector_fit_passivity,
    _variable_fit_weights,
    _model_based_variable_weights,
    _projection_residue_constant_delta,
    _build_real_residue_compensation_basis,
    _project_asymptotic_constant_strictly_passive,
    _solve_asymptotic_residue_compensation,
    _reference_response_rms_at_freqs,
    _response_delta_rms_at_freqs,
    _select_projection_candidate,
    _spectral_norm_project_matrix,
    _base_perturbation_weights,
    _apply_constant_delta,
    _apply_pole_delta,
    _candidate_delta_norm,
    partition_poles,
    enforce_passivity_hamiltonian,
    _trust_region_limit,
    _validate_candidate_on_holdout,
)


def test_hamiltonian_passivity_advanced_perturbations_are_experimental_opt_in():
    signature = inspect.signature(enforce_passivity_hamiltonian)

    assert signature.parameters["perturb_constant"].default is False
    assert signature.parameters["perturb_poles"].default is False
    assert signature.parameters["constant_only_candidates"].default is False
    assert signature.parameters["global_damping_fallback"].default is False
    assert signature.parameters["global_damping_mode"].default == "uniform"
    assert signature.parameters["global_damping_selective_min_frequency"].default == 5e8
    assert signature.parameters["global_damping_safety_margin"].default == 1e-5
    assert signature.parameters["spectral_projection_fallback"].default is False
    assert signature.parameters["spectral_projection_max_delta_norm"].default is None
    assert signature.parameters["spectral_projection_max_response_delta_rms"].default is None
    assert signature.parameters["spectral_projection_max_sigma_regression"].default == 0.0
    assert signature.parameters["spectral_projection_iterations"].default == 1
    assert signature.parameters["spectral_projection_reweight_iterations"].default == 0
    assert signature.parameters["spectral_projection_max_reference_rms_increase"].default is None
    assert signature.parameters["spectral_projection_max_reference_rms_total_increase"].default is None
    assert signature.parameters["spectral_projection_max_reference_rms_per_sigma_improvement"].default is None
    assert signature.parameters["spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement"].default is None
    assert signature.parameters["spectral_projection_late_current_clip_start_iteration"].default == 0
    assert signature.parameters["spectral_projection_max_reference_band_sigma_regression"].default is None
    assert signature.parameters["spectral_projection_reference_band_holdout_start_iteration"].default == 0
    assert signature.parameters["spectral_projection_include_all_reference_violations"].default is False
    assert signature.parameters["spectral_projection_weight_mode"].default == "none"
    assert signature.parameters["spectral_projection_weight_exponent"].default == 1.0
    assert signature.parameters["spectral_projection_active_mode_candidate"].default is False
    assert signature.parameters["spectral_projection_active_mode_start_iteration"].default == 0
    assert signature.parameters["spectral_projection_non_active_stop_iteration"].default is None
    assert signature.parameters["spectral_projection_active_mode_max_responses"].default == 0
    assert signature.parameters["spectral_projection_active_mode_singular_modes"].default == 1
    assert signature.parameters["spectral_projection_active_mode_band_singular_modes"].default == 1
    assert signature.parameters["spectral_projection_active_mode_band_singular_mode_sample_count"].default == 1
    assert signature.parameters["spectral_projection_active_mode_solver"].default == "min_norm"
    assert signature.parameters["spectral_projection_active_mode_target_margin"].default == 0.0
    assert signature.parameters["spectral_projection_active_mode_target_margin_start_iteration"].default == 0
    assert signature.parameters["spectral_projection_active_mode_reference_max_points"].default == 0
    assert signature.parameters["spectral_projection_active_mode_frequency_selection"].default == "top"
    assert signature.parameters["spectral_projection_active_mode_reference_weight"].default == 0.0
    assert signature.parameters["spectral_projection_active_mode_reference_weight_mode"].default == "none"
    assert signature.parameters["spectral_projection_active_mode_reference_weight_candidates"].default == ()
    assert signature.parameters["spectral_projection_active_mode_global_reference_points"].default == 0
    assert signature.parameters["spectral_projection_active_mode_max_reference_rms_total_increase"].default is None
    assert signature.parameters["spectral_projection_active_mode_extra_scales"].default == ()
    assert signature.parameters["spectral_projection_active_mode_extra_scales_min_sigma"].default == 0.0
    assert signature.parameters["spectral_projection_current_clip_candidate"].default is False
    assert signature.parameters["spectral_projection_current_clip_reference_weight"].default == 0.0
    assert signature.parameters["spectral_projection_candidate_reference_max_points"].default == 0
    assert signature.parameters["spectral_projection_frequency_selection"].default == "top"
    assert signature.parameters["spectral_projection_band_sample_count"].default == 8
    assert signature.parameters["spectral_projection_reference_rms_scope"].default == "projection"
    assert signature.parameters["spectral_projection_reference_rms_chunk_size"].default == 0
    assert signature.parameters["spectral_projection_candidate_selection_metric"].default == "passivity"
    assert signature.parameters["spectral_projection_post_damping_selection_start_iteration"].default == 0
    assert signature.parameters["spectral_projection_post_damping_max_sigma_regression"].default is None
    assert signature.parameters["spectral_projection_mode_screen_candidates"].default == 0
    assert signature.parameters["spectral_projection_mode_screen_modes"].default == 2


def test_projection_active_mode_freqs_can_include_reference_holdout_peaks():
    validation_samples = [
        {"frequency_hz": 10.0, "max_sigma": 1.1, "source": "adaptive"},
        {"frequency_hz": 20.0, "max_sigma": 1.4, "source": "reference_grid_holdout"},
        {"frequency_hz": 30.0, "max_sigma": 1.3, "source": "reference_grid_holdout"},
    ]

    assert passivity._projection_active_mode_freqs(
        validation_samples,
        projection_freqs=[10.0],
        max_reference_points=1,
    ) == [10.0, 20.0]
    assert passivity._projection_active_mode_freqs(
        validation_samples,
        projection_freqs=[10.0],
        max_reference_points=0,
    ) == [10.0]


def test_projection_active_mode_freqs_can_cover_reference_violation_bands():
    validation_samples = [
        {"frequency_hz": 10.0, "max_sigma": 1.6, "source": "reference_grid_holdout", "violates": True},
        {"frequency_hz": 11.0, "max_sigma": 1.5, "source": "reference_grid_holdout", "violates": True},
        {"frequency_hz": 100.0, "max_sigma": 1.2, "source": "reference_grid_holdout", "violates": True},
        {"frequency_hz": 101.0, "max_sigma": 1.1, "source": "reference_grid_holdout", "violates": True},
    ]

    assert passivity._projection_active_mode_freqs(
        validation_samples,
        projection_freqs=[1.0],
        max_reference_points=1,
        selection_mode="reference_bands",
        band_sample_count=1,
    ) == [1.0, 10.0, 100.0]


def test_active_mode_band_singular_mode_freqs_selects_holdout_band_peaks():
    selector = getattr(passivity, "_active_mode_band_singular_mode_freqs", None)
    assert selector is not None
    validation_samples = [
        {"frequency_hz": 10.0, "max_sigma": 1.02, "source": "reference_grid_holdout", "violates": True},
        {"frequency_hz": 11.0, "max_sigma": 1.05, "source": "reference_grid_holdout", "violates": True},
        {"frequency_hz": 100.0, "max_sigma": 1.01, "source": "reference_grid_holdout", "violates": True},
        {"frequency_hz": 101.0, "max_sigma": 1.03, "source": "reference_grid_holdout", "violates": True},
        {"frequency_hz": 200.0, "max_sigma": 1.10, "source": "adaptive_interval", "violates": True},
    ]

    assert selector(validation_samples, max_reference_points=0, band_sample_count=1) == [11.0, 101.0]
    assert selector(validation_samples, max_reference_points=1, band_sample_count=1) == [11.0]


def test_projection_frequency_weights_can_equalize_reference_bands():
    samples = [
        {"frequency_hz": 10.0, "max_sigma": 1.2, "violates": True, "source": "reference_grid_holdout"},
        {"frequency_hz": 11.0, "max_sigma": 1.1, "violates": True, "source": "reference_grid_holdout"},
        {"frequency_hz": 12.0, "max_sigma": 1.05, "violates": True, "source": "reference_grid_holdout"},
        {"frequency_hz": 100.0, "max_sigma": 1.02, "violates": True, "source": "reference_grid_holdout"},
    ]

    weights = passivity._projection_frequency_weights(
        samples,
        [10.0, 11.0, 12.0, 100.0],
        mode="reference_band_equalized",
    )

    assert weights == pytest.approx([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0, 1.0])


def test_reference_band_holdout_metrics_track_per_band_regression():
    bands_helper = getattr(passivity, "_reference_band_holdout_ranges", None)
    metrics_helper = getattr(passivity, "_reference_band_holdout_metrics", None)
    assert bands_helper is not None
    assert metrics_helper is not None
    baseline_samples = [
        {"frequency_hz": 10.0, "max_sigma": 1.03, "source": "reference_grid_holdout", "violates": True},
        {"frequency_hz": 11.0, "max_sigma": 1.02, "source": "reference_grid_holdout", "violates": True},
        {"frequency_hz": 100.0, "max_sigma": 1.01, "source": "reference_grid_holdout", "violates": True},
        {"frequency_hz": 101.0, "max_sigma": 1.00, "source": "reference_grid_holdout", "violates": False},
    ]
    candidate_samples = [
        {"frequency_hz": 10.0, "max_sigma": 1.01, "source": "reference_grid_holdout"},
        {"frequency_hz": 11.0, "max_sigma": 1.00, "source": "reference_grid_holdout"},
        {"frequency_hz": 100.0, "max_sigma": 1.04, "source": "reference_grid_holdout"},
        {"frequency_hz": 101.0, "max_sigma": 1.03, "source": "reference_grid_holdout"},
    ]

    bands = bands_helper(baseline_samples)
    metrics = metrics_helper(candidate_samples, bands=bands)

    assert bands == [(10.0, 11.0, pytest.approx(1.03)), (100.0, 100.0, pytest.approx(1.01))]
    assert metrics["max_sigma"] == pytest.approx(1.04)
    assert metrics["max_regression"] == pytest.approx(0.03)


def test_projection_candidate_reject_reason_can_cap_reference_band_regression():
    reason = passivity._projection_candidate_reject_reason(
        {"reference_band_sigma_regression": 0.02},
        max_reference_band_sigma_regression=0.01,
    )

    assert reason == "reference_band_sigma_regression"


def test_active_mode_reference_weight_candidates_default_to_scalar_weight():
    assert passivity._active_mode_reference_weight_candidates(0.1, ()) == [0.1]
    assert passivity._active_mode_reference_weight_candidates(10.0, (0.03, 0.1, 0.3)) == [0.03, 0.1, 0.3]
    assert passivity._active_mode_reference_weight_candidates(0.0, ()) == [0.0]


def test_active_mode_reference_regularization_freqs_can_add_global_reference_points():
    freqs = _active_mode_reference_regularization_freqs(
        [10.0, 30.0],
        [0.0, 10.0, 20.0, 30.0, 40.0],
        global_reference_points=3,
    )

    assert freqs == [0.0, 10.0, 20.0, 30.0, 40.0]


def test_active_mode_reference_regularization_sample_weights_preserve_active_total_weight():
    weights = _active_mode_reference_regularization_sample_weights(
        [10.0, 30.0],
        [2.0, 4.0],
        [0.0, 10.0, 20.0, 30.0, 40.0],
    )

    assert sum(weights) == pytest.approx(6.0)
    assert weights[3] > weights[1]
    assert weights[0] == pytest.approx(weights[2])
    assert weights[2] == pytest.approx(weights[4])


def test_active_mode_solver_candidates_can_expand_reference_hybrid():
    assert passivity._active_mode_solver_candidates("min_norm") == ["min_norm"]
    assert passivity._active_mode_solver_candidates("reference_regularized_hybrid") == [
        "reference_regularized_min_norm",
        "reference_regularized_peak_minimax",
    ]
    assert passivity._active_mode_solver_candidates("reference_compensated_hybrid") == [
        "reference_regularized_min_norm",
        "reference_compensated_min_norm",
    ]


def test_filter_projection_sources_can_stop_non_active_late_stage():
    sources = [
        ("matrix_projection", object(), object(), {}),
        ("current_spectral_clip", object(), object(), {}),
        ("active_mode", object(), object(), {}),
    ]

    assert passivity._filter_projection_sources_for_late_stage(
        sources,
        projection_iteration=7,
        non_active_stop_iteration=8,
    ) == sources
    assert [
        source[0]
        for source in passivity._filter_projection_sources_for_late_stage(
            sources,
            projection_iteration=8,
            non_active_stop_iteration=8,
        )
    ] == ["active_mode"]
    assert passivity._filter_projection_sources_for_late_stage(
        sources,
        projection_iteration=8,
        non_active_stop_iteration=None,
    ) == sources


def test_projection_candidate_scale_values_can_add_active_mode_overrelaxation_only():
    assert passivity._projection_candidate_scale_values(
        "matrix_projection",
        active_mode_extra_scales=(1.25, 1.5),
    ) == (1.0, 0.5, 0.25, 0.125, 0.0625)
    assert passivity._projection_candidate_scale_values(
        "active_mode",
        active_mode_extra_scales=(1.25, 1.5, 1.0, -1.0),
    ) == (1.5, 1.25, 1.0, 0.5, 0.25, 0.125, 0.0625)
    assert passivity._projection_candidate_scale_values(
        "active_mode",
        active_mode_extra_scales=(0.375, 0.1875),
        current_max_sigma=1.0005,
        active_mode_extra_scales_min_sigma=1.001,
    ) == (1.0, 0.5, 0.25, 0.125, 0.0625)
    assert passivity._projection_candidate_scale_values(
        "active_mode",
        active_mode_extra_scales=(0.375, 0.1875),
        current_max_sigma=1.002,
        active_mode_extra_scales_min_sigma=1.001,
    ) == (1.0, 0.5, 0.375, 0.25, 0.1875, 0.125, 0.0625)


def test_streaming_passivity_checker_chunks_frequency_samples():
    calls = []
    freqs = np.array([0.0, 1.0, 2.0, 3.0])

    def provider(chunk_freqs):
        calls.append(list(chunk_freqs))
        matrices = np.zeros((len(chunk_freqs), 2, 2), dtype=complex)
        for index, freq in enumerate(chunk_freqs):
            matrices[index, 0, 0] = 1.2 if freq == 2.0 else 0.5
            matrices[index, 1, 1] = 0.5
        return matrices

    result = sample_streaming_singular_values(provider, freqs, nports=2, chunk_size=2, epsilon=1e-6)

    assert calls == [[0.0, 1.0], [2.0, 3.0]]
    assert result.max_sigma == 1.2
    assert result.max_sigma_frequency_hz == 2.0
    assert result.violation_bands_hz == [[2.0, 2.0]]
    assert result.frequency_points == 4
    assert result.chunk_size == 2


def test_streaming_passivity_checker_merges_contiguous_sampled_violations():
    freqs = np.array([0.0, 1.0, 2.0, 3.0])

    def provider(chunk_freqs):
        matrices = np.zeros((len(chunk_freqs), 2, 2), dtype=complex)
        for index, freq in enumerate(chunk_freqs):
            matrices[index, 0, 0] = 1.1 if freq in {1.0, 2.0} else 0.5
            matrices[index, 1, 1] = 0.5
        return matrices

    result = sample_streaming_singular_values(provider, freqs, nports=2, chunk_size=3, epsilon=1e-6)

    assert result.violation_bands_hz == [[1.0, 2.0]]


def test_streaming_passivity_checker_rejects_bad_provider_shape():
    def provider(chunk_freqs):
        return np.zeros((len(chunk_freqs), 2), dtype=complex)

    with pytest.raises(ValueError, match="provider returned shape"):
        sample_streaming_singular_values(provider, [1.0], nports=2, chunk_size=1)


def test_sample_vector_fit_passivity_builds_s_matrix_per_chunk():
    class FakeVectorFit:
        def __init__(self):
            self.calls = []

        def get_model_response(self, row, column, freqs=None):
            self.calls.append((row, column, tuple(freqs)))
            if row == column:
                return [0.5 if freq != 2.0 else 1.2 for freq in freqs]
            return [0.0 for _ in freqs]

    vector_fit = FakeVectorFit()

    result = sample_vector_fit_passivity(vector_fit, [1.0, 2.0, 3.0], nports=2, chunk_size=2)

    assert result.max_sigma == 1.2
    assert result.max_sigma_frequency_hz == 2.0
    assert result.violation_bands_hz == [[2.0, 2.0]]
    assert vector_fit.calls == [
        (0, 0, (1.0, 2.0)),
        (0, 1, (1.0, 2.0)),
        (1, 0, (1.0, 2.0)),
        (1, 1, (1.0, 2.0)),
        (0, 0, (3.0,)),
        (0, 1, (3.0,)),
        (1, 0, (3.0,)),
        (1, 1, (3.0,)),
    ]


def test_hamiltonian_report_max_sigma_includes_interval_violation_samples(monkeypatch):
    class FakeVectorFit:
        def __init__(self):
            f_mid = 10.0
            omega_mid = 2.0 * np.pi * f_mid
            self.poles = np.array([-0.1 + 1j * omega_mid])
            self.residues = np.array([[0.2 + 0.0j]])
            self.constant_coeff = np.array([0.0])

    monkeypatch.setattr(passivity, "check_passivity_hamiltonian_s", lambda *args, **kwargs: [])

    result = passivity.check_vector_fit_passivity_hamiltonian(FakeVectorFit(), nports=1, f_max=20.0)

    assert result.violation_bands_hz == [[0.0, 20.0]]
    assert result.max_sigma > 1.0
    assert result.max_sigma_frequency_hz == pytest.approx(10.0)


def test_hamiltonian_report_samples_complex_pole_frequencies_when_crossovers_are_missing(monkeypatch):
    class FakeVectorFit:
        def __init__(self):
            peak_freq = 10.0
            omega_peak = 2.0 * np.pi * peak_freq
            self.poles = np.array([-0.1 + 1j * omega_peak])
            self.residues = np.array([[0.2 + 0.0j]])
            self.constant_coeff = np.array([0.0])

    monkeypatch.setattr(passivity, "check_passivity_hamiltonian_s", lambda *args, **kwargs: [])

    result = passivity.check_vector_fit_passivity_hamiltonian(FakeVectorFit(), nports=1, f_max=100.0)

    assert result.violation_bands_hz == [[0.0, 100.0]]
    assert result.max_sigma > 1.0
    assert result.max_sigma_frequency_hz == pytest.approx(10.0)


def test_adaptive_passivity_samples_include_pole_frequency_peak():
    peak_freq = 10.0
    omega_peak = 2.0 * np.pi * peak_freq
    samples = _adaptive_passivity_samples(
        np.array([-0.1 + 1j * omega_peak]),
        np.array([[0.2 + 0.0j]]),
        np.array([0.0]),
        nports=1,
        intervals=[(0.0, 100.0)],
        f_max=100.0,
        epsilon=1e-6,
        max_depth=0,
    )

    peak_samples = [sample for sample in samples if sample["frequency_hz"] == pytest.approx(peak_freq)]
    assert peak_samples
    assert peak_samples[0]["max_sigma"] > 1.0
    assert [sample["frequency_hz"] for sample in samples] == sorted(sample["frequency_hz"] for sample in samples)


def test_adaptive_passivity_samples_refine_curved_interval():
    peak_freq = 10.0
    omega_peak = 2.0 * np.pi * peak_freq
    samples = _adaptive_passivity_samples(
        np.array([-0.1 + 1j * omega_peak]),
        np.array([[0.2 + 0.0j]]),
        np.array([0.0]),
        nports=1,
        intervals=[(0.0, 100.0)],
        f_max=100.0,
        epsilon=1e-6,
        max_depth=2,
        curvature_tol=0.0,
    )

    assert len(samples) > 4
    assert any(sample["refinement_depth"] > 0 for sample in samples)


def test_adaptive_violation_frequencies_for_enforcement_keeps_top_violations():
    peak_freq = 10.0
    omega_peak = 2.0 * np.pi * peak_freq
    violating = _adaptive_violation_frequencies_for_enforcement(
        np.array([-0.1 + 1j * omega_peak]),
        np.array([[0.2 + 0.0j]]),
        np.array([0.0]),
        nports=1,
        points=[0.0, 100.0],
        epsilon=1e-6,
        max_violation_samples=1,
        f_max=100.0,
    )

    assert violating == pytest.approx([(10.0, 2.0)])


def test_reference_grid_violations_are_merged_into_enforcement_constraints():
    violating = _merge_reference_grid_violation_frequencies(
        [],
        poles=np.array([], dtype=complex),
        residues=np.zeros((1, 0), dtype=complex),
        constant_coeff=np.array([1.1], dtype=complex),
        nports=1,
        reference_freqs=np.array([0.0, 1.0, 2.0]),
        epsilon=1e-6,
        max_violation_samples=2,
        f_max=2.0,
    )

    assert violating == pytest.approx([(0.0, 1.1), (1.0, 1.1)])


def test_singular_violation_modes_can_keep_multiple_modes():
    U = np.eye(3, dtype=complex)
    Vh = np.eye(3, dtype=complex)
    modes = _singular_violation_modes(
        U,
        np.array([1.2, 1.1, 0.5]),
        Vh,
        epsilon=1e-6,
        max_modes_per_frequency=2,
    )

    assert [mode[0] for mode in modes] == pytest.approx([1.2, 1.1])


def test_dual_qp_solves_minimum_norm_upper_bound_constraint():
    result = _solve_min_norm_upper_bound_dual_qp(np.array([[1.0]]), np.array([-0.2]))

    assert result.success is True
    assert result.x == pytest.approx([-0.2])
    assert result.regularization > 0.0
    assert np.isfinite(result.dual_condition_number)


def test_dual_qp_leaves_inactive_upper_bound_at_origin():
    result = _solve_min_norm_upper_bound_dual_qp(np.array([[1.0]]), np.array([0.2]))

    assert result.success is True
    assert result.x == pytest.approx([0.0])


def test_dual_qp_normalizes_small_residue_sensitivity_constraints():
    result = _solve_min_norm_upper_bound_dual_qp(
        np.array([[1e-12]]),
        np.array([-2e-6]),
    )

    assert result.success is True
    assert result.x == pytest.approx([-2e6], rel=1e-5)
    assert float((np.array([[1e-12]]) @ result.x).item()) <= -2e-6 + 1e-12


def test_dual_qp_falls_back_when_optimizer_success_is_primal_infeasible():
    result = _solve_min_norm_upper_bound_dual_qp(
        np.array([[1.0]]),
        np.array([-1.5e-6]),
    )

    assert result.success is True
    assert result.x == pytest.approx([-1.5e-6], rel=1e-6)
    assert "primal check failed" in result.message


def test_dual_qp_uses_variable_weights_as_fit_impact_penalty():
    result = _solve_min_norm_upper_bound_dual_qp(
        np.array([[1.0, 1.0]]),
        np.array([-1.0]),
        variable_weights=np.array([1.0, 100.0]),
    )

    assert result.success is True
    assert result.x == pytest.approx([-100.0 / 101.0, -1.0 / 101.0], rel=1e-5)


def test_minimax_slack_qp_balances_incompatible_upper_bounds():
    result = _solve_minimax_slack_upper_bound_dual_qp(
        np.array([[1.0], [-1.0]]),
        np.array([-1.0, -0.5]),
        step_regularization=1.0,
    )

    assert result.success is True
    assert result.x == pytest.approx([-0.25], abs=1e-6)
    assert result.slack == pytest.approx(0.75, abs=1e-6)


def test_minimax_step_regularization_scales_with_constraint_sensitivity():
    regularization = _minimax_step_regularization(
        np.array([[2.0, 0.0]]),
        np.array([-0.5]),
    )

    assert regularization == pytest.approx(8.0)


def test_minimax_slack_weight_candidates_keep_default_repair_conservative():
    assert _minimax_slack_weight_candidates() == pytest.approx([1.0])


def test_edge_constraint_row_indices_select_upper_band_rows():
    rows = _edge_constraint_row_indices(
        [1.0e9, 1.96e9, 1.99e9, 2.0e9],
        edge_frequency_hz=2.0e9,
        relative_window=0.02,
    )

    assert rows.tolist() == [1, 2, 3]


def test_select_active_variable_indices_prefers_weighted_sensitivity():
    matrix = np.array([[1.0, 10.0]])

    selected = _select_active_variable_indices(matrix, 1, variable_weights=np.array([0.01, 100.0]))

    assert selected.tolist() == [0]


def test_residue_variable_fit_weights_estimate_frequency_response_impact():
    weights = _residue_variable_fit_weights(
        np.array([-1.0 + 0.0j, -2.0 + 3.0j, -2.0 - 3.0j]),
        nports=2,
        vars_per_pair=3,
        real_poles=[(0, -1.0)],
        complex_pairs=[(1, 2, -2.0, 3.0)],
        freqs=[0.0, 1.0],
    )

    assert weights.shape == (12,)
    assert np.all(weights > 0.0)
    assert weights[:3].tolist() == pytest.approx(weights[3:6].tolist())


def test_residue_variable_fit_weights_are_bounded_to_keep_qp_well_conditioned():
    weights = _residue_variable_fit_weights(
        np.array([-1.0 + 0.0j, -1.0e12 + 0.0j]),
        nports=1,
        vars_per_pair=2,
        real_poles=[(0, -1.0), (1, -1.0e12)],
        complex_pairs=[],
        freqs=[0.0],
    )

    assert float(np.min(weights)) >= 0.1
    assert float(np.max(weights)) <= 10.0


def test_line_search_eval_frequencies_adds_holdout_neighbors():
    freqs = _line_search_eval_frequencies([0.0, 10.0, 20.0], [(6.0, 1.1)])

    assert freqs == pytest.approx([3.0, 6.0, 8.0])


def test_qp_attempt_diagnostic_records_prediction_and_actual_improvement():
    diagnostic = _qp_attempt_diagnostic(
        iteration=2,
        active_budget=4,
        active_matrix=np.array([[1.0, 0.0], [0.0, 2.0]]),
        qp_result=_solve_min_norm_upper_bound_dual_qp(np.array([[1.0]]), np.array([-0.2])),
        A_ineq=np.array([[1.0, 0.0], [0.0, 1.0]]),
        b_ineq=np.array([-0.2, -0.1]),
        x_delta=np.array([-0.2, -0.1]),
        scale=0.5,
        sampled_score=_PassivityScore(2, 1.2),
        candidate_score=_PassivityScore(1, 1.1),
        accepted=True,
        reject_reason=None,
        variable_weights=np.array([1.0, 4.0]),
    )

    assert diagnostic["iteration"] == 2
    assert diagnostic["active_budget"] == 4
    assert diagnostic["active_rank"] == 2
    assert diagnostic["predicted_improvement"] == pytest.approx(0.1)
    assert diagnostic["actual_improvement"] == pytest.approx(0.1)
    assert diagnostic["line_search_accepted"] is True
    assert diagnostic["selected_for_iteration"] is False
    assert diagnostic["accepted"] is True
    assert diagnostic["active_weight_min"] == pytest.approx(1.0)
    assert diagnostic["active_weight_max"] == pytest.approx(4.0)
    assert diagnostic["weighted_delta_norm"] == pytest.approx(np.linalg.norm(np.array([-0.1, -0.1])))
    json.dumps(diagnostic)


def test_qp_attempt_diagnostic_records_minimax_slack():
    diagnostic = _qp_attempt_diagnostic(
        iteration=0,
        active_budget=1,
        active_matrix=np.array([[1.0], [-1.0]]),
        qp_result=_solve_minimax_slack_upper_bound_dual_qp(
            np.array([[1.0], [-1.0]]),
            np.array([-1.0, -0.5]),
            step_regularization=1.0,
        ),
        A_ineq=np.array([[1.0], [-1.0]]),
        b_ineq=np.array([-1.0, -0.5]),
        x_delta=np.array([-0.25]),
        scale=1.0,
        sampled_score=_PassivityScore(2, 2.0),
        candidate_score=_PassivityScore(2, 1.75),
        accepted=True,
        reject_reason=None,
    )

    assert diagnostic["qp_slack"] == pytest.approx(0.75)
    json.dumps(diagnostic)


def test_singular_violation_modes_keeps_only_worst_mode_by_default():
    U = np.eye(3, dtype=complex)
    Vh = np.eye(3, dtype=complex)
    modes = _singular_violation_modes(U, np.array([1.2, 1.1, 0.5]), Vh, epsilon=1e-6)

    assert len(modes) == 1
    assert modes[0][0] == pytest.approx(1.2)


def test_passivity_score_prefers_lower_sigma_then_fewer_violations():
    assert _PassivityScore(2, 1.1).is_better_than(_PassivityScore(1, 10.0))
    assert _PassivityScore(1, 1.1).is_better_than(_PassivityScore(1, 1.2))
    assert _PassivityScore(1, 1.0).is_better_than(_PassivityScore(2, 1.0))


def test_global_damping_factor_targets_below_passivity_limit():
    factor = _global_damping_factor(max_sigma=1.25, epsilon=1e-6, safety_margin=1e-5)

    assert 0.0 < factor < 1.0
    assert factor * 1.25 < 1.0 - 1e-6


def test_global_damping_factor_leaves_passive_model_unchanged():
    assert _global_damping_factor(max_sigma=0.99, epsilon=1e-6) == pytest.approx(1.0)


def test_global_damping_factor_leaves_passivity_epsilon_gap_unchanged():
    factor = _global_damping_factor(max_sigma=1.0 + 0.5e-6, epsilon=1e-6)

    assert factor == pytest.approx(1.0)


def test_dc_preserving_uniform_damping_restores_dc_with_slowest_real_pole():
    poles = np.array([-1.0, -10.0], dtype=complex)
    residues = np.array([[0.2, -0.1]], dtype=complex)
    constant = np.array([0.9], dtype=complex)
    dc_before = passivity._evaluate_s_matrices_at_freqs(
        poles, residues, constant, nports=1, freqs=[0.0]
    )

    damped_residues, damped_constant, diagnostic = _apply_dc_preserving_uniform_damping(
        poles,
        residues,
        constant,
        nports=1,
        damping_factor=0.99,
    )
    dc_after = passivity._evaluate_s_matrices_at_freqs(
        poles, damped_residues, damped_constant, nports=1, freqs=[0.0]
    )

    assert diagnostic["success"] is True
    assert diagnostic["dc_restore_pole_index"] == 0
    assert diagnostic["dc_error"] < 1e-14
    assert dc_after == pytest.approx(dc_before)
    assert abs(damped_constant[0]) < abs(constant[0])


def test_asymptotic_constant_projection_is_strict_and_matrix_level():
    constant = np.array([1.2, 0.4, 0.4, 1.2], dtype=complex)

    projected, sigma_before, sigma_after, target = _project_asymptotic_constant_strictly_passive(
        constant,
        nports=2,
        epsilon=1e-6,
    )

    assert sigma_before == pytest.approx(1.6)
    assert target == pytest.approx(0.999999)
    assert sigma_after < 1.0
    assert np.max(np.linalg.svd(projected.reshape(2, 2), compute_uv=False)) < 1.0


def test_real_residue_compensation_basis_matches_expanded_response():
    poles = np.array([-2.0, -3.0 + 4.0j, -3.0 - 4.0j], dtype=complex)
    freqs = np.array([0.0, 0.5, 2.0])
    basis, real_poles, complex_pairs = _build_real_residue_compensation_basis(poles, freqs)
    variables = np.array([0.7, -0.2, 0.35])
    residues = np.array(
        [[variables[0], variables[1] + 1j * variables[2], variables[1] - 1j * variables[2]]]
    )
    direct = passivity._evaluate_s_matrices_at_freqs(
        poles,
        residues,
        np.zeros(1, dtype=complex),
        nports=1,
        freqs=freqs,
    ).reshape(-1)

    assert len(real_poles) == 1
    assert len(complex_pairs) == 1
    assert basis[0::2] @ variables == pytest.approx(direct.real)
    assert basis[1::2] @ variables == pytest.approx(direct.imag)


def test_asymptotic_residue_compensation_exact_at_dc_for_real_pole():
    poles = np.array([-1.0], dtype=complex)
    residues = np.array([[-0.3]], dtype=complex)
    constant = np.array([1.2], dtype=complex)
    projected = np.array([0.9], dtype=complex)

    result = _solve_asymptotic_residue_compensation(
        poles,
        residues,
        constant,
        projected,
        nports=1,
        freqs=[0.0],
    )

    assert isinstance(result, AsymptoticCompensationResult)
    assert result.constant_coeff == pytest.approx(projected)
    assert result.residues[0, 0] == pytest.approx(0.0)
    assert result.diagnostics["compensation_residual_rms"] < 1e-14
    assert result.diagnostics["rank"] == 1


def test_asymptotic_residue_compensation_solves_multiple_rhs_in_blocks():
    poles = np.array([-1.0], dtype=complex)
    residues = np.zeros((4, 1), dtype=complex)
    constant = np.array([1.2, 0.2, -0.1, 1.1], dtype=complex)
    projected = np.array([0.9, 0.1, -0.2, 0.8], dtype=complex)

    blocked = _solve_asymptotic_residue_compensation(
        poles,
        residues,
        constant,
        projected,
        nports=2,
        freqs=[0.0],
        response_block_size=1,
    )
    unblocked = _solve_asymptotic_residue_compensation(
        poles,
        residues,
        constant,
        projected,
        nports=2,
        freqs=[0.0],
        response_block_size=None,
    )

    assert blocked.residues == pytest.approx(unblocked.residues)
    assert blocked.diagnostics["rhs_blocks"] == 4
    assert unblocked.diagnostics["rhs_blocks"] == 1
    assert blocked.diagnostics["compensation_residual_rms"] < 1e-14


def test_asymptotic_residue_compensation_preserves_conjugate_residues():
    poles = np.array([-2.0 + 3.0j, -2.0 - 3.0j], dtype=complex)
    residues = np.zeros((1, 2), dtype=complex)

    result = _solve_asymptotic_residue_compensation(
        poles,
        residues,
        np.array([1.2], dtype=complex),
        np.array([0.9], dtype=complex),
        nports=1,
        freqs=[0.0, 0.2],
    )

    assert result.residues[0, 1] == pytest.approx(result.residues[0, 0].conjugate())


def test_asymptotic_residue_compensation_preserves_dynamic_cancellation():
    poles = np.array([-1.0e9], dtype=complex)
    residues = np.array([[-0.3e9]], dtype=complex)
    constant = np.array([1.2], dtype=complex)
    projected = np.array([0.999999], dtype=complex)
    freqs = np.linspace(0.0, 1.0e4, 9)

    result = _solve_asymptotic_residue_compensation(
        poles,
        residues,
        constant,
        projected,
        nports=1,
        freqs=freqs,
    )

    assert abs(result.constant_coeff[0]) < 1.0
    assert result.diagnostics["compensation_residual_rms"] < 1e-5
    assert result.diagnostics["residue_delta_norm"] > 1.0e8


def test_asymptotic_residue_compensation_can_preserve_dc_with_nonzero_reference_grid():
    poles = np.array([-1.0], dtype=complex)
    residues = np.array([[-0.3]], dtype=complex)
    constant = np.array([1.2], dtype=complex)
    projected = np.array([0.9], dtype=complex)

    result = _solve_asymptotic_residue_compensation(
        poles,
        residues,
        constant,
        projected,
        nports=1,
        freqs=[0.1, 1.0, 10.0],
        preserve_dc=True,
    )

    assert result.diagnostics["preserve_dc"] is True
    assert result.diagnostics["dc_error"] < 1e-10


def test_real_residue_compensation_basis_rejects_unpaired_complex_pole():
    with pytest.raises(ValueError, match="must include their conjugates"):
        _build_real_residue_compensation_basis(np.array([-1.0 + 2.0j]), [0.0, 1.0])


def test_enforcement_projects_nonpassive_const_even_without_iterative_repairs():
    vector_fit = type("VectorFit", (), {})()
    vector_fit.poles = np.array([], dtype=complex)
    vector_fit.residues = np.zeros((4, 0), dtype=complex)
    vector_fit.constant_coeff = np.array([1.2, 0.4, 0.4, 1.2], dtype=complex)

    enforce_passivity_hamiltonian(vector_fit, nports=2, epsilon=1e-6, max_iterations=0)

    sigma = np.max(np.linalg.svd(vector_fit.constant_coeff.reshape(2, 2), compute_uv=False))
    diagnostic = vector_fit.passivity_enforcement_diagnostics[0]
    assert sigma < 1.0
    assert diagnostic["type"] == "asymptotic_constant_projection"
    assert diagnostic["projected"] is True
    assert diagnostic["sigma_before"] == pytest.approx(1.6)
    assert diagnostic["sigma_after"] < 1.0


def test_enforcement_does_not_blindly_project_far_nonpassive_const_with_dynamic_terms():
    vector_fit = type("VectorFit", (), {})()
    vector_fit.poles = np.array([-1.0], dtype=complex)
    vector_fit.residues = np.array([[-0.3]], dtype=complex)
    vector_fit.constant_coeff = np.array([1.2], dtype=complex)

    enforce_passivity_hamiltonian(vector_fit, nports=1, epsilon=1e-6, max_iterations=0)

    diagnostic = vector_fit.passivity_enforcement_diagnostics[0]
    final_validation = vector_fit.passivity_enforcement_diagnostics[-1]
    assert vector_fit.constant_coeff[0] == pytest.approx(1.2)
    assert diagnostic["projected"] is False
    assert final_validation["final_validation_passed"] is False
    assert final_validation["final_validation_max_sigma"] == pytest.approx(1.2)


def test_enforcement_compensates_far_nonpassive_asymptote_with_reference_grid():
    vector_fit = type("VectorFit", (), {})()
    vector_fit.poles = np.array([-1.0e9], dtype=complex)
    vector_fit.residues = np.array([[-0.3e9]], dtype=complex)
    vector_fit.constant_coeff = np.array([1.2], dtype=complex)
    reference_freqs = np.linspace(0.0, 1.0e4, 9)
    reference_s = passivity._evaluate_s_matrices_at_freqs(
        vector_fit.poles,
        vector_fit.residues,
        vector_fit.constant_coeff,
        nports=1,
        freqs=reference_freqs,
    )

    enforce_passivity_hamiltonian(
        vector_fit,
        nports=1,
        epsilon=1e-6,
        max_iterations=0,
        f_max=1.0e10,
        spectral_projection_reference_freqs=reference_freqs,
        spectral_projection_reference_s=reference_s,
        asymptotic_compensation_rms_target=1e-3,
        preserve_dc=True,
    )

    compensation = next(
        item
        for item in vector_fit.passivity_enforcement_diagnostics
        if item["type"] == "asymptotic_residue_compensation"
    )
    final_validation = vector_fit.passivity_enforcement_diagnostics[-1]
    assert compensation["accepted"] is True
    assert compensation["reference_rms_after"] <= 1e-3
    assert compensation["dc_error"] <= compensation["dc_tolerance"]
    assert abs(vector_fit.constant_coeff[0]) < 1.0
    assert final_validation["final_validation_passed"] is True


def test_enforcement_rejects_asymptotic_compensation_that_misses_rms_target():
    vector_fit = type("VectorFit", (), {})()
    vector_fit.poles = np.array([-1.0], dtype=complex)
    vector_fit.residues = np.array([[-0.3]], dtype=complex)
    vector_fit.constant_coeff = np.array([1.2], dtype=complex)
    original_residues = vector_fit.residues.copy()
    reference_freqs = np.array([0.0, 1.0, 10.0])
    reference_s = passivity._evaluate_s_matrices_at_freqs(
        vector_fit.poles,
        vector_fit.residues,
        vector_fit.constant_coeff,
        nports=1,
        freqs=reference_freqs,
    )

    enforce_passivity_hamiltonian(
        vector_fit,
        nports=1,
        epsilon=1e-6,
        max_iterations=0,
        f_max=10.0,
        spectral_projection_reference_freqs=reference_freqs,
        spectral_projection_reference_s=reference_s,
        asymptotic_compensation_rms_target=1e-6,
        preserve_dc=True,
    )

    compensation = next(
        item
        for item in vector_fit.passivity_enforcement_diagnostics
        if item["type"] == "asymptotic_residue_compensation"
    )
    assert compensation["accepted"] is False
    assert compensation["reject_reason"] == "reference_rms"
    assert vector_fit.constant_coeff[0] == pytest.approx(1.2)
    assert vector_fit.residues == pytest.approx(original_residues)


def test_global_damping_does_not_overwrite_model_when_rms_target_would_fail():
    vector_fit = type("VectorFit", (), {})()
    vector_fit.poles = np.array([-1.0], dtype=complex)
    vector_fit.residues = np.array([[-0.3]], dtype=complex)
    vector_fit.constant_coeff = np.array([1.2], dtype=complex)
    original_residues = vector_fit.residues.copy()
    reference_freqs = np.array([0.0, 1.0, 10.0])
    reference_s = passivity._evaluate_s_matrices_at_freqs(
        vector_fit.poles,
        vector_fit.residues,
        vector_fit.constant_coeff,
        nports=1,
        freqs=reference_freqs,
    )

    enforce_passivity_hamiltonian(
        vector_fit,
        nports=1,
        epsilon=1e-6,
        max_iterations=0,
        f_max=10.0,
        global_damping_fallback=True,
        spectral_projection_reference_freqs=reference_freqs,
        spectral_projection_reference_s=reference_s,
        asymptotic_compensation_rms_target=1e-6,
        preserve_dc=True,
    )

    damping = next(
        item
        for item in vector_fit.passivity_enforcement_diagnostics
        if item["type"] == "global_damping_fallback"
    )
    assert damping["accepted"] is False
    assert damping["damping_history"][-1]["reject_reason"] == "reference_rms_target"
    assert vector_fit.constant_coeff[0] == pytest.approx(1.2)
    assert vector_fit.residues == pytest.approx(original_residues)


def test_final_validation_accepts_finite_sigma_inside_passivity_epsilon():
    vector_fit = type("VectorFit", (), {})()
    vector_fit.poles = np.array([-1.0], dtype=complex)
    vector_fit.residues = np.array([[0.5000005]], dtype=complex)
    vector_fit.constant_coeff = np.array([0.5], dtype=complex)

    enforce_passivity_hamiltonian(
        vector_fit,
        nports=1,
        epsilon=1e-6,
        max_iterations=0,
        f_max=1.0,
    )

    final_validation = vector_fit.passivity_enforcement_diagnostics[-1]
    assert 1.0 < final_validation["final_validation_max_sigma"] < 1.0 + 1e-6
    assert final_validation["final_validation_passed"] is True
    assert final_validation["final_validation_violation_count"] == 0


@pytest.mark.parametrize("constant_value", [1.0, 1.0 + 0.5e-6, 1.0 + 1.0e-6])
def test_enforcement_accepts_const_at_or_inside_passivity_epsilon(constant_value):
    vector_fit = type("VectorFit", (), {})()
    vector_fit.poles = np.array([], dtype=complex)
    vector_fit.residues = np.zeros((1, 0), dtype=complex)
    vector_fit.constant_coeff = np.array([constant_value], dtype=complex)

    enforce_passivity_hamiltonian(
        vector_fit,
        nports=1,
        epsilon=1e-6,
        max_iterations=0,
        global_damping_fallback=True,
    )

    diagnostic = vector_fit.passivity_enforcement_diagnostics[0]
    assert vector_fit.constant_coeff[0] == pytest.approx(constant_value)
    assert diagnostic["enabled"] is True
    assert diagnostic["projected"] is False
    assert vector_fit.passivity_enforcement_diagnostics[-1]["final_validation_passed"] is True
    assert not any(
        item.get("type") == "global_damping_fallback"
        for item in vector_fit.passivity_enforcement_diagnostics
    )


def test_apply_selective_pole_damping_scales_only_high_frequency_poles_and_constant():
    poles = np.array([-1.0e6 + 0.0j, -1.0e7 + 2j * np.pi * 1.0e9, -1.0e7 - 2j * np.pi * 1.0e9])
    residues = np.ones((1, 3), dtype=complex)
    constant = np.array([2.0 + 0.0j])

    damped_residues, damped_constant = _apply_selective_pole_damping(
        poles,
        residues,
        constant,
        damping_factor=0.5,
        min_frequency_hz=5e8,
    )

    assert damped_residues[0, 0] == pytest.approx(1.0)
    assert damped_residues[0, 1] == pytest.approx(0.5)
    assert damped_residues[0, 2] == pytest.approx(0.5)
    assert damped_constant[0] == pytest.approx(1.0)


def test_optimized_pole_damping_global_energy_weights_protect_slow_energetic_poles():
    poles = np.array([-1.0 + 0.0j, -1.0e6 + 0.0j])
    residues = np.array([[10.0 + 0.0j, 10.0 + 0.0j]])
    constant = np.array([0.1 + 0.0j])

    weights = _optimized_pole_damping_global_energy_weights(poles, residues, constant)

    assert weights[0] == pytest.approx(1.0)
    assert weights[1] < 1e-5
    assert weights[2] < weights[0]


def test_optimized_pole_damping_can_use_less_than_uniform_damping_for_d_only_case():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j])

    damped_residues, damped_constant, diagnostic = _optimized_pole_damping_candidate(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        damping_factor=0.8,
        epsilon=1e-6,
    )

    assert diagnostic["success"] is True
    assert damped_residues.shape == residues.shape
    assert abs(damped_constant[0]) < 1.0
    assert abs(damped_constant[0]) > abs((constant * 0.8)[0])
    assert diagnostic["max_beta"] < 0.2


def test_spectral_norm_project_matrix_clips_only_violating_singular_values():
    matrix = np.diag([1.2, 0.5]).astype(complex)

    projected = _spectral_norm_project_matrix(matrix, target_norm=0.99)
    singular_values = np.linalg.svd(projected, compute_uv=False)

    assert singular_values[0] == pytest.approx(0.99)
    assert singular_values[1] == pytest.approx(0.5)


def test_projection_residue_constant_delta_repairs_constant_one_port_sample():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j])

    candidate_residues, candidate_constant = _projection_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0, 1.0],
        epsilon=1e-6,
        perturb_constant=True,
    )

    assert candidate_residues.shape == residues.shape
    assert abs(candidate_constant[0]) < 1.0


def test_reference_projection_residue_constant_delta_moves_toward_passive_raw_reference():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j])
    reference_freqs = np.array([0.0, 1.0])
    reference_s = np.array([[[0.8 + 0.0j]], [[0.8 + 0.0j]]])

    reference_projection_delta = getattr(passivity, "_reference_projection_residue_constant_delta", None)
    assert reference_projection_delta is not None

    candidate_residues, candidate_constant = reference_projection_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0, 1.0],
        reference_freqs=reference_freqs,
        reference_s=reference_s,
        epsilon=1e-6,
        perturb_constant=True,
    )

    assert candidate_residues.shape == residues.shape
    assert candidate_constant[0].real == pytest.approx(0.8)
    assert abs(candidate_constant[0]) < 1.0


def test_reference_projection_residue_constant_delta_uses_sample_weights():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([0.0 + 0.0j])
    reference_freqs = np.array([0.0, 1.0])
    reference_s = np.array([[[0.2 + 0.0j]], [[0.8 + 0.0j]]])

    unweighted_residues, unweighted_constant = passivity._reference_projection_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0, 1.0],
        reference_freqs=reference_freqs,
        reference_s=reference_s,
        epsilon=1e-6,
        perturb_constant=True,
    )
    weighted_residues, weighted_constant = passivity._reference_projection_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0, 1.0],
        reference_freqs=reference_freqs,
        reference_s=reference_s,
        epsilon=1e-6,
        perturb_constant=True,
        sample_weights=[100.0, 1.0],
    )

    assert unweighted_residues.shape == weighted_residues.shape
    assert unweighted_constant[0].real == pytest.approx(0.5)
    assert weighted_constant[0].real < 0.3


def test_projection_candidate_passivity_samples_include_reference_grid_holdout():
    poles = np.array([-1.0 + 0.0j])
    residues = np.array([[2.1 + 0.0j]])
    constant = np.array([-1.3 + 0.0j])

    candidate_passivity_samples = getattr(passivity, "_projection_candidate_passivity_samples", None)
    assert candidate_passivity_samples is not None

    samples = candidate_passivity_samples(
        poles,
        residues,
        constant,
        nports=1,
        intervals=[(0.0, 0.0)],
        f_max=None,
        epsilon=1e-6,
        reference_freqs=np.array([0.0, 10.0]),
    )

    max_sample = max(samples, key=lambda sample: float(sample["max_sigma"]))
    assert max_sample["frequency_hz"] == pytest.approx(10.0)
    assert max_sample["max_sigma"] > 1.0
    assert max_sample["source"] == "reference_grid_holdout"


def test_projection_candidate_passivity_samples_batch_reference_holdout(monkeypatch):
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([0.0 + 0.0j])
    calls = []

    def fake_batched(poles_arg, residues_arg, constant_arg, *, nports, freqs):
        freqs_list = list(freqs)
        calls.append(freqs_list)
        matrices = np.zeros((len(freqs_list), 1, 1), dtype=complex)
        for index, freq in enumerate(freqs_list):
            matrices[index, 0, 0] = 1.2 if float(freq) == 10.0 else 0.5
        return matrices

    monkeypatch.setattr(passivity, "_evaluate_s_matrices_at_freqs", fake_batched)

    samples = passivity._projection_candidate_passivity_samples(
        poles,
        residues,
        constant,
        nports=1,
        intervals=[],
        f_max=None,
        epsilon=1e-6,
        reference_freqs=np.array([0.0, 10.0, 20.0]),
    )

    assert calls == [[0.0, 10.0, 20.0]]
    assert [sample["frequency_hz"] for sample in samples] == [0.0, 10.0, 20.0]
    assert samples[1]["max_sigma"] == pytest.approx(1.2)
    assert samples[1]["violates"] is True
    assert samples[1]["source"] == "reference_grid_holdout"


def test_projection_candidate_passivity_samples_can_reuse_reference_basis(monkeypatch):
    poles = np.array([-1.0 + 0.0j])
    residues = np.array([[1.0 + 0.0j]])
    constant = np.array([0.0 + 0.0j])
    freqs = np.array([0.0, 10.0])
    basis = passivity._rational_basis_at_freqs(poles, freqs)

    def fail_recompute(*args, **kwargs):
        raise AssertionError("reference basis should be reused")

    monkeypatch.setattr(passivity, "_rational_basis_at_freqs", fail_recompute)

    samples = passivity._projection_candidate_passivity_samples(
        poles,
        residues,
        constant,
        nports=1,
        intervals=[],
        f_max=None,
        epsilon=1e-6,
        reference_freqs=freqs,
        reference_basis=basis,
    )

    assert [sample["frequency_hz"] for sample in samples] == [0.0, 10.0]


def test_candidate_reference_holdout_samples_batch_matches_individual_samples():
    helper = getattr(passivity, "_candidate_reference_holdout_samples_batch", None)
    assert helper is not None
    poles = np.array([-1.0 + 0.0j])
    candidates = [
        (np.array([[1.0 + 0.0j]]), np.array([0.0 + 0.0j])),
        (np.array([[0.5 + 0.0j]]), np.array([0.1 + 0.0j])),
    ]
    freqs = np.array([0.0, 10.0])
    basis = passivity._rational_basis_at_freqs(poles, freqs)

    batched = helper(
        candidates,
        nports=1,
        freqs=freqs,
        epsilon=1e-6,
        basis=basis,
    )
    individual = [
        passivity._singular_samples_at_freqs(
            poles,
            residues,
            constant,
            nports=1,
            freqs=freqs,
            epsilon=1e-6,
            source="reference_grid_holdout",
            basis=basis,
        )
        for residues, constant in candidates
    ]

    assert len(batched) == 2
    for candidate_batched, candidate_individual in zip(batched, individual):
        assert [sample["frequency_hz"] for sample in candidate_batched] == [0.0, 10.0]
        assert [sample["source"] for sample in candidate_batched] == ["reference_grid_holdout"] * 2
        assert [sample["max_sigma"] for sample in candidate_batched] == pytest.approx(
            [sample["max_sigma"] for sample in candidate_individual]
        )


def test_mode_response_magnitudes_from_basis_matches_direct_projection():
    helper = getattr(passivity, "_mode_response_magnitudes_from_basis", None)
    assert helper is not None
    poles = np.array([-1.0 + 0.0j])
    freqs = np.array([0.0, 1.0])
    basis = passivity._rational_basis_at_freqs(poles, freqs)
    residues = np.array(
        [
            [1.0 + 0.0j],
            [0.0 + 0.0j],
            [0.0 + 0.0j],
            [0.5 + 0.0j],
        ]
    )
    constant = np.array([0.1 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j, 0.2 + 0.0j])
    left_vectors = np.array(
        [
            [[1.0 + 0.0j, 0.0 + 0.0j], [0.0 + 0.0j, 1.0 + 0.0j]],
            [[1.0 + 0.0j, 0.0 + 0.0j], [0.0 + 0.0j, 1.0 + 0.0j]],
        ]
    )
    right_vectors = left_vectors.copy()

    magnitudes = helper(
        residues,
        constant,
        nports=2,
        basis=basis,
        left_vectors=left_vectors,
        right_vectors=right_vectors,
    )
    matrices = passivity._evaluate_s_matrices_from_basis(residues, constant, nports=2, basis=basis)
    expected = np.array(
        [
            [
                abs(np.vdot(left_vectors[freq_index, mode_index], matrices[freq_index] @ right_vectors[freq_index, mode_index]))
                for mode_index in range(2)
            ]
            for freq_index in range(2)
        ]
    )

    assert magnitudes.shape == (2, 2)
    assert magnitudes == pytest.approx(expected)


def test_dominant_singular_vectors_at_freqs_reproduce_singular_values():
    helper = getattr(passivity, "_dominant_singular_vectors_at_freqs", None)
    assert helper is not None
    matrices = np.array(
        [
            [[2.0 + 0.0j, 0.0 + 0.0j], [0.0 + 0.0j, 1.0 + 0.0j]],
            [[0.0 + 0.0j, 3.0 + 0.0j], [0.0 + 0.0j, 0.0 + 0.0j]],
        ],
        dtype=complex,
    )

    sigmas, left, right = helper(matrices, mode_count=1)
    responses = np.array(
        [
            abs(np.vdot(left[freq_index, 0], matrices[freq_index] @ right[freq_index, 0]))
            for freq_index in range(2)
        ]
    )

    assert sigmas.shape == (2, 1)
    assert left.shape == (2, 1, 2)
    assert right.shape == (2, 1, 2)
    assert sigmas[:, 0] == pytest.approx([2.0, 3.0])
    assert responses == pytest.approx(sigmas[:, 0])


def test_screen_projection_candidates_by_modes_keeps_lowest_mode_response():
    helper = getattr(passivity, "_screen_projection_candidate_descriptors_by_modes", None)
    assert helper is not None
    basis = np.zeros((1, 0), dtype=complex)
    left_vectors = np.array([[[1.0 + 0.0j]]])
    right_vectors = np.array([[[1.0 + 0.0j]]])
    candidates = [
        {"name": "bad", "residues": np.zeros((1, 0), dtype=complex), "constant": np.array([1.2 + 0.0j])},
        {"name": "good", "residues": np.zeros((1, 0), dtype=complex), "constant": np.array([0.8 + 0.0j])},
        {"name": "best", "residues": np.zeros((1, 0), dtype=complex), "constant": np.array([0.4 + 0.0j])},
    ]

    selected = helper(
        candidates,
        nports=1,
        basis=basis,
        left_vectors=left_vectors,
        right_vectors=right_vectors,
        max_candidates=2,
    )

    assert [candidate["name"] for candidate in selected] == ["best", "good"]
    assert [candidate["mode_screen_max_sigma"] for candidate in selected] == pytest.approx([0.4, 0.8])


def test_projection_candidate_passes_cheap_gates_rejects_reference_rms_regression():
    helper = getattr(passivity, "_projection_candidate_passes_cheap_gates", None)
    assert helper is not None

    assert helper(
        {"delta_norm": 0.01, "response_delta_rms": 0.02, "reference_rms": 0.101},
        max_delta_norm=0.02,
        max_response_delta_rms=0.03,
        baseline_reference_rms=0.10,
        max_reference_rms_increase=0.002,
    )
    assert not helper(
        {"delta_norm": 0.01, "response_delta_rms": 0.02, "reference_rms": 0.105},
        max_delta_norm=0.02,
        max_response_delta_rms=0.03,
        baseline_reference_rms=0.10,
        max_reference_rms_increase=0.002,
    )


def test_projection_candidate_passes_cheap_gates_can_use_total_reference_rms_budget():
    helper = getattr(passivity, "_projection_candidate_passes_cheap_gates", None)
    assert helper is not None

    assert helper(
        {"delta_norm": 0.01, "response_delta_rms": 0.02, "reference_rms": 0.25},
        max_delta_norm=0.02,
        max_response_delta_rms=0.03,
        baseline_reference_rms=0.20,
        max_reference_rms_increase=0.01,
        initial_reference_rms=0.10,
        max_reference_rms_total_increase=0.20,
    )
    assert not helper(
        {"delta_norm": 0.01, "response_delta_rms": 0.02, "reference_rms": 0.31},
        max_delta_norm=0.02,
        max_response_delta_rms=0.03,
        baseline_reference_rms=0.20,
        max_reference_rms_increase=0.01,
        initial_reference_rms=0.10,
        max_reference_rms_total_increase=0.20,
    )


def test_projection_candidate_reference_holdout_keeps_riskiest_and_required_points():
    selector = getattr(passivity, "_projection_candidate_reference_holdout_freqs", None)
    assert selector is not None
    samples = [
        {"frequency_hz": 1.0, "max_sigma": 1.01, "source": "reference_grid_holdout"},
        {"frequency_hz": 2.0, "max_sigma": 1.03, "source": "reference_grid_holdout"},
        {"frequency_hz": 3.0, "max_sigma": 1.02, "source": "reference_grid_holdout"},
        {"frequency_hz": 4.0, "max_sigma": 2.00, "source": "interval_midpoint"},
    ]

    freqs = selector(samples, required_freqs=[1.5], max_reference_points=2)

    assert freqs == [1.5, 2.0, 3.0]


def test_projection_frequency_candidates_can_keep_all_reference_grid_violations():
    samples = [
        {"frequency_hz": 1.0, "max_sigma": 1.30, "violates": True, "source": "interval_midpoint"},
        {"frequency_hz": 2.0, "max_sigma": 1.20, "violates": True, "source": "reference_grid_holdout"},
        {"frequency_hz": 3.0, "max_sigma": 1.10, "violates": True, "source": "reference_grid_holdout"},
        {"frequency_hz": 4.0, "max_sigma": 1.05, "violates": True, "source": "reference_grid_holdout"},
        {"frequency_hz": 5.0, "max_sigma": 0.90, "violates": False, "source": "reference_grid_holdout"},
    ]

    projection_frequency_candidates = getattr(passivity, "_projection_frequency_candidates", None)
    assert projection_frequency_candidates is not None

    capped = projection_frequency_candidates(
        samples,
        max_violation_samples=2,
        include_all_reference_violations=False,
    )
    all_reference = projection_frequency_candidates(
        samples,
        max_violation_samples=2,
        include_all_reference_violations=True,
    )

    assert capped == [1.0, 2.0]
    assert all_reference == [1.0, 2.0, 3.0, 4.0]


def test_projection_frequency_candidates_can_select_reference_violation_bands():
    samples = [
        {"frequency_hz": 1.0, "max_sigma": 1.30, "violates": True, "source": "interval_midpoint"},
        {"frequency_hz": 10.0, "max_sigma": 1.06, "violates": True, "source": "reference_grid_holdout"},
        {"frequency_hz": 11.0, "max_sigma": 1.04, "violates": True, "source": "reference_grid_holdout"},
        {"frequency_hz": 12.0, "max_sigma": 1.05, "violates": True, "source": "reference_grid_holdout"},
        {"frequency_hz": 100.0, "max_sigma": 1.03, "violates": True, "source": "reference_grid_holdout"},
        {"frequency_hz": 101.0, "max_sigma": 1.02, "violates": True, "source": "reference_grid_holdout"},
        {"frequency_hz": 102.0, "max_sigma": 1.01, "violates": True, "source": "reference_grid_holdout"},
    ]
    projection_frequency_candidates = getattr(passivity, "_projection_frequency_candidates", None)
    assert projection_frequency_candidates is not None

    freqs = projection_frequency_candidates(
        samples,
        max_violation_samples=1,
        selection_mode="reference_bands",
        band_sample_count=2,
    )

    assert freqs == [1.0, 10.0, 12.0, 100.0, 101.0]


def test_projection_frequency_weights_can_emphasize_larger_violation_excess():
    projection_frequency_weights = getattr(passivity, "_projection_frequency_weights", None)
    assert projection_frequency_weights is not None
    samples = [
        {"frequency_hz": 1.0, "max_sigma": 1.001, "violates": True},
        {"frequency_hz": 2.0, "max_sigma": 1.020, "violates": True},
    ]

    weights = projection_frequency_weights(
        samples,
        [1.0, 2.0],
        mode="violation_excess",
        epsilon=1e-6,
        exponent=2.0,
    )

    assert weights[1] > weights[0] > 1.0
    assert weights[1] / weights[0] > 100.0


def test_projection_reference_rms_freqs_can_use_candidate_validation_scope():
    selector = getattr(passivity, "_projection_reference_rms_freqs", None)
    assert selector is not None

    projection_scope = selector([1.0, 2.0], [1.0, 2.0, 3.0], mode="projection")
    validation_scope = selector([1.0, 2.0], [1.0, 2.0, 3.0], mode="candidate_validation")
    fallback_scope = selector([1.0, 2.0], None, mode="candidate_validation")

    assert projection_scope == [1.0, 2.0]
    assert validation_scope == [1.0, 2.0, 3.0]
    assert fallback_scope == [1.0, 2.0]


def test_active_mode_residue_constant_delta_repairs_constant_one_port_mode():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j])

    active_mode_delta = getattr(passivity, "_active_mode_residue_constant_delta", None)
    assert active_mode_delta is not None

    candidate_residues, candidate_constant, diagnostic = active_mode_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        epsilon=1e-6,
        perturb_constant=True,
    )

    assert candidate_residues.shape == residues.shape
    assert abs(candidate_constant[0]) < 1.0
    assert diagnostic["success"] is True
    assert diagnostic["constraint_count"] == 1


def test_active_mode_residue_constant_delta_restricts_dominant_response_variables():
    poles = np.array([], dtype=complex)
    residues = np.zeros((4, 0), dtype=complex)
    constant = np.array([0.1 + 0.0j, 0.0j, 0.0j, 1.2 + 0.0j])

    _candidate_residues, _candidate_constant, diagnostic = passivity._active_mode_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=2,
        freqs=[0.0],
        epsilon=1e-6,
        perturb_constant=True,
        max_mode_responses=1,
    )

    assert diagnostic["allowed_response_count"] == 1
    assert diagnostic["active_variable_count"] == 1


def test_active_mode_residue_constant_delta_can_constrain_multiple_singular_modes():
    poles = np.array([], dtype=complex)
    residues = np.zeros((4, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j, 0.0j, 0.0j, 1.1 + 0.0j])

    _one_residues, one_constant, one_diagnostic = passivity._active_mode_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=2,
        freqs=[0.0],
        epsilon=1e-6,
        perturb_constant=True,
        max_mode_responses=1,
        singular_modes=1,
    )
    _two_residues, two_constant, two_diagnostic = passivity._active_mode_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=2,
        freqs=[0.0],
        epsilon=1e-6,
        perturb_constant=True,
        max_mode_responses=1,
        singular_modes=2,
    )

    assert one_diagnostic["constraint_count"] == 1
    assert one_diagnostic["allowed_response_count"] == 1
    assert one_constant[0].real < 1.0
    assert two_diagnostic["constraint_count"] == 2
    assert two_diagnostic["allowed_response_count"] == 2
    assert two_diagnostic["singular_modes"] == 2
    assert two_constant[0].real < 1.0
    assert two_constant[3].real < 1.0


def test_active_mode_residue_constant_delta_can_use_band_selective_singular_modes():
    poles = np.array([], dtype=complex)
    residues = np.zeros((4, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j, 0.0j, 0.0j, 1.1 + 0.0j])

    _candidate_residues, candidate_constant, diagnostic = passivity._active_mode_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=2,
        freqs=[0.0, 1.0],
        epsilon=1e-6,
        perturb_constant=True,
        max_mode_responses=1,
        singular_modes=1,
        band_singular_modes=2,
        band_singular_mode_freqs=[1.0],
    )

    assert diagnostic["constraint_count"] == 3
    assert diagnostic["singular_modes"] == 1
    assert diagnostic["band_singular_modes"] == 2
    assert diagnostic["band_singular_mode_frequency_count"] == 1
    assert diagnostic["allowed_response_count"] == 2
    assert candidate_constant[0].real < 1.0
    assert candidate_constant[3].real < 1.0


def test_dominant_response_indices_from_singular_vectors_are_deterministic():
    selector = getattr(passivity, "_dominant_response_indices_from_singular_vectors", None)
    assert selector is not None

    u_vec = np.array([0.1 + 0.0j, 0.9 + 0.0j])
    v_vec = np.array([0.8 + 0.0j, 0.2 + 0.0j])

    indices = selector(u_vec, v_vec, nports=2, max_responses=2)

    assert indices == [2, 3]


def test_select_projection_candidate_rejects_large_delta_even_with_better_sigma():
    candidates = [
        {
            "scale": 1.0,
            "max_sigma": 1.01,
            "violation_count": 1,
            "delta_norm": 0.20,
        },
        {
            "scale": 0.25,
            "max_sigma": 1.03,
            "violation_count": 1,
            "delta_norm": 0.02,
        },
    ]

    selected = _select_projection_candidate(
        candidates,
        baseline_max_sigma=1.05,
        baseline_violation_count=2,
        max_delta_norm=0.05,
    )

    assert selected["scale"] == pytest.approx(0.25)


def test_select_projection_candidate_can_reject_large_response_delta():
    candidates = [
        {"scale": 1.0, "max_sigma": 1.01, "violation_count": 1, "delta_norm": 0.01, "response_delta_rms": 0.20},
        {"scale": 0.25, "max_sigma": 1.03, "violation_count": 1, "delta_norm": 0.01, "response_delta_rms": 0.02},
    ]

    selected = _select_projection_candidate(
        candidates,
        baseline_max_sigma=1.05,
        baseline_violation_count=2,
        max_response_delta_rms=0.05,
    )

    assert selected["scale"] == pytest.approx(0.25)


def test_select_projection_candidate_can_reject_reference_rms_regression():
    candidates = [
        {
            "scale": 1.0,
            "max_sigma": 1.01,
            "violation_count": 1,
            "delta_norm": 0.01,
            "reference_rms": 0.20,
        },
        {
            "scale": 0.25,
            "max_sigma": 1.03,
            "violation_count": 1,
            "delta_norm": 0.01,
            "reference_rms": 0.11,
        },
    ]

    selected = _select_projection_candidate(
        candidates,
        baseline_max_sigma=1.05,
        baseline_violation_count=2,
        baseline_reference_rms=0.10,
        max_reference_rms_increase=0.02,
    )

    assert selected["scale"] == pytest.approx(0.25)


def test_select_projection_candidate_can_rank_by_post_damping_reference_rms():
    candidates = [
        {
            "scale": 1.0,
            "max_sigma": 1.01,
            "violation_count": 1,
            "delta_norm": 0.01,
            "reference_rms": 0.10,
            "post_damping_reference_rms": 0.20,
        },
        {
            "scale": 0.5,
            "max_sigma": 1.02,
            "violation_count": 2,
            "delta_norm": 0.01,
            "reference_rms": 0.11,
            "post_damping_reference_rms": 0.12,
        },
    ]

    assert (
        _select_projection_candidate(
            candidates,
            baseline_max_sigma=1.03,
            baseline_violation_count=3,
        )["scale"]
        == pytest.approx(1.0)
    )
    assert (
        _select_projection_candidate(
            candidates,
            baseline_max_sigma=1.03,
            baseline_violation_count=3,
            selection_metric="post_damping_reference_rms",
        )["scale"]
        == pytest.approx(0.5)
    )


def test_select_projection_candidate_can_trade_sigma_regression_for_post_damping_rms():
    candidates = [
        {
            "scale": 0.25,
            "max_sigma": 1.0028,
            "violation_count": 134,
            "delta_norm": 0.01,
            "reference_rms": 0.105,
            "post_damping_reference_rms": 0.099,
        }
    ]

    assert (
        _select_projection_candidate(
            candidates,
            baseline_max_sigma=1.0026,
            baseline_violation_count=134,
            selection_metric="post_damping_reference_rms",
            post_damping_max_sigma_regression=3e-4,
            baseline_post_damping_reference_rms=0.10,
        )
        is candidates[0]
    )
    assert (
        _select_projection_candidate(
            candidates,
            baseline_max_sigma=1.0026,
            baseline_violation_count=134,
            selection_metric="post_damping_reference_rms",
            post_damping_max_sigma_regression=1e-4,
            baseline_post_damping_reference_rms=0.10,
        )
        is None
    )


def test_select_projection_candidate_can_trade_tiny_sigma_regression_for_fewer_violations():
    candidates = [
        {
            "scale": 0.0625,
            "max_sigma": 1.00251,
            "violation_count": 134,
            "delta_norm": 0.01,
            "reference_rms": 0.11,
        }
    ]

    selected = _select_projection_candidate(
        candidates,
        baseline_max_sigma=1.00248,
        baseline_violation_count=135,
        max_sigma_regression=0.00005,
    )

    assert selected is candidates[0]


def test_select_projection_candidate_rejects_large_sigma_regression_even_with_fewer_violations():
    candidates = [
        {
            "scale": 0.0625,
            "max_sigma": 1.00300,
            "violation_count": 134,
            "delta_norm": 0.01,
            "reference_rms": 0.11,
        }
    ]

    selected = _select_projection_candidate(
        candidates,
        baseline_max_sigma=1.00248,
        baseline_violation_count=135,
        max_sigma_regression=0.00005,
    )

    assert selected is None


def test_projection_candidate_reject_reason_prefers_total_reference_budget():
    reason = passivity._projection_candidate_reject_reason(
        {
            "scale": 1.0,
            "max_sigma": 1.01,
            "violation_count": 1,
            "delta_norm": 0.01,
            "reference_rms": 0.30,
        },
        baseline_max_sigma=1.05,
        baseline_violation_count=2,
        baseline_reference_rms=0.10,
        max_reference_rms_increase=0.25,
        initial_reference_rms=0.10,
        max_reference_rms_total_increase=0.05,
    )

    assert reason == "reference_rms_total_budget_exceeded"


def test_projection_candidate_reject_reason_can_cap_reference_rms_efficiency():
    reason = passivity._projection_candidate_reject_reason(
        {
            "max_sigma": 1.09,
            "reference_rms": 0.106,
        },
        baseline_max_sigma=1.10,
        baseline_reference_rms=0.10,
        max_reference_rms_per_sigma_improvement=0.5,
    )

    assert reason == "reference_rms_efficiency_exceeded"
    assert (
        passivity._projection_candidate_reject_reason(
            {
                "max_sigma": 1.08,
                "reference_rms": 0.106,
            },
            baseline_max_sigma=1.10,
            baseline_reference_rms=0.10,
            max_reference_rms_per_sigma_improvement=0.5,
        )
        is None
    )
    assert (
        passivity._projection_candidate_reject_reason(
            {
                "max_sigma": 1.09,
                "reference_rms": 0.106,
                "reference_rms_efficiency_gate": False,
            },
            baseline_max_sigma=1.10,
            baseline_reference_rms=0.10,
            max_reference_rms_per_sigma_improvement=0.5,
        )
        is None
    )


def test_projection_candidate_reject_reason_can_cap_late_current_clip_efficiency():
    reason = passivity._projection_candidate_reject_reason(
        {
            "strategy": "current_spectral_clip",
            "projection_iteration": 7,
            "max_sigma": 1.002,
            "reference_rms": 0.22,
        },
        baseline_max_sigma=1.004,
        baseline_reference_rms=0.10,
        late_current_clip_max_reference_rms_per_sigma_improvement=10.0,
        late_current_clip_start_iteration=7,
    )

    assert reason == "late_current_clip_reference_rms_efficiency_exceeded"
    assert (
        passivity._projection_candidate_reject_reason(
            {
                "strategy": "current_spectral_clip",
                "projection_iteration": 6,
                "max_sigma": 1.002,
                "reference_rms": 0.22,
            },
            baseline_max_sigma=1.004,
            baseline_reference_rms=0.10,
            late_current_clip_max_reference_rms_per_sigma_improvement=10.0,
            late_current_clip_start_iteration=7,
        )
        is None
    )


def test_projection_candidate_reject_reason_can_cap_raw_reg_active_mode_total_rms():
    reason = passivity._projection_candidate_reject_reason(
        {
            "strategy": "active_mode",
            "source_diagnostic": {"solver": "reference_regularized_min_norm"},
            "max_sigma": 1.01,
            "violation_count": 1,
            "delta_norm": 0.01,
            "reference_rms": 0.16,
        },
        baseline_max_sigma=1.02,
        baseline_violation_count=2,
        initial_reference_rms=0.10,
        active_mode_max_reference_rms_total_increase=0.05,
    )

    assert reason == "active_mode_reference_rms_total_budget_exceeded"


def test_projection_candidate_reject_reason_caps_peak_minimax_active_mode_total_rms():
    reason = passivity._projection_candidate_reject_reason(
        {
            "strategy": "active_mode",
            "source_diagnostic": {"solver": "reference_regularized_peak_minimax"},
            "max_sigma": 1.01,
            "violation_count": 1,
            "delta_norm": 0.01,
            "reference_rms": 0.16,
        },
        baseline_max_sigma=1.02,
        baseline_violation_count=2,
        initial_reference_rms=0.10,
        active_mode_max_reference_rms_total_increase=0.05,
    )

    assert reason == "active_mode_reference_rms_total_budget_exceeded"


def test_projection_candidate_rejection_summary_counts_final_reasons():
    candidates = [
        {
            "scale": 1.0,
            "max_sigma": 1.01,
            "violation_count": 1,
            "delta_norm": 0.20,
            "reference_rms": 0.10,
        },
        {
            "scale": 0.5,
            "max_sigma": 1.06,
            "violation_count": 1,
            "delta_norm": 0.01,
            "reference_rms": 0.10,
        },
        {
            "scale": 0.25,
            "max_sigma": 1.02,
            "violation_count": 1,
            "delta_norm": 0.01,
            "reference_rms": 0.10,
        },
    ]

    summary = passivity._projection_candidate_rejection_summary(
        candidates,
        baseline_max_sigma=1.05,
        baseline_violation_count=2,
        max_delta_norm=0.05,
    )

    assert summary["accepted_candidates"] == 1
    assert summary["rejected_candidates"] == 2
    assert summary["reasons"] == {
        "delta_norm_exceeded": 1,
        "passivity_not_improved": 1,
    }
    assert summary["best_rejected_candidate"]["reject_reason"] == "passivity_not_improved"
    assert summary["best_rejected_candidate"]["scale"] == pytest.approx(0.5)


def test_response_delta_rms_at_freqs_measures_s_matrix_change():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    before = np.array([1.0 + 0.0j])
    after = np.array([0.9 + 0.0j])

    delta = _response_delta_rms_at_freqs(
        poles,
        residues,
        before,
        residues,
        after,
        nports=1,
        freqs=[0.0, 1.0],
    )

    assert delta == pytest.approx(0.1)


def test_response_delta_rms_at_freqs_can_reuse_precomputed_basis(monkeypatch):
    poles = np.array([-1.0 + 0.0j])
    residues = np.array([[1.0 + 0.0j]])
    before = np.array([0.0 + 0.0j])
    after = np.array([0.1 + 0.0j])
    freqs = [0.0, 1.0]
    basis = passivity._rational_basis_at_freqs(poles, freqs)

    def fail_recompute(*args, **kwargs):
        raise AssertionError("basis should be reused")

    monkeypatch.setattr(passivity, "_rational_basis_at_freqs", fail_recompute)

    delta = _response_delta_rms_at_freqs(
        poles,
        residues,
        before,
        residues,
        after,
        nports=1,
        freqs=freqs,
        basis=basis,
    )

    assert delta == pytest.approx(0.1)


def test_evaluate_s_matrices_at_freqs_matches_scalar_evaluator():
    evaluator = getattr(passivity, "_evaluate_s_matrices_at_freqs", None)
    assert evaluator is not None

    poles = np.array([-1.0 + 0.0j, -2.0 + 3.0j])
    residues = np.array([[2.0 + 0.0j, 1.0 - 0.5j]])
    constant = np.array([0.1 + 0.0j])

    batched = evaluator(poles, residues, constant, nports=1, freqs=[0.0, 2.0, 5.0])
    scalar = np.array(
        [
            passivity._evaluate_s_matrix_at_freq(poles, residues, constant, nports=1, freq=freq)
            for freq in [0.0, 2.0, 5.0]
        ]
    )

    assert batched.shape == (3, 1, 1)
    assert batched == pytest.approx(scalar)


def test_rational_basis_at_freqs_matches_direct_formula():
    helper = getattr(passivity, "_rational_basis_at_freqs", None)
    assert helper is not None
    poles = np.array([-1.0 + 0.0j, -2.0 + 3.0j])
    freqs = np.array([0.0, 2.0])

    basis = helper(poles, freqs)
    expected = 1.0 / (1j * 2.0 * np.pi * freqs[:, None] - poles[None, :])

    assert basis.shape == (2, 2)
    assert basis == pytest.approx(expected)


def test_evaluate_s_matrices_from_basis_matches_scalar_evaluator():
    basis_helper = getattr(passivity, "_rational_basis_at_freqs", None)
    evaluator = getattr(passivity, "_evaluate_s_matrices_from_basis", None)
    assert basis_helper is not None
    assert evaluator is not None
    poles = np.array([-1.0 + 0.0j, -2.0 + 3.0j])
    residues = np.array([[2.0 + 0.0j, 1.0 - 0.5j]])
    constant = np.array([0.1 + 0.0j])
    freqs = [0.0, 2.0, 5.0]

    matrices = evaluator(residues, constant, nports=1, basis=basis_helper(poles, freqs))
    scalar = np.array(
        [
            passivity._evaluate_s_matrix_at_freq(poles, residues, constant, nports=1, freq=freq)
            for freq in freqs
        ]
    )

    assert matrices == pytest.approx(scalar)


def test_reference_response_rms_at_freqs_interpolates_complex_touchstone_data():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.0 + 0.0j])
    reference_freqs = np.array([0.0, 10.0])
    reference_s = np.array([[[1.0 + 0.0j]], [[0.0 + 1.0j]]])

    rms = _reference_response_rms_at_freqs(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[5.0],
        reference_freqs=reference_freqs,
        reference_s=reference_s,
    )

    assert rms == pytest.approx(abs(1.0 - (0.5 + 0.5j)))


def test_current_clip_reference_regularized_projection_weight_zero_matches_current_clip():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j])
    reference_freqs = np.array([0.0])
    reference_s = np.array([[[0.8 + 0.0j]]])

    clip_residues, clip_constant = passivity._projection_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        epsilon=1e-6,
        perturb_constant=True,
    )
    regularized_residues, regularized_constant = passivity._current_clip_reference_regularized_projection_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        reference_freqs=reference_freqs,
        reference_s=reference_s,
        epsilon=1e-6,
        perturb_constant=True,
        reference_weight=0.0,
    )

    assert regularized_residues == pytest.approx(clip_residues)
    assert regularized_constant == pytest.approx(clip_constant)


def test_current_clip_reference_regularized_projection_moves_toward_raw_reference():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j])
    reference_freqs = np.array([0.0])
    reference_s = np.array([[[0.8 + 0.0j]]])

    _clip_residues, clip_constant = passivity._projection_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        epsilon=1e-6,
        perturb_constant=True,
    )
    _regularized_residues, regularized_constant = passivity._current_clip_reference_regularized_projection_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        reference_freqs=reference_freqs,
        reference_s=reference_s,
        epsilon=1e-6,
        perturb_constant=True,
        reference_weight=4.0,
    )

    assert abs(regularized_constant[0] - 0.8) < abs(clip_constant[0] - 0.8)


def test_reference_s_matrices_at_freqs_interpolates_all_ports_once():
    interpolator = getattr(passivity, "_reference_s_matrices_at_freqs", None)
    assert interpolator is not None
    reference_freqs = np.array([0.0, 10.0])
    reference_s = np.array(
        [
            [[1.0 + 0.0j, 0.0 + 0.0j], [0.5 + 0.0j, 0.0 + 1.0j]],
            [[0.0 + 1.0j, 1.0 + 0.0j], [0.0 + 0.5j, 1.0 + 0.0j]],
        ]
    )

    matrices = interpolator([0.0, 5.0, 10.0], reference_freqs=reference_freqs, reference_s=reference_s, nports=2)

    assert matrices.shape == (3, 2, 2)
    assert matrices[1, 0, 0] == pytest.approx(0.5 + 0.5j)
    assert matrices[1, 0, 1] == pytest.approx(0.5 + 0.0j)
    assert matrices[1, 1, 0] == pytest.approx(0.25 + 0.25j)
    assert matrices[1, 1, 1] == pytest.approx(0.5 + 0.5j)


def test_reference_response_rms_to_matrices_reuses_precomputed_reference():
    helper = getattr(passivity, "_reference_response_rms_to_matrices", None)
    assert helper is not None
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.0 + 0.0j])
    reference = np.array([[[1.0 + 0.0j]], [[0.5 + 0.5j]]])

    rms = helper(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0, 5.0],
        reference_matrices=reference,
    )

    assert rms == pytest.approx(np.sqrt((0.0**2 + abs(1.0 - (0.5 + 0.5j)) ** 2) / 2.0))


def test_reference_response_rms_to_matrices_can_reuse_precomputed_basis(monkeypatch):
    helper = getattr(passivity, "_reference_response_rms_to_matrices", None)
    basis_helper = getattr(passivity, "_rational_basis_at_freqs", None)
    assert helper is not None
    assert basis_helper is not None
    poles = np.array([-1.0 + 0.0j])
    residues = np.array([[1.0 + 0.0j]])
    constant = np.array([0.0 + 0.0j])
    freqs = [0.0, 1.0]
    basis = basis_helper(poles, freqs)
    reference = np.zeros((2, 1, 1), dtype=complex)

    def fail_recompute(*args, **kwargs):
        raise AssertionError("basis should be reused")

    monkeypatch.setattr(passivity, "_rational_basis_at_freqs", fail_recompute)

    rms = helper(
        poles,
        residues,
        constant,
        nports=1,
        freqs=freqs,
        reference_matrices=reference,
        basis=basis,
    )

    expected = np.sqrt(np.mean(np.abs(passivity._evaluate_s_matrices_from_basis(residues, constant, nports=1, basis=basis)) ** 2))
    assert rms == pytest.approx(expected)


def test_reference_response_rms_chunked_matches_precomputed_matrices():
    helper = getattr(passivity, "_reference_response_rms_chunked", None)
    assert helper is not None
    poles = np.array([-1.0 + 0.0j])
    residues = np.array(
        [
            [1.0 + 0.0j],
            [0.1 + 0.2j],
            [-0.2 + 0.0j],
            [0.5 - 0.1j],
        ]
    )
    constant = np.array([0.05 + 0.0j, 0.01 + 0.0j, -0.03 + 0.0j, 0.02 + 0.0j])
    freqs = np.array([0.0, 1.0, 2.0, 4.0, 8.0])
    reference_freqs = np.array([0.0, 2.0, 8.0])
    reference_s = np.array(
        [
            [[0.1 + 0.0j, 0.2 + 0.0j], [0.3 + 0.0j, 0.4 + 0.0j]],
            [[0.0 + 0.2j, 0.1 + 0.1j], [0.2 + 0.2j, 0.3 + 0.1j]],
            [[0.3 + 0.0j, 0.2 + 0.3j], [0.1 + 0.2j, 0.0 + 0.1j]],
        ],
        dtype=complex,
    )
    reference = passivity._reference_s_matrices_at_freqs(
        freqs,
        reference_freqs=reference_freqs,
        reference_s=reference_s,
        nports=2,
    )
    expected = passivity._reference_response_rms_to_matrices(
        poles,
        residues,
        constant,
        nports=2,
        freqs=freqs,
        reference_matrices=reference,
        basis=passivity._rational_basis_at_freqs(poles, freqs),
    )

    actual = helper(
        poles,
        residues,
        constant,
        nports=2,
        freqs=freqs,
        reference_freqs=reference_freqs,
        reference_s=reference_s,
        chunk_size=2,
    )

    assert actual == pytest.approx(expected)


def test_reference_response_rms_chunked_uses_bounded_frequency_chunks(monkeypatch):
    helper = getattr(passivity, "_reference_response_rms_chunked", None)
    assert helper is not None
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.0 + 0.0j])
    freqs = np.array([0.0, 1.0, 2.0, 3.0])
    calls = []

    def fake_evaluator(poles_arg, residues_arg, constant_arg, *, nports, freqs):
        freqs_list = list(freqs)
        calls.append(freqs_list)
        return np.ones((len(freqs_list), 1, 1), dtype=complex)

    monkeypatch.setattr(passivity, "_evaluate_s_matrices_at_freqs", fake_evaluator)

    helper(
        poles,
        residues,
        constant,
        nports=1,
        freqs=freqs,
        reference_freqs=freqs,
        reference_s=np.zeros((4, 1, 1), dtype=complex),
        chunk_size=2,
    )

    assert calls == [[0.0, 1.0], [2.0, 3.0]]


def test_reference_response_rms_candidates_chunked_reuses_chunk_basis_and_reference(monkeypatch):
    helper = getattr(passivity, "_reference_response_rms_candidates_chunked", None)
    assert helper is not None
    poles = np.array([-1.0 + 0.0j])
    candidates = [
        (np.array([[1.0 + 0.0j]]), np.array([0.0 + 0.0j])),
        (np.array([[0.5 + 0.0j]]), np.array([0.1 + 0.0j])),
        (np.array([[0.25 + 0.0j]]), np.array([0.2 + 0.0j])),
    ]
    freqs = np.array([0.0, 1.0, 2.0, 3.0])
    reference_s = np.zeros((4, 1, 1), dtype=complex)
    expected = [
        passivity._reference_response_rms_chunked(
            poles,
            residues,
            constant,
            nports=1,
            freqs=freqs,
            reference_freqs=freqs,
            reference_s=reference_s,
            chunk_size=2,
        )
        for residues, constant in candidates
    ]
    basis_calls = []
    reference_calls = []
    original_basis = passivity._rational_basis_at_freqs
    original_reference = passivity._reference_s_matrices_at_freqs

    def counting_basis(poles_arg, freqs_arg):
        freqs_list = list(freqs_arg)
        basis_calls.append(freqs_list)
        return original_basis(poles_arg, freqs_arg)

    def counting_reference(freqs_arg, *, reference_freqs, reference_s, nports):
        freqs_list = list(freqs_arg)
        reference_calls.append(freqs_list)
        return original_reference(freqs_arg, reference_freqs=reference_freqs, reference_s=reference_s, nports=nports)

    monkeypatch.setattr(passivity, "_rational_basis_at_freqs", counting_basis)
    monkeypatch.setattr(passivity, "_reference_s_matrices_at_freqs", counting_reference)

    actual = helper(
        poles,
        candidates,
        nports=1,
        freqs=freqs,
        reference_freqs=freqs,
        reference_s=reference_s,
        chunk_size=2,
    )

    assert actual == pytest.approx(expected)
    assert basis_calls == [[0.0, 1.0], [2.0, 3.0]]
    assert reference_calls == [[0.0, 1.0], [2.0, 3.0]]


def test_reference_response_rms_at_freqs_uses_vectorized_reference_interpolation(monkeypatch):
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.0 + 0.0j])
    reference_freqs = np.array([0.0, 10.0])
    reference_s = np.array([[[1.0 + 0.0j]], [[0.0 + 1.0j]]])
    calls = []

    def fake_batched(poles_arg, residues_arg, constant_arg, *, nports, freqs):
        calls.append(list(freqs))
        return np.ones((len(list(freqs)), 1, 1), dtype=complex)

    monkeypatch.setattr(passivity, "_evaluate_s_matrices_at_freqs", fake_batched)

    rms = _reference_response_rms_at_freqs(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0, 5.0, 10.0],
        reference_freqs=reference_freqs,
        reference_s=reference_s,
    )

    assert calls == [[0.0, 5.0, 10.0]]
    assert rms == pytest.approx(
        np.sqrt((0.0**2 + abs(1.0 - (0.5 + 0.5j)) ** 2 + abs(1.0 - 1.0j) ** 2) / 3.0)
    )


def test_candidate_update_tie_breaks_equal_passivity_by_smaller_delta_norm():
    score = _PassivityScore(1, 1.01)

    assert _is_candidate_update_better(score, 0.5, score, 1.0)
    assert not _is_candidate_update_better(score, 2.0, score, 1.0)
    assert _is_candidate_update_better(_PassivityScore(0, 1.0), 10.0, score, 0.1)


def test_candidate_update_prefers_lower_priority_for_numerically_close_scores():
    best_score = _PassivityScore(1, 1.01)
    candidate_score = _PassivityScore(1, 1.01 - 1e-10)

    assert not _is_candidate_update_better(
        candidate_score,
        0.1,
        best_score,
        1.0,
        candidate_priority=1,
        best_priority=0,
        score_abs_tol=1e-8,
    )


def test_candidate_update_allows_lower_priority_when_score_improvement_is_meaningful():
    best_score = _PassivityScore(1, 1.01)
    candidate_score = _PassivityScore(1, 1.009)

    assert _is_candidate_update_better(
        candidate_score,
        0.1,
        best_score,
        1.0,
        candidate_priority=1,
        best_priority=0,
        score_abs_tol=1e-8,
    )


def test_qp_candidate_rejects_holdout_regression():
    accepted, diagnostic = _validate_candidate_on_holdout(
        sampled_score=_PassivityScore(1, 1.2),
        candidate_score=_PassivityScore(1, 1.1),
        holdout_score=_PassivityScore(1, 1.05),
        candidate_holdout_score=_PassivityScore(1, 1.06),
        candidate_delta_norm=0.01,
        trust_region_limit=0.05,
        candidate_improves_best=True,
    )

    assert accepted is False
    assert diagnostic["reject_reason"] == "holdout_regression"


def test_qp_candidate_rejects_trust_region_excess():
    accepted, diagnostic = _validate_candidate_on_holdout(
        sampled_score=_PassivityScore(1, 1.2),
        candidate_score=_PassivityScore(1, 1.1),
        holdout_score=_PassivityScore(1, 1.05),
        candidate_holdout_score=_PassivityScore(1, 1.04),
        candidate_delta_norm=0.10,
        trust_region_limit=0.05,
        candidate_improves_best=True,
    )

    assert accepted is False
    assert diagnostic["reject_reason"] == "trust_region_exceeded"


def test_candidate_delta_norm_is_relative_to_current_model_size():
    value = _candidate_delta_norm(
        np.array([[1.0, 1.0]]),
        np.array([[1.1, 1.0]]),
        np.array([1.0]),
        np.array([1.0]),
        np.array([-1.0]),
        np.array([-1.0]),
    )

    assert value == pytest.approx(0.1 / (np.sqrt(2.0) + 1.0 + 1.0))


def test_trust_region_limit_tightens_with_iterations():
    first = _trust_region_limit(0, _PassivityScore(1, 1.2), base_limit=0.05)
    later = _trust_region_limit(3, _PassivityScore(1, 1.2), base_limit=0.05)

    assert first == pytest.approx(0.05)
    assert later < first


def test_fit_weighted_qp_is_always_explored_as_a_candidate():
    assert _should_try_fit_weighted_qp(None)
    assert _should_try_fit_weighted_qp(_PassivityScore(1, 1.01))


def test_best_passivity_snapshot_keeps_accepted_final_iteration_improvement():
    current = np.array([[1.0]])
    candidate = np.array([[2.0]])
    best = np.array([[0.0]])

    best_residues, best_score = _best_passivity_snapshot(
        candidate,
        _PassivityScore(1, 1.01),
        best,
        _PassivityScore(1, 1.02),
    )

    assert best_residues is not candidate
    assert best_residues.tolist() == [[2.0]]
    assert best_score == _PassivityScore(1, 1.01)

    unchanged_residues, unchanged_score = _best_passivity_snapshot(
        current,
        _PassivityScore(2, 1.03),
        best_residues,
        best_score,
    )

    assert unchanged_residues.tolist() == [[2.0]]
    assert unchanged_score == _PassivityScore(1, 1.01)


def test_evaluate_passivity_score_at_freqs_counts_violations_and_max_sigma():
    poles = np.array([], dtype=complex)
    residues = np.zeros((4, 0), dtype=complex)
    constant = np.array([1.2, 0.0, 0.0, 0.5], dtype=complex)

    score = _evaluate_passivity_score_at_freqs(poles, residues, constant, nports=2, freqs=[1.0, 2.0], epsilon=1e-6)

    assert score.violation_count == 2
    assert score.max_sigma == pytest.approx(1.2)


def test_select_active_variable_indices_keeps_highest_sensitivity_columns():
    matrix = np.array(
        [
            [0.0, 3.0, -1.0, 0.2],
            [4.0, 0.1, 0.0, 0.5],
        ]
    )

    assert _select_active_variable_indices(matrix, 2).tolist() == [0, 1]


def test_select_active_variable_indices_keeps_all_columns_when_limit_is_zero():
    matrix = np.array([[0.0, 3.0, -1.0]])

    assert _select_active_variable_indices(matrix, 0).tolist() == [0, 1, 2]


def test_constant_active_variable_indices_select_only_constant_block_by_sensitivity():
    matrix = np.array([
        [100.0, 0.0, 0.2, 0.8, 0.1],
        [90.0, 0.0, 0.3, 0.4, 0.9],
    ])

    selected = _constant_active_variable_indices(
        matrix,
        max_active_variables=2,
        n_residue_vars=2,
        n_constant_vars=3,
    )

    assert selected.tolist() == [4, 3]


def test_active_variable_budget_candidates_probe_smaller_windows_before_cap():
    assert _active_variable_budget_candidates(2048, 10000) == [512, 1024, 2048]
    assert _active_variable_budget_candidates(4096, 3000) == [750, 1500, 3000]
    assert _active_variable_budget_candidates(0, 3000) == [0]


def test_apply_constant_delta():
    constant = np.array([1.0, 2.0, 3.0, 4.0])
    x_delta = np.array([0.0, 0.0, 0.0, 0.0, 0.1, -0.2, 0.3, -0.4])
    updated = _apply_constant_delta(constant, x_delta, nports=2, offset=4, scale=0.5)
    expected = np.array([1.0 + 0.05, 2.0 - 0.1, 3.0 + 0.15, 4.0 - 0.2])
    assert np.allclose(updated, expected)


def test_apply_pole_delta():
    poles = np.array([-1.0, -2.0 + 3.0j, -2.0 - 3.0j])
    real_poles = [(0, -1.0)]
    complex_pairs = [(1, 2, -2.0, 3.0)]
    x_delta = np.array([0.0, 0.0, 0.1, -0.2, 0.3])
    updated = _apply_pole_delta(poles, x_delta, real_poles=real_poles, complex_pairs=complex_pairs, offset=2, scale=0.5)
    expected = np.array([-0.95, -2.1 + 3.15j, -2.1 - 3.15j])
    assert np.allclose(updated, expected)


def test_variable_fit_weights_with_all_perturbations():
    poles = np.array([-1.0, -2.0 + 3.0j, -2.0 - 3.0j])
    residues = np.ones((4, 3), dtype=complex)
    real_poles, complex_pairs = partition_poles(poles)
    weights = _variable_fit_weights(
        poles=poles,
        residues=residues,
        nports=2,
        vars_per_pair=3,
        real_poles=real_poles,
        complex_pairs=complex_pairs,
        freqs=[1.0, 2.0],
        perturb_constant=True,
        perturb_poles=True,
        constant_weight=2.0,
        pole_weight=1.5,
    )
    # n_vars = n_residues (2*2*3 = 12) + n_constant (2*2 = 4) + n_poles (3) = 19
    assert len(weights) == 19
    # constant weights should be equal to constant_weight
    assert np.allclose(weights[12:16], 2.0)


def test_base_perturbation_weights_apply_constant_and_pole_penalties():
    weights = _base_perturbation_weights(
        n_residue_vars=3,
        n_constant_vars=2,
        n_pole_vars=1,
        constant_weight=0.25,
        pole_weight=4.0,
    )

    assert weights.tolist() == pytest.approx([1.0, 1.0, 1.0, 0.25, 0.25, 4.0])


def test_model_based_gramian_weights_follow_state_impact():
    A = np.diag([-1.0, -10.0])
    B = np.array([[1.0], [10.0]])

    weights = _controllability_gramian_weights(A, B)

    assert weights.shape == (2,)
    assert weights[1] > weights[0]
    assert np.all(weights >= 0.1)
    assert np.all(weights <= 10.0)


def test_model_based_variable_weights_map_gramian_to_residue_variables():
    poles = np.array([-1.0 + 0.0j, -10.0 + 0.0j])
    residues = np.array([[1.0 + 0.0j, 1.0 + 0.0j]])

    weights = _model_based_variable_weights(
        poles,
        residues,
        np.array([0.0]),
        nports=1,
        vars_per_pair=2,
        real_poles=[(0, -1.0), (1, -10.0)],
        complex_pairs=[],
        perturb_constant=False,
        perturb_poles=False,
    )

    assert weights.shape == (2,)
    assert weights[0] > weights[1]


def test_active_mode_residue_constant_delta_can_use_minimax_solver():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j])

    _candidate_residues, candidate_constant, diagnostic = passivity._active_mode_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        epsilon=1e-6,
        perturb_constant=True,
        solver="minimax_slack",
    )

    assert abs(candidate_constant[0]) < 1.2
    assert diagnostic["success"] is True
    assert diagnostic["solver"] == "minimax_slack"
    assert diagnostic["slack"] is not None


def test_active_mode_residue_constant_delta_can_target_margin():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j])

    _default_residues, default_constant, default_diagnostic = passivity._active_mode_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        epsilon=1e-6,
        perturb_constant=True,
    )
    _margin_residues, margin_constant, margin_diagnostic = passivity._active_mode_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        epsilon=1e-6,
        perturb_constant=True,
        target_margin=0.05,
    )

    assert default_diagnostic["target_margin"] == 0.0
    assert margin_diagnostic["target_margin"] == pytest.approx(0.05)
    assert abs(margin_constant[0]) < abs(default_constant[0])


def test_active_mode_residue_constant_delta_can_regularize_toward_reference():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j])
    reference_s = np.array([[[0.5 + 0.0j]]], dtype=complex)

    _candidate_residues, candidate_constant, diagnostic = passivity._active_mode_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        epsilon=1e-6,
        perturb_constant=True,
        solver="reference_regularized_min_norm",
        reference_freqs=[0.0],
        reference_s=reference_s,
        reference_weight=100.0,
    )

    assert diagnostic["success"] is True
    assert diagnostic["solver"] == "reference_regularized_min_norm"
    assert diagnostic["reference_row_count"] == 2
    assert abs(candidate_constant[0] - 0.5) < abs(1.0 - 0.5)


def test_active_mode_residue_constant_delta_can_use_reference_peak_minimax_solver():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j])
    reference_s = np.array([[[1.0 + 0.0j]]], dtype=complex)

    _min_norm_residues, min_norm_constant, min_norm_diagnostic = (
        passivity._active_mode_residue_constant_delta(
            poles,
            residues,
            constant,
            nports=1,
            freqs=[0.0],
            epsilon=1e-6,
            perturb_constant=True,
            solver="reference_regularized_min_norm",
            reference_freqs=[0.0],
            reference_s=reference_s,
            reference_weight=100.0,
        )
    )
    _peak_residues, peak_constant, peak_diagnostic = passivity._active_mode_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        epsilon=1e-6,
        perturb_constant=True,
        solver="reference_regularized_peak_minimax",
        reference_freqs=[0.0],
        reference_s=reference_s,
        reference_weight=100.0,
    )

    assert min_norm_diagnostic["success"] is True
    assert peak_diagnostic["success"] is True
    assert peak_diagnostic["solver"] == "reference_regularized_peak_minimax"
    assert peak_diagnostic["peak_slack"] < 0.0
    assert abs(peak_constant[0]) < abs(min_norm_constant[0])


def test_active_mode_residue_constant_delta_can_compensate_reference_target():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j])
    reference_s = np.array([[[0.5 + 0.0j]]], dtype=complex)

    _regular_residues, regular_constant, regular_diagnostic = passivity._active_mode_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        epsilon=1e-6,
        perturb_constant=True,
        solver="reference_regularized_min_norm",
        reference_freqs=[0.0],
        reference_s=reference_s,
        reference_weight=100.0,
    )
    _comp_residues, compensated_constant, compensated_diagnostic = (
        passivity._active_mode_residue_constant_delta(
            poles,
            residues,
            constant,
            nports=1,
            freqs=[0.0],
            epsilon=1e-6,
            perturb_constant=True,
            solver="reference_compensated_min_norm",
            reference_freqs=[0.0],
            reference_s=reference_s,
            reference_weight=100.0,
            reference_target_scale=2.0,
        )
    )

    assert regular_diagnostic["success"] is True
    assert compensated_diagnostic["success"] is True
    assert compensated_diagnostic["solver"] == "reference_compensated_min_norm"
    assert compensated_diagnostic["reference_target_scale"] == pytest.approx(2.0)
    assert regular_constant[0].real < compensated_constant[0].real
    assert compensated_constant[0].real <= 1.0


def test_active_mode_reference_rows_can_be_built_for_selected_variables_only():
    poles = np.array([], dtype=complex)
    residues = np.zeros((4, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j, 0.0j, 0.0j, 0.1 + 0.0j])
    reference_s = np.array([[[0.5 + 0.0j, 0.0j], [0.0j, 0.1 + 0.0j]]], dtype=complex)

    rows, targets = passivity._active_mode_reference_rows(
        poles,
        residues,
        constant,
        nports=2,
        freqs=[0.0],
        reference_freqs=[0.0],
        reference_s=reference_s,
        response_indices=[0],
        variable_indices=[0],
        vars_per_pair=0,
        n_residue_vars=0,
        n_vars=4,
        real_poles=[],
        complex_pairs=[],
        perturb_constant=True,
    )

    assert rows.shape == (2, 1)
    assert targets.tolist() == pytest.approx([-0.7, 0.0])


def test_active_mode_reference_scalar_rows_regularize_dominant_mode_only():
    poles = np.array([], dtype=complex)
    residues = np.zeros((4, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j, 0.0j, 0.0j, 0.1 + 0.0j])
    reference_s = np.array([[[0.5 + 0.0j, 0.0j], [0.0j, 0.1 + 0.0j]]], dtype=complex)

    rows, targets = passivity._active_mode_reference_scalar_rows(
        poles,
        residues,
        constant,
        nports=2,
        freqs=[0.0],
        reference_freqs=[0.0],
        reference_s=reference_s,
        variable_indices=[0, 3],
        vars_per_pair=0,
        n_residue_vars=0,
        n_vars=4,
        real_poles=[],
        complex_pairs=[],
        perturb_constant=True,
    )

    assert rows.shape == (2, 2)
    assert targets.tolist() == pytest.approx([-0.7, 0.0])
    assert rows[0].tolist() == pytest.approx([1.0, 0.0])


def test_active_mode_reference_scalar_rows_apply_sample_weights():
    poles = np.array([], dtype=complex)
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j])
    reference_s = np.array([[[0.4 + 0.0j]], [[0.8 + 0.0j]]], dtype=complex)

    rows, targets = passivity._active_mode_reference_scalar_rows(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[1.0, 2.0],
        reference_freqs=[1.0, 2.0],
        reference_s=reference_s,
        variable_indices=[0],
        vars_per_pair=0,
        n_residue_vars=0,
        n_vars=1,
        real_poles=[],
        complex_pairs=[],
        perturb_constant=True,
        sample_weights=[0.25, 1.0],
    )

    assert rows[:, 0].tolist() == pytest.approx([0.5, 0.0, 1.0, 0.0])
    assert targets.tolist() == pytest.approx([-0.4, 0.0, -0.4, 0.0])


def test_active_mode_reference_regularized_solver_can_use_global_reference_points():
    residues = np.zeros((1, 0), dtype=complex)
    constant = np.array([1.2 + 0.0j])
    reference_s = np.array([[[0.8 + 0.0j]], [[0.9 + 0.0j]], [[0.7 + 0.0j]]], dtype=complex)

    _updated_residues, updated_constant, diagnostic = passivity._active_mode_residue_constant_delta(
        np.array([], dtype=complex),
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        epsilon=1e-6,
        perturb_constant=True,
        solver="reference_regularized_min_norm",
        reference_freqs=[0.0, 1.0, 2.0],
        reference_s=reference_s,
        reference_weight=0.1,
        reference_global_points=3,
    )

    assert diagnostic["success"] is True
    assert diagnostic["reference_global_points"] == 3
    assert diagnostic["reference_frequency_count"] == 3
    assert diagnostic["reference_row_count"] == 6
    assert abs(updated_constant[0]) < abs(constant[0])


def test_enforce_passivity_hamiltonian_with_perturbations():
    class FakeVectorFit:
        def __init__(self):
            self.poles = np.array([-1.0])
            self.residues = np.array([[1.1]])  # nports=1, 1 pole, 1 violation
            self.constant_coeff = np.array([1.2])

    vf = FakeVectorFit()
    enforce_passivity_hamiltonian(
        vf,
        nports=1,
        max_iterations=5,
        perturb_constant=True,
        perturb_poles=False,
        constant_only_candidates=True,
    )
    # Verify modification
    assert np.max(np.abs(vf.constant_coeff)) < 1.2 or np.max(np.abs(vf.residues)) < 1.1
    assert any(
        diagnostic.get("weighting") == "constant_only"
        for diagnostic in vf.passivity_enforcement_diagnostics
    )


def test_enforce_passivity_hamiltonian_records_final_validation():
    class FakeVectorFit:
        def __init__(self):
            self.poles = np.array([-1.0])
            self.residues = np.array([[1.1]])
            self.constant_coeff = np.array([1.2])

    vf = FakeVectorFit()
    enforce_passivity_hamiltonian(
        vf,
        nports=1,
        max_iterations=1,
        f_max=10.0,
        perturb_constant=True,
    )

    final_records = [
        diagnostic
        for diagnostic in vf.passivity_enforcement_diagnostics
        if diagnostic.get("type") == "final_validation"
    ]
    assert final_records
    assert "final_validation_max_sigma" in final_records[-1]
    assert "final_validation_violation_count" in final_records[-1]
    assert "final_validation_passed" in final_records[-1]


def test_enforce_repairs_violation_below_numeric_epsilon_to_strictly_passive():
    class FakeVectorFit:
        def __init__(self):
            self.poles = np.array([-1.0])
            self.residues = np.array([[1.0000005]])
            self.constant_coeff = np.array([0.0])

    vf = FakeVectorFit()
    enforce_passivity_hamiltonian(
        vf,
        nports=1,
        epsilon=1e-6,
        max_iterations=1,
        f_max=1.0,
        max_violation_samples=1,
        spectral_projection_reference_freqs=np.array([0.0]),
        spectral_projection_reference_s=np.array([[[1.0000005]]]),
    )

    sigma_at_dc = abs(complex(vf.constant_coeff[0] + vf.residues[0, 0]))
    final_validation = vf.passivity_enforcement_diagnostics[-1]
    assert sigma_at_dc < 1.0
    assert final_validation["type"] == "final_validation"
    assert final_validation["final_validation_passed"] is True
    assert final_validation["final_validation_max_sigma"] < 1.0


def test_enforce_rejects_qp_candidate_with_full_frequency_regression(monkeypatch):
    class FakeVectorFit:
        def __init__(self):
            self.poles = np.array([-1.0])
            self.residues = np.array([[1.1]])
            self.constant_coeff = np.array([1.2])

    monkeypatch.setattr(
        passivity,
        "_full_frequency_passivity_score",
        lambda *args, **kwargs: _PassivityScore(1, 10.0),
        raising=False,
    )
    vf = FakeVectorFit()
    residues_before = vf.residues.copy()
    constant_before = vf.constant_coeff.copy()

    enforce_passivity_hamiltonian(
        vf,
        nports=1,
        max_iterations=1,
        f_max=10.0,
        perturb_constant=True,
    )

    assert np.array_equal(vf.residues, residues_before)
    assert np.array_equal(vf.constant_coeff, constant_before)
    selected = [
        diagnostic
        for diagnostic in vf.passivity_enforcement_diagnostics
        if diagnostic.get("reject_reason") == "full_frequency_regression"
    ]
    assert selected
    assert selected[-1]["full_validation_max_sigma_after"] == pytest.approx(10.0)


def test_enforce_full_frequency_line_search_can_accept_smaller_qp_step(monkeypatch):
    class FakeVectorFit:
        def __init__(self):
            self.poles = np.array([-1.0])
            self.residues = np.array([[1.1]])
            self.constant_coeff = np.array([1.2])

    scores = iter([10.0, 1.01, 1.02, 1.03, 1.04])
    monkeypatch.setattr(
        passivity,
        "_full_frequency_passivity_score",
        lambda *args, **kwargs: _PassivityScore(1, next(scores)),
    )
    vf = FakeVectorFit()
    residues_before = vf.residues.copy()

    enforce_passivity_hamiltonian(
        vf,
        nports=1,
        max_iterations=1,
        f_max=10.0,
        perturb_constant=True,
    )

    assert not np.array_equal(vf.residues, residues_before)
    selected = [
        diagnostic
        for diagnostic in vf.passivity_enforcement_diagnostics
        if diagnostic.get("type") == "full_frequency_line_search"
    ]
    assert selected[-1]["accepted"] is True
    assert selected[-1]["selected_scale"] == pytest.approx(0.5)
    assert selected[-1]["max_sigma_after"] == pytest.approx(1.01)


def test_enforce_full_frequency_line_search_selects_best_post_damping_reference_rms(monkeypatch):
    class FakeVectorFit:
        def __init__(self):
            self.poles = np.array([-1.0])
            self.residues = np.array([[1.1]])
            self.constant_coeff = np.array([1.2])

    scores = iter([10.0, 1.01, 1.02, 1.03, 1.04])
    monkeypatch.setattr(
        passivity,
        "_full_frequency_passivity_score",
        lambda *args, **kwargs: _PassivityScore(1, next(scores)),
    )
    monkeypatch.setattr(passivity, "_reference_response_rms_chunked", lambda *args, **kwargs: 0.05)
    monkeypatch.setattr(
        passivity,
        "_reference_response_rms_candidates_chunked",
        lambda *args, **kwargs: [0.08, 0.07, 0.03, 0.06, 0.07],
    )
    vf = FakeVectorFit()

    enforce_passivity_hamiltonian(
        vf,
        nports=1,
        max_iterations=1,
        f_max=10.0,
        perturb_constant=True,
        global_damping_fallback=True,
        spectral_projection_reference_freqs=np.array([0.0, 10.0]),
        spectral_projection_reference_s=np.zeros((2, 1, 1), dtype=complex),
    )

    selected = [
        diagnostic
        for diagnostic in vf.passivity_enforcement_diagnostics
        if diagnostic.get("type") == "full_frequency_line_search"
    ][-1]
    assert selected["accepted"] is True
    assert selected["selected_scale"] == pytest.approx(0.25)
    assert selected["selected_post_damping_reference_rms"] == pytest.approx(0.03)
    assert selected["baseline_post_damping_reference_rms"] == pytest.approx(0.05)


def test_enforce_does_not_rank_hypothetical_post_damping_when_fallback_is_disabled(monkeypatch):
    class FakeVectorFit:
        def __init__(self):
            self.poles = np.array([-1.0])
            self.residues = np.array([[1.1]])
            self.constant_coeff = np.array([1.2])

    scores = iter([1.01, 1.02, 1.03, 1.04, 1.05])
    monkeypatch.setattr(
        passivity,
        "_full_frequency_passivity_score",
        lambda *args, **kwargs: _PassivityScore(1, next(scores)),
    )

    def unexpected_post_damping_rms(*args, **kwargs):
        raise AssertionError("post-damping RMS must not run without global damping fallback")

    monkeypatch.setattr(passivity, "_reference_response_rms_chunked", unexpected_post_damping_rms)
    monkeypatch.setattr(passivity, "_reference_response_rms_candidates_chunked", unexpected_post_damping_rms)
    vf = FakeVectorFit()

    enforce_passivity_hamiltonian(
        vf,
        nports=1,
        max_iterations=1,
        f_max=10.0,
        perturb_constant=True,
        global_damping_fallback=False,
        spectral_projection_reference_freqs=np.array([0.0, 10.0]),
        spectral_projection_reference_s=np.zeros((2, 1, 1), dtype=complex),
    )

    selected = [
        diagnostic
        for diagnostic in vf.passivity_enforcement_diagnostics
        if diagnostic.get("type") == "full_frequency_line_search"
    ][-1]
    assert selected["selected_scale"] == pytest.approx(1.0)
    assert selected["max_sigma_after"] == pytest.approx(1.01)
    assert selected["baseline_post_damping_reference_rms"] is None


def test_enforce_passivity_global_damping_fallback_scales_model_below_one():
    class FakeVectorFit:
        def __init__(self):
            self.poles = np.array([])
            self.residues = np.zeros((1, 0), dtype=complex)
            self.constant_coeff = np.array([1.2])

    vf = FakeVectorFit()
    enforce_passivity_hamiltonian(
        vf,
        nports=1,
        max_iterations=0,
        f_max=10.0,
        global_damping_fallback=True,
    )

    assert abs(vf.constant_coeff[0]) < 1.0
    damping_records = [
        diagnostic
        for diagnostic in vf.passivity_enforcement_diagnostics
        if diagnostic.get("type") == "global_damping_fallback"
    ]
    assert damping_records
    assert damping_records[-1]["safety_margin"] == 1e-5


def test_global_damping_includes_nonpassive_asymptote_when_finite_band_is_passive():
    class FakeVectorFit:
        def __init__(self):
            self.poles = np.array([-1e9])
            self.residues = np.array([[-0.3e9]], dtype=complex)
            self.constant_coeff = np.array([1.2])

    vf = FakeVectorFit()
    enforce_passivity_hamiltonian(
        vf,
        nports=1,
        epsilon=1e-6,
        max_iterations=0,
        f_max=1.0,
        global_damping_fallback=True,
    )

    final_validation = vf.passivity_enforcement_diagnostics[-1]
    assert abs(vf.constant_coeff[0]) < 1.0
    assert final_validation["final_validation_passed"] is True
    assert final_validation["final_validation_max_sigma"] < 1.0


def test_enforce_passivity_global_damping_revalidates_until_sampled_passive(monkeypatch):
    class FakeVectorFit:
        def __init__(self):
            self.poles = np.array([])
            self.residues = np.zeros((1, 0), dtype=complex)
            self.constant_coeff = np.array([1.2])

    sample_sigmas = iter([1.2, 1.01, 0.999])
    sample_calls = []

    def fake_crossovers(*args, **kwargs):
        return []

    def fake_samples(*args, **kwargs):
        sigma = next(sample_sigmas)
        sample_calls.append(sigma)
        return [
            {
                "frequency_hz": 0.0,
                "max_sigma": sigma,
                "violates": sigma > 1.0 + 1e-6,
            }
        ]

    monkeypatch.setattr(passivity, "check_passivity_hamiltonian_s", fake_crossovers)
    monkeypatch.setattr(passivity, "_projection_candidate_passivity_samples", fake_samples)

    vf = FakeVectorFit()
    enforce_passivity_hamiltonian(
        vf,
        nports=1,
        max_iterations=0,
        f_max=10.0,
        global_damping_fallback=True,
    )

    damping_records = [
        diagnostic
        for diagnostic in vf.passivity_enforcement_diagnostics
        if diagnostic.get("type") == "global_damping_fallback"
    ]
    assert sample_calls == [1.2, 1.01, 0.999]
    assert damping_records[-1]["damping_iterations"] == 2
    assert damping_records[-1]["max_sigma_after"] == pytest.approx(0.999)


def test_enforce_passivity_iterative_spectral_projection_records_multiple_steps():
    class FakeVectorFit:
        def __init__(self):
            self.poles = np.array([])
            self.residues = np.zeros((1, 0), dtype=complex)
            self.constant_coeff = np.array([1.2])

    vf = FakeVectorFit()
    enforce_passivity_hamiltonian(
        vf,
        nports=1,
        max_iterations=0,
        f_max=10.0,
        perturb_constant=True,
        spectral_projection_fallback=True,
        spectral_projection_max_response_delta_rms=0.051,
        spectral_projection_iterations=2,
    )

    projection_records = [
        diagnostic
        for diagnostic in vf.passivity_enforcement_diagnostics
        if diagnostic.get("type") == "spectral_projection_fallback"
    ]
    assert len(projection_records) == 2
    assert abs(vf.constant_coeff[0]) < 1.15


def test_enforce_passivity_spectral_projection_uses_raw_reference_target_when_available():
    class FakeVectorFit:
        def __init__(self):
            self.poles = np.array([])
            self.residues = np.zeros((1, 0), dtype=complex)
            self.constant_coeff = np.array([1.2 + 0.0j])

    vf = FakeVectorFit()
    enforce_passivity_hamiltonian(
        vf,
        nports=1,
        max_iterations=0,
        f_max=10.0,
        perturb_constant=True,
        spectral_projection_fallback=True,
        spectral_projection_reference_freqs=np.array([0.0, 10.0]),
        spectral_projection_reference_s=np.array([[[0.8 + 0.0j]], [[0.8 + 0.0j]]]),
    )

    assert vf.constant_coeff[0].real == pytest.approx(0.8, abs=1e-5)
    projection_records = [
        diagnostic
        for diagnostic in vf.passivity_enforcement_diagnostics
        if diagnostic.get("type") == "spectral_projection_fallback"
    ]
    assert projection_records[-1]["selected_reference_rms"] == pytest.approx(0.0, abs=1e-5)
