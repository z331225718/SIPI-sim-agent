"""QR-compressed residue perturbation using Gustavsen's homogeneous NNLS step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import qr, solve_triangular

from agent_spice.sparam.mft_nnls.model import evaluate
from agent_spice.sparam.mft_nnls.nnls import solve_homogeneous_nnls
from agent_spice.sparam.mft_nnls.passivity import PassivityAssessment, assess_s_passivity, assess_y_passivity, select_violation_extrema
from agent_spice.sparam.mft_nnls.types import MFTDiagnostics, MFTResult, PoleResidueModel
from agent_spice.sparam.mft_nnls.vector_fit import _basis, _complex_pair_index, _matlab_lower_triangle_indices


@dataclass(frozen=True)
class ResiduePerturbationConfig:
    parameter_type: Literal["S", "Y"] = "S"
    outer_iterations: int = 10
    tolerance: float = 1.0e-8
    passivity_tolerance: float = 1.0e-6
    alpha: float = 1.0
    local_violations: bool = True
    weight_mode: int = 1

    def __post_init__(self) -> None:
        if self.parameter_type not in {"S", "Y"}:
            raise ValueError("parameter_type must be 'S' or 'Y'")
        if self.outer_iterations < 1:
            raise ValueError("outer_iterations must be positive")
        if not np.isfinite(self.tolerance) or self.tolerance <= 0.0:
            raise ValueError("tolerance must be finite and positive")
        if not np.isfinite(self.passivity_tolerance) or self.passivity_tolerance <= 0.0:
            raise ValueError("passivity_tolerance must be finite and positive")
        if not np.isfinite(self.alpha) or self.alpha <= 0.0:
            raise ValueError("alpha must be finite and positive")
        if self.weight_mode != 1:
            raise ValueError("weight_mode must be 1; other RPdriver weighting modes are not implemented")


@dataclass(frozen=True)
class PerturbationSystem:
    constraint_matrix: NDArray[np.float64]
    constraint_rhs: NDArray[np.float64]
    qr_blocks: tuple[NDArray[np.float64], ...]
    column_scales: tuple[NDArray[np.float64], ...]
    pair_index: NDArray[np.int_]
    lower_rows: NDArray[np.int_]
    lower_columns: NDArray[np.int_]
    active_column_count: int


def _assessment(model: PoleResidueModel, frequencies_hz: NDArray[np.float64], parameter_type: str) -> PassivityAssessment:
    f_max = float(np.max(frequencies_hz))
    return assess_s_passivity(model, f_max=f_max) if parameter_type == "S" else assess_y_passivity(model, f_max=f_max)


def _metric_excess(value: float, parameter_type: str) -> float:
    return value - 1.0 if parameter_type == "S" else -value


def build_residue_perturbation_system(
    model: PoleResidueModel,
    frequencies_hz: NDArray[np.float64],
    *,
    parameter_type: Literal["S", "Y"],
    local_violations: bool = True,
    passivity_tolerance: float = 1.0e-6,
    alpha: float = 1.0,
) -> PerturbationSystem:
    """Build ``B R^-1`` constraints for residue-only RP-NNLS perturbation."""

    frequencies = np.asarray(frequencies_hz, dtype=float).reshape(-1)
    if len(frequencies) < 2 or not np.isfinite(frequencies).all() or np.any(frequencies < 0.0):
        raise ValueError("frequencies_hz must contain finite non-negative samples")
    local_columns = len(model.poles)
    basis, pair_index = _basis(2j * np.pi * frequencies, model.poles, 1)
    rows, columns = _matlab_lower_triangle_indices(model.ports)
    qr_blocks: list[NDArray[np.float64]] = []
    column_scales: list[NDArray[np.float64]] = []
    for row, column in zip(rows, columns, strict=True):
        design = np.concatenate((basis[:, :local_columns].real, basis[:, :local_columns].imag), axis=0)
        qr_scale = np.linalg.norm(design, axis=0)
        if row != column:
            # MATLAB packs symmetric off-diagonal responses with sqrt(2)
            # in the QR objective while their passivity derivative is doubled.
            scale = np.sqrt(2.0) * qr_scale
        else:
            scale = qr_scale
        if np.any(qr_scale == 0.0):
            raise ValueError("residue LS column scale is zero")
        _, r = qr(design / qr_scale, mode="economic", pivoting=False, check_finite=False)
        if np.linalg.matrix_rank(r) < local_columns:
            raise ValueError("residue QR block is rank deficient")
        qr_blocks.append(r)
        column_scales.append(scale)
    assessment = _assessment(model, frequencies, parameter_type)
    extrema = select_violation_extrema(model, assessment, local=local_violations)
    gradients = np.zeros((len(extrema), len(rows) * local_columns), dtype=float)
    rhs = np.zeros(len(extrema), dtype=float)
    for index, extremum in enumerate(extrema):
        s = 2j * np.pi * extremum.frequency_hz
        local_basis, _ = _basis(np.asarray([s]), model.poles, 1)
        for element, (row, column) in enumerate(zip(rows, columns, strict=True)):
            for pole_column in range(local_columns):
                derivative = np.zeros((model.ports, model.ports), dtype=complex)
                derivative[row, column] = local_basis[0, pole_column]
                derivative[column, row] = local_basis[0, pole_column]
                if parameter_type == "S":
                    assert extremum.right_vector is not None
                    sensitivity = float(np.real(np.vdot(extremum.left_vector, derivative @ extremum.right_vector)))
                else:
                    sensitivity = float(np.real(np.vdot(extremum.left_vector, derivative @ extremum.left_vector)))
                gradients[index, element * local_columns + pole_column] = sensitivity
        if parameter_type == "S":
            rhs[index] = -(passivity_tolerance + alpha * max(extremum.value - 1.0, 0.0))
        else:
            # MATLAB RP_QRNNLS_Y: c=-TOLG+alpha*lambda_min.
            rhs[index] = -passivity_tolerance + alpha * extremum.value
    transformed = np.zeros_like(gradients)
    for element, block in enumerate(qr_blocks):
        start = element * local_columns
        stop = start + local_columns
        scaled_gradient = gradients[:, start:stop] / column_scales[element]
        transformed[:, start:stop] = solve_triangular(block.T, scaled_gradient.T, lower=True).T
    constraint_matrix = -transformed if parameter_type == "S" else transformed
    return PerturbationSystem(
        constraint_matrix=constraint_matrix,
        constraint_rhs=rhs,
        qr_blocks=tuple(qr_blocks),
        column_scales=tuple(column_scales),
        pair_index=pair_index,
        lower_rows=rows,
        lower_columns=columns,
        active_column_count=int(np.count_nonzero(np.any(np.abs(transformed) > 0.0, axis=0))),
    )


def _recover_delta(system: PerturbationSystem, xbar: NDArray[np.float64]) -> NDArray[np.float64]:
    local_columns = len(system.pair_index)
    delta = np.empty_like(xbar)
    for element, block in enumerate(system.qr_blocks):
        start = element * local_columns
        stop = start + local_columns
        delta[start:stop] = solve_triangular(block, xbar[start:stop], lower=False) / system.column_scales[element]
    return delta


def _apply_residue_delta(model: PoleResidueModel, system: PerturbationSystem, delta: NDArray[np.float64]) -> PoleResidueModel:
    residues = np.array(model.residues, copy=True)
    local_columns = len(system.pair_index)
    for element, (row, column) in enumerate(zip(system.lower_rows, system.lower_columns, strict=True)):
        values = delta[element * local_columns : (element + 1) * local_columns]
        for pole_column, kind in enumerate(system.pair_index):
            if kind == 0:
                residues[row, column, pole_column] += values[pole_column]
                if row != column:
                    residues[column, row, pole_column] += values[pole_column]
            elif kind == 1:
                change = values[pole_column] + 1j * values[pole_column + 1]
                residues[row, column, pole_column] += change
                if row != column:
                    residues[column, row, pole_column] += change
                residues[row, column, pole_column + 1] += change.conjugate()
                if row != column:
                    residues[column, row, pole_column + 1] += change.conjugate()
    return PoleResidueModel(model.poles, residues, model.constant, model.proportional)


def enforce_passivity(
    model: PoleResidueModel,
    frequencies_hz: NDArray[np.float64],
    config: ResiduePerturbationConfig,
) -> MFTResult:
    """Run bounded outer RP-NNLS iterations with non-regression rollback."""

    frequencies = np.asarray(frequencies_hz, dtype=float).reshape(-1)
    reference = evaluate(model, 2j * np.pi * frequencies)
    current = model
    history: list[dict[str, float | int | bool]] = []
    assessment = _assessment(current, frequencies, config.parameter_type)
    for iteration in range(config.outer_iterations):
        excess = _metric_excess(assessment.worst_value, config.parameter_type)
        if excess <= 1.0e-6:
            break
        system = build_residue_perturbation_system(
            current,
            frequencies,
            parameter_type=config.parameter_type,
            local_violations=config.local_violations,
            passivity_tolerance=config.passivity_tolerance,
            alpha=config.alpha,
        )
        if not len(system.constraint_rhs):
            break
        solution = solve_homogeneous_nnls(system.constraint_matrix, system.constraint_rhs, tolerance=config.tolerance)
        delta = _recover_delta(system, solution.x)
        candidate = _apply_residue_delta(current, system, delta)
        candidate_assessment = _assessment(candidate, frequencies, config.parameter_type)
        candidate_excess = _metric_excess(candidate_assessment.worst_value, config.parameter_type)
        accepted = bool(np.isfinite(candidate_excess) and candidate_excess < excess)
        history.append(
            {
                "iteration": iteration + 1,
                "constraint_count": int(len(system.constraint_rhs)),
                "kkt_stationarity_inf_norm": solution.kkt_stationarity_inf_norm,
                "excess_before": excess,
                "excess_after": candidate_excess,
                "accepted": accepted,
            }
        )
        if not accepted:
            break
        current = candidate
        assessment = candidate_assessment
    response = evaluate(current, 2j * np.pi * frequencies)
    rms = float(np.sqrt(np.mean(np.abs(response - reference) ** 2)))
    return MFTResult(
        current,
        MFTDiagnostics("passivity_enforcement", iterations=len(history), details={"history": history, "final_assessment": assessment}),
        rms,
    )
