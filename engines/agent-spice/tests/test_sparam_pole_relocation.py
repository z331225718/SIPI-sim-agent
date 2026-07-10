import numpy as np

from agent_spice.sparam.pole_relocation import (
    streaming_pole_relocation,
    streaming_reciprocal_pole_relocation,
)


def _sample_relocation_inputs():
    freqs = np.array([1.0e6, 2.0e6, 5.0e6, 9.0e6], dtype=float)
    poles = np.array([-1.0e7 + 0.0j, -2.0e7 + 3.0e7j], dtype=complex)
    responses = np.array(
        [
            [0.1 + 0.01j, 0.2 + 0.03j, 0.3 + 0.02j, 0.4 + 0.04j],
            [0.5 - 0.02j, 0.45 - 0.03j, 0.35 - 0.01j, 0.25 - 0.02j],
        ],
        dtype=complex,
    )
    weights = np.linalg.norm(responses, axis=1)
    return poles, freqs, responses, weights


def test_streaming_pole_relocation_matches_saved_skrf_reference():
    poles, freqs, responses, weights = _sample_relocation_inputs()

    actual = streaming_pole_relocation(
        poles,
        freqs,
        responses,
        weights,
        True,
        False,
    )

    expected = (
        np.array([-42527137.94517688, -3747626.09717429, -40702259.76764055]),
        np.float64(-3.868654854772534),
        np.float64(94.3151781398695),
        np.int64(0),
        np.array([0.03965238]),
        np.array([1.9977542, 0.0832964, 0.03988982, 0.02118168]),
    )
    for actual_value, expected_value in zip(actual, expected):
        np.testing.assert_allclose(actual_value, expected_value, rtol=1e-8, atol=1e-8)


def test_streaming_pole_relocation_can_return_c_res_diagnostics():
    poles, freqs, responses, weights = _sample_relocation_inputs()

    result = streaming_pole_relocation(
        poles,
        freqs,
        responses,
        weights,
        True,
        False,
        return_diagnostics=True,
    )

    assert len(result) == 7
    diagnostics = result[-1]
    np.testing.assert_allclose(diagnostics["input_poles"], poles)
    assert diagnostics["c_res"].shape == (3,)
    assert diagnostics["c_res_by_pole"].shape == poles.shape
    assert np.all(diagnostics["c_res_by_pole"] >= 0.0)
    assert isinstance(diagnostics["d_res"], complex)


def test_streaming_pole_relocation_accepts_out_of_band_c_res_regularization():
    freqs = np.array([1.0e6, 2.0e6, 5.0e6, 9.0e6], dtype=float)
    poles = np.array([-1.0e7 + 0.0j, -2.0e7 + 2j * np.pi * 20.0e6], dtype=complex)
    responses = np.array(
        [
            [0.1 + 0.01j, 0.2 + 0.03j, 0.3 + 0.02j, 0.4 + 0.04j],
            [0.5 - 0.02j, 0.45 - 0.03j, 0.35 - 0.01j, 0.25 - 0.02j],
        ],
        dtype=complex,
    )
    weights = np.linalg.norm(responses, axis=1)

    result = streaming_pole_relocation(
        poles,
        freqs,
        responses,
        weights,
        True,
        False,
        return_diagnostics=True,
        out_of_band_pole_regularization_weight=0.1,
        out_of_band_pole_regularization_start_fraction=1.0,
    )

    assert len(result) == 7
    assert result[-1]["c_res_by_pole"][1] >= 0.0


def test_streaming_pole_relocation_avoids_stacked_real_imag_temp(monkeypatch):
    poles, freqs, responses, weights = _sample_relocation_inputs()

    def fail_vstack(*args, **kwargs):
        raise AssertionError("streaming relocation should reuse a real work buffer instead of vstack")

    monkeypatch.setattr(np, "vstack", fail_vstack)

    streaming_pole_relocation(
        poles,
        freqs,
        responses,
        weights,
        True,
        False,
    )


def test_streaming_reciprocal_pole_relocation_matches_symmetric_full_matrix():
    freqs = np.array([1.0e6, 2.0e6, 5.0e6, 9.0e6], dtype=float)
    poles = np.array([-1.0e7 + 0.0j, -2.0e7 + 3.0e7j], dtype=complex)
    s11 = np.array([0.1 + 0.01j, 0.2 + 0.03j, 0.3 + 0.02j, 0.4 + 0.04j])
    s12 = np.array([0.5 - 0.02j, 0.45 - 0.03j, 0.35 - 0.01j, 0.25 - 0.02j])
    s22 = np.array([0.05 + 0.02j, 0.07 + 0.01j, 0.09 - 0.02j, 0.11 - 0.03j])
    responses = np.array([s11, s12, s12, s22], dtype=complex)
    weights = np.linalg.norm(responses, axis=1)

    actual = streaming_reciprocal_pole_relocation(
        poles,
        freqs,
        responses,
        weights,
        True,
        False,
    )
    expected = streaming_pole_relocation(
        poles,
        freqs,
        responses,
        weights,
        True,
        False,
    )

    for actual_value, expected_value in zip(actual, expected):
        np.testing.assert_allclose(actual_value, expected_value, rtol=1e-10, atol=1e-10)
