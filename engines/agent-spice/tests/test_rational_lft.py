from types import SimpleNamespace

import numpy as np
import pytest

from agent_spice.sparam.artifacts import evaluate_fitted_s, evaluate_fitted_y
from agent_spice.sparam.rational_lft import exact_y_to_s_descriptor_rational, exact_y_to_s_rational
from agent_spice.sparam.y_pr import enforce_y_positive_real_kyp


def _one_port_y_model(*, proportional: complex = 0j) -> SimpleNamespace:
    return SimpleNamespace(
        network=SimpleNamespace(nports=1),
        poles=np.array([-2.0e8 + 0j]),
        residues=np.array([[3.0e6 + 0j]]),
        constant_coeff=np.array([0.02 + 0j]),
        proportional_coeff=np.array([proportional]),
    )


def test_exact_y_to_s_rational_matches_bilinear_evaluation() -> None:
    y_model = _one_port_y_model()
    s_model = exact_y_to_s_rational(y_model, 50.0)
    frequencies = np.array([0.0, 1.0e6, 50.0e6, 500.0e6])
    y = evaluate_fitted_y(y_model, frequencies)
    expected = (1.0 - 50.0 * y) / (1.0 + 50.0 * y)
    np.testing.assert_allclose(evaluate_fitted_s(s_model, frequencies), expected, rtol=1e-10, atol=1e-10)
    assert np.all(s_model.poles.real < 0.0)
    assert np.all(s_model.proportional_coeff == 0.0)


def test_exact_y_to_s_rational_rejects_proportional_y() -> None:
    with pytest.raises(ValueError, match="proper Y model"):
        exact_y_to_s_rational(_one_port_y_model(proportional=1e-9), 50.0)


def test_exact_descriptor_y_to_s_preserves_capacitive_proportional_term() -> None:
    y_model = SimpleNamespace(
        network=SimpleNamespace(nports=1),
        poles=np.array([], dtype=complex),
        residues=np.empty((1, 0), dtype=complex),
        constant_coeff=np.array([0.02 + 0j]),
        proportional_coeff=np.array([1.0e-9 + 0j]),
    )
    s_model = exact_y_to_s_descriptor_rational(y_model, 50.0)
    frequencies = np.array([0.0, 1.0e6, 100.0e6, 2.0e9])
    y = evaluate_fitted_y(y_model, frequencies)
    expected = (1.0 - 50.0 * y) / (1.0 + 50.0 * y)
    np.testing.assert_allclose(evaluate_fitted_s(s_model, frequencies), expected, rtol=1e-10, atol=1e-10)


def test_kyp_enforcement_corrects_negative_conductance() -> None:
    model = _one_port_y_model()
    model.constant_coeff = np.array([-0.02 + 0j])
    model.residues = np.array([[0.0 + 0j]])

    enforced, certificate = enforce_y_positive_real_kyp(model, max_states=8)

    assert certificate.kyp_max_eigenvalue <= 1e-7
    assert certificate.p_min_eigenvalue >= -1e-7
    assert enforced.constant_coeff[0] >= -1e-7


def test_kyp_enforcement_preserves_positive_capacitive_term() -> None:
    model = _one_port_y_model(proportional=1e-9)

    enforced, certificate = enforce_y_positive_real_kyp(model, max_states=8)

    assert certificate.kyp_max_eigenvalue <= 1e-7
    np.testing.assert_allclose(enforced.proportional_coeff, model.proportional_coeff)
