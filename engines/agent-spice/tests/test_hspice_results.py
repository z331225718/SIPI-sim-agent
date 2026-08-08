from pathlib import Path

from agent_spice.hspice.results import parse_ngspice_measurements, write_ngspice_waveform_csv


def test_parse_ngspice_measurements_keeps_value_and_optional_time():
    stdout = """
  Measurements for Transient Analysis

min_vdd             =  7.99574e-01 at=  5.00000e-09
peak_current        = -1.25e+00
"""

    assert parse_ngspice_measurements(stdout) == [
        {"name": "min_vdd", "value": 0.799574, "at": 5e-09},
        {"name": "peak_current", "value": -1.25},
    ]


def test_write_ngspice_waveform_csv_combines_paginated_print_table(tmp_path: Path):
    stdout = """
Index time v(load)
------------------
0 0.0 0.8
1 1e-9 0.79
Index time v(load)
------------------
2 2e-9 0.78
"""

    path = tmp_path / "waveform.csv"

    assert write_ngspice_waveform_csv(stdout, path) == 3
    assert path.read_text(encoding="utf-8") == "time,v(load)\n0.0,0.8\n1e-09,0.79\n2e-09,0.78\n"
