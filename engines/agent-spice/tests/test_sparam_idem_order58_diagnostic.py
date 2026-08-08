import json
from dataclasses import replace
from pathlib import Path

import pytest

from agent_spice.sparam.benchmark import CorpusEntry, ToolTrial


DIAGNOSTIC_IDS = [
    "baseline-cap56",
    "baseline-cap58",
    "baseline-cap60",
    "cap58-reject-poles-1p0",
    "cap58-skimming-1e-4",
    "cap58-p4poles-eye",
]


def _write_s2p(path: Path) -> None:
    path.write_text(
        "# Hz S RI R 50\n"
        "1e6 0 0 0.5 0 0.5 0 0 0\n"
        "2e6 0 0 0.5 0 0.5 0 0 0\n",
        encoding="utf-8",
    )


def _entry(tmp_path: Path) -> CorpusEntry:
    touchstone = tmp_path / "line.s2p"
    _write_s2p(touchstone)
    return CorpusEntry(
        path=touchstone,
        relative_path="line.s2p",
        sha256="87fccc96196d8c149d1b3ba985701dd56a78f5d9904984f55f8161c39cdd7c7e",
        size_bytes=touchstone.stat().st_size,
        ports=19,
        frequency_points=826,
        frequency_min_hz=1e6,
        frequency_max_hz=2e6,
        reference_impedance=(50.0,),
    )


def _trial(status: str, reason: str | None, *, rms: float | None = 0.0008, order: int = 58) -> ToolTrial:
    return ToolTrial(
        tool="idem-adaptive",
        requested_order=order,
        requested_order_step=2,
        effective_order_step=2,
        effective_order=order,
        pre_mean_rms=rms,
        final_mean_rms=rms,
        status=status,
        failure_reason=reason,
        target_met=status == "PASS",
        elapsed_seconds=12.0,
        peak_memory_mb=34.0,
    )


def test_diagnostic_manifest_has_six_fixed_trials_and_contract():
    import scripts.sparam_idem_order58_diagnostic as diagnostic

    trials = diagnostic.build_diagnostic_trials()

    assert [trial.trial_id for trial in trials] == DIAGNOSTIC_IDS
    assert [trial.order_max for trial in trials] == [56, 58, 60, 58, 58, 58]
    assert {trial.order_min for trial in trials} == {4}
    assert {trial.order_step for trial in trials} == {2}
    assert {trial.rms_target for trial in trials} == {0.001}
    assert {trial.threads for trial in trials} == {8}
    assert {trial.phase_timeout_seconds for trial in trials} == {1800.0}
    assert {trial.fit_idle_timeout_seconds for trial in trials} == {300.0}
    assert all(trial.adaptive_options.split_type == "none" for trial in trials)
    assert trials[3].adaptive_options.reject_poles is True
    assert trials[3].adaptive_options.reject_poles_max_relative_frequency == pytest.approx(1.0)
    assert trials[4].adaptive_options.skimming_tolerance == pytest.approx(1.0e-4)
    assert trials[5].adaptive_options.p4poles_type == "eye"

    manifest = diagnostic.diagnostic_manifest_payload()
    assert manifest["stage"] == "order58-diagnostic"
    assert manifest["source_of_truth"] == "scripts.sparam_idem_order58_diagnostic:build_diagnostic_trials"
    assert manifest["global_contract"]["input_sha256"] == diagnostic.EXPECTED_INPUT_SHA256
    assert manifest["trials"] == [trial.to_dict() for trial in trials]


def test_diagnostic_runs_first_three_only_when_cap58_and_cap60_do_not_stall(
    tmp_path: Path, monkeypatch
):
    import scripts.sparam_idem_order58_diagnostic as diagnostic

    calls: list[str] = []
    partial_counts: list[int] = []
    real_atomic = diagnostic.atomic_write_json

    def fake_entry(input_path):
        return _entry(tmp_path)

    def fake_run(entry, config, output_dir, *, resume=True, idem_bin_dir=None):
        calls.append(config.trial_id)
        assert output_dir.name == config.trial_id
        (output_dir / "fit.json").parent.mkdir(parents=True, exist_ok=True)
        real_atomic(output_dir / "fit.json", {"status": "completed", "model": {"error_history": [0.2], "orders_history": [config.order_max]}})
        real_atomic(output_dir / "history.json", {"status": "completed", "error_history": [0.2], "orders_history": [config.order_max]})
        return _trial("FAIL", "pre_rms_above_target", rms=0.002, order=config.order_max)

    def tracking_atomic(path: Path, payload: dict) -> None:
        if path.name == "summary.partial.json":
            partial_counts.append(payload["completed_trial_count"])
        real_atomic(path, payload)

    monkeypatch.setattr(diagnostic, "_entry_from_input_path", fake_entry)
    monkeypatch.setattr(diagnostic, "run_adaptive_trial", fake_run)
    monkeypatch.setattr(diagnostic, "atomic_write_json", tracking_atomic)

    summary = diagnostic.run_diagnostic(tmp_path / "line.s2p", tmp_path / "runs")

    assert calls == DIAGNOSTIC_IDS[:3]
    assert partial_counts == [1, 2, 3]
    assert summary["conditional_rule"]["executed_variants"] is False
    assert summary["decision"]["stable_reproduction"] is False
    assert summary["decision"]["next_phase"] == "stop_order58_diagnostic_original_stall_not_stably_reproduced"
    assert json.loads((tmp_path / "runs" / "summary.partial.json").read_text(encoding="utf-8")) == summary
    assert (tmp_path / "runs" / "summary.csv").is_file()


def test_diagnostic_executes_variants_and_summarizes_stall_telemetry(
    tmp_path: Path, monkeypatch
):
    import scripts.sparam_idem_order58_diagnostic as diagnostic

    calls: list[str] = []
    real_atomic = diagnostic.atomic_write_json

    def fake_entry(input_path):
        return _entry(tmp_path)

    def fake_run(entry, config, output_dir, *, resume=True, idem_bin_dir=None):
        calls.append(config.trial_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        if config.trial_id in {"baseline-cap58", "baseline-cap60", "cap58-skimming-1e-4", "cap58-p4poles-eye"}:
            telemetry = {"termination_reason": "idle_stall", "last_progress_age": 301.0, "cpu": {"process_tree_seconds": 88.0}}
            real_atomic(output_dir / "fit.json", {"status": "stalled", "telemetry": telemetry})
            return _trial("ERROR", "phase_stalled:fit", rms=None, order=config.order_max)
        real_atomic(output_dir / "fit.json", {"status": "completed", "model": {"error_history": [0.2, 0.0012], "orders_history": [4, config.order_max]}})
        real_atomic(output_dir / "history.json", {"status": "completed", "error_history": [0.2, 0.0012], "orders_history": [4, config.order_max]})
        real_atomic(output_dir / "pre_accuracy.json", {"status": "completed", "metrics": {"mean_rms": 0.0012}})
        return _trial("FAIL", "pre_rms_above_target", rms=0.0012, order=config.order_max)

    monkeypatch.setattr(diagnostic, "_entry_from_input_path", fake_entry)
    monkeypatch.setattr(diagnostic, "run_adaptive_trial", fake_run)

    summary = diagnostic.run_diagnostic(tmp_path / "line.s2p", tmp_path / "runs")

    assert calls == DIAGNOSTIC_IDS
    cap58 = next(row for row in summary["trials"] if row["trial_id"] == "baseline-cap58")
    reject = next(row for row in summary["trials"] if row["trial_id"] == "cap58-reject-poles-1p0")
    assert cap58["diagnostic"]["stalled_phase"] == "fit"
    assert cap58["diagnostic"]["stall_telemetry"]["termination_reason"] == "idle_stall"
    assert reject["trial"]["status"] == "FAIL"
    assert reject["diagnostic"]["fitting_completed"] is True
    assert reject["diagnostic"]["stalled_phase"] is None
    assert reject["diagnostic"]["history"]["orders_history"] == [4, 58]
    assert reject["diagnostic"]["pre_accuracy"]["mean_rms"] == pytest.approx(0.0012)
    assert summary["decision"]["stable_reproduction"] is True
    assert summary["decision"]["bypass_mechanisms"] == ["reject-poles-1p0"]
    assert summary["decision"]["next_phase"] == "resume_single_variable_direction:reject-poles-1p0"


def test_diagnostic_rejects_wrong_input_sha_and_does_not_load_manifest_overrides(tmp_path: Path, monkeypatch):
    import scripts.sparam_idem_order58_diagnostic as diagnostic

    wrong = replace(_entry(tmp_path), sha256="wrong")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"order_max": 999, "phase_timeout_seconds": 1}), encoding="utf-8")

    monkeypatch.setattr(diagnostic, "_entry_from_input_path", lambda input_path: wrong)

    with pytest.raises(ValueError, match="input sha256"):
        diagnostic.run_diagnostic(tmp_path / "line.s2p", tmp_path / "runs", manifest_path=manifest)

    assert [trial.order_max for trial in diagnostic.build_diagnostic_trials()] == [56, 58, 60, 58, 58, 58]
    assert {trial.phase_timeout_seconds for trial in diagnostic.build_diagnostic_trials()} == {1800.0}


def test_cli_exposes_run_stall_diagnostic(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    seen = {}

    def fake_run(input_path, output_root, *, resume=True):
        seen["input_path"] = input_path
        seen["output_root"] = output_root
        seen["resume"] = resume
        return {
            "completed_trial_count": 3,
            "decision": {"next_phase": "stop_order58_diagnostic_original_stall_not_stably_reproduced"},
        }

    monkeypatch.setattr(cli, "run_idem_order58_diagnostic", fake_run, raising=False)

    code = cli.main(
        [
            "run-stall-diagnostic",
            "--input",
            str(tmp_path / "line.s19p"),
            "--output-root",
            str(tmp_path / "runs"),
            "--no-resume",
        ]
    )

    assert code == 0
    assert seen["resume"] is False
    assert seen["output_root"] == tmp_path / "runs"
    assert "run-stall-diagnostic trials=3" in capsys.readouterr().out
