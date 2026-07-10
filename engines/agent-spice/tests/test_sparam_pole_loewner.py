import inspect
from types import SimpleNamespace

import numpy as np

from agent_spice.sparam import pole_loewner


TRUE_POLES = np.array(
    [
        -2.0 * np.pi * 1.0e6,
        (-0.04 + 1j) * 2.0 * np.pi * 25.0e6,
        (-0.04 - 1j) * 2.0 * np.pi * 25.0e6,
    ],
    dtype=complex,
)
TRUE_RESIDUES = np.array([0.2, 0.03 + 0.05j, 0.03 - 0.05j], dtype=complex)
TRUE_HALF_PAIR_POLES = TRUE_POLES[[0, 1]]
TRUE_ORDER6_POLES = np.array(
    [
        -2.0 * np.pi * 1.0e6,
        -2.0 * np.pi * 8.0e6,
        (-0.05 + 1j) * 2.0 * np.pi * 30.0e6,
        (-0.05 - 1j) * 2.0 * np.pi * 30.0e6,
        (-0.08 + 1j) * 2.0 * np.pi * 90.0e6,
        (-0.08 - 1j) * 2.0 * np.pi * 90.0e6,
    ],
    dtype=complex,
)
TRUE_ORDER6_RESIDUES = np.array(
    [
        0.20,
        -0.08,
        0.03 + 0.05j,
        0.03 - 0.05j,
        -0.02 + 0.04j,
        -0.02 - 0.04j,
    ],
    dtype=complex,
)
TRUE_ORDER6_HALF_PAIR_POLES = TRUE_ORDER6_POLES[[0, 1, 2, 4]]
FREQS = np.array([0.0, 1.0e6, 3.0e6], dtype=float)
S_MATRIX = np.array(
    [
        [[1.0 + 0.0j, 2.0 - 1.0j], [3.0 + 2.0j, -1.0 + 0.0j]],
        [[1.5 + 0.5j, 1.0 + 2.0j], [2.0 - 1.0j, -0.5 + 0.5j]],
        [[0.5 - 0.5j, -2.0 + 1.0j], [1.0 + 3.0j, 2.0 + 0.0j]],
    ],
    dtype=complex,
)


def evaluate_real_rational_response(
    freqs_hz: np.ndarray, poles: np.ndarray, residues: np.ndarray
) -> np.ndarray:
    s_axis = 2j * np.pi * np.asarray(freqs_hz, dtype=float)
    return np.sum(residues[np.newaxis, :] / (s_axis[:, np.newaxis] - poles[np.newaxis, :]), axis=1)


def nearest_relative_pole_error(actual: np.ndarray, expected: np.ndarray) -> float:
    return max(
        min(abs(candidate - target) / max(1.0, abs(target)) for candidate in actual)
        for target in expected
    )


def test_loewner_recovers_stable_real_system_poles():
    freqs = np.concatenate(([0.0], np.geomspace(1.0e4, 1.0e8, 160)))
    samples = evaluate_real_rational_response(freqs, TRUE_POLES, TRUE_RESIDUES)

    pencil = pole_loewner.build_stacked_loewner_pencil(freqs, samples[np.newaxis, :])
    result = pole_loewner.extract_stable_half_pair_poles(pencil, requested_order=3)

    assert result.accepted
    assert result.effective_order == 3
    assert nearest_relative_pole_error(result.poles, TRUE_HALF_PAIR_POLES) < 0.05


def test_constant_trace_is_rejected_as_rank_zero():
    freqs = np.concatenate(([0.0], np.geomspace(1.0e4, 1.0e8, 20)))
    pencil = pole_loewner.build_stacked_loewner_pencil(freqs, np.ones((1, freqs.size), dtype=complex))

    result = pole_loewner.extract_stable_half_pair_poles(pencil, requested_order=1)

    assert not result.accepted
    assert result.numerical_rank == 0
    assert result.rejection_reason == "requested_order_exceeds_numerical_rank"


def test_insufficient_points_are_rejected_without_fabricating_poles():
    pencil = pole_loewner.build_stacked_loewner_pencil(
        np.array([0.0]), np.array([[1.0 + 0.0j]])
    )

    result = pole_loewner.extract_stable_half_pair_poles(pencil, requested_order=1)

    assert not result.accepted
    assert result.poles.size == 0
    assert result.rejection_reason == "insufficient_points"


def test_requested_order_above_numerical_rank_is_rejected():
    freqs = np.concatenate(([0.0], np.geomspace(1.0e4, 1.0e8, 80)))
    samples = evaluate_real_rational_response(freqs, TRUE_POLES, TRUE_RESIDUES)
    pencil = pole_loewner.build_stacked_loewner_pencil(freqs, samples[np.newaxis, :])

    result = pole_loewner.extract_stable_half_pair_poles(pencil, requested_order=4)

    assert not result.accepted
    assert result.numerical_rank == 3
    assert result.rejection_reason == "requested_order_exceeds_numerical_rank"


def test_eigenvalues_without_conjugate_partner_are_rejected():
    pencil = SimpleNamespace(
        loewner=np.eye(2, dtype=complex),
        shifted_loewner=np.diag([-2.0 + 3.0j, -5.0 + 0.0j]),
        partition_index=0,
    )

    result = pole_loewner.extract_stable_half_pair_poles(pencil, requested_order=2)

    assert not result.accepted
    assert result.poles.size == 0
    assert result.rejection_reason == "missing_conjugate_partner"


def test_unstable_eigenvalues_are_rejected_without_reflection():
    pencil = SimpleNamespace(
        loewner=np.eye(1, dtype=complex),
        shifted_loewner=np.array([[2.0 + 0.0j]]),
        partition_index=0,
    )

    result = pole_loewner.extract_stable_half_pair_poles(pencil, requested_order=1)

    assert not result.accepted
    assert result.poles.size == 0
    assert result.rejection_reason == "unstable_eigenvalue"


def test_duplicate_eigenvalues_are_rejected_when_they_reduce_effective_order():
    pencil = SimpleNamespace(
        loewner=np.eye(4, dtype=complex),
        shifted_loewner=np.diag([-5.0, -5.0, -2.0 + 3.0j, -2.0 - 3.0j]),
        partition_index=0,
    )

    result = pole_loewner.extract_stable_half_pair_poles(pencil, requested_order=4)

    assert not result.accepted
    assert result.poles.size == 0
    assert result.rejection_reason == "effective_order_mismatch"


def test_random_projections_are_deterministic_and_do_not_change_frequency_count():
    first = pole_loewner.project_sparameter_traces(FREQS, S_MATRIX, probe_count=4, seed=20260710)
    second = pole_loewner.project_sparameter_traces(FREQS, S_MATRIX, probe_count=4, seed=20260710)

    np.testing.assert_allclose(first, second)
    assert first.shape == (4, len(FREQS))


def test_random_projections_use_unit_vectors_and_bilinear_trace_evaluation():
    left_vectors, right_vectors = pole_loewner._deterministic_probe_vectors(
        nports=S_MATRIX.shape[1], probe_count=4, seed=20260710
    )

    traces = pole_loewner.project_sparameter_traces(FREQS, S_MATRIX, probe_count=4, seed=20260710)
    expected = np.einsum("ki,fij,kj->kf", left_vectors.conj(), S_MATRIX, right_vectors)

    np.testing.assert_allclose(np.linalg.norm(left_vectors, axis=1), 1.0)
    np.testing.assert_allclose(np.linalg.norm(right_vectors, axis=1), 1.0)
    assert np.isrealobj(left_vectors)
    assert np.isrealobj(right_vectors)
    np.testing.assert_allclose(traces, expected)


def test_stacked_pencil_uses_documented_loewner_formulas_for_every_trace():
    traces = np.vstack(
        (
            np.array([1.0 + 0.0j, 2.0 + 1.0j, 4.0 - 1.0j]),
            np.array([-1.0 + 0.5j, 3.0 + 2.0j, 1.0 - 2.0j]),
        )
    )
    pencil = pole_loewner.build_stacked_loewner_pencil(FREQS, traces, partition_index=1)

    left_s = pencil.s_axis[pencil.left_indices]
    right_s = pencil.s_axis[pencil.right_indices]
    expected_loewner = []
    expected_shifted = []
    for trace in pencil.augmented_traces:
        left_samples = trace[pencil.left_indices]
        right_samples = trace[pencil.right_indices]
        denominator = left_s[:, np.newaxis] - right_s[np.newaxis, :]
        expected_loewner.append((left_samples[:, np.newaxis] - right_samples[np.newaxis, :]) / denominator)
        expected_shifted.append(
            (left_s[:, np.newaxis] * left_samples[:, np.newaxis]
            - right_s[np.newaxis, :] * right_samples[np.newaxis, :])
            / denominator
        )

    np.testing.assert_allclose(pencil.loewner, np.vstack(expected_loewner))
    np.testing.assert_allclose(pencil.shifted_loewner, np.vstack(expected_shifted))


def test_conjugate_augmentation_and_partitions_are_deterministic():
    traces = np.array([[1.0 + 2.0j, 3.0 - 1.0j, -2.0 + 4.0j]])
    first = pole_loewner.build_stacked_loewner_pencil(FREQS, traces, partition_index=0)
    second = pole_loewner.build_stacked_loewner_pencil(FREQS, traces, partition_index=1)

    np.testing.assert_allclose(
        first.s_axis,
        2j * np.pi * np.array([-3.0e6, -1.0e6, 0.0, 1.0e6, 3.0e6]),
    )
    np.testing.assert_allclose(
        first.augmented_traces,
        np.array([[np.conj(traces[0, 2]), np.conj(traces[0, 1]), traces[0, 0], traces[0, 1], traces[0, 2]]]),
    )
    assert np.array_equal(np.sort(np.concatenate((first.left_indices, first.right_indices))), np.arange(first.s_axis.size))
    assert not np.array_equal(first.left_indices, second.left_indices)


def test_discovery_tries_every_partition_order_pair_deterministically():
    freqs = np.concatenate(([0.0], np.geomspace(1.0e4, 1.0e8, 80)))
    samples = evaluate_real_rational_response(freqs, TRUE_POLES, TRUE_RESIDUES)
    s_parameters = samples[:, np.newaxis, np.newaxis]
    config = pole_loewner.LoewnerConfig(
        requested_orders=(6, 8, 10), probe_count=2, partition_count=3, seed=7
    )

    first = pole_loewner.discover_loewner_candidates(freqs, s_parameters, config=config)
    second = pole_loewner.discover_loewner_candidates(freqs, s_parameters, config=config)

    assert len(first) == config.partition_count * len(config.requested_orders)
    assert [(item.partition_index, item.requested_order, item.accepted) for item in first] == [
        (item.partition_index, item.requested_order, item.accepted) for item in second
    ]
    assert all(item.requested_order in config.requested_orders for item in first)
    assert all(item.poles.size == 0 for item in first if not item.accepted)


def test_discovery_recovers_a_real_multiport_order6_system_with_default_orders():
    freqs = np.concatenate(([0.0], np.geomspace(1.0e4, 2.0e8, 120)))
    scalar_response = evaluate_real_rational_response(
        freqs, TRUE_ORDER6_POLES, TRUE_ORDER6_RESIDUES
    )
    real_port_coupling = np.array([[1.0, 0.25], [-0.4, 0.7]], dtype=float)
    s_parameters = scalar_response[:, np.newaxis, np.newaxis] * real_port_coupling

    diagnostics = pole_loewner.discover_loewner_candidates(
        freqs,
        s_parameters,
        config=pole_loewner.LoewnerConfig(
            requested_orders=(6, 8, 10),
            probe_count=4,
            partition_count=4,
            seed=20260710,
        ),
    )

    accepted_order6 = [
        item for item in diagnostics if item.accepted and item.requested_order == 6
    ]
    assert accepted_order6
    assert min(
        nearest_relative_pole_error(item.poles, TRUE_ORDER6_HALF_PAIR_POLES)
        for item in accepted_order6
    ) < 0.05


def test_discovery_rejects_orders_outside_the_research_contract():
    freqs = np.concatenate(([0.0], np.geomspace(1.0e4, 1.0e8, 40)))
    samples = evaluate_real_rational_response(freqs, TRUE_POLES, TRUE_RESIDUES)

    with np.testing.assert_raises_regex(ValueError, "exactly 6, 8, and 10"):
        pole_loewner.discover_loewner_candidates(
            freqs,
            samples[:, np.newaxis, np.newaxis],
            config=pole_loewner.LoewnerConfig(requested_orders=(3, 6)),
        )


def test_public_api_does_not_accept_idem_or_oracle_inputs():
    functions = (
        pole_loewner.project_sparameter_traces,
        pole_loewner.build_stacked_loewner_pencil,
        pole_loewner.extract_stable_half_pair_poles,
        pole_loewner.discover_loewner_candidates,
    )

    for function in functions:
        parameter_names = inspect.signature(function).parameters
        assert not {"idem_model", "idem_poles", "oracle_poles", "oracle_model"} & set(parameter_names)
