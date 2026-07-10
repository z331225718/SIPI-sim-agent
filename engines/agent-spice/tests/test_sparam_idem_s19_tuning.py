import json
from pathlib import Path

import pytest

from agent_spice.sparam.benchmark import CorpusEntry, ToolTrial, atomic_write_json
from agent_spice.sparam.idem import IdemCommandResult

import scripts.sparam_idem_s19_tuning as tuning


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
        sha256="sha-line",
        size_bytes=touchstone.stat().st_size,
        ports=2,
        frequency_points=2,
        frequency_min_hz=1e6,
        frequency_max_hz=2e6,
        reference_impedance=(50.0,),
    )


def _command(seconds: float = 0.1, memory: float = 2.0) -> dict:
    return IdemCommandResult(["idem"], 0, "Results\n", "", seconds, memory).to_dict()


def _fit_payload(model_path: Path, *, order: int = 8, error_history=None, orders_history=None) -> dict:
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text("model", encoding="utf-8")
    return {
        "status": "completed",
        "model_path": str(model_path),
        "model": {
            "order": order,
            "total_pole_count": order,
            "error_history": [0.2, 0.0008] if error_history is None else error_history,
            "orders_history": [4, order] if orders_history is None else orders_history,
            "pole_blocks": [{"order": order}],
        },
        "command": _command(),
    }


def _accuracy_payload(tmp_path: Path, entry: CorpusEntry, rms: float) -> dict:
    return {
        "status": "completed",
        "metrics": {
            "ports": entry.ports,
            "frequency_points": entry.frequency_points,
            "max_error": rms * 2,
            "mean_rms": rms,
        },
        "command": _command(),
        "report_path": str(tmp_path / "accuracy.txt"),
    }


def _passivity_payload(output_model: Path, *, passive: bool = True, order: int = 8) -> dict:
    output_model.parent.mkdir(parents=True, exist_ok=True)
    output_model.write_text("passive model", encoding="utf-8")
    return {
        "status": "completed",
        "passivity": {
            "passive": passive,
            "max_singular_values": [{"value": 0.999, "frequency_hz": 1e6}],
        },
        "model": {"order": order, "total_pole_count": order},
        "output_model_path": str(output_model),
        "command": _command(),
    }


def _export_payload(output_path: Path) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_s2p(output_path)
    return {"status": "completed", "output_path": str(output_path), "command": _command()}


class FakePhases:
    def __init__(
        self,
        tmp_path: Path,
        entry: CorpusEntry,
        *,
        pre_rms: float = 0.0008,
        final_rms: float = 0.0008,
        passive: bool = True,
        audit_status: str = "PASS",
        audit_reason: str | None = None,
        order: int = 8,
        error_history=None,
        orders_history=None,
    ) -> None:
        self.tmp_path = tmp_path
        self.entry = entry
        self.pre_rms = pre_rms
        self.final_rms = final_rms
        self.passive = passive
        self.audit_status = audit_status
        self.audit_reason = audit_reason
        self.order = order
        self.error_history = error_history
        self.orders_history = orders_history
        self.calls: list[str] = []

    def fit(self, touchstone_path, model_path, **kwargs):
        self.calls.append("fit")
        return _fit_payload(
            model_path,
            order=self.order,
            error_history=self.error_history,
            orders_history=self.orders_history,
        )

    def accuracy(self, touchstone_path, model_path, report_path, **kwargs):
        phase = "pre_accuracy" if "pre" in str(report_path) else "final_accuracy"
        self.calls.append(phase)
        rms = self.pre_rms if phase == "pre_accuracy" else self.final_rms
        return _accuracy_payload(self.tmp_path, self.entry, rms)

    def passivity(self, model_path, output_model_path, **kwargs):
        phase = "final_check" if kwargs.get("only_check") == 1 else "enforce"
        self.calls.append(phase)
        return _passivity_payload(output_model_path, passive=self.passive, order=self.order)

    def export(self, model_path, output_path, **kwargs):
        self.calls.append("export")
        return _export_payload(output_path)

    def audit(self, original_path, exported_path, **kwargs):
        self.calls.append("audit")
        return {
            "status": self.audit_status,
            "failure_reason": self.audit_reason,
            "frequency_grid_match": self.audit_status == "PASS",
            "mean_rms": self.final_rms if self.audit_status == "PASS" else None,
            "sampled_max_sigma": 0.999 if self.audit_status == "PASS" else None,
        }


def _patch_phases(monkeypatch, fake: FakePhases) -> None:
    monkeypatch.setattr(tuning, "run_idem_adaptive_fitting", fake.fit)
    monkeypatch.setattr(tuning, "run_idem_accuracy_check", fake.accuracy)
    monkeypatch.setattr(tuning, "run_idem_passivity", fake.passivity)
    monkeypatch.setattr(tuning, "run_idem_touchstone_export", fake.export)
    monkeypatch.setattr(tuning, "audit_touchstone_model", fake.audit)
    monkeypatch.setattr(tuning, "idem_tool_identity", lambda idem_bin_dir=None: "idem-test")
    monkeypatch.setattr(tuning, "benchmark_implementation_identity", lambda: "validation-test")


def test_pre_rms_above_target_stops_before_passivity_and_saves_history(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    fake = FakePhases(tmp_path, entry, pre_rms=0.002)
    _patch_phases(monkeypatch, fake)

    trial = tuning.run_adaptive_trial(entry, tuning.IdemAdaptiveTrialConfig(), tmp_path / "trial")

    assert trial.status == "FAIL"
    assert trial.failure_reason == "pre_rms_above_target"
    assert fake.calls == ["fit", "pre_accuracy"]
    assert (tmp_path / "trial" / "fit.json").is_file()
    history = json.loads((tmp_path / "trial" / "history.json").read_text(encoding="utf-8"))
    assert history["error_history"] == [0.2, 0.0008]
    assert history["orders_history"] == [4, 8]
    assert (tmp_path / "trial" / "pre_accuracy.json").is_file()
    assert not (tmp_path / "trial" / "enforce.json").exists()


def test_post_enforcement_rms_above_target_fails_after_final_accuracy(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    fake = FakePhases(tmp_path, entry, final_rms=0.002)
    _patch_phases(monkeypatch, fake)

    trial = tuning.run_adaptive_trial(entry, tuning.IdemAdaptiveTrialConfig(), tmp_path / "trial")

    assert trial.status == "FAIL"
    assert trial.failure_reason == "final_rms_above_target"
    assert fake.calls == ["fit", "pre_accuracy", "enforce", "final_accuracy"]
    assert (tmp_path / "trial" / "final_accuracy.json").is_file()
    assert not (tmp_path / "trial" / "final_check.json").exists()


def test_check_only_non_passive_fails_without_export(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    fake = FakePhases(tmp_path, entry, passive=False)
    _patch_phases(monkeypatch, fake)

    trial = tuning.run_adaptive_trial(entry, tuning.IdemAdaptiveTrialConfig(), tmp_path / "trial")

    assert trial.status == "FAIL"
    assert trial.failure_reason == "final_check_non_passive"
    assert fake.calls == ["fit", "pre_accuracy", "enforce", "final_accuracy", "final_check"]
    assert not (tmp_path / "trial" / "export.json").exists()


def test_exported_grid_mismatch_is_invalid_from_independent_audit(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    fake = FakePhases(tmp_path, entry, audit_status="INVALID", audit_reason="frequency_grid_mismatch")
    _patch_phases(monkeypatch, fake)

    trial = tuning.run_adaptive_trial(entry, tuning.IdemAdaptiveTrialConfig(), tmp_path / "trial")

    assert trial.status == "INVALID"
    assert trial.failure_reason == "audit_failed:frequency_grid_mismatch"
    assert fake.calls == ["fit", "pre_accuracy", "enforce", "final_accuracy", "final_check", "export", "audit"]


def test_successful_audit_passes_full_adaptive_trial(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    fake = FakePhases(tmp_path, entry)
    _patch_phases(monkeypatch, fake)

    trial = tuning.run_adaptive_trial(entry, tuning.IdemAdaptiveTrialConfig(), tmp_path / "trial")

    assert trial.status == "PASS"
    assert trial.target_met is True
    assert trial.effective_order == 8
    assert trial.final_mean_rms == pytest.approx(0.0008)
    assert trial.authoritative_passive is True
    assert trial.sampled_max_sigma == pytest.approx(0.999)


def test_final_order_above_order_max_is_invalid(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    fake = FakePhases(tmp_path, entry, order=101)
    _patch_phases(monkeypatch, fake)

    trial = tuning.run_adaptive_trial(entry, tuning.IdemAdaptiveTrialConfig(order_max=100), tmp_path / "trial")

    assert trial.status == "INVALID"
    assert trial.failure_reason == "final_order_above_order_max"
    assert fake.calls == ["fit"]


def test_truncated_trial_json_or_fingerprint_mismatch_reruns(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    output_dir = tmp_path / "trial"
    output_dir.mkdir()
    (output_dir / "trial.json").write_text("{", encoding="utf-8")
    fake = FakePhases(tmp_path, entry)
    _patch_phases(monkeypatch, fake)

    first = tuning.run_adaptive_trial(entry, tuning.IdemAdaptiveTrialConfig(), output_dir, resume=True)

    assert first.status == "PASS"
    assert fake.calls
    fake.calls.clear()
    payload = json.loads((output_dir / "trial.json").read_text(encoding="utf-8"))
    payload["fingerprint"] = "wrong"
    atomic_write_json(output_dir / "trial.json", payload)

    second = tuning.run_adaptive_trial(entry, tuning.IdemAdaptiveTrialConfig(), output_dir, resume=True)

    assert second.status == "PASS"
    assert fake.calls


def test_exact_valid_fingerprint_resume_makes_zero_phase_calls(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    output_dir = tmp_path / "trial"
    output_dir.mkdir()
    config = tuning.IdemAdaptiveTrialConfig()
    monkeypatch.setattr(tuning, "idem_tool_identity", lambda idem_bin_dir=None: "idem-test")
    monkeypatch.setattr(tuning, "benchmark_implementation_identity", lambda: "validation-test")
    fingerprint = tuning.adaptive_trial_fingerprint(entry, config, idem_bin_dir=None)
    for name in tuning.PHASE_FILE_NAMES:
        atomic_write_json(output_dir / name, {"status": "completed"})
    selected_model = output_dir / "passive.mod.h5"
    exported_touchstone = output_dir / f"passive.s{entry.ports}p"
    selected_model.write_text("model", encoding="utf-8")
    _write_s2p(exported_touchstone)
    trial = ToolTrial(
        tool="idem-adaptive",
        requested_order=config.order_max,
        effective_order=8,
        pre_mean_rms=0.0008,
        final_mean_rms=0.0008,
        authoritative_passive=True,
        final_max_sigma=0.999,
        sampled_max_sigma=0.999,
        target_met=True,
        status="PASS",
        fingerprint=fingerprint,
        artifact_paths={
            "selected_model": str(selected_model),
            "exported_touchstone": str(exported_touchstone),
        },
    )
    atomic_write_json(output_dir / "trial.json", trial.to_dict())
    fake = FakePhases(tmp_path, entry)
    _patch_phases(monkeypatch, fake)

    resumed = tuning.run_adaptive_trial(entry, config, output_dir, resume=True)

    assert resumed.status == "PASS"
    assert fake.calls == []


def test_fingerprint_payload_uses_adaptive_contract_and_complete_config(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    config = tuning.IdemAdaptiveTrialConfig(order_min=4, order_step=4, order_max=12, threads=3)
    monkeypatch.setattr(tuning, "idem_tool_identity", lambda idem_bin_dir=None: "idem-test")
    monkeypatch.setattr(tuning, "benchmark_implementation_identity", lambda: "validation-test")

    payload = tuning.adaptive_trial_fingerprint_payload(entry, config, idem_bin_dir=None)

    assert payload == {
        "contract_version": "idem_s19_adaptive_v1",
        "input_sha256": "sha-line",
        "idem_identity": "idem-test",
        "validation_identity": "validation-test",
        "trial_config": config.to_dict(),
    }
    assert "order" not in payload["trial_config"]["adaptive_options"]


def test_history_normalization_warns_without_aligning_mismatched_or_nonfinite_lists(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    fake = FakePhases(tmp_path, entry, error_history=[0.2, float("inf")], orders_history=[4])
    _patch_phases(monkeypatch, fake)

    trial = tuning.run_adaptive_trial(entry, tuning.IdemAdaptiveTrialConfig(), tmp_path / "trial")

    assert trial.status == "PASS"
    history = json.loads((tmp_path / "trial" / "history.json").read_text(encoding="utf-8"))
    assert history["error_history"] == [0.2, None]
    assert history["orders_history"] == [4]
    assert set(history["warnings"]) == {"history_length_mismatch", "history_non_finite"}
