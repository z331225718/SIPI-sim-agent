from __future__ import annotations

import numpy as np
import pytest

from agent_spice.sparam.mft_nnls.model import evaluate
from agent_spice.sparam.mft_nnls.perturb import (
    ResiduePerturbationConfig,
    build_residue_perturbation_system,
    enforce_passivity,
)
from agent_spice.sparam.mft_nnls.types import PoleResidueModel


def _active_scalar_s_model() -> PoleResidueModel:
    return PoleResidueModel(
        poles=np.array([-1.0 + 0.0j]),
        residues=np.array([[[2.0 + 0.0j]]]),
        constant=np.array([[0.0 + 0.0j]]),
        proportional=np.array([[0.0 + 0.0j]]),
    )


def test_s_perturbation_system_uses_qr_compressed_constraints() -> None:
    model = _active_scalar_s_model()
    frequencies = np.linspace(0.0, 1.0, 41)

    system = build_residue_perturbation_system(model, frequencies, parameter_type="S")

    assert system.constraint_matrix.shape[0] == 1
    assert system.constraint_rhs.shape == (1,)
    assert system.qr_blocks
    assert system.active_column_count == 1
    assert system.constraint_rhs[0] < 0.0


def test_s_residue_perturbation_reduces_sigma_without_nonfinite_response() -> None:
    model = _active_scalar_s_model()
    frequencies = np.linspace(0.0, 1.0, 81)

    result = enforce_passivity(
        model,
        frequencies,
        ResiduePerturbationConfig(parameter_type="S", outer_iterations=4, tolerance=1.0e-8),
    )
    values = evaluate(result.model, 2j * np.pi * frequencies)

    assert result.diagnostics.details["final_assessment"].max_value <= 1.0 + 1.0e-6
    assert np.isfinite(values).all()
    assert result.rms_error < 1.0


def test_s_one_step_update_matches_matlab_rp_qrnnls_fixture() -> None:
    with np.load("tests/fixtures/mft_nnls/rp_reference.npz") as fixture:
        frequencies = fixture["s"].imag / (2.0 * np.pi)
        result = enforce_passivity(
            _active_scalar_s_model(),
            frequencies,
            ResiduePerturbationConfig(parameter_type="S", outer_iterations=1, tolerance=1.0e-8),
        )

        assert result.model.residues[0, 0, 0] == pytest.approx(fixture["s_residue"].item(), rel=1.0e-6)


def test_y_residue_perturbation_reduces_negative_real_part() -> None:
    model = PoleResidueModel(
        poles=np.array([-1.0 + 0.0j]),
        residues=np.array([[[-2.0 + 0.0j]]]),
        constant=np.array([[1.0 + 0.0j]]),
        proportional=np.array([[0.0 + 0.0j]]),
    )
    frequencies = np.linspace(0.0, 1.0, 81)

    result = enforce_passivity(
        model,
        frequencies,
        ResiduePerturbationConfig(parameter_type="Y", outer_iterations=4, tolerance=1.0e-8),
    )

    assert result.diagnostics.details["final_assessment"].min_value >= -1.0e-6


def test_two_port_s_update_matches_matlab_residue_coordinates() -> None:
    with np.load("tests/fixtures/mft_nnls/rp_reference.npz") as fixture:
        frequencies = fixture["s"].imag / (2.0 * np.pi)
        model = PoleResidueModel(
            poles=np.array([-1.0 + 0.0j]),
            residues=np.array([[[2.0], [0.0]], [[0.0], [0.5]]], dtype=complex),
            constant=np.zeros((2, 2), dtype=complex),
            proportional=np.zeros((2, 2), dtype=complex),
        )
        result = enforce_passivity(model, frequencies, ResiduePerturbationConfig(parameter_type="S", outer_iterations=1))

        assert result.model.residues[:, :, 0] == pytest.approx(fixture["s2_residues"], rel=1.0e-6)
