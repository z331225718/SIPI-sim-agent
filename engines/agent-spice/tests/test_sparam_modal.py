import numpy as np
import pytest

from agent_spice.sparam.modal import (
    ModalZFitConfig,
    _select_anchor_ports_by_projection_search,
    build_modal_basis,
    fit_fixed_pole_response,
    fit_reduced_modal_z,
    pole_frequencies_hz,
    project_z_to_basis,
    reconstruct_z_from_basis,
    s_rms_error,
    stable_poles,
    z_log_magnitude_rms_error,
)


def test_z_log_magnitude_rms_error_is_zero_for_identical_arrays():
    z = np.array([[[1.0 + 0j, 0.1 + 0j], [0.1 + 0j, 2.0 + 0j]]])

    assert z_log_magnitude_rms_error(z, z) == 0.0


def test_s_rms_error_is_zero_for_identical_arrays():
    s = np.array([[[0.0 + 0j, 1.0 + 0j], [1.0 + 0j, 0.0 + 0j]]])

    assert s_rms_error(s, s) == 0.0


def test_modal_projection_reconstructs_rank_one_z_matrix():
    z = np.array([[[3.0 + 0j, 0.0 + 0j], [0.0 + 0j, 0.0 + 0j]]])

    basis = build_modal_basis(z, mode_count=1, decomposition="svd")
    reduced = project_z_to_basis(z, basis)
    reconstructed = reconstruct_z_from_basis(reduced, basis)

    assert z_log_magnitude_rms_error(z[:, :1, :1], reconstructed[:, :1, :1]) < 1e-12


def test_build_modal_basis_rejects_invalid_shape_and_mode_count():
    with pytest.raises(ValueError, match="shape"):
        build_modal_basis(np.zeros((2, 2)), mode_count=1)
    with pytest.raises(ValueError, match="mode_count"):
        build_modal_basis(np.zeros((1, 2, 2)), mode_count=3)
    with pytest.raises(ValueError, match="decomposition"):
        build_modal_basis(np.zeros((1, 2, 2)), mode_count=1, decomposition="bad")


def test_build_modal_basis_can_anchor_ports():
    z = np.zeros((2, 3, 3), dtype=complex)
    z[:, 0, 0] = 1.0
    z[:, 1, 1] = 2.0
    z[:, 2, 2] = 3.0

    basis = build_modal_basis(z, mode_count=2, decomposition="svd", anchor_ports=(3,))

    assert np.allclose(basis[:, 0], np.array([0.0, 0.0, 1.0]))
    assert np.allclose(basis.conj().T @ basis, np.eye(2), atol=1e-12)


def test_anchor_port_search_uses_projection_error_not_just_greedy_scores():
    freqs = np.array([1.0])
    z = np.zeros((1, 3, 3), dtype=complex)
    z[:, 0, 0] = 1.0
    z[:, 2, 2] = 1.0
    projected = z.copy()
    projected[:, 0, 0] = 10.0
    projected[:, 1, 1] = 10.0

    ports = _select_anchor_ports_by_projection_search(
        freqs,
        z,
        ModalZFitConfig(mode_count=2, basis_frequency_sample_count=1, decomposition="svd"),
        mode_count=2,
        basis_sample_count=1,
        anchor_count=2,
        unanchored_projected=projected,
    )

    assert set(ports) == {1, 3}


def test_stable_poles_are_left_half_plane():
    freqs = np.array([0.0, 1e6, 2e6, 3e6])

    poles = stable_poles(freqs, scalar_fit_order=5, damping=0.1)

    assert len(poles) == 5
    assert np.all(poles.real < 0.0)
    assert any(pole.imag > 0.0 for pole in poles)
    assert any(pole.imag < 0.0 for pole in poles)


def test_fixed_pole_fit_preserves_constant_response():
    freqs = np.array([0.0, 1e6, 2e6, 3e6])
    values = np.array([2.5 + 0.2j] * len(freqs))

    fitted = fit_fixed_pole_response(freqs, values, scalar_fit_order=4)

    assert np.max(np.abs(fitted - values)) < 1e-10


def test_fit_reduced_modal_z_reports_basis_and_fit_error():
    freqs = np.array([0.0, 1e6, 2e6, 3e6])
    z = np.zeros((len(freqs), 2, 2), dtype=complex)
    z[:, 0, 0] = 2.0 + 0.1j

    result = fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, scalar_fit_order=4, decomposition="svd"))

    assert result.mode_count == 1
    assert result.z_log_magnitude_rms_error < 1e-10
    assert result.basis_projection_z_log_magnitude_rms_error < 1e-10
    assert result.worst_error_frequency_hz in set(freqs)
    assert result.worst_error_port_pair == (1, 1)


def test_fit_reduced_modal_z_can_use_vector_fitting_for_reduced_matrix():
    freqs = np.array([0.0, 1e6, 2e6, 3e6, 4e6])
    z = np.zeros((len(freqs), 2, 2), dtype=complex)
    z[:, 0, 0] = 1.0 + 1j * freqs / 1e6

    result = fit_reduced_modal_z(
        freqs,
        z,
        ModalZFitConfig(
            mode_count=1,
            scalar_fit_order=6,
            decomposition="svd",
            reduced_fit_method="vector",
        ),
    )

    assert result.reduced_fit_method == "vector"
    assert result.z_log_magnitude_rms_error < 1e-8


def test_fit_reduced_modal_z_can_use_shared_adaptive_poles():
    freqs = np.linspace(1e6, 20e6, 32)
    pole = -1e7 + 2j * np.pi * 7e6
    response = 0.25 + 1e7 / (2j * np.pi * freqs - pole)
    z = np.zeros((len(freqs), 2, 2), dtype=complex)
    z[:, 0, 0] = response

    result = fit_reduced_modal_z(
        freqs,
        z,
        ModalZFitConfig(
            mode_count=1,
            scalar_fit_order=6,
            decomposition="svd",
            reduced_fit_method="shared-poles",
            shared_pole_trace_count=1,
            vector_target_error=0.001,
        ),
    )

    assert result.reduced_fit_method == "shared-poles"
    assert result.z_log_magnitude_rms_error < 0.02


def test_fit_reduced_modal_z_can_use_peak_poles():
    freqs = np.linspace(1e6, 20e6, 32)
    resonance = 7e6
    response = 0.25 + 4.0 / (1.0 + 1j * (freqs - resonance) / 5e5)
    z = np.zeros((len(freqs), 2, 2), dtype=complex)
    z[:, 0, 0] = response

    result = fit_reduced_modal_z(
        freqs,
        z,
        ModalZFitConfig(
            mode_count=1,
            scalar_fit_order=6,
            decomposition="svd",
            reduced_fit_method="peak-poles",
            shared_pole_trace_count=1,
            pole_damping=0.08,
        ),
    )

    assert result.reduced_fit_method == "peak-poles"
    assert result.selected_poles is not None
    assert 0 < len(result.selected_poles) <= 6
    assert result.z_log_magnitude_rms_error < 0.05


def test_peak_poles_can_complete_unique_pole_order():
    freqs = np.linspace(1e6, 20e6, 32)
    resonance = 7e6
    response = 0.25 + 4.0 / (1.0 + 1j * (freqs - resonance) / 5e5)
    z = np.zeros((len(freqs), 2, 2), dtype=complex)
    z[:, 0, 0] = response

    result = fit_reduced_modal_z(
        freqs,
        z,
        ModalZFitConfig(
            mode_count=1,
            scalar_fit_order=6,
            decomposition="svd",
            reduced_fit_method="peak-poles",
            shared_pole_trace_count=1,
            pole_damping=0.08,
            peak_pole_complete_order=True,
        ),
    )

    assert result.selected_poles is not None
    assert len(result.selected_poles) == 6


def test_peak_poles_can_reserve_low_frequency_head_poles():
    freqs = np.array([0.0, 0.1, 0.12, 1e6, 2e6, 3e6])
    response = np.array([10.0, 1e6, 8e5, 1.0, 1.2, 0.9], dtype=complex)
    z = np.zeros((len(freqs), 1, 1), dtype=complex)
    z[:, 0, 0] = response

    result = fit_reduced_modal_z(
        freqs,
        z,
        ModalZFitConfig(
            mode_count=1,
            scalar_fit_order=8,
            decomposition="svd",
            reduced_fit_method="peak-poles",
            frequency_sample_head_count=3,
            peak_pole_frequency_head_count=2,
            shared_pole_trace_count=1,
        ),
    )

    selected_frequencies = pole_frequencies_hz(result.selected_poles)
    assert any(abs(freq - 0.1) < 1e-12 for freq in selected_frequencies)
    assert any(abs(freq - 0.12) < 1e-12 for freq in selected_frequencies)


def test_peak_poles_can_use_full_pair_projection_candidates():
    freqs = np.linspace(1e6, 20e6, 32)
    resonance = 11e6
    z = np.zeros((len(freqs), 2, 2), dtype=complex)
    z[:, 0, 0] = 1.0
    z[:, 1, 1] = 1.0
    z[:, 0, 1] = 0.1 + 3.0 / (1.0 + 1j * (freqs - resonance) / 5e5)

    result = fit_reduced_modal_z(
        freqs,
        z,
        ModalZFitConfig(
            mode_count=1,
            scalar_fit_order=8,
            decomposition="svd",
            reduced_fit_method="peak-poles",
            shared_pole_trace_count=1,
            pole_damping=0.08,
            peak_pole_full_pair_count=1,
        ),
    )

    selected_frequencies = pole_frequencies_hz(result.selected_poles)
    assert any(abs(freq - resonance) / resonance < 0.1 for freq in selected_frequencies)


def test_fit_reduced_modal_z_rejects_negative_relative_weight_power():
    freqs = np.linspace(1e6, 3e6, 3)
    z = np.zeros((len(freqs), 1, 1), dtype=complex)
    z[:, 0, 0] = 1.0

    with pytest.raises(ValueError, match="relative_weight_power"):
        fit_reduced_modal_z(
            freqs,
            z,
            ModalZFitConfig(
                mode_count=1,
                reduced_fit_method="peak-poles",
                relative_weight_power=-0.1,
            ),
        )


def test_fit_reduced_modal_z_rejects_unknown_relative_weight_mode():
    freqs = np.linspace(1e6, 3e6, 3)
    z = np.zeros((len(freqs), 1, 1), dtype=complex)
    z[:, 0, 0] = 1.0

    with pytest.raises(ValueError, match="relative_weight_mode"):
        fit_reduced_modal_z(
            freqs,
            z,
            ModalZFitConfig(
                mode_count=1,
                reduced_fit_method="peak-poles",
                relative_weight_mode="bad",
            ),
        )


def test_fit_reduced_modal_z_rejects_invalid_relative_weight_iteration_config():
    freqs = np.linspace(1e6, 3e6, 3)
    z = np.zeros((len(freqs), 1, 1), dtype=complex)
    z[:, 0, 0] = 1.0

    with pytest.raises(ValueError, match="relative_weight_iterations"):
        fit_reduced_modal_z(
            freqs,
            z,
            ModalZFitConfig(
                mode_count=1,
                reduced_fit_method="peak-poles",
                relative_weight_iterations=0,
            ),
        )
    with pytest.raises(ValueError, match="relative_weight_update"):
        fit_reduced_modal_z(
            freqs,
            z,
            ModalZFitConfig(
                mode_count=1,
                reduced_fit_method="peak-poles",
                relative_weight_update="bad",
            ),
        )


def test_fit_reduced_modal_z_can_use_target_error_weighting():
    freqs = np.linspace(1e6, 8e6, 8)
    z = np.zeros((len(freqs), 2, 2), dtype=complex)
    z[:, 0, 0] = 1.0 + 0.1j * freqs / 1e6
    z[:, 0, 1] = 0.05 + 0.01j * freqs / 1e6
    z[:, 1, 0] = z[:, 0, 1]

    result = fit_reduced_modal_z(
        freqs,
        z,
        ModalZFitConfig(
            mode_count=1,
            scalar_fit_order=4,
            decomposition="svd",
            reduced_fit_method="peak-poles",
            relative_weight_mode="full-projected",
            relative_weight_iterations=2,
            target_error_weight_power=1.0,
            target_error_weight_max=4.0,
            target_error_pair_count=1,
        ),
    )

    assert result.z_log_magnitude_rms_error >= 0.0


def test_fit_reduced_modal_z_can_apply_residual_pair_correction():
    freqs = np.linspace(1e6, 8e6, 8)
    z = np.zeros((len(freqs), 2, 2), dtype=complex)
    z[:, 0, 0] = 2.0
    z[:, 1, 1] = 1.0
    z[:, 0, 1] = 0.45 + 0.05j * freqs / 1e6
    z[:, 1, 0] = z[:, 0, 1]
    base_config = ModalZFitConfig(
        mode_count=1,
        scalar_fit_order=4,
        decomposition="svd",
        reduced_fit_method="peak-poles",
    )

    baseline = fit_reduced_modal_z(freqs, z, base_config)
    corrected = fit_reduced_modal_z(
        freqs,
        z,
        ModalZFitConfig(
            mode_count=1,
            scalar_fit_order=4,
            decomposition="svd",
            reduced_fit_method="peak-poles",
            residual_pair_count=2,
            residual_fit_order=4,
            residual_weight_power=0.5,
            residual_gain=0.8,
        ),
    )

    assert corrected.residual_correction_pairs
    assert corrected.z_log_magnitude_rms_error < baseline.z_log_magnitude_rms_error


def test_fit_reduced_modal_z_rejects_invalid_target_error_weighting_config():
    freqs = np.linspace(1e6, 3e6, 3)
    z = np.zeros((len(freqs), 1, 1), dtype=complex)
    z[:, 0, 0] = 1.0

    with pytest.raises(ValueError, match="target_error_weight_power"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, target_error_weight_power=-0.1))
    with pytest.raises(ValueError, match="target_error_weight_max"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, target_error_weight_max=0.5))
    with pytest.raises(ValueError, match="target_error_pair_count"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, target_error_pair_count=-1))


def test_fit_reduced_modal_z_rejects_invalid_residual_correction_config():
    freqs = np.linspace(1e6, 3e6, 3)
    z = np.zeros((len(freqs), 1, 1), dtype=complex)
    z[:, 0, 0] = 1.0

    with pytest.raises(ValueError, match="residual_pair_count"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, residual_pair_count=-1))
    with pytest.raises(ValueError, match="residual_fit_order"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, residual_fit_order=0))
    with pytest.raises(ValueError, match="residual_pole_damping"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, residual_pole_damping=0.0))
    with pytest.raises(ValueError, match="residual_weight_power"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, residual_weight_power=-0.1))
    with pytest.raises(ValueError, match="residual_gain"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, residual_gain=-0.1))


def test_fit_reduced_modal_z_rejects_invalid_basis_sampling_config():
    freqs = np.linspace(1e6, 3e6, 3)
    z = np.zeros((len(freqs), 1, 1), dtype=complex)
    z[:, 0, 0] = 1.0

    with pytest.raises(ValueError, match="basis_frequency_sample_count"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, basis_frequency_sample_count=0))
    with pytest.raises(ValueError, match="basis_frequency_sampling"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, basis_frequency_sampling="bad"))


def test_fit_reduced_modal_z_rejects_negative_frequency_sample_head_count():
    freqs = np.linspace(1e6, 3e6, 3)
    z = np.zeros((len(freqs), 1, 1), dtype=complex)
    z[:, 0, 0] = 1.0

    with pytest.raises(ValueError, match="frequency_sample_head_count"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, frequency_sample_head_count=-1))


def test_fit_reduced_modal_z_rejects_invalid_peak_pole_config():
    freqs = np.linspace(1e6, 3e6, 3)
    z = np.zeros((len(freqs), 1, 1), dtype=complex)
    z[:, 0, 0] = 1.0

    with pytest.raises(ValueError, match="peak_pole_frequency_head_count"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, peak_pole_frequency_head_count=-1))
    with pytest.raises(ValueError, match="peak_pole_entry_count"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, peak_pole_entry_count=-1))
    with pytest.raises(ValueError, match="peak_pole_full_pair_count"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, peak_pole_full_pair_count=-1))


def test_fit_reduced_modal_z_auto_order_stops_at_first_passing_candidate():
    freqs = np.array([0.0, 1e6, 2e6, 3e6])
    z = np.zeros((len(freqs), 1, 1), dtype=complex)
    z[:, 0, 0] = 2.0 + 0.1j

    result = fit_reduced_modal_z(
        freqs,
        z,
        ModalZFitConfig(
            mode_count=1,
            scalar_fit_order=6,
            auto_order_candidates=(2, 4, 6),
            auto_order_max_z_log_magnitude_rms_error=1e-8,
        ),
    )

    assert result.scalar_fit_order == 2
    assert [trial.scalar_fit_order for trial in result.auto_order_trials] == [2]


def test_fit_reduced_modal_z_auto_order_returns_best_candidate_when_threshold_is_not_met():
    freqs = np.array([0.0, 1e6, 2e6, 3e6])
    z = np.zeros((len(freqs), 1, 1), dtype=complex)
    z[:, 0, 0] = 2.0 + 0.1j

    result = fit_reduced_modal_z(
        freqs,
        z,
        ModalZFitConfig(
            mode_count=1,
            scalar_fit_order=6,
            auto_order_candidates=(2, 4),
            auto_order_max_z_log_magnitude_rms_error=0.0,
        ),
    )

    assert result.scalar_fit_order in {2, 4}
    assert [trial.scalar_fit_order for trial in result.auto_order_trials] == [2, 4]


def test_fit_reduced_modal_z_auto_basis_sweeps_mode_basis_and_order_candidates():
    freqs = np.array([0.0, 1e6, 2e6, 3e6])
    z = np.zeros((len(freqs), 2, 2), dtype=complex)
    z[:, 0, 0] = 2.0 + 0.1j
    z[:, 1, 1] = 0.5 + 0.2j * freqs / 1e6

    result = fit_reduced_modal_z(
        freqs,
        z,
        ModalZFitConfig(
            mode_count=1,
            scalar_fit_order=4,
            auto_basis_mode_counts=(1, 2),
            auto_basis_sample_counts=(2, 3),
            auto_basis_anchor_port_counts=(0, 1),
            auto_order_candidates=(2, 4),
        ),
    )

    assert len(result.auto_basis_trials) == 20
    assert any(trial.mode_count == 2 and trial.basis_anchor_ports == (1,) for trial in result.auto_basis_trials)
    assert result.mode_count in {1, 2}
    assert result.basis_frequency_sample_count in {2, 3}
    assert len(result.basis_anchor_ports) in {0, 1}
    assert result.scalar_fit_order in {2, 4}


def test_fit_reduced_modal_z_auto_basis_can_sweep_pole_selection_candidates():
    freqs = np.array([0.0, 1e6, 2e6, 3e6])
    z = np.zeros((len(freqs), 1, 1), dtype=complex)
    z[:, 0, 0] = 2.0 + 0.1j * freqs / 1e6

    result = fit_reduced_modal_z(
        freqs,
        z,
        ModalZFitConfig(
            mode_count=1,
            scalar_fit_order=4,
            decomposition="svd",
            reduced_fit_method="peak-poles",
            auto_pole_dampings=(0.05, 0.1),
            auto_shared_pole_trace_counts=(1, 2),
            auto_peak_pole_entry_counts=(0, 1),
            auto_basis_diagonal_weight=0.5,
        ),
    )

    assert len(result.auto_basis_trials) == 8
    assert result.pole_damping in {0.05, 0.1}
    assert result.shared_pole_trace_count in {1, 2}
    assert result.peak_pole_entry_count in {0, 1}
    assert {trial.pole_damping for trial in result.auto_basis_trials} == {0.05, 0.1}
    assert {trial.shared_pole_trace_count for trial in result.auto_basis_trials} == {1, 2}
    assert {trial.peak_pole_entry_count for trial in result.auto_basis_trials} == {0, 1}
    assert all(trial.selection_score >= trial.z_log_magnitude_rms_error for trial in result.auto_basis_trials)


def test_fit_reduced_modal_z_auto_basis_can_try_multiple_anchor_combinations():
    freqs = np.array([0.0, 1e6, 2e6, 3e6])
    z = np.zeros((len(freqs), 3, 3), dtype=complex)
    z[:, 0, 0] = 2.0 + 0.1j
    z[:, 1, 1] = 1.0 + 0.2j * freqs / 1e6
    z[:, 2, 2] = 0.5 + 0.3j * freqs / 1e6

    result = fit_reduced_modal_z(
        freqs,
        z,
        ModalZFitConfig(
            mode_count=1,
            scalar_fit_order=4,
            decomposition="svd",
            auto_basis_anchor_port_counts=(1,),
            auto_basis_anchor_combo_count=2,
        ),
    )

    assert len(result.auto_basis_trials) == 2
    assert len({trial.basis_anchor_ports for trial in result.auto_basis_trials}) == 2


def test_fit_reduced_modal_z_rejects_invalid_auto_order_config():
    freqs = np.linspace(1e6, 3e6, 3)
    z = np.zeros((len(freqs), 1, 1), dtype=complex)
    z[:, 0, 0] = 1.0

    with pytest.raises(ValueError, match="auto_order_candidates"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, auto_order_candidates=(0, 2)))
    with pytest.raises(ValueError, match="auto_order_max_z_log_magnitude_rms_error"):
        fit_reduced_modal_z(
            freqs,
            z,
            ModalZFitConfig(mode_count=1, auto_order_max_z_log_magnitude_rms_error=-0.1),
        )


def test_fit_reduced_modal_z_rejects_invalid_auto_basis_config():
    freqs = np.linspace(1e6, 3e6, 3)
    z = np.zeros((len(freqs), 1, 1), dtype=complex)
    z[:, 0, 0] = 1.0

    with pytest.raises(ValueError, match="auto_basis_mode_counts"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, auto_basis_mode_counts=(0,)))
    with pytest.raises(ValueError, match="auto_basis_sample_counts"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, auto_basis_sample_counts=(0,)))
    with pytest.raises(ValueError, match="basis_frequency_indices"):
        fit_reduced_modal_z(
            freqs,
            z,
            ModalZFitConfig(
                mode_count=1,
                basis_frequency_indices=(0, 1),
                auto_basis_sample_counts=(2,),
            ),
        )
    with pytest.raises(ValueError, match="basis_anchor_ports"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, basis_anchor_ports=(0,)))
    with pytest.raises(ValueError, match="basis_anchor_ports"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, basis_anchor_ports=(1, 1)))
    with pytest.raises(ValueError, match="auto_basis_anchor_port_counts"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, auto_basis_anchor_port_counts=(-1,)))
    with pytest.raises(ValueError, match="auto_basis_anchor_candidate_count"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, auto_basis_anchor_candidate_count=0))
    with pytest.raises(ValueError, match="auto_basis_anchor_combo_count"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, auto_basis_anchor_combo_count=0))
    with pytest.raises(ValueError, match="auto_pole_dampings"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, auto_pole_dampings=(0.0,)))
    with pytest.raises(ValueError, match="auto_shared_pole_trace_counts"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, auto_shared_pole_trace_counts=(0,)))
    with pytest.raises(ValueError, match="auto_peak_pole_entry_counts"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, auto_peak_pole_entry_counts=(-1,)))
    with pytest.raises(ValueError, match="auto_basis_diagonal_weight"):
        fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, auto_basis_diagonal_weight=-0.1))
