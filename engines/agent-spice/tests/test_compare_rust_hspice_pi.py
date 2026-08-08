from __future__ import annotations

import pytest

from scripts.compare_rust_hspice_pi import native_measurements


def test_native_measurements_reads_engine_measurement_results() -> None:
    result = {
        "measurements": [
            {"analysis": "dc", "name": "dc_load", "value": 0.8},
            {"analysis": "ac", "name": "ac_load_mag", "value": 0.63},
            {"analysis": "ac", "name": "ac_load_phase", "value": -127.8},
            {"analysis": "tran", "name": "min_vload", "value": 0.7995},
        ]
    }

    assert native_measurements(result) == {
        "dc_load": 0.8,
        "ac_load_mag": 0.63,
        "ac_load_phase": -127.8,
        "min_vload": 0.7995,
    }


def test_native_measurements_rejects_missing_engine_results() -> None:
    with pytest.raises(RuntimeError, match="missing native measurements"):
        native_measurements({"measurements": []})
