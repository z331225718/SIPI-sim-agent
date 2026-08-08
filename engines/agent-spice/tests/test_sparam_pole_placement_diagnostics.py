import numpy as np

import scripts.sparam_pole_placement_diagnostics as diag


def test_describe_poles_reports_frequency_and_damping():
    poles = np.array([-2.0, -3.0 + 4.0j, -5.0 + 12.0j])

    rows = diag.describe_poles(poles)

    assert rows[0]["kind"] == "real"
    assert rows[0]["frequency_hz"] == 0.0
    assert rows[1]["kind"] == "complex"
    assert rows[1]["frequency_hz"] == diag._hz_from_rad_per_s(4.0)
    assert rows[1]["damping_ratio"] == 3.0 / 4.0
    assert rows[2]["frequency_hz"] > rows[1]["frequency_hz"]


def test_compare_pole_distributions_includes_real_pole_distances():
    idem_rows = diag.describe_poles(np.array([-2.0 * np.pi * 1.0e6, -2.0 * np.pi * 10.0e6 + 1j * 2.0 * np.pi * 1.0e9]))
    native_rows = diag.describe_poles(np.array([-2.0 * np.pi * 2.0e6, -2.0 * np.pi * 20.0e6 + 1j * 2.0 * np.pi * 1.2e9]))

    comparison = diag.compare_pole_distributions(idem_rows, native_rows)

    assert comparison["idem_real_frequencies_hz"] == [1.0e6]
    assert comparison["native_real_frequencies_hz"] == [2.0e6]
    assert comparison["native_real_to_idem_real"]["distances_hz"] == [1.0e6]
    assert comparison["native_complex_to_idem_complex"]["distances_hz"] == [2.0e8]


def test_band_counts_reports_complex_pairs_in_target_bands():
    rows = [
        {"kind": "real", "frequency_hz": 0.0},
        {"kind": "complex", "frequency_hz": 1.37e9},
        {"kind": "complex", "frequency_hz": 1.95e9},
        {"kind": "complex", "frequency_hz": 2.20e9},
    ]

    counts = diag._band_counts(rows, [(1.3e9, 1.45e9), (1.8e9, 2.0e9)])

    assert counts == [
        {"lo_hz": 1.3e9, "hi_hz": 1.45e9, "complex_pair_count": 1},
        {"lo_hz": 1.8e9, "hi_hz": 2.0e9, "complex_pair_count": 1},
    ]
