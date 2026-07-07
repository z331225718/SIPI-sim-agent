import json
import inspect

import numpy as np
import pytest

from agent_spice.sparam.passivity import (
    _PassivityScore,
    _active_variable_budget_candidates,
    _best_passivity_snapshot,
    _line_search_eval_frequencies,
    _qp_attempt_diagnostic,
    _is_candidate_update_better,
    _evaluate_passivity_score_at_freqs,
    _residue_variable_fit_weights,
    _should_try_fit_weighted_qp,
    _select_active_variable_indices,
    _solve_min_norm_upper_bound_dual_qp,
    _singular_violation_modes,
    sample_streaming_singular_values,
    sample_vector_fit_passivity,
    _variable_fit_weights,
    _apply_constant_delta,
    _apply_pole_delta,
    partition_poles,
    enforce_passivity_hamiltonian,
)


def test_hamiltonian_passivity_advanced_perturbations_are_experimental_opt_in():
    signature = inspect.signature(enforce_passivity_hamiltonian)

    assert signature.parameters["perturb_constant"].default is False
    assert signature.parameters["perturb_poles"].default is False


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


def test_dual_qp_uses_variable_weights_as_fit_impact_penalty():
    result = _solve_min_norm_upper_bound_dual_qp(
        np.array([[1.0, 1.0]]),
        np.array([-1.0]),
        variable_weights=np.array([1.0, 100.0]),
    )

    assert result.success is True
    assert result.x == pytest.approx([-100.0 / 101.0, -1.0 / 101.0], rel=1e-5)


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


def test_fit_weighted_qp_is_only_a_fallback_when_residue_norm_has_no_candidate():
    assert _should_try_fit_weighted_qp(None)
    assert not _should_try_fit_weighted_qp(_PassivityScore(1, 1.01))


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
    )
    # Verify modification
    assert np.max(np.abs(vf.constant_coeff)) < 1.2 or np.max(np.abs(vf.residues)) < 1.1
