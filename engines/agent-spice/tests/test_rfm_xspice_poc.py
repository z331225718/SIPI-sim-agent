from pathlib import Path

import numpy as np

from agent_spice.sparam.rfm import RfmModel
from scripts.rfm_xspice_scaling_poc import _deck, expand_block_diagonal


def _two_port_model() -> RfmModel:
    return RfmModel(
        version=200600,
        nports=2,
        matrix_type="S",
        z0=50.0,
        poles=np.array([-2.0 + 0.0j, -3.0 + 4.0j]),
        residues=np.array(
            [
                [0.01 + 0.0j, 0.002 + 0.003j],
                [0.20 + 0.0j, 0.010 - 0.020j],
                [0.20 + 0.0j, 0.010 - 0.020j],
                [0.01 + 0.0j, 0.002 + 0.003j],
            ]
        ),
        constant_coeff=np.array([0.01, 0.1, 0.1, 0.01], dtype=complex),
        source_path=Path("source.rfm"),
    )


def test_wave_schur_complement_matches_standard_s_to_y_conversion() -> None:
    model = _two_port_model()
    scattering = model.evaluate_s([0.0, 1.0, 10.0])
    identity = np.eye(model.nports)

    for sample in scattering:
        standard = (identity - sample) @ np.linalg.inv(identity + sample) / model.z0
        xspice_stamp = (2.0 * np.linalg.inv(identity + sample) - identity) / model.z0
        np.testing.assert_allclose(xspice_stamp, standard, rtol=1e-13, atol=1e-15)


def test_scaling_model_is_exact_block_diagonal_repetition() -> None:
    source = _two_port_model()
    expanded = expand_block_diagonal(source, 8)
    source_response = source.evaluate_s([1.0])[0]
    expanded_response = expanded.evaluate_s([1.0])[0]

    for block in range(4):
        offset = 2 * block
        np.testing.assert_allclose(
            expanded_response[offset : offset + 2, offset : offset + 2],
            source_response,
        )
    np.testing.assert_allclose(expanded_response[:2, 2:], 0.0)
    assert expanded.effective_order == source.effective_order


def test_direct_deck_uses_one_dynamic_gd_vector_and_rfm_file() -> None:
    model = expand_block_diagonal(_two_port_model(), 8)
    text = _deck(model, Path("model.rfm"), direct=True)

    assert "Arfm %gd[p1 0 p2 0 p3 0 p4 0 p5 0 p6 0 p7 0 p8 0] rfm_model" in text
    assert 'nport_rfm(rfm_file="' in text
    assert ".include" not in text
