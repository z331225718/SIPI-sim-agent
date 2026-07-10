import csv
import json
from pathlib import Path

import pytest

import scripts.sparam_target_parity as parity


def report_payload(
    *,
    tool: str,
    rms: float = 0.0009,
    sigma: float = 0.99999,
    order: int = 8,
    seconds: float = 20.0,
    memory_mb: float = 400.0,
    target: float = 0.001,
    policy: str = "enforce",
    points: int = 611,
) -> dict:
    return {
        "tool": tool,
        "touchstone_path": "C:/data/Test16.s91p",
        "rms_target": target,
        "passivity_policy": policy,
        "comparison_mean_rms_error": rms,
        "passivity_max_sigma_after": sigma,
        "selected_effective_order": order,
        "elapsed_seconds": seconds,
        "peak_memory_mb": memory_mb,
        "frequency_points": points,
        "evaluation_frequency_points": points,
        "rms_formula": "mean_s_rms_v1",
        "order_formula": "real_plus_twice_complex_v1",
        "benchmark_contract_version": "sparam_target_v1",
        "target_met": True,
    }


def test_normalize_report_extracts_fixed_metrics():
    normalized = parity.normalize_report(report_payload(tool="native"), tool="native")

    assert normalized["final_rms"] == pytest.approx(0.0009)
    assert normalized["final_max_sigma"] == pytest.approx(0.99999)
    assert normalized["effective_order"] == 8
    assert normalized["elapsed_seconds"] == pytest.approx(20.0)
    assert normalized["peak_memory_mb"] == pytest.approx(400.0)


def test_compare_reports_applies_all_parity_ratios():
    ours = report_payload(tool="native", order=10, seconds=39.0, memory_mb=590.0)
    idem = report_payload(tool="idem", order=8, seconds=20.0, memory_mb=400.0)

    cell = parity.compare_reports(ours, idem)

    assert cell["valid_comparison"] is True
    assert cell["order_ratio"] == pytest.approx(1.25)
    assert cell["time_ratio"] == pytest.approx(1.95)
    assert cell["memory_ratio"] == pytest.approx(1.475)
    assert cell["overall_parity"] is True


def test_compare_reports_fails_missing_metric_instead_of_ignoring_it():
    ours = report_payload(tool="native")
    ours["peak_memory_mb"] = None

    cell = parity.compare_reports(ours, report_payload(tool="idem"))

    assert cell["memory_pass"] is False
    assert cell["overall_parity"] is False


def test_check_policy_does_not_require_passive_model():
    ours = report_payload(tool="native", policy="check", sigma=1.2)
    idem = report_payload(tool="idem", policy="check", sigma=1.3)

    cell = parity.compare_reports(ours, idem)

    assert cell["passivity_pass"] is True


def test_metadata_mismatch_invalidates_comparison():
    ours = report_payload(tool="native", points=611)
    idem = report_payload(tool="idem", points=256)

    cell = parity.compare_reports(ours, idem)

    assert cell["valid_comparison"] is False
    assert "evaluation_frequency_points" in cell["invalid_reasons"]
    assert cell["overall_parity"] is False


def test_missing_required_metadata_invalidates_comparison():
    ours = report_payload(tool="native")
    idem = report_payload(tool="idem")
    del ours["benchmark_contract_version"]
    del idem["benchmark_contract_version"]

    cell = parity.compare_reports(ours, idem)

    assert cell["valid_comparison"] is False
    assert "benchmark_contract_version_missing" in cell["invalid_reasons"]


def test_idem_must_meet_the_same_target_for_a_valid_comparison():
    idem = report_payload(tool="idem")
    idem["target_met"] = False

    cell = parity.compare_reports(report_payload(tool="native"), idem)

    assert cell["valid_comparison"] is False
    assert "idem_target_not_met" in cell["invalid_reasons"]


def test_write_summary_creates_json_and_csv(tmp_path: Path):
    native_path = tmp_path / "native.json"
    idem_path = tmp_path / "idem.json"
    output_path = tmp_path / "summary.json"
    csv_path = tmp_path / "summary.csv"
    native_path.write_text(json.dumps(report_payload(tool="native")), encoding="utf-8")
    idem_path.write_text(json.dumps(report_payload(tool="idem")), encoding="utf-8")

    summary = parity.run_parity_summary(
        [(native_path, idem_path)],
        output_path=output_path,
        csv_path=csv_path,
    )

    assert summary["overall_parity"] is True
    assert json.loads(output_path.read_text(encoding="utf-8"))["cells"][0]["overall_parity"] is True
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["corpus"] == "Test16.s91p"


def test_empty_summary_writes_header_only_csv(tmp_path: Path):
    output_path = tmp_path / "summary.json"
    csv_path = tmp_path / "summary.csv"

    summary = parity.run_parity_summary([], output_path=output_path, csv_path=csv_path)

    assert summary["overall_parity"] is False
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert "overall_parity" in reader.fieldnames
        assert list(reader) == []
