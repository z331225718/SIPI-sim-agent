from __future__ import annotations

import numpy as np
import pytest

from agent_spice.sparam import passivity


def test_active_mode_residue_sensitivity_matches_two_port_finite_difference() -> None:
    poles = np.array([-2.0 + 0.0j])
    residues = np.zeros((4, 1), dtype=complex)
    constant = np.array([1.1 + 0.0j, 0.10 + 0.0j, 0.05 + 0.0j, 0.25 + 0.0j])
    frequency_hz = 0.0

    system = passivity.build_active_mode_residue_sensitivity_system(
        poles,
        residues,
        constant,
        nports=2,
        freqs=[frequency_hz],
        epsilon=0.0,
        perturb_constant=True,
    )

    assert system.constraint_count == 1
    assert system.residue_variable_count == 4
    assert system.constant_variable_count == 4
    assert system.constraint_frequencies_hz == (frequency_hz,)
    assert system.constraint_sigmas[0] > 1.0
    assert system.diagnostics()["constraint_rank"] == 1
    assert system.diagnostics()["finite"] is True

    delta = 1.0e-7
    before = passivity._evaluate_s_matrix_at_freq(
        poles, residues, constant, nports=2, freq=frequency_hz
    )
    perturbed_residues = residues.copy()
    perturbed_residues[0, 0] += delta
    after = passivity._evaluate_s_matrix_at_freq(
        poles, perturbed_residues, constant, nports=2, freq=frequency_hz
    )
    finite_difference = (
        float(np.max(np.linalg.svd(after, compute_uv=False)))
        - float(np.max(np.linalg.svd(before, compute_uv=False)))
    ) / delta

    assert system.A_ineq[0, 0] == pytest.approx(finite_difference, rel=1.0e-5, abs=1.0e-6)
    assert system.b_ineq[0] == pytest.approx(1.0 - system.constraint_sigmas[0])


def test_active_mode_sensitivity_omits_passive_samples() -> None:
    system = passivity.build_active_mode_residue_sensitivity_system(
        np.array([-1.0 + 0.0j]),
        np.zeros((1, 1), dtype=complex),
        np.array([0.9 + 0.0j]),
        nports=1,
        freqs=[0.0, 1.0],
        epsilon=1.0e-6,
        perturb_constant=False,
    )

    assert system.constraint_count == 0
    assert system.A_ineq.shape == (0, 1)
    assert system.b_ineq.shape == (0,)


def test_active_mode_sensitivity_handles_negative_imaginary_pole_first() -> None:
    poles = np.array([-2.0 - 3.0j, -2.0 + 3.0j])
    residues = np.zeros((1, 2), dtype=complex)
    constant = np.array([1.1 + 0.0j])
    system = passivity.build_active_mode_residue_sensitivity_system(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        epsilon=0.0,
        perturb_constant=False,
    )

    delta = 1.0e-7
    perturbed = residues.copy()
    perturbed[0, 0] -= 1j * delta
    perturbed[0, 1] += 1j * delta
    before = float(np.max(np.linalg.svd(
        passivity._evaluate_s_matrix_at_freq(poles, residues, constant, nports=1, freq=0.0),
        compute_uv=False,
    )))
    after = float(np.max(np.linalg.svd(
        passivity._evaluate_s_matrix_at_freq(poles, perturbed, constant, nports=1, freq=0.0),
        compute_uv=False,
    )))

    assert system.A_ineq[0, 1] == pytest.approx((after - before) / delta, rel=1.0e-5, abs=1.0e-6)
    assert passivity.partition_poles(poles)[1][0][:2] == (1, 0)


def test_active_mode_residue_update_does_not_increase_sigma_for_negative_imaginary_pole_first() -> None:
    poles = np.array([-2.0 - 3.0j, -2.0 + 3.0j])
    residues = np.zeros((1, 2), dtype=complex)
    constant = np.array([1.1 + 0.0j])
    before = float(np.max(np.linalg.svd(
        passivity._evaluate_s_matrix_at_freq(poles, residues, constant, nports=1, freq=0.0),
        compute_uv=False,
    )))

    updated_residues, updated_constant, diagnostic = passivity._active_mode_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        epsilon=0.0,
        perturb_constant=False,
    )
    after = float(np.max(np.linalg.svd(
        passivity._evaluate_s_matrix_at_freq(poles, updated_residues, updated_constant, nports=1, freq=0.0),
        compute_uv=False,
    )))

    assert diagnostic["success"] is True
    assert after < before


def test_active_mode_sensitivity_uses_safety_margin_as_target() -> None:
    system = passivity.build_active_mode_residue_sensitivity_system(
        np.array([-1.0 + 0.0j]),
        np.zeros((1, 1), dtype=complex),
        np.array([0.995 + 0.0j]),
        nports=1,
        freqs=[0.0],
        epsilon=0.0,
        safety_margin=0.01,
        perturb_constant=False,
    )

    assert system.constraint_count == 1
    assert system.b_ineq[0] == pytest.approx(0.99 - 0.995)


def test_active_mode_sensitivity_compresses_to_dominant_response_coordinates() -> None:
    system = passivity.build_active_mode_residue_sensitivity_system(
        np.array([-1.0 + 0.0j]),
        np.zeros((4, 1), dtype=complex),
        np.array([1.1 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j, 0.2 + 0.0j]),
        nports=2,
        freqs=[0.0],
        epsilon=0.0,
        perturb_constant=True,
        max_mode_responses=1,
    )

    # The active singular mode is entirely S11, so all inactive response
    # coordinates must be eliminated from the NNLS problem.
    assert system.response_indices == (0,)
    assert system.full_variable_count == 8
    assert system.variable_count == 2
    assert system.full_variable_indices.tolist() == [0, 4]


def test_nnls_dual_transform_matches_reference_dual_qp() -> None:
    A_ineq = np.array([[1.0, 0.2], [0.1, 1.0]])
    b_ineq = np.array([-0.3, -0.2])
    weights = np.array([2.0, 0.5])

    nnls_result = passivity._solve_min_norm_upper_bound_nnls(
        A_ineq,
        b_ineq,
        variable_weights=weights,
    )
    qp_result = passivity._solve_min_norm_upper_bound_dual_qp(
        A_ineq,
        b_ineq,
        variable_weights=weights,
    )

    assert nnls_result.success is True
    assert qp_result.success is True
    assert nnls_result.x == pytest.approx(qp_result.x, rel=1.0e-5, abs=1.0e-7)
    assert np.max(A_ineq @ nnls_result.x - b_ineq) <= 1.0e-6


def test_active_mode_nnls_solver_reduces_a_single_violation() -> None:
    poles = np.array([-1.0 + 0.0j])
    residues = np.zeros((1, 1), dtype=complex)
    constant = np.array([1.1 + 0.0j])
    updated_residues, updated_constant, diagnostic = passivity._active_mode_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=1,
        freqs=[0.0],
        epsilon=0.0,
        perturb_constant=True,
        solver="nnls",
    )
    sigma = float(np.max(np.linalg.svd(
        passivity._evaluate_s_matrix_at_freq(poles, updated_residues, updated_constant, nports=1, freq=0.0),
        compute_uv=False,
    )))

    assert diagnostic["success"] is True
    assert diagnostic["solver"] == "nnls"
    assert sigma < 1.1


def test_active_mode_nnls_uses_compressed_response_system() -> None:
    poles = np.array([-1.0 + 0.0j])
    residues = np.zeros((4, 1), dtype=complex)
    constant = np.array([1.1 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j, 0.2 + 0.0j])

    _residues, _constant, diagnostic = passivity._active_mode_residue_constant_delta(
        poles,
        residues,
        constant,
        nports=2,
        freqs=[0.0],
        epsilon=0.0,
        perturb_constant=True,
        solver="nnls",
        max_mode_responses=1,
        band_singular_mode_freqs=[],
    )

    assert diagnostic["success"] is True
    assert diagnostic["compressed"] is True
    assert diagnostic["full_variable_count"] == 8
    assert diagnostic["active_variable_count"] == 2
    assert diagnostic["response_indices"] == [0]


def test_reference_regularized_nnls_matches_reference_dual_qp() -> None:
    A_ineq = np.array([[1.0, 0.1], [0.2, 1.0]])
    b_ineq = np.array([-0.2, -0.3])
    C_ref = np.eye(2)
    d_ref = np.array([0.03, -0.02])

    nnls_result = passivity._solve_reference_regularized_upper_bound_nnls(
        A_ineq,
        b_ineq,
        C_ref,
        d_ref,
        reference_weight=0.5,
    )
    qp_result = passivity._solve_reference_regularized_upper_bound_dual_qp(
        A_ineq,
        b_ineq,
        C_ref,
        d_ref,
        reference_weight=0.5,
    )

    assert nnls_result.success is True
    assert qp_result.success is True
    assert nnls_result.x == pytest.approx(qp_result.x, rel=2.0e-4, abs=5.0e-5)
    assert np.max(A_ineq @ nnls_result.x - b_ineq) <= 1.0e-6


def test_compact_projection_diagnostic_preserves_nnls_compression_dimensions() -> None:
    compact = passivity._compact_projection_candidate_diagnostic(
        {
            "source_diagnostic": {
                "solver": "nnls",
                "compressed": True,
                "full_variable_count": 33573,
                "variable_count": 2976,
                "response_count": 32,
            }
        },
        reject_reason=None,
    )

    source = compact["source_diagnostic"]
    assert source["solver"] == "nnls"
    assert source["compressed"] is True
    assert source["full_variable_count"] == 33573
    assert source["variable_count"] == 2976
    assert source["response_count"] == 32
