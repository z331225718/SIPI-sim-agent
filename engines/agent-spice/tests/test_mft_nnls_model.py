from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from agent_spice.sparam.mft_nnls.model import (
    canonicalize_poles,
    evaluate,
    reconstruct_symmetric_residues,
    stabilize_poles,
)
from agent_spice.sparam.mft_nnls.types import MFTConfig, MFTDiagnostics, MFTResult, PoleResidueModel


def test_model_rejects_residue_shape_that_does_not_match_poles() -> None:
    with pytest.raises(ValueError, match="residues shape"):
        PoleResidueModel(
            poles=np.array([-1.0 + 0.0j, -2.0 + 0.0j]),
            residues=np.zeros((1, 1, 1), dtype=complex),
            constant=np.zeros((1, 1), dtype=complex),
            proportional=np.zeros((1, 1), dtype=complex),
        )


def test_stabilize_poles_reflects_unstable_real_parts() -> None:
    stabilized = stabilize_poles(np.array([2.0 + 3.0j, -1.0 + 4.0j, 0.0 + 0.0j]))

    assert stabilized == pytest.approx(np.array([-2.0 + 3.0j, -1.0 + 4.0j, -0.0 + 0.0j]))
    assert np.all(stabilized.real <= 0.0)


def test_canonicalize_poles_orders_real_poles_then_conjugate_pairs() -> None:
    canonical = canonicalize_poles(np.array([2.0 - 3.0j, -4.0 + 0.0j, 2.0 + 3.0j, -1.0 + 0.0j]))

    assert canonical == pytest.approx(np.array([-4.0 + 0.0j, -1.0 + 0.0j, -2.0 + 3.0j, -2.0 - 3.0j]))


def test_canonicalize_poles_rejects_an_unpaired_lower_half_plane_pole() -> None:
    with pytest.raises(ValueError, match="unpaired lower-half-plane pole"):
        canonicalize_poles(np.array([-2.0 - 3.0j]))


def test_reconstruct_symmetric_residues_averages_port_axes() -> None:
    residues = np.array([[[1.0], [3.0]], [[5.0], [7.0]]], dtype=complex)

    symmetric = reconstruct_symmetric_residues(residues)

    assert symmetric[:, :, 0] == pytest.approx(np.array([[1.0, 4.0], [4.0, 7.0]]))


def test_evaluate_uses_pole_residue_constant_and_proportional_terms() -> None:
    model = PoleResidueModel(
        poles=np.array([-2.0 + 0.0j]),
        residues=np.array([[[6.0 + 0.0j]]]),
        constant=np.array([[1.0 + 0.0j]]),
        proportional=np.array([[0.5 + 0.0j]]),
    )

    values = evaluate(model, np.array([0.0 + 0.0j, 2.0j]))

    assert values[:, 0, 0] == pytest.approx([4.0 + 0.0j, 2.5 - 0.5j])


def test_result_and_fixture_contract_are_immutable() -> None:
    model = PoleResidueModel(
        poles=np.array([-1.0 + 0.0j]),
        residues=np.ones((1, 1, 1), dtype=complex),
        constant=np.zeros((1, 1), dtype=complex),
        proportional=np.zeros((1, 1), dtype=complex),
    )
    result = MFTResult(model=model, diagnostics=MFTDiagnostics(stage="model"), rms_error=0.0)

    with pytest.raises(AttributeError):
        result.rms_error = 1.0  # type: ignore[misc]
    assert MFTConfig().parameter_type == "S"
    assert Path("tests/fixtures/mft_nnls/ex4_s_small.npz").is_file()
