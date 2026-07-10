from pathlib import Path
import inspect

import numpy as np

import scripts.sparam_pole_manifold_probe as probe
from agent_spice.sparam.pole_discovery import PoleCandidateEvaluation
from scripts.sparam_passivity_source_attribution import RawTouchstone


def test_probe_uses_full_test16_grid_and_data_only_policy(monkeypatch, tmp_path):
    raw = RawTouchstone(
        path=Path("Test16.s91p"),
        freqs_hz=np.linspace(1.0e6, 3.0e9, 611),
        s=np.zeros((611, 1, 1), dtype=complex),
        nports=1,
    )
    seen = {}

    def fake_generate(freqs, responses, topology, *, candidate_count, seed):
        seen["generate"] = (len(freqs), responses.shape, topology, candidate_count, seed)
        return []

    def fake_evaluate(freqs, responses, *, nports, candidates, full_sigma_candidate_count):
        seen["evaluate"] = (len(freqs), responses.shape, nports, len(candidates), full_sigma_candidate_count)
        return []

    monkeypatch.setattr(probe, "load_raw_touchstone", lambda path: raw)
    monkeypatch.setattr(probe, "generate_data_only_candidates", fake_generate)
    monkeypatch.setattr(probe, "evaluate_pole_candidates", fake_evaluate)

    result = probe.run_pole_manifold_probe(
        touchstone_path=tmp_path / "Test16.s91p", output_dir=tmp_path / "out"
    )

    assert seen["generate"][:2] == (611, (1, 611))
    assert seen["generate"][2].real_count == 4
    assert seen["generate"][2].complex_pair_count == 2
    assert seen["generate"][3:] == (32, 20260710)
    assert seen["evaluate"] == (611, (1, 611), 1, 0, 8)
    assert result["oracle_policy"] == {
        "idem_poles_used_for_generation": False,
        "idem_poles_used_for_initialization": False,
        "idem_poles_used_for_objective": False,
        "idem_topology_used_for_attribution_only": True,
    }
    assert result["reference_grid"] == {"training_frequency_points": 611, "evaluation_frequency_points": 611}


def test_probe_gate_requires_candidate_to_meet_both_thresholds():
    class Candidate:
        fingerprint = "candidate"
        source = "stratified"
        seed_index = 0
        poles = np.array([-1.0])

    passing = PoleCandidateEvaluation(Candidate(), 0.0029, 1.029, 1.0, 0)
    failing_sigma = PoleCandidateEvaluation(Candidate(), 0.0029, 1.03, 1.0, 0)

    assert probe.d11_gate([passing])["advance_to_d12"] is True
    assert probe.d11_gate([failing_sigma])["advance_to_d12"] is False
    assert probe.d11_gate([])["fallback_stop_rule"] is True


def test_probe_api_has_no_idem_model_or_oracle_argument():
    parameter_names = inspect.signature(probe.run_pole_manifold_probe).parameters
    assert not {"idem_model", "idem_poles", "oracle_poles", "oracle_model"} & set(parameter_names)
