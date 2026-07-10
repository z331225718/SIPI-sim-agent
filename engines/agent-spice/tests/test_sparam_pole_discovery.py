import inspect

import numpy as np

from agent_spice.sparam import pole_discovery


FREQS = np.geomspace(1.0e6, 3.0e9, 25)
RESPONSES = np.vstack(
    [
        0.1 / (1.0 + 1j * FREQS / 8.0e7),
        0.05 / (1.0 + 1j * FREQS / 1.7e9),
    ]
)
TOPOLOGY = pole_discovery.PoleTopology(real_count=4, complex_pair_count=2)
TEST16_LIKE_FREQS = np.concatenate(
    (
        np.array([0.0]),
        np.geomspace(0.1, 1.0e7, 31),
        np.geomspace(1.1e7, 2.0e9, 121),
    )
)
TEST16_LIKE_RESPONSES = np.vstack(
    [
        0.1 / (1.0 + 1j * TEST16_LIKE_FREQS / 9.0e7),
        0.04 / (1.0 + 1j * TEST16_LIKE_FREQS / 1.4e9),
    ]
)


def test_make_stable_poles_preserves_requested_topology():
    poles = pole_discovery.make_stable_poles(
        real_decay_hz=[1e6, 1e7, 1e8, 5e8],
        complex_frequency_hz=[1.2e9, 1.9e9],
        damping_ratio=[0.03, 0.05],
    )

    assert len(poles) == 6
    assert np.all(poles.real < 0.0)
    assert pole_discovery.effective_order(poles) == 8
    assert np.count_nonzero(np.abs(poles.imag) > 0.0) == 2


def test_generator_is_deterministic_and_data_only():
    first = pole_discovery.generate_data_only_candidates(
        FREQS, RESPONSES, TOPOLOGY, candidate_count=16, seed=7
    )
    second = pole_discovery.generate_data_only_candidates(
        FREQS, RESPONSES, TOPOLOGY, candidate_count=16, seed=7
    )

    assert [candidate.fingerprint for candidate in first] == [candidate.fingerprint for candidate in second]
    assert all(candidate.source in {"log_grid", "response_activity", "stratified"} for candidate in first)


def test_generator_keeps_every_pole_within_raw_frequency_bounds():
    candidates = pole_discovery.generate_data_only_candidates(
        FREQS, RESPONSES, TOPOLOGY, candidate_count=16, seed=7
    )
    lower = float(np.min(FREQS[FREQS > 0.0]))
    upper = float(np.max(FREQS))

    for candidate in candidates:
        poles = candidate.poles
        frequencies = np.where(
            np.abs(poles.imag) > 1e-15,
            np.abs(poles.imag) / (2.0 * np.pi),
            np.abs(poles.real) / (2.0 * np.pi),
        )
        complex_poles = poles[np.abs(poles.imag) > 1e-15]
        damping = -complex_poles.real / np.maximum(np.abs(complex_poles.imag), np.finfo(float).tiny)
        assert np.all((lower * (1.0 - 1e-12) <= frequencies) & (frequencies <= upper * (1.0 + 1e-12)))
        assert np.all((0.01 - 1e-12 <= damping) & (damping <= 0.20 + 1e-12))
        assert np.all(poles.real < 0.0)
        assert pole_discovery.effective_order(poles) == TOPOLOGY.effective_order


def test_wide_grid_candidates_avoid_endpoint_collapse_and_cover_high_real_poles():
    first = pole_discovery.generate_data_only_candidates(
        TEST16_LIKE_FREQS, TEST16_LIKE_RESPONSES, TOPOLOGY, candidate_count=32, seed=20260710
    )
    second = pole_discovery.generate_data_only_candidates(
        TEST16_LIKE_FREQS, TEST16_LIKE_RESPONSES, TOPOLOGY, candidate_count=32, seed=20260710
    )
    upper = float(np.max(TEST16_LIKE_FREQS))
    activity_candidates = [candidate for candidate in first if candidate.source == "response_activity"]
    stratified_candidates = [candidate for candidate in first if candidate.source == "stratified"]

    assert [candidate.fingerprint for candidate in first] == [candidate.fingerprint for candidate in second]
    assert len(activity_candidates) == 16
    assert all(
        not np.allclose(np.abs(candidate.poles[4:].imag) / (2.0 * np.pi), upper, rtol=0.0, atol=upper * 1e-12)
        for candidate in activity_candidates
    )
    assert all(
        np.log(np.max(np.abs(candidate.poles[4:].imag)) / np.min(np.abs(candidate.poles[4:].imag))) >= 0.05
        for candidate in activity_candidates
    )
    activity_complex_frequencies = np.concatenate(
        [np.abs(candidate.poles[4:].imag) / (2.0 * np.pi) for candidate in activity_candidates]
    )
    assert len(np.unique(np.round(activity_complex_frequencies, decimals=3))) >= 12
    assert any(np.any(np.abs(candidate.poles[:4].real) / (2.0 * np.pi) > 1.0e7) for candidate in stratified_candidates)

    for candidate in first:
        poles = candidate.poles
        complex_poles = poles[np.abs(poles.imag) > 1e-15]
        damping = -complex_poles.real / np.abs(complex_poles.imag)
        assert len(poles) == 6
        assert np.all(poles.real < 0.0)
        assert pole_discovery.effective_order(poles) == 8
        assert np.all((0.01 - 1e-12 <= damping) & (damping <= 0.20 + 1e-12))


def test_discovery_api_does_not_accept_idem_or_oracle_inputs():
    for function in (
        pole_discovery.make_stable_poles,
        pole_discovery.generate_data_only_candidates,
        pole_discovery.evaluate_pole_candidates,
        pole_discovery.pareto_front,
    ):
        parameter_names = inspect.signature(function).parameters
        assert not {"idem_model", "idem_poles", "oracle_poles", "oracle_model"} & set(parameter_names)


def test_evaluation_runs_sigma_only_for_lowest_rms_candidates(monkeypatch):
    response = RESPONSES[:1]
    candidates = pole_discovery.generate_data_only_candidates(FREQS, response, TOPOLOGY, candidate_count=4, seed=7)
    sigma_calls = []

    def fake_fit(poles, freqs, responses, fit_constant, fit_proportional, enforce_dc):
        scale = float(np.abs(poles[0]))
        residues = np.full((responses.shape[0], len(poles)), scale, dtype=complex)
        return residues, np.zeros(responses.shape[0], dtype=complex), np.zeros(responses.shape[0], dtype=complex), None, 0, []

    def fake_evaluate(poles, residues, constant, proportional, freqs):
        return np.full((response.shape[0], len(freqs)), residues[0, 0], dtype=complex)

    def fake_sigma(responses, freqs, nports):
        sigma_calls.append(float(responses[0, 0].real))
        return 1.0, float(freqs[0]), 0

    monkeypatch.setattr(pole_discovery.NativeVectorFitting, "_fit_residues", staticmethod(fake_fit))
    monkeypatch.setattr(pole_discovery.NativeVectorFitting, "_evaluate_residue_model", staticmethod(fake_evaluate))
    monkeypatch.setattr(pole_discovery, "_full_grid_sigma", fake_sigma)

    evaluations = pole_discovery.evaluate_pole_candidates(
        FREQS, response, nports=1, candidates=candidates, full_sigma_candidate_count=2
    )

    assert len(evaluations) == 4
    assert len(sigma_calls) == 2
    assert sum(item.max_sigma is not None for item in evaluations) == 2
    assert [item.mean_rms for item in evaluations] == sorted(item.mean_rms for item in evaluations)


def test_pareto_front_excludes_candidates_without_full_sigma():
    candidates = pole_discovery.generate_data_only_candidates(
        FREQS, RESPONSES, TOPOLOGY, candidate_count=2, seed=7
    )
    evaluations = [
        pole_discovery.PoleCandidateEvaluation(candidates[0], 0.001, None, None, None),
        pole_discovery.PoleCandidateEvaluation(candidates[1], 0.002, 1.0, 1.0e6, 0),
    ]

    assert pole_discovery.pareto_front(evaluations) == [evaluations[1]]
