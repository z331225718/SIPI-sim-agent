from __future__ import annotations

from scripts.sparam_mft_s19_gate_b import classify_gate_b


def test_gate_b_classifies_fit_failure_before_passivity() -> None:
    report = classify_gate_b(rms_error=1.1e-3, max_sigma=0.9, stable=True)

    assert report["status"] == "FIT_FAILURE"


def test_gate_b_requires_full_grid_passivity_and_stability() -> None:
    assert classify_gate_b(rms_error=1.0e-3, max_sigma=1.0 + 1.0e-6, stable=True)["status"] == "PASS"
    assert classify_gate_b(rms_error=1.0e-3, max_sigma=1.0 + 2.0e-6, stable=True)["status"] == "PASSIVITY_FAILURE"
    assert classify_gate_b(rms_error=1.0e-3, max_sigma=1.0, stable=False)["status"] == "COLLAPSE_DIAGNOSIS"
