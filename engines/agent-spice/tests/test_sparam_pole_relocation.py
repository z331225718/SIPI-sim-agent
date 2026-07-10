import numpy as np

from agent_spice.sparam.pole_relocation import (
    _legacy_low_memory_pole_relocation,
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
    # provenance=9faf1e3: generated from the pre-migration relocation module
    # before relocation migration, using streaming_pole_relocation on this sample.
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
        np.array([-42527137.94517688, -3747626.097174291, -40702259.767640546]),
        np.float64(-3.868654854772534),
        np.float64(94.3151781398695),
        np.int64(0),
        np.array([0.03965238167868129]),
        np.array([1.997754201109218, 0.08329640133845319, 0.03988982052818989, 0.02118168295400499]),
    )
    for actual_value, expected_value in zip(actual, expected):
        np.testing.assert_allclose(actual_value, expected_value, rtol=1e-10, atol=1e-10)


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
    # provenance=9faf1e3: generated from the pre-migration relocation module
    # before relocation migration, using streaming_pole_relocation with
    # out_of_band_pole_regularization_weight=0.1 and return_diagnostics=True.
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
    expected = (
        np.array([-11164040.829069769 + 0.0j, -20000000.0 + 1.2566370614359172e8j]),
        np.float64(1.9230852268185354),
        np.float64(16.762446294151715),
        np.int64(0),
        np.array([0.02333767419830265]),
        np.array([1.4117036829567522, 1.0000000000000002, 0.9999999999999963, 0.08421823749253625]),
    )
    for actual_value, expected_value in zip(result[:-1], expected):
        np.testing.assert_allclose(actual_value, expected_value, rtol=1e-10, atol=1e-10)
    expected_diagnostics = {
        "input_poles": np.array([-10000000.0 + 0.0j, -20000000.0 + 1.2566370614359173e8j]),
        "c_res": np.array([2.2385497217976642e6 + 0.0j, -3.4643640767866193e-10 + 0.0j, -3.3437856079824499e-10 + 0.0j]),
        "c_res_by_pole": np.array([2.238549721797664e6, 4.814843782375516e-10]),
        "d_res": 1.9230852268185354 + 0.0j,
    }
    for key, expected_value in expected_diagnostics.items():
        np.testing.assert_allclose(result[-1][key], expected_value, rtol=1e-10, atol=1e-10)


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


def test_legacy_low_memory_relocation_avoids_large_temp_and_matches_default(monkeypatch):
    poles, freqs, responses, weights = _sample_relocation_inputs()
    expected = streaming_pole_relocation(
        poles,
        freqs,
        responses,
        weights,
        True,
        False,
    )
    original_empty = np.empty

    def fail_vstack(*args, **kwargs):
        raise AssertionError("legacy low-memory relocation should reuse a real work buffer instead of vstack")

    def guarded_empty(shape, *args, **kwargs):
        if shape == (9, 4):
            raise AssertionError("legacy low-memory relocation should not allocate response-scaled A_fast")
        return original_empty(shape, *args, **kwargs)

    monkeypatch.setattr(np, "vstack", fail_vstack)
    monkeypatch.setattr(np, "empty", guarded_empty)

    actual = _legacy_low_memory_pole_relocation(
        poles,
        freqs,
        responses,
        weights,
        True,
        False,
    )

    for actual_value, expected_value in zip(actual, expected):
        np.testing.assert_allclose(actual_value, expected_value, rtol=1e-10, atol=1e-10)


def test_streaming_reciprocal_pole_relocation_matches_symmetric_full_matrix():
    # provenance=9faf1e3: generated from the pre-migration relocation module
    # before relocation migration, using streaming_reciprocal_pole_relocation.
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
    expected_baseline = (
        np.array([-41962068.29691965, -5251884.398602006, -43865124.44478916]),
        np.float64(-7.519914690596802),
        np.float64(65.54638929046135),
        np.int64(0),
        np.array([0.18841066895997569]),
        np.array([1.9951496199975773, 0.12172560997213663, 0.06028559278663163, 0.03043874180706277]),
    )

    for actual_value, expected_value in zip(actual, expected):
        np.testing.assert_allclose(actual_value, expected_value, rtol=1e-10, atol=1e-10)
    for actual_value, expected_value in zip(actual, expected_baseline):
        np.testing.assert_allclose(actual_value, expected_value, rtol=1e-10, atol=1e-10)
