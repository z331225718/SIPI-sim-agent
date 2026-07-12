from __future__ import annotations

import numpy as np
import pytest

from agent_spice.sparam.mft_nnls.poles import initialize_poles


def test_linear_complex_poles_follow_matlab_endpoint_and_damping_rules() -> None:
    poles = initialize_poles(np.array([1.0, 10.0]), order=4, pole_type="lincmplx", damping=0.1)

    scale = 2.0 * np.pi
    assert poles == pytest.approx(np.array([-0.1 - 1.0j, -0.1 + 1.0j, -1.0 - 10.0j, -1.0 + 10.0j]) * scale)


def test_log_complex_odd_order_adds_geometric_midpoint_real_pole() -> None:
    poles = initialize_poles(np.array([1.0, 100.0]), order=3, pole_type="logcmplx", damping=0.1)

    assert poles == pytest.approx(np.array([-0.1 - 1.0j, -0.1 + 1.0j, -10.0 + 0.0j]) * (2.0 * np.pi))


def test_linlog_complex_matches_matlab_pair_count_and_uses_log_midpoint_for_odd_order() -> None:
    poles = initialize_poles(np.array([1.0, 100.0]), order=9, pole_type="linlogcmplx", damping=0.1)

    assert len(poles) == 9
    assert np.count_nonzero(np.abs(poles.imag) > 0.0) == 8
    assert poles[-1] == pytest.approx(-10.0 * 2.0 * np.pi + 0.0j)
    assert np.all(poles.real < 0.0)


def test_linlog_uses_log_complex_for_small_orders_and_ignores_dc_when_selecting_lower_bound() -> None:
    poles = initialize_poles(np.array([0.0, 1.0, 100.0]), order=3, pole_type="linlogcmplx", damping=0.1)

    assert poles == pytest.approx(np.array([-0.1 - 1.0j, -0.1 + 1.0j, -10.0 + 0.0j]) * (2.0 * np.pi))


def test_poles_reject_invalid_order_frequency_and_type() -> None:
    with pytest.raises(ValueError, match="order"):
        initialize_poles(np.array([1.0, 2.0]), order=0, pole_type="lincmplx")
    with pytest.raises(ValueError, match="positive"):
        initialize_poles(np.array([0.0, 0.0]), order=2, pole_type="lincmplx")
    with pytest.raises(ValueError, match="pole_type"):
        initialize_poles(np.array([1.0, 2.0]), order=2, pole_type="unknown")
