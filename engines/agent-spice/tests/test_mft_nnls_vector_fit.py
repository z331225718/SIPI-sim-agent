from __future__ import annotations

import numpy as np
import pytest

from agent_spice.sparam.mft_nnls.model import canonicalize_poles
from agent_spice.sparam.mft_nnls.vector_fit import RelocationOptions, fit_fixed_poles, relocate_iterations, relocate_once


def _response(freqs_hz: np.ndarray) -> np.ndarray:
    s = 2j * np.pi * freqs_hz
    values = 0.2 + 4.0 / (s + 2.0e7) + 3.0 / (s + 1.0e7 - 2j * np.pi * 4.0e6)
    values += 3.0 / (s + 1.0e7 + 2j * np.pi * 4.0e6)
    return values[:, None, None]


def test_relaxed_relocation_returns_stable_common_poles_and_diagnostics() -> None:
    freqs = np.geomspace(1.0e5, 1.0e7, 21)
    initial = np.array([-2.0e6 - 2j * np.pi * 3.0e6, -2.0e6 + 2j * np.pi * 3.0e6])

    result = relocate_once(freqs, _response(freqs), initial, options=RelocationOptions(relaxed=True))

    assert len(result.poles) == len(initial)
    assert np.all(result.poles.real <= 0.0)
    assert result.diagnostics["relaxed"] is True
    assert result.diagnostics["rank"] > 0
    assert result.diagnostics["sigma_constant"] != 0.0


def test_standard_relocation_returns_stable_common_poles() -> None:
    freqs = np.geomspace(1.0e5, 1.0e7, 21)
    initial = np.array([-2.0e6 - 2j * np.pi * 3.0e6, -2.0e6 + 2j * np.pi * 3.0e6])

    result = relocate_once(freqs, _response(freqs), initial, options=RelocationOptions(relaxed=False))

    assert len(result.poles) == len(initial)
    assert np.all(result.poles.real <= 0.0)
    assert result.diagnostics["relaxed"] is False


@pytest.mark.parametrize("asymptotic_order", [1, 3])
def test_relocation_supports_no_constant_and_proportional_asymptotes(asymptotic_order: int) -> None:
    freqs = np.geomspace(1.0e5, 1.0e7, 21)
    initial = np.array([-2.0e6 - 2j * np.pi * 3.0e6, -2.0e6 + 2j * np.pi * 3.0e6])

    result = relocate_once(
        freqs,
        _response(freqs),
        initial,
        options=RelocationOptions(asymptotic_order=asymptotic_order),
    )

    assert len(result.poles) == len(initial)
    assert np.all(result.poles.real <= 0.0)


def test_relocation_canonical_comparison_is_independent_of_conjugate_order() -> None:
    freqs = np.geomspace(1.0e5, 1.0e7, 21)
    upper_first = np.array([-2.0e6 + 2j * np.pi * 3.0e6, -2.0e6 - 2j * np.pi * 3.0e6])
    lower_first = upper_first[::-1]

    upper_result = relocate_once(freqs, _response(freqs), upper_first)
    lower_result = relocate_once(freqs, _response(freqs), lower_first)

    assert canonicalize_poles(upper_result.poles) == pytest.approx(canonicalize_poles(lower_result.poles))


def test_relocation_iterations_record_stable_deterministic_trajectory() -> None:
    freqs = np.geomspace(1.0e5, 1.0e7, 21)
    initial = np.array([-2.0e6 - 2j * np.pi * 3.0e6, -2.0e6 + 2j * np.pi * 3.0e6])

    first = relocate_iterations(freqs, _response(freqs), initial, iterations=3)
    second = relocate_iterations(freqs, _response(freqs), initial, iterations=3)

    assert first.poles == pytest.approx(second.poles)
    assert np.all(first.poles.real <= 0.0)
    assert 1 <= len(first.diagnostics["trajectory"]) <= 3
    record = first.diagnostics["trajectory"][0]
    assert {"iteration", "pole_frequencies_hz", "pole_real_parts", "condition_number", "input_sigma_residue_magnitudes"} <= record.keys()
    assert len(record["pole_frequencies_hz"]) == len(initial)
    assert len(record["input_sigma_residue_magnitudes"]) == len(initial)


def test_relocation_iterations_stop_when_delta_is_within_configured_tolerance() -> None:
    freqs = np.geomspace(1.0e5, 1.0e7, 21)
    initial = np.array([-2.0e6 - 2j * np.pi * 3.0e6, -2.0e6 + 2j * np.pi * 3.0e6])

    result = relocate_iterations(freqs, _response(freqs), initial, iterations=3, convergence_rtol=2.0)

    assert result.diagnostics["converged"] is True
    assert result.diagnostics["iterations"] == 1


def test_relocation_rejects_unpaired_complex_initial_poles() -> None:
    freqs = np.geomspace(1.0e5, 1.0e7, 21)

    with pytest.raises(ValueError, match="conjugate"):
        relocate_once(freqs, _response(freqs), np.array([-1.0e6 + 2j * np.pi * 3.0e6]))


def test_medium_order_matlab_fixture_matches_relocated_response() -> None:
    with np.load("tests/fixtures/mft_nnls/ex4_s_small.npz") as fixture:
        result = relocate_once(
            fixture["medium_frequencies_hz"],
            fixture["medium_response"],
            fixture["medium_initial_poles"],
        )
        fitted = fit_fixed_poles(
            fixture["medium_frequencies_hz"],
            fixture["medium_response"],
            result.poles,
        )

        assert fixture["medium_rms"].item() < 0.01
        assert canonicalize_poles(result.poles) == pytest.approx(
            canonicalize_poles(fixture["medium_relocated_poles"]),
            rel=1.0e-8,
            abs=2.0 * np.pi * 1.0e-3,
        )
        assert fitted == pytest.approx(fixture["medium_fitted_response"], rel=1.0e-7, abs=1.0e-10)


@pytest.mark.parametrize("order", [4, 6])
def test_relaxed_relocation_matches_matlab_vectfit4_fixture(order: int) -> None:
    with np.load("tests/fixtures/mft_nnls/ex4_s_small.npz") as fixture:
        assert fixture["fixture_kind"].item() == "matlab_vfdriver_reference"
        frequencies_hz = fixture["s"].imag / (2.0 * np.pi)
        result = relocate_once(frequencies_hz, fixture["response"], fixture[f"relocation_initial_poles_{order}"])

        assert canonicalize_poles(result.poles) == pytest.approx(
            canonicalize_poles(fixture[f"relocation_poles_{order}"]),
            rel=1.0e-8,
            abs=2.0 * np.pi * 1.0e-3,
        )


@pytest.mark.xfail(strict=True, reason="raw ex4 one-step fit is not a response-quality gate")
@pytest.mark.parametrize("order", [5, 7, 9, 13])
def test_raw_ex4_ill_conditioned_pole_diagnostics_remain_visible(order: int) -> None:
    test_relaxed_relocation_matches_matlab_vectfit4_fixture(order)


def test_raw_ex4_one_step_fixtures_are_not_response_quality_gates() -> None:
    with np.load("tests/fixtures/mft_nnls/ex4_s_small.npz") as fixture:
        rms = np.array([fixture[f"relocation_rms_{order}"].item() for order in (4, 5, 6, 7, 9, 13)])

    assert np.all(rms > 0.01)
