from __future__ import annotations

import numpy as np
import pytest

from agent_spice.sparam.mft_nnls.model import canonicalize_poles
from agent_spice.sparam.mft_nnls.vector_fit import RelocationOptions, relocate_once


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


def test_relocation_canonical_comparison_is_independent_of_conjugate_order() -> None:
    freqs = np.geomspace(1.0e5, 1.0e7, 21)
    upper_first = np.array([-2.0e6 + 2j * np.pi * 3.0e6, -2.0e6 - 2j * np.pi * 3.0e6])
    lower_first = upper_first[::-1]

    upper_result = relocate_once(freqs, _response(freqs), upper_first)
    lower_result = relocate_once(freqs, _response(freqs), lower_first)

    assert canonicalize_poles(upper_result.poles) == pytest.approx(canonicalize_poles(lower_result.poles))


def test_relocation_rejects_unpaired_complex_initial_poles() -> None:
    freqs = np.geomspace(1.0e5, 1.0e7, 21)

    with pytest.raises(ValueError, match="conjugate"):
        relocate_once(freqs, _response(freqs), np.array([-1.0e6 + 2j * np.pi * 3.0e6]))
