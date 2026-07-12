from types import SimpleNamespace

import numpy as np
import pytest

from agent_spice.sparam.artifacts import (
    evaluate_fitted_s,
    rank_element_rms,
    write_fitted_touchstone,
)


class _SmallVectorFit:
    """Small native-vector-fit shaped model with one real and one complex pole."""

    def __init__(self) -> None:
        self.network = SimpleNamespace(nports=2)
        self.poles = np.array([-2.0 + 0.0j, -3.0 + 4.0j])
        self.residues = np.array(
            [
                [1.0 + 0.0j, 0.20 + 0.30j],
                [0.5 + 0.0j, 0.10 - 0.20j],
                [0.4 + 0.0j, 0.05 + 0.10j],
                [0.8 + 0.0j, 0.30 - 0.10j],
            ]
        )
        self.constant_coeff = np.array([0.1, 0.2, 0.3, 0.4], dtype=complex)
        self.proportional_coeff = np.zeros(4, dtype=complex)


def test_evaluate_fitted_s_returns_native_matrix_values() -> None:
    model = _SmallVectorFit()
    frequencies_hz = np.array([0.0, 1.0])

    fitted = evaluate_fitted_s(model, frequencies_hz)

    assert fitted.shape == (2, 2, 2)
    s = 2j * np.pi * frequencies_hz
    pole = model.poles[1]
    expected_s11 = (
        model.constant_coeff[0]
        + model.residues[0, 0] / (s - model.poles[0])
        + model.residues[0, 1] / (s - pole)
        + np.conj(model.residues[0, 1]) / (s - np.conj(pole))
    )
    np.testing.assert_allclose(fitted[:, 0, 0], expected_s11)
    assert np.any(np.abs(fitted[:, 1, 0]) > 0.0)


def test_write_fitted_touchstone_round_trips_frequencies_values_and_z0(tmp_path) -> None:
    import skrf as rf

    model = _SmallVectorFit()
    frequencies_hz = np.array([1.0e6, 2.0e6, 3.0e6])
    fitted = evaluate_fitted_s(model, frequencies_hz)
    output = tmp_path / "fitted.s2p"
    z0 = np.array([75.0, 60.0])

    written = write_fitted_touchstone(output, frequencies_hz, fitted, z0)
    reread = rf.Network(str(written))

    assert written == output
    np.testing.assert_allclose(reread.f, frequencies_hz)
    np.testing.assert_allclose(reread.s, fitted)
    np.testing.assert_allclose(reread.z0, np.broadcast_to(z0, (len(frequencies_hz), 2)))


def test_rank_element_rms_is_descending_with_stable_row_column_ties() -> None:
    original = np.zeros((2, 2, 2), dtype=complex)
    fitted = np.zeros_like(original)
    fitted[:, 0, 0] = 2.0
    fitted[:, 0, 1] = 1.0
    fitted[:, 1, 0] = 1.0

    ranked = rank_element_rms(original, fitted)

    assert [(item.row, item.column, item.rms) for item in ranked] == [
        (0, 0, pytest.approx(2.0)),
        (0, 1, pytest.approx(1.0)),
        (1, 0, pytest.approx(1.0)),
        (1, 1, pytest.approx(0.0)),
    ]


@pytest.mark.parametrize("nonfinite", [np.nan + 0j, np.inf + 0j])
def test_rank_element_rms_rejects_nonfinite_s_data(nonfinite: complex) -> None:
    original = np.zeros((1, 1, 1), dtype=complex)
    fitted = np.zeros_like(original)
    fitted[0, 0, 0] = nonfinite

    with pytest.raises(ValueError, match="finite"):
        rank_element_rms(original, fitted)
