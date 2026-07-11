from __future__ import annotations

import numpy as np
import pytest

from agent_spice.sparam.mft_nnls.nnls import solve_homogeneous_nnls, solve_least_distance_nnls


def test_nnls_matches_known_nonnegative_solution_and_kkt_residual() -> None:
    system = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    target = np.array([1.0, -1.0, 1.0])

    result = solve_least_distance_nnls(system, target, tolerance=1.0e-10)

    assert result.x == pytest.approx([1.0, 0.0], abs=1.0e-10)
    assert result.residual_norm == pytest.approx(1.0)
    assert result.kkt_stationarity_inf_norm <= 1.0e-10


def test_nnls_handles_rank_deficient_system_without_negative_solution() -> None:
    result = solve_least_distance_nnls(np.array([[1.0, 1.0], [2.0, 2.0]]), np.array([1.0, 2.0]), tolerance=1.0e-10)

    assert result.rank == 1
    assert np.all(result.x >= 0.0)
    assert result.residual_norm <= 1.0e-10


def test_nnls_rejects_inconsistent_shapes_and_nonpositive_tolerance() -> None:
    with pytest.raises(ValueError, match="rows"):
        solve_least_distance_nnls(np.ones((2, 2)), np.ones(3), tolerance=1.0e-8)
    with pytest.raises(ValueError, match="tolerance"):
        solve_least_distance_nnls(np.ones((2, 2)), np.ones(2), tolerance=0.0)


def test_homogeneous_qr_nnls_matches_matlab_reference_artifact() -> None:
    with np.load("tests/fixtures/mft_nnls/nnls_reference.npz") as fixture:
        result = solve_homogeneous_nnls(fixture["constraint_matrix"], fixture["constraint_rhs"], tolerance=1.0e-12)

        assert result.x == pytest.approx(fixture["xbar"], rel=1.0e-12, abs=1.0e-12)
        assert result.homogeneous_residual == pytest.approx(fixture["residual"], rel=1.0e-12, abs=1.0e-12)
        assert result.dual_variables == pytest.approx(fixture["dual_variables"], rel=1.0e-12, abs=1.0e-12)
