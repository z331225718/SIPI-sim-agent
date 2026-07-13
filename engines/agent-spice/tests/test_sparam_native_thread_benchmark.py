import hashlib
import json
from pathlib import Path

import pytest

import scripts.sparam_native_thread_benchmark as benchmark


def _write_report(path: Path, *, order: int = 9, quality: str = "PASS") -> None:
    path.write_text(
        json.dumps(
            {
                "quality": {"overall_status": quality},
                "expanded_model_order": order,
                "fit_seconds": 4.0,
                "check_seconds": 1.0,
                "enforce_seconds": 2.0,
                "elapsed_seconds": 8.0,
                "peak_memory_mb": 30.0,
            }
        ),
        encoding="utf-8",
    )


def test_build_child_environment_preserves_parent_and_sets_exact_thread_budget():
    environment = benchmark.build_child_environment(64, {"PATH": "x", "OMP_NUM_THREADS": "old"})

    assert environment["PATH"] == "x"
    assert {environment[name] for name in benchmark.BLAS_THREAD_ENVIRONMENT} == {"64"}


def test_collect_trial_rejects_quality_or_order_drift_from_single_thread_reference(tmp_path: Path, monkeypatch):
    source = tmp_path / "case.s2p"
    source.write_text("test", encoding="utf-8")
    case = benchmark.ThreadBenchmarkCase("case", source, 2, 0.001)
    process = {"status": "completed", "returncode": 0, "elapsed_seconds": 9.0, "peak_memory_mb": 40.0}
    report_order = {"value": 9}
    def fake_child(command, **kwargs):
        report_path = Path(command[command.index("--report") + 1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        _write_report(report_path, order=report_order["value"])
        return process
    monkeypatch.setattr(benchmark, "run_monitored_child", fake_child)

    reference = benchmark.collect_trial(case, 1, tmp_path / "one", python_executable="python")
    assert reference["quality_status"] == "PASS"
    assert reference["input_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()

    report_order["value"] = 10
    with pytest.raises(benchmark.QualityDriftError, match="effective order"):
        benchmark.collect_trial(case, 8, tmp_path / "eight", python_executable="python", reference=reference)


def test_render_markdown_uses_machine_summary_only():
    summary = {
        "cases": [{"name": "Test3", "trials": [
            {"threads": 1, "status": "ok", "elapsed_seconds": 100.0, "fit_seconds": 80.0,
             "check_seconds": 10.0, "enforce_seconds": 5.0, "peak_memory_mb": 100.0, "cpu_utilization_percent": 90.0},
            {"threads": 64, "status": "ok", "elapsed_seconds": 25.0, "fit_seconds": 15.0,
             "check_seconds": 5.0, "enforce_seconds": 2.0, "peak_memory_mb": 120.0, "cpu_utilization_percent": 4000.0},
        ]}],
    }

    rendered = benchmark.render_markdown(summary)

    assert "Test3" in rendered
    assert "4.00x" in rendered
    assert "4000.0" in rendered
