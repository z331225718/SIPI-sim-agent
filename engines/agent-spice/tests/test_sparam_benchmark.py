import hashlib
import json
import math
from pathlib import Path

import pytest

from agent_spice.sparam.benchmark import (
    BenchmarkContract,
    ToolTrial,
    atomic_write_json,
    benchmark_fingerprint,
    discover_touchstone_corpus,
    load_benchmark_cases,
    run_order_sweep,
    run_benchmark_order_search,
    run_sparam_benchmarks,
    write_benchmark_reports,
)


def _write_s2p(path: Path, *, scale: float = 1.0) -> None:
    path.write_text(
        "# Hz S RI R 50\n"
        f"1e6 0 0 {scale} 0 {scale} 0 0 0\n"
        f"2e6 0 0 {scale} 0 {scale} 0 0 0\n",
        encoding="utf-8",
    )


def _trial(order: int, *, target_met: bool) -> ToolTrial:
    return ToolTrial(
        tool="native",
        requested_order=order,
        effective_order=order,
        pre_mean_rms=0.0008 if target_met else 0.002,
        final_mean_rms=0.0009 if target_met else 0.002,
        authoritative_passive=target_met,
        final_max_sigma=0.999 if target_met else 1.01,
        sampled_max_sigma=0.999 if target_met else 1.01,
        fit_seconds=1.0,
        check_seconds=0.2,
        enforce_seconds=0.3,
        validation_seconds=0.1,
        elapsed_seconds=1.6,
        peak_memory_mb=10.0,
        target_met=target_met,
        status="PASS" if target_met else "FAIL",
        failure_reason=None if target_met else "final_rms_above_target",
        fingerprint=f"trial-{order}",
    )


def _write_manifest(path: Path, touchstone: str) -> None:
    path.write_text(
        "\n".join(
            [
                "base_dir: .",
                "cases:",
                "  - id: local_2port",
                f"    touchstone: {touchstone}",
                "    description: Local two-port smoke",
                "    tags:",
                "      - smoke",
                "    fit:",
                "      mode: manual",
                "      n_poles_real: 1",
                "      n_poles_cmplx: 0",
                "      enforce_passivity: false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


class FakeQualityReport:
    status = "WARN"
    allowed_for = "report_only"
    blocking_reasons: list[str] = []
    warnings = ["passivity_enforcement"]

    def to_dict(self):
        return {
            "profile": "explore",
            "status": self.status,
            "allowed_for": self.allowed_for,
            "blocking_reasons": self.blocking_reasons,
            "warnings": self.warnings,
            "diagnostics": [],
        }


class FakeFitResult:
    quality_report = FakeQualityReport()
    fit_frequency_points = 2
    fit_frequency_range_hz = [1e6, 2e6]
    comparison_frequency_points = 2
    quality_frequency_points = 2
    rms_error = 0.01
    comparison_rms_error = 0.02
    z_comparison_rms_error = 0.03
    z_log_magnitude_rms_error = 0.04


def test_discover_touchstone_corpus_is_strict_and_deterministic(tmp_path: Path):
    _write_s2p(tmp_path / "zeta.s2p")
    upper = tmp_path / "alpha.S19P"
    upper.write_text("# Hz S RI R 50\n1e6 " + "0 0 " * (19 * 19) + "\n", encoding="utf-8")
    (tmp_path / "PowerModel.sp").write_text("* spice\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not touchstone\n", encoding="utf-8")

    entries = discover_touchstone_corpus(tmp_path)

    assert [(entry.ports, entry.path.name) for entry in entries] == [
        (2, "zeta.s2p"),
        (19, "alpha.S19P"),
    ]
    assert entries[0].frequency_points == 2
    assert entries[0].frequency_min_hz == pytest.approx(1e6)
    assert entries[0].frequency_max_hz == pytest.approx(2e6)
    assert entries[0].sha256 == hashlib.sha256((tmp_path / "zeta.s2p").read_bytes()).hexdigest()
    assert all(entry.path.suffix.lower() != ".sp" for entry in entries)


def test_shared_scheduler_uses_even_ladder_then_odd_backfill():
    outcomes = {4: False, 6: False, 8: True, 7: True}
    calls = []

    def evaluate(order: int) -> ToolTrial:
        calls.append(order)
        return _trial(order, target_met=outcomes[order])

    result = run_benchmark_order_search(BenchmarkContract(max_order=10), evaluate)

    assert calls == [4, 6, 8, 7]
    assert result.selected_order == 7
    assert result.attempted_orders == (4, 6, 8, 7)


def test_shared_scheduler_exhausts_at_100_without_duplicate_trials():
    calls = []

    def evaluate(order: int) -> ToolTrial:
        calls.append(order)
        return _trial(order, target_met=False)

    result = run_benchmark_order_search(BenchmarkContract(max_order=100), evaluate)

    assert result.selected_trial is None
    assert result.attempted_orders == tuple(range(4, 101, 2))
    assert len(calls) == len(set(calls))


def test_atomic_json_and_fingerprint_are_deterministic(tmp_path: Path):
    output = tmp_path / "nested" / "result.json"
    atomic_write_json(output, {"b": 2, "a": 1})

    assert json.loads(output.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
    assert not list(output.parent.glob("*.tmp"))

    base = benchmark_fingerprint(
        input_sha256="abc",
        contract=BenchmarkContract(),
        tool="idem",
        tool_identity="IdEM 2026.02",
        order=8,
        options={"initial_iterations": 3},
    )
    same = benchmark_fingerprint(
        input_sha256="abc",
        contract=BenchmarkContract(),
        tool="idem",
        tool_identity="IdEM 2026.02",
        order=8,
        options={"initial_iterations": 3},
    )
    changed = benchmark_fingerprint(
        input_sha256="abc",
        contract=BenchmarkContract(threads=4),
        tool="idem",
        tool_identity="IdEM 2026.02",
        order=8,
        options={"initial_iterations": 3},
    )

    assert base == same
    assert base != changed


def test_trial_serialization_converts_non_finite_metrics_to_null():
    trial = _trial(8, target_met=False)
    trial.final_mean_rms = math.inf
    trial.final_max_sigma = math.nan

    payload = trial.to_dict()

    assert payload["final_mean_rms"] is None
    assert payload["final_max_sigma"] is None


def test_load_benchmark_cases_resolves_paths_and_fit_config(tmp_path: Path):
    _write_s2p(tmp_path / "line.s2p")
    manifest = tmp_path / "cases.yaml"
    _write_manifest(manifest, "line.s2p")

    cases = load_benchmark_cases(manifest)

    assert len(cases) == 1
    assert cases[0].id == "local_2port"
    assert cases[0].touchstone_path == (tmp_path / "line.s2p").resolve()
    assert cases[0].fit_config.mode == "manual"
    assert cases[0].fit_config.enforce_passivity is False


def test_run_sparam_benchmarks_metadata_only_records_metrics(tmp_path: Path):
    _write_s2p(tmp_path / "line.s2p")
    manifest = tmp_path / "cases.yaml"
    _write_manifest(manifest, "line.s2p")

    results = run_sparam_benchmarks(manifest, tmp_path / "runs")

    assert results[0]["status"] == "completed"
    assert results[0]["mode"] == "metadata"
    assert results[0]["ports"] == 2
    assert results[0]["frequency_points"] == 2
    assert results[0]["file_size_bytes"] > 0
    assert results[0]["elapsed_seconds"] >= 0
    assert results[0]["peak_memory_mb"] >= 0


def test_run_sparam_benchmarks_skips_missing_private_case(tmp_path: Path):
    manifest = tmp_path / "cases.yaml"
    _write_manifest(manifest, "missing.s2p")

    results = run_sparam_benchmarks(manifest, tmp_path / "runs")

    assert results[0]["status"] == "skipped"
    assert results[0]["reason"] == "touchstone file not found"


def test_run_sparam_benchmarks_run_fit_records_artifacts_and_quality(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.benchmark as benchmark

    _write_s2p(tmp_path / "line.s2p")
    manifest = tmp_path / "cases.yaml"
    _write_manifest(manifest, "line.s2p")
    calls = []

    def fake_fit(
        touchstone_path,
        output_path,
        config=None,
        report_path=None,
        html_report_path=None,
        log_path=None,
    ):
        calls.append((touchstone_path, output_path, config, report_path, html_report_path, log_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(".subckt preview 1 2\n.ends preview\n", encoding="utf-8")
        report_path.write_text("{}\n", encoding="utf-8")
        html_report_path.write_text("<html></html>\n", encoding="utf-8")
        log_path.write_text("ok\n", encoding="utf-8")
        return FakeFitResult()

    monkeypatch.setattr(benchmark, "fit_touchstone_to_spice", fake_fit)

    results = run_sparam_benchmarks(manifest, tmp_path / "runs", run_fit=True)

    assert results[0]["status"] == "completed"
    assert results[0]["mode"] == "fit"
    assert results[0]["quality_status"] == "WARN"
    assert results[0]["allowed_for"] == "report_only"
    assert results[0]["warnings"] == ["passivity_enforcement"]
    assert results[0]["fit_frequency_points"] == 2
    assert results[0]["comparison_frequency_points"] == 2
    assert results[0]["quality_frequency_points"] == 2
    assert results[0]["rms_error"] == 0.01
    assert results[0]["comparison_rms_error"] == 0.02
    assert results[0]["z_comparison_rms_error"] == 0.03
    assert results[0]["z_log_magnitude_rms_error"] == 0.04
    assert results[0]["spice_size_bytes"] > 0
    assert calls[0][2].mode == "manual"


def test_run_order_sweep_records_each_order(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.benchmark as benchmark

    _write_s2p(tmp_path / "line.s2p")
    manifest = tmp_path / "cases.yaml"
    _write_manifest(manifest, "line.s2p")
    case = load_benchmark_cases(manifest)[0]
    calls = []

    def fake_fit(
        touchstone_path,
        output_path,
        config=None,
        report_path=None,
        html_report_path=None,
        log_path=None,
    ):
        calls.append((touchstone_path, output_path, config, report_path, html_report_path, log_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(".subckt preview 1 2\n.ends preview\n", encoding="utf-8")
        report_path.write_text("{}\n", encoding="utf-8")
        html_report_path.write_text("<html></html>\n", encoding="utf-8")
        log_path.write_text("ok\n", encoding="utf-8")
        return FakeFitResult()

    monkeypatch.setattr(benchmark, "fit_touchstone_to_spice", fake_fit)

    results = run_order_sweep(case, tmp_path / "runs", [20, 40])

    assert [result["case_id"] for result in results] == [
        "local_2port/order20",
        "local_2port/order40",
    ]
    assert [result["base_case_id"] for result in results] == ["local_2port", "local_2port"]
    assert [result["sweep_model_order_max"] for result in results] == [20, 40]
    assert [call[2].model_order_max for call in calls] == [20, 40]
    assert calls[0][1].parent != calls[1][1].parent
    assert results[0]["z_comparison_rms_error"] == 0.03
    assert results[0]["z_log_magnitude_rms_error"] == 0.04


def test_write_benchmark_reports_writes_jsonl_and_csv(tmp_path: Path):
    results = [
        {
            "case_id": "local_2port",
            "status": "completed",
            "mode": "metadata",
            "touchstone_path": "line.s2p",
            "ports": 2,
            "frequency_points": 2,
            "z_log_magnitude_rms_error": 0.04,
            "blocking_reasons": [],
            "warnings": ["dc_coverage"],
        }
    ]
    jsonl_path = tmp_path / "benchmark.jsonl"
    csv_path = tmp_path / "benchmark.csv"

    write_benchmark_reports(results, jsonl_path, csv_path)

    assert json.loads(jsonl_path.read_text(encoding="utf-8"))["case_id"] == "local_2port"
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "case_id,status,mode" in csv_text
    assert "dc_coverage" in csv_text
    assert "z_log_magnitude_rms_error" in csv_text
