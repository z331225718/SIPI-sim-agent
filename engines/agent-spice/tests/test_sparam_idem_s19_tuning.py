import json
import math
import os
from pathlib import Path
import inspect
import importlib
import subprocess
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest

from agent_spice.sparam.benchmark import CorpusEntry, ToolTrial, atomic_write_json
from agent_spice.sparam.idem import CommandIdleStallError, IdemCommandResult

import scripts.sparam_idem_s19_tuning as tuning


STAGE1_TRIAL_IDS = [
    "baseline-adaptive",
    "enhanced-placement",
    "postadding-2",
    "postadding-3",
    "iterations-initial5-final3",
    "stagnation-alpha0p01",
    "stagnation-alpha0p001",
    "stagnation-back5",
    "guaranteed-0p01",
    "guaranteed-0p001",
    "skimming-1e-4",
    "skimming-1e-5",
    "final-skimming-1e-4",
    "final-skimming-1e-5",
    "reject-poles-1p0",
    "reject-poles-1p2",
    "reject-poles-2p0",
    "asymptotic-relocate",
    "p4poles-eye",
    "p4poles-largest4",
    "p4poles-largest8",
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
    order_min: int = 4,
    order_step: int = 2,
    order_max: int = 8,
    target: float = 0.001,
    bandwidth_hz: float = 2e6,
    threads: int = 8,
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
        "command": IdemCommandResult(
            [
                "idemmp_fitting.exe",
                "-its",
                "line.s2p",
                "-o",
                str(model_path),
                "-tol",
                f"{target:.16g}",
                "-orderMin",
                str(order_min),
                "-orderStep",
                str(order_step),
                "-orderMax",
                str(order_max),
                "-bandwidth",
                f"{bandwidth_hz:.16g}",
                "-DC",
                "1",
                "-nThreads",
                str(threads),
                "-xml",
                str(options_xml_path),
            ],
            0,
            "Results\n",
            "",
            0.1,
            2.0,
        ).to_dict(),
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
        self.fit_kwargs: dict[str, object] | None = None

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
        idle_timeout_seconds: float | None = None,
    ):
        self.calls.append("fit")
        self.fit_kwargs = {
            "order_min": order_min,
            "order_step": order_step,
            "order_max": order_max,
            "target": target,
            "bandwidth_hz": bandwidth_hz,
            "threads": threads,
            "options_xml_path": options_xml_path,
            "idle_timeout_seconds": idle_timeout_seconds,
        }
        return _fit_payload(
            model_path,
            options_xml_path=options_xml_path,
            order_min=order_min,
            order_step=order_step,
            order_max=order_max,
            target=target,
            bandwidth_hz=bandwidth_hz,
            threads=threads,
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
    runtime_contract = tuning._adaptive_runtime_contract(entry, config)
    selected_model = output_dir / "passive.mod.h5"
    exported_touchstone = output_dir / f"passive.s{entry.ports}p"
    selected_model.write_text("model", encoding="utf-8")
    _write_s2p(exported_touchstone)
    trial = ToolTrial(
        tool="idem-adaptive",
        requested_order=config.order_max,
        requested_order_step=runtime_contract.requested_order_step,
        effective_order_step=runtime_contract.effective_order_step,
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
        warnings=list(runtime_contract.warnings),
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


def _changed_adaptive_option_fields(
    baseline: tuning.IdemAdaptiveTrialConfig,
    candidate: tuning.IdemAdaptiveTrialConfig,
) -> set[str]:
    baseline_options = baseline.to_dict()["adaptive_options"]
    candidate_options = candidate.to_dict()["adaptive_options"]
    return {key for key in sorted(baseline_options) if baseline_options[key] != candidate_options[key]}


def test_build_stage1_manifest_has_all_fixed_ids_stable_order_and_single_mechanism_changes():
    trials = tuning.build_stage1_trials()

    assert [trial.trial_id for trial in trials] == STAGE1_TRIAL_IDS
    assert [trial.trial_id for trial in tuning.build_stage1_trials()] == STAGE1_TRIAL_IDS
    assert len({trial.trial_id for trial in trials}) == len(STAGE1_TRIAL_IDS)
    assert all(tuning._safe_trial_dir_name(trial.trial_id) == trial.trial_id for trial in trials)

    baseline = trials[0]
    assert baseline.trial_id == "baseline-adaptive"
    assert baseline.order_min == 4
    assert baseline.order_step == 2
    assert baseline.order_max == 100
    assert baseline.rms_target == pytest.approx(0.001)
    assert baseline.passivity_epsilon == pytest.approx(1.0e-6)
    assert baseline.threads == 8
    assert baseline.phase_timeout_seconds == pytest.approx(7200.0)
    assert baseline.adaptive_options.split_type == "none"
    assert baseline.adaptive_options.p4poles_n_largest == "INF"

    expected_groups = {
        "enhanced-placement": {"enhance_poles_placement"},
        "postadding-2": {"postadding_iterations"},
        "postadding-3": {"postadding_iterations"},
        "iterations-initial5-final3": {"initial_iterations", "final_iterations"},
        "stagnation-alpha0p01": {"stagnation_alpha"},
        "stagnation-alpha0p001": {"stagnation_alpha"},
        "stagnation-back5": {"stagnation_back_steps"},
        "guaranteed-0p01": {"guaranteed_accuracy"},
        "guaranteed-0p001": {"guaranteed_accuracy"},
        "skimming-1e-4": {"skimming_tolerance"},
        "skimming-1e-5": {"skimming_tolerance"},
        "final-skimming-1e-4": {"final_skimming_tolerance"},
        "final-skimming-1e-5": {"final_skimming_tolerance"},
        "reject-poles-1p0": {"reject_poles", "reject_poles_max_relative_frequency"},
        "reject-poles-1p2": {"reject_poles", "reject_poles_max_relative_frequency"},
        "reject-poles-2p0": {"reject_poles", "reject_poles_max_relative_frequency"},
        "asymptotic-relocate": {"asymptotic_relocate_poles"},
        "p4poles-eye": {"p4poles_type"},
        "p4poles-largest4": {"p4poles_n_largest"},
        "p4poles-largest8": {"p4poles_n_largest"},
    }

    baseline_global = {
        key: value
        for key, value in baseline.to_dict().items()
        if key not in {"trial_id", "adaptive_options"}
    }
    for trial in trials[1:]:
        trial_global = {
            key: value
            for key, value in trial.to_dict().items()
            if key not in {"trial_id", "adaptive_options"}
        }
        assert trial_global == baseline_global
        assert _changed_adaptive_option_fields(baseline, trial) == expected_groups[trial.trial_id]


def test_stage1_manifest_file_roundtrips_from_builder_without_dual_source_drift():
    manifest_path = Path("configs/idem-s19-adaptive-v1.json")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["contract_version"] == tuning.CONTRACT_VERSION
    assert payload["stage"] == "stage1"
    assert payload["source_of_truth"] == "scripts.sparam_idem_s19_tuning:build_stage1_trials"
    assert payload["trials"] == [trial.to_dict() for trial in tuning.build_stage1_trials()]
    assert json.loads(json.dumps(payload, sort_keys=True, allow_nan=False)) == payload


def test_run_experiment_runs_trials_sequentially_and_writes_partial_summary_after_each(
    tmp_path: Path, monkeypatch
):
    input_path = tmp_path / "line.s2p"
    _write_s2p(input_path)
    active: list[str] = []
    calls: list[str] = []
    partial_counts: list[int] = []
    real_atomic_write_json = tuning.atomic_write_json

    def fake_run_adaptive_trial(entry, config, output_dir, *, resume=True, idem_bin_dir=None):
        assert active == []
        active.append(config.trial_id)
        calls.append(config.trial_id)
        assert output_dir.name == config.trial_id
        trial = ToolTrial(
            tool="idem-adaptive",
            requested_order=config.order_max,
            effective_order=8,
            pre_mean_rms=0.0008,
            final_mean_rms=0.0007,
            target_met=False,
            status="FAIL",
            failure_reason="pre_rms_above_target",
            elapsed_seconds=float(len(calls)),
            peak_memory_mb=10.0 + len(calls),
        )
        active.pop()
        return trial

    def tracking_atomic_write_json(path: Path, payload: dict) -> None:
        if path.name == "summary.partial.json":
            partial_counts.append(payload["completed_trial_count"])
        real_atomic_write_json(path, payload)

    monkeypatch.setattr(tuning, "run_adaptive_trial", fake_run_adaptive_trial)
    monkeypatch.setattr(tuning, "atomic_write_json", tracking_atomic_write_json)

    summary = tuning.run_experiment(input_path, tmp_path / "runs", stage="stage1", resume=True)

    assert calls == STAGE1_TRIAL_IDS
    assert partial_counts == list(range(1, len(STAGE1_TRIAL_IDS) + 1))
    assert summary["completed_trial_count"] == len(STAGE1_TRIAL_IDS)
    assert [row["trial_id"] for row in summary["trials"]] == STAGE1_TRIAL_IDS
    assert json.loads((tmp_path / "runs" / "summary.partial.json").read_text(encoding="utf-8")) == summary
    assert json.loads((tmp_path / "runs" / "manifest.json").read_text(encoding="utf-8"))["stage"] == "stage1"
    assert json.loads((tmp_path / "runs" / "summary.json").read_text(encoding="utf-8")) == summary
    assert (tmp_path / "runs" / "summary.csv").read_text(encoding="utf-8").splitlines()[0].startswith("trial_id,")


def test_single_variable_stage_applies_stop_rule_after_first_passing_splitting_none_trial(
    tmp_path: Path, monkeypatch
):
    input_path = tmp_path / "line.s2p"
    _write_s2p(input_path)
    calls: list[str] = []

    def fake_run_adaptive_trial(entry, config, output_dir, *, resume=True, idem_bin_dir=None):
        calls.append(config.trial_id)
        target_met = config.trial_id == "enhanced-placement"
        return ToolTrial(
            tool="idem-adaptive",
            requested_order=config.order_max,
            effective_order=8,
            pre_mean_rms=0.0008,
            final_mean_rms=0.0007,
            authoritative_passive=target_met,
            sampled_max_sigma=0.999 if target_met else None,
            target_met=target_met,
            status="PASS" if target_met else "FAIL",
            failure_reason=None if target_met else "pre_rms_above_target",
        )

    monkeypatch.setattr(tuning, "run_adaptive_trial", fake_run_adaptive_trial)

    summary = tuning.run_experiment(input_path, tmp_path / "runs", stage="single-variable", resume=True)

    assert calls == ["baseline-adaptive", "enhanced-placement"]
    assert summary["completed_trial_count"] == 2
    assert summary["stop_rule"]["triggered"] is True
    assert summary["stop_rule"]["trial_id"] == "enhanced-placement"


def test_combination_trials_encode_ab_then_c_configs_and_task7_runtime_contract():
    trials = tuning.build_combination_trials()

    assert [trial.trial_id for trial in trials] == [
        "combination-a-alpha0p01-postadding3",
        "combination-b-alpha0p01-initial5-final3",
        "combination-c-alpha0p01-postadding3-initial5-final3",
    ]
    assert all(trial.phase_timeout_seconds == pytest.approx(1800.0) for trial in trials)
    assert all(trial.fit_idle_timeout_seconds == pytest.approx(300.0) for trial in trials)
    assert all(trial.adaptive_options.stagnation_alpha == pytest.approx(0.01) for trial in trials)
    assert [trial.adaptive_options.postadding_iterations for trial in trials] == [3, 1, 3]
    assert [trial.adaptive_options.initial_iterations for trial in trials] == [3, 5, 5]
    assert [trial.adaptive_options.final_iterations for trial in trials] == [1, 3, 3]
    assert all(trial.adaptive_options.split_type == "none" for trial in trials)


def test_combination_stage_runs_ab_only_when_not_both_improve_and_never_runs_fixed_baseline(
    tmp_path: Path, monkeypatch
):
    input_path = tmp_path / "line.s2p"
    _write_s2p(input_path)
    calls: list[str] = []

    def fake_run_adaptive_trial(entry, config, output_dir, *, resume=True, idem_bin_dir=None):
        calls.append(config.trial_id)
        assert output_dir.name == config.trial_id
        if config.trial_id.startswith("combination-a-"):
            return ToolTrial(
                tool="idem-adaptive",
                requested_order=config.order_max,
                effective_order=72,
                final_mean_rms=0.0009,
                elapsed_seconds=130.0,
                target_met=True,
                status="PASS",
                authoritative_passive=True,
                sampled_max_sigma=0.999,
            )
        return ToolTrial(
            tool="idem-adaptive",
            requested_order=config.order_max,
            effective_order=72,
            final_mean_rms=0.0011,
            elapsed_seconds=90.0,
            target_met=False,
            status="FAIL",
            failure_reason="final_rms_above_target",
        )

    monkeypatch.setattr(tuning, "run_adaptive_trial", fake_run_adaptive_trial)
    monkeypatch.setattr(
        tuning,
        "run_fixed_order_control",
        lambda *args, **kwargs: pytest.fail("combination stage must not rerun fixed baseline"),
    )

    summary = tuning.run_experiment(input_path, tmp_path / "runs", stage="combination", resume=False)

    assert calls == ["combination-a-alpha0p01-postadding3", "combination-b-alpha0p01-initial5-final3"]
    assert summary["completed_trial_count"] == 2
    assert summary["combination_decision"]["a_improves"] is True
    assert summary["combination_decision"]["b_improves"] is False
    assert summary["combination_decision"]["run_c"] is False
    assert "fixed_order_control" not in summary
    assert summary["local_best_trial_id"] == "combination-a-alpha0p01-postadding3"
    assert summary["overall_reference_trial_id"] == "stagnation-alpha0p01"
    assert summary["overall_best"]["source"] == "local_trial"
    assert summary["overall_best"]["trial_id"] == "combination-a-alpha0p01-postadding3"
    assert summary["best_trial_id"] == "combination-a-alpha0p01-postadding3"
    assert json.loads((tmp_path / "runs" / "manifest.json").read_text(encoding="utf-8"))["baseline_reference"][
        "fingerprint"
    ] == tuning.COMBINATION_BASELINE_REFERENCE["fingerprint"]


def test_combination_stage_runs_c_only_after_a_and_b_both_improve(tmp_path: Path, monkeypatch):
    input_path = tmp_path / "line.s2p"
    _write_s2p(input_path)
    calls: list[str] = []

    def fake_run_adaptive_trial(entry, config, output_dir, *, resume=True, idem_bin_dir=None):
        if config.trial_id.startswith("combination-c-"):
            assert calls == ["combination-a-alpha0p01-postadding3", "combination-b-alpha0p01-initial5-final3"]
        calls.append(config.trial_id)
        return ToolTrial(
            tool="idem-adaptive",
            requested_order=config.order_max,
            effective_order=72 if not config.trial_id.startswith("combination-c-") else 68,
            final_mean_rms=0.0009,
            elapsed_seconds=130.0,
            target_met=True,
            status="PASS",
            authoritative_passive=True,
            sampled_max_sigma=0.999,
        )

    monkeypatch.setattr(tuning, "run_adaptive_trial", fake_run_adaptive_trial)

    summary = tuning.run_experiment(input_path, tmp_path / "runs", stage="combination", resume=False)

    assert calls == [
        "combination-a-alpha0p01-postadding3",
        "combination-b-alpha0p01-initial5-final3",
        "combination-c-alpha0p01-postadding3-initial5-final3",
    ]
    assert summary["completed_trial_count"] == 3
    assert summary["combination_decision"]["a_improves"] is True
    assert summary["combination_decision"]["b_improves"] is True
    assert summary["combination_decision"]["run_c"] is True


def test_combination_summary_keeps_external_reference_from_looking_like_local_best(
    tmp_path: Path, monkeypatch
):
    input_path = tmp_path / "line.s2p"
    _write_s2p(input_path)

    def fake_run_adaptive_trial(entry, config, output_dir, *, resume=True, idem_bin_dir=None):
        return ToolTrial(
            tool="idem-adaptive",
            requested_order=config.order_max,
            effective_order=tuning.COMBINATION_BASELINE_REFERENCE["effective_order"],
            final_mean_rms=tuning.COMBINATION_BASELINE_REFERENCE["final_mean_rms"] + 1e-5,
            elapsed_seconds=tuning.COMBINATION_BASELINE_REFERENCE["elapsed_seconds"] + 1.0,
            target_met=True,
            status="PASS",
            authoritative_passive=True,
            sampled_max_sigma=0.999,
        )

    monkeypatch.setattr(tuning, "run_adaptive_trial", fake_run_adaptive_trial)

    summary = tuning.run_experiment(input_path, tmp_path / "runs", stage="combination", resume=False)

    assert summary["local_best_trial_id"] == "combination-a-alpha0p01-postadding3"
    assert summary["overall_reference_trial_id"] == "stagnation-alpha0p01"
    assert summary["overall_best"]["source"] == "external_reference"
    assert summary["overall_best"]["trial_id"] == "stagnation-alpha0p01"
    assert summary["best_trial_id"] == "stagnation-alpha0p01"


def test_residual_by_frequency_streams_exact_input_frequencies_and_finds_worst_band(tmp_path: Path):
    original = tmp_path / "original.s2p"
    exported = tmp_path / "exported.s2p"
    original.write_text(
        "# Hz S RI R 50\n"
        "1 0 0 0 0 0 0 0 0\n"
        "2 0 0 0 0 0 0 0 0\n"
        "3 0 0 0 0 0 0 0 0\n"
        "4 0 0 0 0 0 0 0 0\n",
        encoding="utf-8",
    )
    exported.write_text(
        "# Hz S RI R 50\n"
        "1 1 0 0 0 0 0 0 0\n"
        "2 3 0 0 0 0 0 0 0\n"
        "3 4 0 0 0 0 0 0 0\n"
        "4 1 0 0 0 0 0 0 0\n",
        encoding="utf-8",
    )

    evidence = tuning.compute_residual_by_frequency(original, exported, tmp_path / "residual_by_frequency.csv")

    rows = (tmp_path / "residual_by_frequency.csv").read_text(encoding="utf-8").splitlines()
    assert rows[0] == "frequency_hz,aggregate_squared_error,mean_rms,max_error"
    assert [line.split(",", 1)[0] for line in rows[1:]] == ["1", "2", "3", "4"]
    assert evidence["total_squared_error"] == pytest.approx(27.0)
    assert evidence["mean_rms"] == pytest.approx(math.sqrt(27.0 / 4.0) / 2.0)
    assert evidence["worst_contiguous_band"]["start_frequency_hz"] == pytest.approx(2.0)
    assert evidence["worst_contiguous_band"]["end_frequency_hz"] == pytest.approx(3.0)
    assert evidence["worst_contiguous_band"]["contribution_ratio"] == pytest.approx(25.0 / 27.0)
    assert evidence["eligibility"]["eligible"] is True


def test_weighting_stage_skips_idem_when_worst_band_below_half(tmp_path: Path, monkeypatch):
    input_path = tmp_path / "line.s2p"
    baseline_export = tmp_path / "baseline.s2p"
    _write_s2p(input_path)
    _write_s2p(baseline_export)

    def not_eligible(original_path, exported_path, csv_path):
        csv_path.write_text("frequency_hz,aggregate_squared_error,mean_rms,max_error\n1,1,0.5,1\n", encoding="utf-8")
        return {
            "reference": {"baseline_exported_touchstone": str(exported_path)},
            "frequency_points": 1,
            "total_squared_error": 1.0,
            "mean_rms": 0.5,
            "max_error": 1.0,
            "worst_contiguous_band": {"contribution_ratio": 0.49},
            "eligibility": {"eligible": False, "reason": "worst_band_below_50_percent"},
        }

    monkeypatch.setattr(tuning, "compute_residual_by_frequency", not_eligible)
    monkeypatch.setattr(tuning, "run_adaptive_trial", lambda *args, **kwargs: pytest.fail("ineligible must skip IdEM"))

    summary = tuning.run_weighting_experiment(
        input_path,
        tmp_path / "runs",
        baseline_exported_touchstone=baseline_export,
        resume=False,
    )

    assert summary["completed_trial_count"] == 0
    assert summary["weighting"]["eligibility"]["eligible"] is False
    assert summary["weighting"]["skip_reason"] == "weighting_not_justified"
    assert summary["weighting"]["trials_run"] == 0
    assert (tmp_path / "runs" / "weighting_not_justified").read_text(encoding="utf-8").strip()
    assert (tmp_path / "runs" / "residual_by_frequency.csv").is_file()


def test_weighting_stage_builds_two_weighted_trials_only_when_eligible(tmp_path: Path, monkeypatch):
    input_path = tmp_path / "line.s2p"
    baseline_export = tmp_path / "baseline.s2p"
    _write_s2p(input_path)
    _write_s2p(baseline_export)
    calls: list[tuple[str, tuple[tuple[float, float], ...], str]] = []

    def eligible(original_path, exported_path, csv_path):
        csv_path.write_text(
            "frequency_hz,aggregate_squared_error,mean_rms,max_error\n"
            "1,1,0.5,1\n2,9,1.5,3\n3,16,2,4\n4,1,0.5,1\n",
            encoding="utf-8",
        )
        return {
            "reference": {"baseline_exported_touchstone": str(exported_path)},
            "frequency_points": 4,
            "total_squared_error": 27.0,
            "mean_rms": 1.299,
            "max_error": 4.0,
            "rows": [
                {"frequency_hz": 1.0, "aggregate_squared_error": 1.0},
                {"frequency_hz": 2.0, "aggregate_squared_error": 9.0},
                {"frequency_hz": 3.0, "aggregate_squared_error": 16.0},
                {"frequency_hz": 4.0, "aggregate_squared_error": 1.0},
            ],
            "worst_contiguous_band": {
                "start_index": 1,
                "end_index": 2,
                "start_frequency_hz": 2.0,
                "end_frequency_hz": 3.0,
                "contribution_ratio": 25.0 / 27.0,
            },
            "eligibility": {"eligible": True, "reason": "worst_band_at_least_50_percent"},
        }

    def fake_run_adaptive_trial(entry, config, output_dir, *, resume=True, idem_bin_dir=None):
        points = config.adaptive_options.absolute_frequency_weight_points
        calls.append((config.trial_id, points, config.adaptive_options.split_type))
        return ToolTrial(
            tool="idem-adaptive",
            requested_order=config.order_max,
            effective_order=76,
            final_mean_rms=0.00095,
            elapsed_seconds=140.0,
            target_met=True,
            status="PASS",
            authoritative_passive=True,
            sampled_max_sigma=0.999,
        )

    monkeypatch.setattr(tuning, "compute_residual_by_frequency", eligible)
    monkeypatch.setattr(tuning, "run_adaptive_trial", fake_run_adaptive_trial)

    summary = tuning.run_weighting_experiment(
        input_path,
        tmp_path / "runs",
        baseline_exported_touchstone=baseline_export,
        resume=False,
    )

    assert [call[0] for call in calls] == ["weighting-baseline-strength", "weighting-stronger"]
    assert all(split_type == "none" for _, _, split_type in calls)
    assert all(2 <= len(points) <= 4 for _, points, _ in calls)
    assert all(1.0e-3 <= weight <= 1.0 for _, points, _ in calls for _, weight in points)
    assert summary["completed_trial_count"] == 2
    assert summary["weighting"]["eligibility"]["eligible"] is True
    assert summary["weighting"]["trials_run"] == 2
    assert summary["weighting"]["s19_reciprocity"]["splitting"] == "disallowed"
    assert summary["overall_reference_trial_id"] == "stagnation-alpha0p01"


def test_baseline_stage_runs_fixed_order_control_and_adaptive_baseline(tmp_path: Path, monkeypatch):
    input_path = tmp_path / "line.s2p"
    _write_s2p(input_path)
    adaptive_calls: list[str] = []
    fixed_calls: list[int] = []

    def fake_entry(path):
        return _entry(tmp_path)

    def fake_fixed(entry, order, contract, output_dir, *, resume=False, idem_bin_dir=None, tool_identity=None):
        fixed_calls.append(order)
        assert contract.max_order == 100
        assert contract.threads == 8
        assert output_dir.name == "fixed-order-order100"
        return ToolTrial(
            tool="idem",
            requested_order=order,
            effective_order=order,
            pre_mean_rms=0.014961,
            final_mean_rms=0.014961,
            target_met=False,
            status="FAIL",
            failure_reason="pre_rms_above_target",
        )

    def fake_adaptive(entry, config, output_dir, *, resume=True, idem_bin_dir=None):
        adaptive_calls.append(config.trial_id)
        return ToolTrial(
            tool="idem-adaptive",
            requested_order=config.order_max,
            effective_order=100,
            pre_mean_rms=0.002,
            final_mean_rms=0.002,
            target_met=False,
            status="FAIL",
            failure_reason="pre_rms_above_target",
        )

    monkeypatch.setattr(tuning, "_entry_from_input_path", fake_entry)
    monkeypatch.setattr(tuning, "run_fixed_order_control", fake_fixed)
    monkeypatch.setattr(tuning, "run_adaptive_trial", fake_adaptive)

    summary = tuning.run_experiment(input_path, tmp_path / "runs", stage="baseline", resume=True)

    assert fixed_calls == [100]
    assert adaptive_calls == ["baseline-adaptive"]
    assert summary["fixed_order_control"]["trial"]["pre_mean_rms"] == pytest.approx(0.014961)
    assert [row["trial_id"] for row in summary["trials"]] == ["baseline-adaptive"]
    assert (tmp_path / "runs" / "summary.csv").is_file()


def test_fixed_order_control_imports_sibling_benchmark_when_script_package_is_unavailable(
    tmp_path: Path, monkeypatch
):
    entry = _entry(tmp_path)
    calls: list[int] = []

    def fake_import_module(name: str):
        if name == "scripts.sparam_full_corpus_benchmark":
            raise ModuleNotFoundError("No module named 'scripts'", name="scripts")
        if name == "sparam_full_corpus_benchmark":
            return SimpleNamespace(
                run_idem_order_trial=lambda entry, order, contract, output_dir, **kwargs: calls.append(order)
                or ToolTrial(tool="idem", requested_order=order, status="FAIL")
            )
        raise AssertionError(name)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    trial = tuning.run_fixed_order_control(
        entry,
        100,
        tuning.IdemAdaptiveTrialConfig().benchmark_contract(),
        tmp_path / "fixed-order-order100",
        resume=True,
    )

    assert calls == [100]
    assert trial.tool == "idem"


def test_run_experiment_rejects_unsafe_trial_id_before_creating_escape_directory(tmp_path: Path, monkeypatch):
    input_path = tmp_path / "line.s2p"
    _write_s2p(input_path)
    unsafe = tuning.IdemAdaptiveTrialConfig(trial_id="../escape")
    monkeypatch.setattr(tuning, "build_stage1_trials", lambda: (unsafe,))

    with pytest.raises(ValueError, match="unsafe trial id"):
        tuning.run_experiment(input_path, tmp_path / "runs", stage="stage1")

    assert not (tmp_path / "escape").exists()


def test_summarize_trials_ranks_by_target_rms_order_time_and_keeps_json_finite():
    records = [
        {
            "trial_id": "baseline-adaptive",
            "trial": {
                "status": "PASS",
                "target_met": True,
                "pre_mean_rms": 0.01,
                "final_mean_rms": 0.001,
                "effective_order": 10,
                "elapsed_seconds": 5.0,
                "peak_memory_mb": 50.0,
            },
        },
        {
            "trial_id": "improved",
            "trial": {
                "status": "PASS",
                "target_met": True,
                "pre_mean_rms": 0.005,
                "final_mean_rms": 0.0005,
                "effective_order": 12,
                "elapsed_seconds": 8.0,
                "peak_memory_mb": 60.0,
            },
        },
        {
            "trial_id": "missing-rms",
            "trial": {
                "status": "PASS",
                "target_met": True,
                "pre_mean_rms": float("nan"),
                "final_mean_rms": float("nan"),
                "effective_order": None,
                "elapsed_seconds": None,
                "peak_memory_mb": None,
            },
        },
        {
            "trial_id": "failed-low-rms",
            "trial": {
                "status": "FAIL",
                "target_met": False,
                "pre_mean_rms": 0.002,
                "final_mean_rms": 0.0001,
                "effective_order": 1,
                "elapsed_seconds": 1.0,
                "peak_memory_mb": 1.0,
            },
        },
    ]

    summary = tuning.summarize_trials(records)

    assert summary["best_trial_id"] == "improved"
    assert [row["trial_id"] for row in summary["ranking"]] == [
        "improved",
        "baseline-adaptive",
        "missing-rms",
        "failed-low-rms",
    ]
    improved = next(row for row in summary["trials"] if row["trial_id"] == "improved")
    assert improved["delta_vs_baseline"]["pre_rms_improvement_ratio"] == pytest.approx(0.5)
    assert improved["delta_vs_baseline"]["effective_order_delta"] == 2
    assert improved["delta_vs_baseline"]["elapsed_seconds_delta"] == pytest.approx(3.0)
    assert improved["delta_vs_baseline"]["peak_memory_mb_delta"] == pytest.approx(10.0)
    missing = next(row for row in summary["trials"] if row["trial_id"] == "missing-rms")
    assert missing["trial"]["pre_mean_rms"] is None
    assert missing["sort_key"] == [False, None, None, None]
    assert json.loads(json.dumps(summary, allow_nan=False)) == summary


def test_summarize_trials_leaves_pre_rms_improvement_missing_when_baseline_denominator_is_zero():
    summary = tuning.summarize_trials(
        [
            {
                "trial_id": "baseline-adaptive",
                "trial": {"target_met": True, "pre_mean_rms": 0.0, "final_mean_rms": 0.0},
            },
            {
                "trial_id": "candidate",
                "trial": {"target_met": True, "pre_mean_rms": 0.001, "final_mean_rms": 0.0},
            },
        ]
    )

    candidate = next(row for row in summary["trials"] if row["trial_id"] == "candidate")
    assert candidate["delta_vs_baseline"]["pre_rms_improvement_ratio"] is None


def test_summarize_trials_has_no_best_without_pass_target_valid_candidate():
    summary = tuning.summarize_trials(
        [
            {
                "trial_id": "baseline-adaptive",
                "trial": {"status": "ERROR", "target_met": False, "failure_reason": "phase_stalled:fit"},
            },
            {
                "trial_id": "failed-low-rms",
                "trial": {
                    "status": "FAIL",
                    "target_met": False,
                    "final_mean_rms": 0.0001,
                    "effective_order": 1,
                    "elapsed_seconds": 1.0,
                },
            },
        ]
    )

    assert summary["best_trial_id"] is None


def test_cli_help_mentions_task4_stage_commands(capsys):
    with pytest.raises(SystemExit) as exc:
        tuning.main(["--help"])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "run-one" in out
    assert "run-stage" in out
    assert "--help-config" in out


def test_run_one_cli_executes_brief_parameterized_trial(tmp_path: Path, monkeypatch, capsys):
    entry = _entry(tmp_path)
    fake = FakePhases(tmp_path, entry, order=8, pre_rms=0.2, final_rms=0.2)
    _patch_phases(monkeypatch, fake)
    monkeypatch.setattr(tuning, "idem_tool_identity", lambda idem_bin_dir=None: "idem-test")
    monkeypatch.setattr(tuning, "benchmark_implementation_identity", lambda: "validation-test")

    exit_code = tuning.main(
        [
            "run-one",
            "--input",
            str(entry.path),
            "--output-root",
            str(tmp_path / "runs"),
            "--order-min",
            "2",
            "--order-step",
            "1",
            "--order-max",
            "8",
            "--target",
            "0.5",
            "--threads",
            "8",
            "--resume",
        ]
    )

    assert exit_code == 0
    assert fake.calls == ["fit", "pre_accuracy", "enforce", "final_accuracy", "final_check", "export", "audit"]
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["requested_order"] == 8
    assert payload["requested_order_step"] == 1
    assert payload["effective_order_step"] == 2
    assert json.loads((tmp_path / "runs" / "history.json").read_text(encoding="utf-8"))["final_order"] == 8


def test_run_stage_cli_accepts_brief_flags_threads_resume_and_single_variable_stage(
    tmp_path: Path, monkeypatch, capsys
):
    input_path = tmp_path / "line.s2p"
    _write_s2p(input_path)
    seen: dict[str, object] = {}

    def fake_run_experiment(input_arg, output_arg, *, stage, resume=True, idem_bin_dir=None):
        seen.update(
            {
                "input": Path(input_arg),
                "output": Path(output_arg),
                "stage": stage,
                "resume": resume,
            }
        )
        return {"stage": stage, "completed_trial_count": 0}

    monkeypatch.setattr(tuning, "run_experiment", fake_run_experiment)

    exit_code = tuning.main(
        [
            "run-stage",
            "--input",
            str(input_path),
            "--output-root",
            str(tmp_path / "runs"),
            "--stage",
            "single-variable",
            "--threads",
            "8",
            "--resume",
        ]
    )

    assert exit_code == 0
    assert seen == {
        "input": input_path,
        "output": tmp_path / "runs",
        "stage": "single-variable",
        "resume": True,
    }
    assert json.loads(capsys.readouterr().out)["stage"] == "single-variable"


def test_run_adaptive_trial_uses_one_canonical_runtime_contract_for_command_xml_and_reports(
    tmp_path: Path, monkeypatch
):
    entry = _entry(tmp_path)
    fake = FakePhases(tmp_path, entry)
    _patch_phases(monkeypatch, fake)
    config = tuning.IdemAdaptiveTrialConfig(order_min=2, order_step=1, order_max=8, rms_target=0.5, threads=3)
    output_dir = tmp_path / "trial"

    trial = tuning.run_adaptive_trial(entry, config, output_dir)

    assert trial.status == "PASS"
    assert trial.requested_order_step == 1
    assert trial.effective_order_step == 2
    assert fake.fit_kwargs == {
        "order_min": 2,
        "order_step": 2,
        "order_max": 8,
        "target": 0.5,
        "bandwidth_hz": 2e6,
        "threads": 3,
        "options_xml_path": output_dir / "adaptive_options.fopt.xml",
        "idle_timeout_seconds": 900.0,
    }
    fit = json.loads((output_dir / "fit.json").read_text(encoding="utf-8"))
    trial_report = json.loads((output_dir / "trial.json").read_text(encoding="utf-8"))
    assert fit["requested_order_step"] == 1
    assert fit["effective_order_step"] == 2
    assert fit["order_step"] == 2
    assert fit["warnings"] == ["odd_order_step_canonicalized_to_next_even_for_idem_runtime"]
    assert trial_report["requested_order_step"] == 1
    assert trial_report["effective_order_step"] == 2
    assert trial_report["warnings"] == ["odd_order_step_canonicalized_to_next_even_for_idem_runtime"]

    command = fit["command"]["command"]
    cli = {flag: command[command.index(flag) + 1] for flag in ["-orderMin", "-orderStep", "-orderMax", "-tol", "-bandwidth", "-nThreads"]}
    root = ET.fromstring((output_dir / "adaptive_options.fopt.xml").read_text(encoding="utf-8"))
    namespace = {"f": "OptionsFittingSchema.xsd"}
    assert root.findtext("./f:options/f:order/f:type", namespaces=namespace) == "custom"
    assert root.findtext("./f:options/f:order/f:min", namespaces=namespace) == cli["-orderMin"] == "2"
    assert root.findtext("./f:options/f:order/f:increment", namespaces=namespace) == cli["-orderStep"] == "2"
    assert root.findtext("./f:options/f:order/f:max", namespaces=namespace) == cli["-orderMax"] == "8"
    assert root.find("./f:options/f:order/f:value", namespaces=namespace) is None
    assert root.findtext("./f:options/f:errorControl/f:accuracy/f:target", namespaces=namespace) == cli["-tol"] == "0.5"
    assert root.findtext("./f:options/f:bandwidth", namespaces=namespace) == cli["-bandwidth"] == "2000000"
    assert root.findtext("./f:options/f:threads", namespaces=namespace) == cli["-nThreads"] == "3"

    fingerprint_payload = tuning.adaptive_trial_fingerprint_payload(entry, config, idem_bin_dir=None)
    assert fingerprint_payload["trial_config"]["order_step"] == 2
    assert fingerprint_payload["trial_config"]["requested_order_step"] == 1
    assert fingerprint_payload["trial_config"]["effective_order_step"] == 2


def test_run_adaptive_trial_canonicalizes_odd_order_step_to_next_even_number(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    fake = FakePhases(tmp_path, entry)
    _patch_phases(monkeypatch, fake)
    config = tuning.IdemAdaptiveTrialConfig(order_min=2, order_step=3, order_max=9, rms_target=0.5, threads=4)
    output_dir = tmp_path / "trial"

    trial = tuning.run_adaptive_trial(entry, config, output_dir)

    assert trial.status == "PASS"
    assert trial.requested_order_step == 3
    assert trial.effective_order_step == 4
    assert fake.fit_kwargs["order_step"] == 4
    assert trial.warnings == ["odd_order_step_canonicalized_to_next_even_for_idem_runtime"]
    fit = json.loads((output_dir / "fit.json").read_text(encoding="utf-8"))
    assert fit["requested_order_step"] == 3
    assert fit["effective_order_step"] == 4
    assert fit["order_step"] == 4
    assert fit["warnings"] == ["odd_order_step_canonicalized_to_next_even_for_idem_runtime"]
    command = fit["command"]["command"]
    assert command[command.index("-orderStep") + 1] == "4"
    root = ET.fromstring((output_dir / "adaptive_options.fopt.xml").read_text(encoding="utf-8"))
    namespace = {"f": "OptionsFittingSchema.xsd"}
    assert root.findtext("./f:options/f:order/f:increment", namespaces=namespace) == "4"
    fingerprint_payload = tuning.adaptive_trial_fingerprint_payload(entry, config, idem_bin_dir=None)
    assert fingerprint_payload["trial_config"]["order_step"] == 4
    assert fingerprint_payload["trial_config"]["requested_order_step"] == 3
    assert fingerprint_payload["trial_config"]["effective_order_step"] == 4


def test_run_adaptive_trial_keeps_even_order_step_unchanged_without_warning(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)
    fake = FakePhases(tmp_path, entry)
    _patch_phases(monkeypatch, fake)
    config = tuning.IdemAdaptiveTrialConfig(order_min=2, order_step=6, order_max=12, rms_target=0.5, threads=4)
    output_dir = tmp_path / "trial"

    trial = tuning.run_adaptive_trial(entry, config, output_dir)

    assert trial.status == "PASS"
    assert trial.requested_order_step == 6
    assert trial.effective_order_step == 6
    assert fake.fit_kwargs["order_step"] == 6
    assert trial.warnings == []
    fit = json.loads((output_dir / "fit.json").read_text(encoding="utf-8"))
    assert fit["requested_order_step"] == 6
    assert fit["effective_order_step"] == 6
    assert fit["order_step"] == 6
    assert fit["warnings"] == []
    command = fit["command"]["command"]
    assert command[command.index("-orderStep") + 1] == "6"
    root = ET.fromstring((output_dir / "adaptive_options.fopt.xml").read_text(encoding="utf-8"))
    namespace = {"f": "OptionsFittingSchema.xsd"}
    assert root.findtext("./f:options/f:order/f:increment", namespaces=namespace) == "6"


def test_run_adaptive_trial_records_stalled_fit_from_idle_watchdog(tmp_path: Path, monkeypatch):
    entry = _entry(tmp_path)

    def stalled_fit(*args, **kwargs):
        command_result = IdemCommandResult(
            ["idemmp_fitting.exe"],
            -9,
            "stdout before stall",
            "stderr before stall",
            901.0,
            123.0,
            telemetry={
                "idle_limit": 900.0,
                "elapsed": 901.0,
                "last_progress_age": 900.5,
                "cpu": {"process_tree_seconds": 184.0},
                "output_bytes": {"stdout": 19, "stderr": 19, "total": 38},
                "artifacts": [{"path": "fit.mod.h5", "exists": False, "size": None, "mtime": None}],
                "pid": 1234,
                "child_pids": [5678],
                "termination_reason": "idle_stall",
                "owned_pids_alive_after_kill": [],
            },
        )
        raise CommandIdleStallError(command_result)

    monkeypatch.setattr(tuning, "run_idem_adaptive_fitting", stalled_fit)
    monkeypatch.setattr(tuning, "idem_tool_identity", lambda idem_bin_dir=None: "idem-test")
    monkeypatch.setattr(tuning, "benchmark_implementation_identity", lambda: "validation-test")

    trial = tuning.run_adaptive_trial(entry, tuning.IdemAdaptiveTrialConfig(), tmp_path / "trial")

    assert trial.status == "ERROR"
    assert trial.failure_reason == "phase_stalled:fit"
    fit = json.loads((tmp_path / "trial" / "fit.json").read_text(encoding="utf-8"))
    assert fit["status"] == "stalled"
    assert fit["command"]["stdout"] == "stdout before stall"
    assert fit["telemetry"]["termination_reason"] == "idle_stall"
    assert fit["telemetry"]["pid"] == 1234
    assert json.loads(json.dumps(fit["telemetry"], allow_nan=False)) == fit["telemetry"]


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
        "runtime_contract": {
            "order_min": 4,
            "order_step": 4,
            "order_max": 12,
            "target": 0.001,
            "bandwidth_hz": 2e6,
            "threads": 3,
            "requested_order_step": 4,
            "effective_order_step": 4,
            "warnings": [],
        },
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
            idle_timeout_seconds: float | None = None,
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
            idle_timeout_seconds: float | None = None,
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


def _canonical_report_summary() -> dict:
    return {
        "sources": {
            "baseline_summary": "runs-sparam/idem-s19-adaptive-v1-pipe-drain/summary.json",
            "old_baseline_summary": "runs-sparam/idem-s19-adaptive-v1/summary.json",
            "order58_diagnostic_summary": "runs-sparam/idem-s19-order58-diagnostic/summary.json",
            "combination_summary": "runs-sparam/idem-s19-combinations-v1/summary.json",
            "weighting_summary": "runs-sparam/idem-s19-weighting-v1/summary.json",
        },
        "input": {
            "sha256": "87fccc96196d8c149d1b3ba985701dd56a78f5d9904984f55f8161c39cdd7c7e",
            "frequency_points": 826,
            "ports": 19,
            "frequency_min_hz": 0.0,
            "frequency_max_hz": 2_000_000_000.0,
        },
        "contract": {
            "contract_version": "idem_s19_adaptive_v1",
            "threads": 8,
            "order": "4:2:100",
            "target": 0.001,
            "phase_timeout_seconds": 1800.0,
            "fit_idle_timeout_seconds": 300.0,
            "splitting": "none",
        },
        "fixed_order_control": {
            "trial_id": "fixed-order-order100",
            "status": "FAIL",
            "failure_reason": "pre_rms_above_target",
            "effective_order": 100,
            "final_mean_rms": 0.01496172037,
            "elapsed_seconds": 6.061134000075981,
            "peak_memory_mb": 91.60546875,
        },
        "old_order58_observation": {
            "status": "ERROR",
            "failure_reason": "adaptive_fit_failed",
            "effective_order": None,
            "elapsed_seconds": 1301.5000721998513,
            "peak_memory_mb": 67.33984375,
        },
        "order58_diagnostic": {
            "decision": {
                "stable_reproduction": False,
                "next_phase": "stop_order58_diagnostic_original_stall_not_stably_reproduced",
            },
            "trials": [
                {
                    "trial_id": "baseline-cap56",
                    "status": "FAIL",
                    "failure_reason": "pre_rms_above_target",
                    "effective_order": 56,
                    "final_mean_rms": 0.001452594546,
                    "elapsed_seconds": 65.08048240002245,
                },
                {
                    "trial_id": "baseline-cap58",
                    "status": "FAIL",
                    "failure_reason": "pre_rms_above_target",
                    "effective_order": 58,
                    "final_mean_rms": 0.001397860094,
                    "elapsed_seconds": 70.15553370001726,
                },
                {
                    "trial_id": "baseline-cap60",
                    "status": "FAIL",
                    "failure_reason": "pre_rms_above_target",
                    "effective_order": 60,
                    "final_mean_rms": 0.001244555245,
                    "elapsed_seconds": 75.60521820001304,
                },
            ],
        },
        "single_variable": {
            "completed_trial_count": 6,
            "stop_rule": {
                "triggered": True,
                "trial_id": "stagnation-alpha0p01",
                "reason": "splitting_none_trial_met_final_contract",
            },
            "trials": [
                {
                    "trial_id": "baseline-adaptive",
                    "status": "FAIL",
                    "failure_reason": "pre_rms_above_target",
                    "effective_order": 70,
                    "final_mean_rms": 0.001025020608,
                    "elapsed_seconds": 102.36535029998049,
                    "peak_memory_mb": 75.3984375,
                },
                {
                    "trial_id": "stagnation-alpha0p01",
                    "status": "PASS",
                    "failure_reason": None,
                    "target_met": True,
                    "effective_order": 74,
                    "final_mean_rms": 0.0009369159680584244,
                    "authoritative_passive": True,
                    "sampled_max_sigma": 0.9999999944613438,
                    "elapsed_seconds": 118.46026999992318,
                    "peak_memory_mb": 88.29296875,
                    "fingerprint": "3f573f18841d9978f8f8df7304b542c3d7e35652df711df519a0ef83509b1845",
                },
            ],
        },
        "accepted_model": {
            "trial_id": "stagnation-alpha0p01",
            "effective_order": 74,
            "final_mean_rms": 0.0009369159680584244,
            "authoritative_passive": True,
            "sampled_max_sigma": 0.9999999944613438,
            "elapsed_seconds": 118.46026999992318,
            "peak_memory_mb": 88.29296875,
            "fingerprint": "3f573f18841d9978f8f8df7304b542c3d7e35652df711df519a0ef83509b1845",
        },
        "combination": {
            "local_best_trial_id": "combination-b-alpha0p01-initial5-final3",
            "best_trial_id": "combination-b-alpha0p01-initial5-final3",
            "combination_decision": {"a_improves": False, "b_improves": False, "run_c": False},
            "trials": [
                {
                    "trial_id": "combination-a-alpha0p01-postadding3",
                    "status": "FAIL",
                    "failure_reason": "final_rms_above_target",
                    "effective_order": 68,
                    "final_mean_rms": 0.001037690482,
                    "elapsed_seconds": 136.75867230002768,
                },
                {
                    "trial_id": "combination-b-alpha0p01-initial5-final3",
                    "status": "PASS",
                    "failure_reason": None,
                    "effective_order": 74,
                    "final_mean_rms": 0.0009970539140490779,
                    "elapsed_seconds": 123.74417429999448,
                    "sampled_max_sigma": 0.9999999944613451,
                },
            ],
        },
        "weighting": {
            "completed_trial_count": 0,
            "best_trial_id": "stagnation-alpha0p01",
            "best_trial_id_scope": "overall_reference_inclusive",
            "overall_best": {
                "source": "external_reference",
                "trial_id": "stagnation-alpha0p01",
                "effective_order": 74,
                "final_mean_rms": 0.0009369159680584244,
            },
            "weighting": {
                "skip_reason": "weighting_not_justified",
                "trials_run": 0,
                "eligibility": {
                    "eligible": False,
                    "reason": "worst_band_below_50_percent",
                    "threshold": 0.5,
                },
                "residual": {
                    "mean_rms": 0.0009369159680584245,
                    "frequency_points": 826,
                    "ports": 19,
                    "total_squared_error": 0.2617511092432544,
                    "worst_contiguous_band": {
                        "selection_rule": "aggregate_squared_error_gt_mean",
                        "threshold": 0.0003168899627642306,
                        "start_index": 117,
                        "end_index": 195,
                        "start_frequency_hz": 4786.30092322638,
                        "end_frequency_hz": 6309573.44480193,
                        "squared_error": 0.12485886611607,
                        "contribution_ratio": 0.4770137038847629,
                    },
                },
                "s19_reciprocity": {
                    "reciprocal": True,
                    "splitting": "disallowed",
                    "split_type": "none",
                },
            },
        },
    }


def test_render_s19_tuning_markdown_pins_canonical_conclusions_and_labels():
    text = tuning.render_s19_tuning_markdown(_canonical_report_summary())

    assert text.endswith("\n")
    assert "## Evidence Labels" in text
    assert "[FACT] Accepted model: `stagnation-alpha0p01`" in text
    assert "final independent RMS `0.0009369159680584244`" in text
    assert "authoritative passive `true`" in text
    assert "sigma `0.9999999944613438`" in text
    assert "peak `88.29296875` MiB" in text
    assert "Task 7 root-local B is not the overall best" in text
    assert "above-mean contiguous segment" in text
    assert "`47.70137038847629%` < `50%`; weighting trials were skipped" in text
    assert "old runner pipe backpressure is more likely" in text
    assert "IdEM algorithm defect" not in text
    assert "`combination-b-alpha0p01-initial5-final3`" in text
    assert "overall accepted=stagnation-alpha0p01" in text


def test_render_s19_tuning_markdown_is_byte_stable_and_renders_missing_values_as_na():
    summary = _canonical_report_summary()
    summary["accepted_model"]["sampled_max_sigma"] = None
    summary["combination"]["trials"][1]["elapsed_seconds"] = None

    first = tuning.render_s19_tuning_markdown(summary).encode("utf-8")
    second = tuning.render_s19_tuning_markdown(summary).encode("utf-8")

    assert first == second
    text = first.decode("utf-8")
    assert "sigma `N/A`" in text
    assert "| `combination-b-alpha0p01-initial5-final3` | PASS | 74 | 0.0009970539140490779 | N/A | N/A |" in text
