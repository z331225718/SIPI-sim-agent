from __future__ import annotations

import numpy as np
import pytest

from agent_spice.sparam.mft_nnls.weights import build_weights


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (1, np.ones((2, 2, 2))),
        (2, np.array([[[1.0, 0.5], [0.25, 0.125]], [[0.5, 0.25], [0.125, 0.0625]]])),
        (3, np.array([[[1.0, 1 / np.sqrt(2)], [0.5, 1 / np.sqrt(8)]], [[1 / np.sqrt(2), 0.5], [1 / np.sqrt(8), 0.25]]])),
    ],
)
def test_individual_mft_weight_modes_follow_response_magnitude(mode: int, expected: np.ndarray) -> None:
    response = np.array([[[1.0, 2.0], [4.0, 8.0]], [[2.0, 4.0], [8.0, 16.0]]], dtype=complex)

    weights = build_weights(response, mode)

    assert weights == pytest.approx(expected)


@pytest.mark.parametrize("mode", [4, 5])
def test_common_mft_weight_modes_use_lower_triangle_vector_norm(mode: int) -> None:
    response = np.array([[[3.0, 99.0], [4.0, 12.0]], [[6.0, 99.0], [8.0, 24.0]]], dtype=complex)

    weights = build_weights(response, mode)

    norms = np.array([np.linalg.norm([3.0, 4.0, 12.0]), np.linalg.norm([6.0, 8.0, 24.0])])
    expected = 1.0 / (norms if mode == 4 else np.sqrt(norms))
    assert weights == pytest.approx(np.broadcast_to(expected[:, None, None], response.shape))


def test_weights_floor_zero_magnitudes_and_accept_explicit_weights() -> None:
    response = np.zeros((2, 1, 1), dtype=complex)
    explicit = np.array([[[2.0]], [[3.0]]])

    automatic = build_weights(response, 2)
    supplied = build_weights(response, 1, explicit=explicit)

    assert np.isfinite(automatic).all()
    assert automatic[0, 0, 0] == pytest.approx(1.0 / np.finfo(float).eps)
    assert supplied == pytest.approx(explicit)


def test_weights_reject_invalid_mode_and_explicit_shape() -> None:
    response = np.ones((2, 1, 1), dtype=complex)

    with pytest.raises(ValueError, match="mode"):
        build_weights(response, 6)
    with pytest.raises(ValueError, match="explicit"):
        build_weights(response, 1, explicit=np.ones((1, 1, 1)))
