import math

import numpy as np
import pytest

from agent_spice.sparam.z_metrics import invert_y_strict, strict_z_log_magnitude_rms_error, z_log_metric_summary


def test_strict_log_z_metric_does_not_drop_nonfinite_samples() -> None:
    reference = np.ones((2, 1, 1), dtype=complex)
    fitted = reference.copy()
    fitted[1, 0, 0] = np.nan

    assert math.isinf(strict_z_log_magnitude_rms_error(reference, fitted))


def test_z_metric_summary_uses_none_for_empty_offdiagonal_set() -> None:
    values = np.ones((2, 1, 1), dtype=complex)

    assert z_log_metric_summary(values, values) == {
        "z_log_magnitude_rms_error": 0.0,
        "diagonal_z_log_magnitude_rms_error": 0.0,
        "offdiagonal_z_log_magnitude_rms_error": None,
    }


def test_invert_y_strict_can_report_high_but_finite_input_conditioning() -> None:
    y = np.array([[[1.0, 0.0], [0.0, 1e-14]]], dtype=complex)
    inverted, conditions = invert_y_strict(y)

    np.testing.assert_allclose(inverted, np.linalg.inv(y))
    assert conditions[0] == pytest.approx(1e14)
    with pytest.raises(ValueError, match="condition limit"):
        invert_y_strict(y, condition_limit=1e12)
