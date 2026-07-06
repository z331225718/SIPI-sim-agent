import json
from pathlib import Path

from agent_spice.sparam.benchmark import (
    load_benchmark_cases,
    run_order_sweep,
    run_sparam_benchmarks,
    write_benchmark_reports,
)


def _write_s2p(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Hz S RI R 50",
                "1e6 0 0 1 0 1 0 0 0",
                "2e6 0 0 1 0 1 0 0 0",
            ]
        )
        + "\n",
        encoding="utf-8",
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

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
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

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        calls.append((touchstone_path, output_path, config, report_path, html_report_path, log_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(".subckt preview 1 2\n.ends preview\n", encoding="utf-8")
        report_path.write_text("{}\n", encoding="utf-8")
        html_report_path.write_text("<html></html>\n", encoding="utf-8")
        log_path.write_text("ok\n", encoding="utf-8")
        return FakeFitResult()

    monkeypatch.setattr(benchmark, "fit_touchstone_to_spice", fake_fit)

    results = run_order_sweep(case, tmp_path / "runs", [20, 40])

    assert [result["case_id"] for result in results] == ["local_2port/order20", "local_2port/order40"]
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
