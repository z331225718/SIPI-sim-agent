import math

import numpy as np

from agent_spice.sparam.metrics import DEFAULT_FREQUENCY_BANDS, FrequencyBand, compute_banded_network_metrics


def test_compute_banded_network_metrics_uses_half_open_frequency_bands():
    frequencies = np.array([0.0, 1.0e6, 2.0e6, 200.0e6])
    original_s = np.full((4, 1, 1), 10.0 + 0.0j)
    fitted_s = original_s + np.array([1.0, 2.0, 3.0, 4.0]).reshape(4, 1, 1)
    original_z = np.ones((4, 1, 1), dtype=complex)
    fitted_z = np.array([10.0, 100.0, 1000.0, 10000.0], dtype=complex).reshape(4, 1, 1)

    metrics = compute_banded_network_metrics(
        frequencies,
        original_s,
        fitted_s,
        original_z,
        fitted_z,
        bands=[
            FrequencyBand("low", 0.0, 1.0e6),
            FrequencyBand("mid", 1.0e6, 100.0e6),
            FrequencyBand("high", 100.0e6, None),
        ],
    )

    assert metrics["bands"]["low"]["frequency_point_count"] == 1
    assert metrics["bands"]["mid"]["frequency_point_count"] == 2
    assert metrics["bands"]["high"]["frequency_point_count"] == 1
    assert metrics["bands"]["low"]["s_mean_rms_error"] == 1.0
    assert math.isclose(metrics["bands"]["mid"]["s_mean_rms_error"], math.sqrt((4.0 + 9.0) / 2.0))
    assert metrics["bands"]["high"]["s_relative_rms_error"] == 0.4
    assert metrics["bands"]["full"]["frequency_point_count"] == 4
    assert math.isclose(metrics["bands"]["full"]["diagonal_z_log_magnitude_rms_error"], math.sqrt(30.0 / 4.0))


def test_compute_banded_network_metrics_reports_empty_band_as_none():
    frequencies = np.array([2.0e6])
    original_s = np.ones((1, 1, 1), dtype=complex)
    fitted_s = original_s.copy()
    original_z = np.ones((1, 1, 1), dtype=complex)
    fitted_z = original_z.copy()

    metrics = compute_banded_network_metrics(
        frequencies,
        original_s,
        fitted_s,
        original_z,
        fitted_z,
        bands=[FrequencyBand("empty", 0.0, 1.0e6)],
    )

    empty = metrics["bands"]["empty"]
    assert empty["frequency_point_count"] == 0
    assert empty["s_mean_rms_error"] is None
    assert empty["diagonal_z_log_magnitude_rms_error"] is None


def test_default_frequency_bands_include_above_1mhz_summary():
    assert any(band.name == "above_1mhz" and band.f_min_hz == 1.0e6 for band in DEFAULT_FREQUENCY_BANDS)
