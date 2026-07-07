import numpy as np
import pytest

from agent_spice.sparam.passivity import (
    _PassivityScore,
    _active_variable_budget_candidates,
    _best_passivity_snapshot,
    _is_candidate_update_better,
    _evaluate_passivity_score_at_freqs,
    _select_active_variable_indices,
    _solve_min_norm_upper_bound_dual_qp,
    _singular_violation_modes,
    sample_streaming_singular_values,
    sample_vector_fit_passivity,
)


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


def test_dual_qp_leaves_inactive_upper_bound_at_origin():
    result = _solve_min_norm_upper_bound_dual_qp(np.array([[1.0]]), np.array([0.2]))

    assert result.success is True
    assert result.x == pytest.approx([0.0])


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
