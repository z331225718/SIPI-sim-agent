from __future__ import annotations

from pathlib import Path

import pytest

from scripts.compare_rust_hspice_measure_events import (
    hspice_measurements,
    native_measurements,
)


def test_event_gate_reads_native_and_hspice_measurements(tmp_path: Path) -> None:
    native = {
        "measurements": [
            {"name": "when_rise", "value": 2.5e-9},
            {"name": "when_fall", "value": 1.5e-9},
            {"name": "when_cross", "value": 3.5e-9},
            {"name": "when_last", "value": 3.5e-9},
            {"name": "when_td", "value": 2.5e-9},
            {"name": "sampled", "value": 2.5},
            {"name": "delay", "value": 1.5e-9},
            {"name": "delay_at", "value": 1.0e-9},
            {"name": "param_norm", "value": 1.0},
            {"name": "param_chain", "value": 3.5},
            {"name": "param_func", "value": 2.5},
            {"name": "param_si", "value": 3.0},
            {"name": "deriv_at", "value": 1.0e9},
            {"name": "deriv_when", "value": 1.0e9},
            {"name": "integ_target", "value": 4.0e-9},
            {"name": "integ_signal", "value": 2.0e-9},
        ]
    }
    listing = tmp_path / "hspice.lis"
    listing.write_text(
        "when_rise=2.5n\nwhen_fall=1.5n\nwhen_cross=3.5n\n"
        "when_last=3.5n\nwhen_td=2.5n\nsampled=2.5\ndelay=1.5n\n"
        "delay_at=1n\nparam_norm=1\nparam_chain=3.5\n"
        "param_func=2.5\nparam_si=3\nderiv_at=1000x\nderiv_when=1g\n"
        "integ_target=4n\ninteg_signal=2n\n",
        encoding="utf-8",
    )

    assert native_measurements(native) == pytest.approx(hspice_measurements(listing))
