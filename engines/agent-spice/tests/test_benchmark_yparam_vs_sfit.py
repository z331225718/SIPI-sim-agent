import importlib.util
from pathlib import Path

import pytest


def _benchmark_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_yparam_vs_sfit.py"
    spec = importlib.util.spec_from_file_location("benchmark_yparam_vs_sfit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_y_win_gate_requires_a_strict_lower_z_log_rms() -> None:
    module = _benchmark_module()
    rows = [
        {"domain": "s", "complex_pairs_requested": 10, "z_status": "PASS", "heldout_z_log_magnitude_rms_error": 0.8},
        {"domain": "y", "complex_pairs_requested": 10, "z_status": "PASS", "heldout_z_log_magnitude_rms_error": 0.7},
    ]

    gate = module._y_win_gate(rows, metric="heldout")

    assert gate["passed"] is True
    assert gate["comparisons"][0]["absolute_improvement"] == pytest.approx(0.1)


def test_y_win_gate_rejects_a_tie_or_missing_metric() -> None:
    module = _benchmark_module()
    tie_rows = [
        {"domain": "s", "complex_pairs_requested": 10, "z_status": "PASS", "z_log_magnitude_rms_error": 0.7},
        {"domain": "y", "complex_pairs_requested": 10, "z_status": "PASS", "z_log_magnitude_rms_error": 0.7},
    ]

    assert module._y_win_gate(tie_rows, metric="full")["passed"] is False
