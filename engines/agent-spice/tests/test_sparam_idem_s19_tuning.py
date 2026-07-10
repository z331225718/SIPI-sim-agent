import json
import math
import os
from pathlib import Path
import inspect
import subprocess

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


def _fit_payload(
    model_path: Path,
    *,
    options_xml_path: Path | None = None,
    order: int = 8,
    error_history=None,
    orders_history=None,
) -> dict:
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text("model", encoding="utf-8")
    return {
        "probe": "idem_adaptive_fitting",
        "status": "completed",
        "model_path": str(model_path),
        "xml_path": str(options_xml_path) if options_xml_path is not None else None,
        "model": {
            "order": order,
            "total_pole_count": order,
            "error_history": [0.2, 0.0008] if error_history is None else error_history,
            "orders_history": [4, order] if orders_history is None else orders_history,
            "pole_blocks": [{"order": order}],
        },
        "command": _command(),
    }


def _accuracy_payload(entry: CorpusEntry, model_path: Path, report_path: Path, rms: float) -> dict:
    return {
        "probe": "idem_accuracy_check",
        "touchstone_path": str(entry.path),
        "model_path": str(model_path),
        "status": "completed",
        "metrics": {
            "ports": entry.ports,
            "frequency_points": entry.frequency_points,
            "max_error": rms * 2,
            "mean_rms": rms,
        },
        "command": _command(),
        "report_path": str(report_path),
    }


def _passivity_payload(output_model: Path, *, passive: bool = True, order: int = 8) -> dict:
    output_model.parent.mkdir(parents=True, exist_ok=True)
    output_model.write_text("passive model", encoding="utf-8")
    return {
        "probe": "idem_passivity",
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
    return {
        "probe": "idem_touchstone_export",
        "status": "completed",
        "output_path": str(output_path),
        "command": _command(),
    }


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

    def fit(
        self,
        touchstone_path: Path,
        model_path: Path,
        *,
        order_min: int,
        order_step: int,
        order_max: int,
        target: float,
        bandwidth_hz: float,
        threads: int,
        options_xml_path: Path,
        idem_bin_dir: Path | None = None,
        timeout_seconds: float | None = None,
    ):
        self.calls.append("fit")
        return _fit_payload(
            model_path,
            options_xml_path=options_xml_path,
            order=self.order,
            error_history=self.error_history,
            orders_history=self.orders_history,
        )

    def accuracy(
        self,
        touchstone_path: Path,
        model_path: Path,
        report_path: Path,
        *,
        idem_bin_dir: Path | None = None,
        timeout_seconds: float | None = None,
    ):
        phase = "pre_accuracy" if "pre" in str(report_path) else "final_accuracy"
        self.calls.append(phase)
        rms = self.pre_rms if phase == "pre_accuracy" else self.final_rms
        return _accuracy_payload(self.entry, model_path, report_path, rms)

    def passivity(
        self,
        model_path: Path,
        output_model_path: Path,
        *,
        idem_bin_dir: Path | None = None,
        threads: int = 8,
        ham_solver: int | None = None,
        preserve_dc: bool = False,
        only_check: int | None = None,
        options_xml_path: Path | None = None,
        timeout_seconds: float | None = None,
    ):
        phase = "final_check" if only_check == 1 else "enforce"
        self.calls.append(phase)
        return _passivity_payload(output_model_path, passive=self.passive, order=self.order)

    def export(
        self,
        model_path: Path,
        output_path: Path,
        *,
        idem_bin_dir: Path | None = None,
        timeout_seconds: float | None = None,
    ):
        self.calls.append("export")
        return _export_payload(output_path)

    def audit(self, original_path: Path, exported_path: Path, *, chunk_size: int = 32):
        self.calls.append("audit")
        return {
            "status": self.audit_status,
            "failure_reason": self.audit_reason,
            "frequency_grid_match": self.audit_status == "PASS",
            "ports": self.entry.ports,
            "frequency_points": self.entry.frequency_points,
            "exported_ports": self.entry.ports,
            "exported_frequency_points": self.entry.frequency_points,
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


def _write_cached_trial(
    output_dir: Path,
    entry: CorpusEntry,
    config: tuning.IdemAdaptiveTrialConfig,
    *,
    status: str = "PASS",
    failure_reason: str | None = None,
    artifact_paths: dict[str, str] | None = None,
) -> ToolTrial:
    fingerprint = tuning.adaptive_trial_fingerprint(entry, config, idem_bin_dir=None)
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
        target_met=status == "PASS",
        status=status,
        failure_reason=failure_reason,
        fingerprint=fingerprint,
        artifact_paths=artifact_paths
        or {
            "selected_model": str(selected_model),
            "exported_touchstone": str(exported_touchstone),
        },
    )
    atomic_write_json(output_dir / "trial.json", trial.to_dict())
    return trial


def _assert_no_var_kwargs_and_matching_signature(fake_method, real_function) -> None:
    fake_signature = inspect.signature(fake_method)
    real_signature = inspect.signature(real_function)
    assert list(fake_signature.parameters) == list(real_signature.parameters)
    for fake_param, real_param in zip(fake_signature.parameters.values(), real_signature.parameters.values()):
        assert fake_param.kind == real_param.kind
        assert fake_param.kind is not inspect.Parameter.VAR_KEYWORD


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


def test_exact_signature_fakes_match_every_idem_adapter_call_and_schema(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    fake = FakePhases(tmp_path, entry)
    _assert_no_var_kwargs_and_matching_signature(fake.fit, tuning.run_idem_adaptive_fitting)
    _assert_no_var_kwargs_and_matching_signature(fake.accuracy, tuning.run_idem_accuracy_check)
    _assert_no_var_kwargs_and_matching_signature(fake.passivity, tuning.run_idem_passivity)
    _assert_no_var_kwargs_and_matching_signature(fake.export, tuning.run_idem_touchstone_export)
    _assert_no_var_kwargs_and_matching_signature(fake.audit, tuning.audit_touchstone_model)
    _patch_phases(monkeypatch, fake)

    trial = tuning.run_adaptive_trial(entry, tuning.IdemAdaptiveTrialConfig(), tmp_path / "trial")

    assert trial.status == "PASS"
    assert fake.calls == ["fit", "pre_accuracy", "enforce", "final_accuracy", "final_check", "export", "audit"]
    assert json.loads((tmp_path / "trial" / "fit.json").read_text(encoding="utf-8"))["probe"] == "idem_adaptive_fitting"
    assert json.loads((tmp_path / "trial" / "pre_accuracy.json").read_text(encoding="utf-8"))["probe"] == "idem_accuracy_check"
    assert json.loads((tmp_path / "trial" / "enforce.json").read_text(encoding="utf-8"))["probe"] == "idem_passivity"
    assert json.loads((tmp_path / "trial" / "export.json").read_text(encoding="utf-8"))["probe"] == "idem_touchstone_export"


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
    seeded = FakePhases(tmp_path, entry)
    _patch_phases(monkeypatch, seeded)
    trial = tuning.run_adaptive_trial(entry, config, output_dir, resume=False)
    assert trial.fingerprint == fingerprint
    assert trial.status == "PASS"
    fake = FakePhases(tmp_path, entry)
    _patch_phases(monkeypatch, fake)

    resumed = tuning.run_adaptive_trial(entry, config, output_dir, resume=True)

    assert resumed.status == "PASS"
    assert fake.calls == []


@pytest.mark.parametrize("status", ["FAIL", "INVALID", "ERROR"])
def test_matching_fingerprint_non_pass_terminal_trials_rerun(tmp_path: Path, monkeypatch, status: str):
    entry = _entry(tmp_path)
    output_dir = tmp_path / "trial"
    output_dir.mkdir()
    config = tuning.IdemAdaptiveTrialConfig()
    monkeypatch.setattr(tuning, "idem_tool_identity", lambda idem_bin_dir=None: "idem-test")
    monkeypatch.setattr(tuning, "benchmark_implementation_identity", lambda: "validation-test")
    _write_cached_trial(output_dir, entry, config, status=status, failure_reason="old_terminal")
    atomic_write_json(output_dir / "fit.json", {"status": "failed", "phase": "fit", "old": True})
    fake = FakePhases(tmp_path, entry)
    _patch_phases(monkeypatch, fake)

    trial = tuning.run_adaptive_trial(entry, config, output_dir, resume=True)

    assert trial.status == "PASS"
    assert fake.calls == ["fit", "pre_accuracy", "enforce", "final_accuracy", "final_check", "export", "audit"]
    assert json.loads((output_dir / "fit.json").read_text(encoding="utf-8")).get("old") is not True


def test_cached_pass_rejects_legacy_phase_payloads_without_provenance(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    output_dir = tmp_path / "trial"
    output_dir.mkdir()
    config = tuning.IdemAdaptiveTrialConfig()
    monkeypatch.setattr(tuning, "idem_tool_identity", lambda idem_bin_dir=None: "idem-test")
    monkeypatch.setattr(tuning, "benchmark_implementation_identity", lambda: "validation-test")
    for name in tuning.PHASE_FILE_NAMES:
        atomic_write_json(output_dir / name, {"status": "completed"})
    _write_cached_trial(output_dir, entry, config)
    fake = FakePhases(tmp_path, entry)
    _patch_phases(monkeypatch, fake)

    trial = tuning.run_adaptive_trial(entry, config, output_dir, resume=True)

    assert trial.status == "PASS"
    assert fake.calls


def test_cached_pass_rejects_artifacts_outside_current_trial_directory(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    output_dir = tmp_path / "trial"
    output_dir.mkdir()
    other_dir = tmp_path / "old-trial"
    other_dir.mkdir()
    old_model = other_dir / "passive.mod.h5"
    old_export = other_dir / f"passive.s{entry.ports}p"
    old_model.write_text("old model", encoding="utf-8")
    _write_s2p(old_export)
    config = tuning.IdemAdaptiveTrialConfig()
    monkeypatch.setattr(tuning, "idem_tool_identity", lambda idem_bin_dir=None: "idem-test")
    monkeypatch.setattr(tuning, "benchmark_implementation_identity", lambda: "validation-test")
    seeded = FakePhases(tmp_path, entry)
    _patch_phases(monkeypatch, seeded)
    tuning.run_adaptive_trial(entry, config, output_dir, resume=False)
    payload = json.loads((output_dir / "trial.json").read_text(encoding="utf-8"))
    payload["artifact_paths"]["selected_model"] = str(old_model)
    payload["artifact_paths"]["exported_touchstone"] = str(old_export)
    atomic_write_json(output_dir / "trial.json", payload)
    fake = FakePhases(tmp_path, entry)
    _patch_phases(monkeypatch, fake)

    trial = tuning.run_adaptive_trial(entry, config, output_dir, resume=True)

    assert trial.status == "PASS"
    assert fake.calls


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


def test_adaptive_config_serializes_positive_infinity_as_inf_string_and_roundtrips(tmp_path: Path):
    entry = _entry(tmp_path)
    default_config = tuning.IdemAdaptiveTrialConfig()
    finite_config = tuning.IdemAdaptiveTrialConfig(
        adaptive_options=tuning.IdemAdaptiveFittingOptions(reject_poles_max_relative_frequency=2.0)
    )

    payload = default_config.to_dict()
    roundtripped = json.loads(json.dumps(payload, allow_nan=False))

    assert roundtripped["adaptive_options"]["reject_poles_max_relative_frequency"] == "INF"
    assert tuning.adaptive_trial_fingerprint(entry, default_config) != tuning.adaptive_trial_fingerprint(
        entry, finite_config
    )
    assert tuning._json_safe(float("inf")) is None
    assert tuning._json_safe(float("nan")) is None


def test_idem_tool_identity_hashes_every_executable_used_by_pipeline(tmp_path: Path):
    bin_dir = tmp_path / "idem-bin"
    bin_dir.mkdir()
    for exe_name in (
        "idemmp_fitting.exe",
        "idemmp_checkaccuracy.exe",
        "idemmp_passivity.exe",
        "idemmp_export.exe",
    ):
        path = bin_dir / exe_name
        path.write_bytes(f"{exe_name}:v1".encode("utf-8"))
        os.utime(path, (1_700_000_000, 1_700_000_000))

    before = tuning.idem_tool_identity(bin_dir)
    passivity = bin_dir / "idemmp_passivity.exe"
    passivity.write_bytes(b"idemmp_passivity.exe:v2")
    os.utime(passivity, (1_700_000_000, 1_700_000_000))
    after = tuning.idem_tool_identity(bin_dir)

    for exe_name in (
        "idemmp_fitting.exe",
        "idemmp_checkaccuracy.exe",
        "idemmp_passivity.exe",
        "idemmp_export.exe",
    ):
        assert exe_name in before
    assert "sha256=" in before
    assert before != after


def test_validation_identity_hashes_script_benchmark_and_idem_sources(tmp_path: Path, monkeypatch):
    root = tmp_path / "repo"
    script = root / "scripts" / "sparam_idem_s19_tuning.py"
    benchmark = root / "src" / "agent_spice" / "sparam" / "benchmark.py"
    idem = root / "src" / "agent_spice" / "sparam" / "idem.py"
    script.parent.mkdir(parents=True)
    benchmark.parent.mkdir(parents=True)
    script.write_text("script v1", encoding="utf-8")
    benchmark.write_text("benchmark v1", encoding="utf-8")
    idem.write_text("idem v1", encoding="utf-8")
    for path in (script, benchmark, idem):
        os.utime(path, (1_700_000_000, 1_700_000_000))
    monkeypatch.setattr(tuning, "__file__", str(script))

    before = tuning.benchmark_implementation_identity()
    idem.write_text("idem v2", encoding="utf-8")
    os.utime(idem, (1_700_000_000, 1_700_000_000))
    after = tuning.benchmark_implementation_identity()

    assert "sparam_idem_s19_tuning.py" in before
    assert "benchmark.py" in before
    assert "idem.py" in before
    assert "sha256=" in before
    assert before != after


@pytest.mark.parametrize(
    "exception",
    [
        TimeoutError("timed out"),
        subprocess.TimeoutExpired(cmd=["idemmp_fitting.exe"], timeout=0.01),
    ],
)
def test_adapter_timeouts_are_terminal_phase_timeout_errors_and_rerun_on_resume(
    tmp_path: Path, monkeypatch, exception: BaseException
):
    entry = _entry(tmp_path)
    output_dir = tmp_path / "trial"
    config = tuning.IdemAdaptiveTrialConfig()
    monkeypatch.setattr(tuning, "idem_tool_identity", lambda idem_bin_dir=None: "idem-test")
    monkeypatch.setattr(tuning, "benchmark_implementation_identity", lambda: "validation-test")

    def timeout_fit(
        touchstone_path: Path,
        model_path: Path,
        *,
        order_min: int,
        order_step: int,
        order_max: int,
        target: float,
        bandwidth_hz: float,
        threads: int,
        options_xml_path: Path,
        idem_bin_dir: Path | None = None,
        timeout_seconds: float | None = None,
    ):
        raise exception

    monkeypatch.setattr(tuning, "run_idem_adaptive_fitting", timeout_fit)

    first = tuning.run_adaptive_trial(entry, config, output_dir, resume=True)

    assert first.status == "ERROR"
    assert first.failure_reason == "phase_timeout:fit"
    assert json.loads((output_dir / "fit.json").read_text(encoding="utf-8"))["status"] == "timeout"
    assert json.loads((output_dir / "trial.json").read_text(encoding="utf-8"))["status"] == "ERROR"

    fake = FakePhases(tmp_path, entry)
    _patch_phases(monkeypatch, fake)
    second = tuning.run_adaptive_trial(entry, config, output_dir, resume=True)

    assert second.status == "PASS"
    assert fake.calls


@pytest.mark.parametrize("exception", [KeyboardInterrupt(), SystemExit(2)])
def test_base_exceptions_are_not_swallowed_by_phase_error_handler(tmp_path: Path, monkeypatch, exception: BaseException):
    entry = _entry(tmp_path)
    config = tuning.IdemAdaptiveTrialConfig()
    monkeypatch.setattr(tuning, "idem_tool_identity", lambda idem_bin_dir=None: "idem-test")
    monkeypatch.setattr(tuning, "benchmark_implementation_identity", lambda: "validation-test")

    def interrupted_fit(
        touchstone_path: Path,
        model_path: Path,
        *,
        order_min: int,
        order_step: int,
        order_max: int,
        target: float,
        bandwidth_hz: float,
        threads: int,
        options_xml_path: Path,
        idem_bin_dir: Path | None = None,
        timeout_seconds: float | None = None,
    ):
        raise exception

    monkeypatch.setattr(tuning, "run_idem_adaptive_fitting", interrupted_fit)

    with pytest.raises(type(exception)):
        tuning.run_adaptive_trial(entry, config, tmp_path / "trial", resume=True)


def test_terminal_fail_does_not_reuse_stale_selected_or_export_artifacts(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    output_dir = tmp_path / "trial"
    output_dir.mkdir()
    (output_dir / "passive.mod.h5").write_text("old selected", encoding="utf-8")
    _write_s2p(output_dir / f"passive.s{entry.ports}p")
    fake = FakePhases(tmp_path, entry, pre_rms=0.002)
    _patch_phases(monkeypatch, fake)

    trial = tuning.run_adaptive_trial(entry, tuning.IdemAdaptiveTrialConfig(), output_dir, resume=False)

    assert trial.status == "FAIL"
    assert trial.failure_reason == "pre_rms_above_target"
    assert not (output_dir / "passive.mod.h5").exists()
    assert not (output_dir / f"passive.s{entry.ports}p").exists()


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
