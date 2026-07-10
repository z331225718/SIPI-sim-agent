from pathlib import Path
import inspect
from types import SimpleNamespace

import numpy as np

import scripts.sparam_loewner_pole_probe as probe
from agent_spice.sparam.pole_discovery import PoleCandidateEvaluation
from agent_spice.sparam.pole_loewner import LoewnerCandidateDiagnostics
from scripts.sparam_passivity_source_attribution import RawTouchstone


def _diagnostic(*, accepted: bool, order: int, partition: int) -> LoewnerCandidateDiagnostics:
    poles = (
        np.array([-1.0, -2.0, -3.0 + 4.0j, -5.0 + 6.0j], dtype=complex)
        if accepted
        else np.array([], dtype=complex)
    )
    return LoewnerCandidateDiagnostics(
        requested_order=order,
        numerical_rank=10,
        singular_values=np.array([3.0, 1.0]),
        raw_eigenvalues=poles,
        poles=poles,
        effective_order=6 if accepted else 0,
        accepted=accepted,
        rejection_reason=None if accepted else "unstable_eigenvalue",
        partition_index=partition,
    )


def test_probe_uses_full_grid_and_only_accepted_loewner_candidates(monkeypatch, tmp_path):
    raw = RawTouchstone(
        path=Path("Test16.s91p"),
        freqs_hz=np.linspace(0.0, 2.0e9, 611),
        s=np.zeros((611, 1, 1), dtype=complex),
        nports=1,
    )
    seen = {}

    def fake_discover(freqs, s_parameters, *, config):
        seen["discover"] = (len(freqs), s_parameters.shape, config)
        return [
            _diagnostic(accepted=True, order=6, partition=0),
            _diagnostic(accepted=False, order=8, partition=0),
        ]

    def fake_evaluate(freqs, responses, *, nports, candidates, full_sigma_candidate_count):
        seen["evaluate"] = (
            len(freqs),
            responses.shape,
            nports,
            len(candidates),
            full_sigma_candidate_count,
        )
        candidate = candidates[0]
        return [PoleCandidateEvaluation(candidate, 0.0029, 1.029, 1.5e9, 1)]

    monkeypatch.setattr(probe, "load_raw_touchstone", lambda path: raw)
    monkeypatch.setattr(probe, "discover_loewner_candidates", fake_discover)
    monkeypatch.setattr(probe, "evaluate_pole_candidates", fake_evaluate)

    result = probe.run_loewner_pole_probe(
        touchstone_path=tmp_path / "Test16.s91p",
        output_dir=tmp_path / "out",
        requested_orders=(6, 8, 10),
        probe_count=4,
        partition_count=4,
        seed=20260710,
    )

    assert seen["discover"][:2] == (611, (611, 1, 1))
    assert seen["discover"][2].requested_orders == (6, 8, 10)
    assert seen["evaluate"] == (611, (1, 611), 1, 1, 8)
    assert result["reference_grid"] == {
        "training_frequency_points": 611,
        "evaluation_frequency_points": 611,
    }
    assert result["accepted_candidate_count"] == 1
    assert result["rejected_candidate_count"] == 1
    assert result["full_sigma_candidate_count"] == 8
    assert result["oracle_policy"] == {"idem_numeric_poles_used": False}
    assert result["decision"]["advance_to_variable_projection"] is True
    assert (tmp_path / "out" / "summary.json").exists()
    assert (tmp_path / "out" / "benchmark_note.md").exists()


def test_gate_requires_rms_sigma_and_effective_order():
    order10 = SimpleNamespace(
        fingerprint="order10", topology=SimpleNamespace(effective_order=10)
    )
    order11 = SimpleNamespace(
        fingerprint="order11", topology=SimpleNamespace(effective_order=11)
    )
    passing = PoleCandidateEvaluation(order10, 0.0029, 1.029, 1.0, 0)
    failing_sigma = PoleCandidateEvaluation(order10, 0.0029, 1.03, 1.0, 0)
    failing_order = PoleCandidateEvaluation(order11, 0.0029, 1.029, 1.0, 0)

    assert probe.loewner_gate([passing])["advance_to_variable_projection"] is True
    assert probe.loewner_gate([failing_sigma])["advance_to_variable_projection"] is False
    assert probe.loewner_gate([failing_order])["advance_to_variable_projection"] is False
    assert probe.loewner_gate([])["stop_and_reassess"] is True


def test_probe_api_has_no_idem_or_oracle_argument():
    parameter_names = inspect.signature(probe.run_loewner_pole_probe).parameters
    assert not {"idem_model", "idem_poles", "oracle_poles", "oracle_model"} & set(
        parameter_names
    )
