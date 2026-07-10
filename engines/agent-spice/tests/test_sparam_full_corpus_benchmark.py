from pathlib import Path
import json
import math
import subprocess

import pytest

from agent_spice.sparam.benchmark import BenchmarkContract, CorpusEntry, ToolTrial
from agent_spice.sparam.idem import IdemCommandResult
import scripts.sparam_full_corpus_benchmark as full_benchmark


def _entry(tmp_path: Path) -> CorpusEntry:
    touchstone = tmp_path / "line.s2p"
    touchstone.write_text(
        "# Hz S RI R 50\n"
        "1e6 0 0 0.5 0 0.5 0 0 0\n"
        "2e6 0 0 0.4 0 0.4 0 0 0\n",
        encoding="utf-8",
    )
    return CorpusEntry(
        path=touchstone,
        relative_path="line.s2p",
        sha256="input-sha",
        size_bytes=touchstone.stat().st_size,
        ports=2,
        frequency_points=2,
        frequency_min_hz=1e6,
        frequency_max_hz=2e6,
        reference_impedance=(50.0, 50.0),
    )


def _install_fake_idem(
    monkeypatch,
    *,
    order: int,
    pre_rms: float = 0.0008,
    final_rms: float = 0.0009,
    passive: bool = True,
    audited_rms: float | None = None,
):
    calls = []

    def fake_fit(touchstone_path, model_path, **kwargs):
        calls.append("fit")
        model_path.write_text("model", encoding="utf-8")
        return IdemCommandResult([], 0, "End of model build", "", 1.0, 20.0)

    def fake_accuracy(touchstone_path, model_path, report_path, **kwargs):
        phase = "pre_accuracy" if report_path.name.startswith("pre") else "final_accuracy"
        calls.append(phase)
        rms = pre_rms if phase == "pre_accuracy" else final_rms
        report_path.write_text("report", encoding="utf-8")
        return {
            "status": "completed",
            "metrics": {"ports": 2, "frequency_points": 2, "mean_rms": rms, "max_error": rms},
            "command": {"elapsed_seconds": 0.2, "peak_memory_mb": 5.0},
        }

    def fake_passivity(model_path, output_model_path, **kwargs):
        phase = "check" if kwargs.get("only_check") == 1 else "enforce"
        calls.append(phase)
        if phase == "enforce":
            output_model_path.write_text("passive model", encoding="utf-8")
        return {
            "status": "completed",
            "passivity": {"passive": passive, "max_singular_values": []},
            "model": {"order": order},
            "command": {"elapsed_seconds": 0.3, "peak_memory_mb": 30.0},
        }

    def fake_export(model_path, output_path, **kwargs):
        calls.append("export")
        output_path.write_text("export", encoding="utf-8")
        return {
            "status": "completed",
            "command": {"elapsed_seconds": 0.1, "peak_memory_mb": 4.0},
        }

    def fake_audit(original_path, exported_path, **kwargs):
        calls.append("audit")
        rms = final_rms if audited_rms is None else audited_rms
        return {
            "status": "PASS",
            "frequency_grid_match": True,
            "ports": 2,
            "frequency_points": 2,
            "mean_rms": rms,
            "sampled_max_sigma": 0.999,
        }

    monkeypatch.setattr(full_benchmark, "run_idem_fitting", fake_fit)
    monkeypatch.setattr(full_benchmark, "run_idem_accuracy_check", fake_accuracy)
    monkeypatch.setattr(full_benchmark, "run_idem_passivity", fake_passivity)
    monkeypatch.setattr(full_benchmark, "run_idem_touchstone_export", fake_export)
    monkeypatch.setattr(full_benchmark, "audit_touchstone_model", fake_audit)
    monkeypatch.setattr(full_benchmark, "inspect_idem_model", lambda path: {"order": order})
    return calls


def test_idem_trial_skips_passivity_when_pre_rms_misses_target(tmp_path: Path, monkeypatch):
    calls = _install_fake_idem(monkeypatch, order=8, pre_rms=0.002)

    trial = full_benchmark.run_idem_order_trial(
        _entry(tmp_path),
        8,
        BenchmarkContract(max_order=8),
        tmp_path / "trial",
        tool_identity="fake-idem",
    )

    assert calls == ["fit", "pre_accuracy"]
    assert trial.target_met is False
    assert trial.failure_reason == "pre_rms_above_target"


def test_idem_trial_uses_post_enforcement_rms_and_passivity(tmp_path: Path, monkeypatch):
    calls = _install_fake_idem(monkeypatch, order=8, final_rms=0.0011)

    trial = full_benchmark.run_idem_order_trial(
        _entry(tmp_path),
        8,
        BenchmarkContract(max_order=8),
        tmp_path / "trial",
        tool_identity="fake-idem",
    )

    assert calls == ["fit", "pre_accuracy", "enforce", "final_accuracy", "check"]
    assert trial.target_met is False
    assert trial.failure_reason == "final_rms_above_target"


def test_idem_trial_passes_only_after_independent_export_audit(tmp_path: Path, monkeypatch):
    calls = _install_fake_idem(monkeypatch, order=8)

    trial = full_benchmark.run_idem_order_trial(
        _entry(tmp_path),
        8,
        BenchmarkContract(max_order=8),
        tmp_path / "trial",
        tool_identity="fake-idem",
    )

    assert calls == ["fit", "pre_accuracy", "enforce", "final_accuracy", "check", "export", "audit"]
    assert trial.target_met is True
    assert trial.authoritative_passive is True
    assert trial.final_mean_rms == pytest.approx(0.0009)
    assert trial.sampled_max_sigma == pytest.approx(0.999)


def test_idem_trial_rejects_nonpassive_check_and_order_mismatch(tmp_path: Path, monkeypatch):
    _install_fake_idem(monkeypatch, order=8, passive=False)
    nonpassive = full_benchmark.run_idem_order_trial(
        _entry(tmp_path),
        8,
        BenchmarkContract(max_order=8),
        tmp_path / "nonpassive",
        tool_identity="fake-idem",
    )
    assert nonpassive.failure_reason == "authoritative_passivity_failed"

    _install_fake_idem(monkeypatch, order=9)
    mismatch = full_benchmark.run_idem_order_trial(
        _entry(tmp_path),
        8,
        BenchmarkContract(max_order=8),
        tmp_path / "mismatch",
        tool_identity="fake-idem",
    )
    assert mismatch.failure_reason == "effective_order_mismatch"


def test_idem_trial_resumes_only_exact_valid_fingerprint(tmp_path: Path, monkeypatch):
    calls = _install_fake_idem(monkeypatch, order=8)
    entry = _entry(tmp_path)
    output_dir = tmp_path / "trial"
    contract = BenchmarkContract(max_order=8)

    first = full_benchmark.run_idem_order_trial(
        entry,
        8,
        contract,
        output_dir,
        tool_identity="fake-idem",
    )
    calls.clear()
    resumed = full_benchmark.run_idem_order_trial(
        entry,
        8,
        contract,
        output_dir,
        tool_identity="fake-idem",
        resume=True,
    )

    assert calls == []
    assert resumed.to_dict() == first.to_dict()

    full_benchmark.run_idem_order_trial(
        entry,
        8,
        BenchmarkContract(max_order=8, threads=4),
        output_dir,
        tool_identity="fake-idem",
        resume=True,
    )
    assert calls[0] == "fit"


def test_idem_trial_records_timeout_instead_of_raising(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        full_benchmark,
        "run_idem_fitting",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("idem", 1.0)),
    )

    trial = full_benchmark.run_idem_order_trial(
        _entry(tmp_path),
        8,
        BenchmarkContract(max_order=8),
        tmp_path / "trial",
        tool_identity="fake-idem",
    )

    assert trial.status == "ERROR"
    assert trial.failure_reason == "phase_timeout:fit"


def test_idem_trial_rejects_non_finite_accuracy_and_audit_disagreement(tmp_path: Path, monkeypatch):
    calls = _install_fake_idem(monkeypatch, order=8, pre_rms=math.nan)
    invalid_accuracy = full_benchmark.run_idem_order_trial(
        _entry(tmp_path),
        8,
        BenchmarkContract(max_order=8),
        tmp_path / "nonfinite",
        tool_identity="fake-idem",
    )
    assert calls == ["fit", "pre_accuracy"]
    assert invalid_accuracy.failure_reason == "pre_accuracy_invalid"

    _install_fake_idem(monkeypatch, order=8, audited_rms=0.00095)
    disagreement = full_benchmark.run_idem_order_trial(
        _entry(tmp_path),
        8,
        BenchmarkContract(max_order=8),
        tmp_path / "disagreement",
        tool_identity="fake-idem",
    )
    assert disagreement.failure_reason == "accuracy_audit_disagreement"


def test_idem_trial_does_not_resume_semantically_invalid_pass(tmp_path: Path, monkeypatch):
    calls = _install_fake_idem(monkeypatch, order=8)
    entry = _entry(tmp_path)
    output_dir = tmp_path / "trial"
    contract = BenchmarkContract(max_order=8)
    full_benchmark.run_idem_order_trial(
        entry,
        8,
        contract,
        output_dir,
        tool_identity="fake-idem",
    )
    payload = json.loads((output_dir / "trial.json").read_text(encoding="utf-8"))
    payload["final_mean_rms"] = None
    (output_dir / "trial.json").write_text(json.dumps(payload), encoding="utf-8")
    calls.clear()

    full_benchmark.run_idem_order_trial(
        entry,
        8,
        contract,
        output_dir,
        tool_identity="fake-idem",
        resume=True,
    )

    assert calls[0] == "fit"


def test_idem_target_search_keeps_passing_models_for_zero_work_resume(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    output_root = tmp_path / "search"
    outcomes = {4: False, 6: False, 8: True, 7: True}

    def fake_trial(entry, order, contract, output_dir, **kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        model = output_dir / ("passive.mod.h5" if outcomes[order] else "fit.mod.h5")
        model.write_text("model", encoding="utf-8")
        return ToolTrial(
            tool="idem",
            requested_order=order,
            effective_order=order,
            final_mean_rms=0.0009 if outcomes[order] else 0.002,
            authoritative_passive=outcomes[order],
            final_max_sigma=0.999 if outcomes[order] else 1.01,
            sampled_max_sigma=0.999 if outcomes[order] else 1.01,
            target_met=outcomes[order],
            status="PASS" if outcomes[order] else "FAIL",
            artifact_paths={"selected_model": str(model)},
        )

    monkeypatch.setattr(full_benchmark, "run_idem_order_trial", fake_trial)

    result = full_benchmark.run_idem_target_search(
        entry,
        BenchmarkContract(max_order=8),
        output_root,
        tool_identity="fake-idem",
    )

    assert result.selected_order == 7
    assert not (output_root / "order4" / "fit.mod.h5").exists()
    assert not (output_root / "order6" / "fit.mod.h5").exists()
    assert (output_root / "order7" / "passive.mod.h5").exists()
    assert (output_root / "order8" / "passive.mod.h5").exists()
