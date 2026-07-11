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
    inner_iterations: int = 1
    tolerance: float = 1.0e-8
    passivity_tolerance: float = 1.0e-6
    alpha: float = 1.0
    local_violations: bool = True
    weight_mode: int = 1
    pole_indices: tuple[int, ...] | None = None
    bandwidth: int | None = None
    auxiliary_weight_factor: float = 1.0e-3
    proportional_tolerance: float = 1.0e-12

    def __post_init__(self) -> None:
        if self.parameter_type not in {"S", "Y"}:
            raise ValueError("parameter_type must be 'S' or 'Y'")
        if self.outer_iterations < 1:
            raise ValueError("outer_iterations must be positive")
        if self.inner_iterations < 1:
            raise ValueError("inner_iterations must be positive")
        if not np.isfinite(self.tolerance) or self.tolerance <= 0.0:
            raise ValueError("tolerance must be finite and positive")
        if not np.isfinite(self.passivity_tolerance) or self.passivity_tolerance <= 0.0:
            raise ValueError("passivity_tolerance must be finite and positive")
        if not np.isfinite(self.alpha) or self.alpha <= 0.0:
            raise ValueError("alpha must be finite and positive")
        if self.weight_mode != 1:
            raise ValueError("weight_mode must be 1; other RPdriver weighting modes are not implemented")
        if self.pole_indices is not None and (not self.pole_indices or any(index < 0 for index in self.pole_indices)):
            raise ValueError("pole_indices must be a non-empty tuple of non-negative indices")
        if self.bandwidth is not None and self.bandwidth < 0:
            raise ValueError("bandwidth must be non-negative")
        if not np.isfinite(self.auxiliary_weight_factor) or self.auxiliary_weight_factor <= 0.0:
            raise ValueError("auxiliary_weight_factor must be finite and positive")
        if not np.isfinite(self.proportional_tolerance) or self.proportional_tolerance <= 0.0:
            raise ValueError("proportional_tolerance must be finite and positive")


@dataclass(frozen=True)
class PerturbationSystem:
    constraint_matrix: NDArray[np.float64]
    constraint_rhs: NDArray[np.float64]
    qr_blocks: tuple[NDArray[np.float64], ...]
    column_scales: tuple[NDArray[np.float64], ...]
    pair_index: NDArray[np.int_]
    lower_rows: NDArray[np.int_]
    lower_columns: NDArray[np.int_]
    pole_indices: NDArray[np.int_]
    active_column_count: int
    fit_frequencies_hz: NDArray[np.float64]
    fit_weights: NDArray[np.float64]
    dynamic_columns: tuple[Literal["constant", "proportional"], ...]
    coordinate_count: int


def _assessment(model: PoleResidueModel, frequencies_hz: NDArray[np.float64], parameter_type: str) -> PassivityAssessment:
    f_max = float(np.max(frequencies_hz))
    return assess_s_passivity(model, f_max=f_max) if parameter_type == "S" else assess_y_passivity(model, f_max=f_max)


def _metric_excess(value: float, parameter_type: str) -> float:
    return value - 1.0 if parameter_type == "S" else -value


def _rp_auxiliary_frequencies(
    frequencies_hz: NDArray[np.float64],
    poles: NDArray[np.complex128],
    pair_index: NDArray[np.int_],
    parameter_type: Literal["S", "Y"],
    extrema_hz: NDArray[np.float64],
    include_proportional: bool,
) -> NDArray[np.float64]:
    """Reproduce RP_QRNNLS's auxiliary LS samples for weight mode 1."""

    omega = 2.0 * np.pi * frequencies_hz
    lower = float(np.min(omega))
    upper = float(np.max(omega))
    outside: list[float] = []
    for index, pole in enumerate(poles):
        if pair_index[index] == 2:
            continue
        candidate = abs(float(pole.real)) if pair_index[index] == 0 else abs(float(pole.imag))
        if candidate > upper or candidate < lower:
            outside.append(candidate / (2.0 * np.pi))
    if parameter_type == "S":
        # RP_QRNNLS_S appends out-of-band samples and one DC point.  Its
        # later s_ekstra assignment is intentionally not duplicated here:
        # the reference function does not append it to s either.
        extra = outside + [0.0]
    else:
        # RP_QRNLLS_Y adds the unique violation frequencies and one DC point
        # when E is not being perturbed.  ``s_ekstra`` belongs to the driver
        # sweep path and is deliberately a separate later-stage input.
        extra = outside + np.unique(extrema_hz).tolist()
        if not include_proportional:
            extra.append(0.0)
    return np.concatenate((frequencies_hz, np.asarray(extra, dtype=float)))


def _dynamic_columns(model: PoleResidueModel, parameter_type: Literal["S", "Y"]) -> tuple[Literal["constant", "proportional"], ...]:
    constant = 0.5 * (model.constant + model.constant.conj().T)
    proportional = 0.5 * (model.proportional + model.proportional.conj().T)
    if parameter_type == "S":
        return ("constant",) if np.any(np.linalg.svd(constant, compute_uv=False) > 1.0) else ()
    columns: list[Literal["constant", "proportional"]] = []
    if np.any(np.abs(constant) > 0.0) and np.min(np.linalg.eigvalsh(constant).real) < 0.0:
        columns.append("constant")
    if np.any(np.abs(proportional) > 0.0) and np.min(np.linalg.eigvalsh(proportional).real) < 0.0:
        columns.append("proportional")
    return tuple(columns)


def build_residue_perturbation_system(
    model: PoleResidueModel,
    frequencies_hz: NDArray[np.float64],
    *,
    parameter_type: Literal["S", "Y"],
    local_violations: bool = True,
    passivity_tolerance: float = 1.0e-6,
    alpha: float = 1.0,
    pole_indices: tuple[int, ...] | None = None,
    bandwidth: int | None = None,
    auxiliary_weight_factor: float = 1.0e-3,
    proportional_tolerance: float = 1.0e-12,
    qr_reference: PerturbationSystem | None = None,
) -> PerturbationSystem:
    """Build ``B R^-1`` constraints for residue-only RP-NNLS perturbation."""

    frequencies = np.asarray(frequencies_hz, dtype=float).reshape(-1)
    if len(frequencies) < 2 or not np.isfinite(frequencies).all() or np.any(frequencies < 0.0):
        raise ValueError("frequencies_hz must contain finite non-negative samples")
    if not np.isfinite(auxiliary_weight_factor) or auxiliary_weight_factor <= 0.0:
        raise ValueError("auxiliary_weight_factor must be finite and positive")
    if not np.isfinite(proportional_tolerance) or proportional_tolerance <= 0.0:
        raise ValueError("proportional_tolerance must be finite and positive")
    selected_indices = np.arange(len(model.poles), dtype=int) if pole_indices is None else np.asarray(pole_indices, dtype=int)
    if len(selected_indices) == 0 or np.any(selected_indices < 0) or np.any(selected_indices >= len(model.poles)) or len(np.unique(selected_indices)) != len(selected_indices):
        raise ValueError("pole_indices must be unique valid model pole indices")
    selected_indices.sort()
    full_pair_index = _complex_pair_index(model.poles)
    for index in selected_indices:
        if full_pair_index[index] == 1 and index + 1 not in selected_indices:
            raise ValueError("pole_indices must include complete adjacent conjugate pairs")
        if full_pair_index[index] == 2 and index - 1 not in selected_indices:
            raise ValueError("pole_indices must include complete adjacent conjugate pairs")
    selected_poles = model.poles[selected_indices]
    local_columns = len(selected_poles)
    _, pair_index = _basis(2j * np.pi * frequencies, selected_poles, 1)
    dynamic_columns = _dynamic_columns(model, parameter_type)
    assessment = _assessment(model, frequencies, parameter_type)
    extrema = select_violation_extrema(model, assessment, local=local_violations)
    fit_frequencies = _rp_auxiliary_frequencies(
        frequencies,
        selected_poles,
        pair_index,
        parameter_type,
        np.asarray([extremum.frequency_hz for extremum in extrema], dtype=float),
        "proportional" in dynamic_columns,
    )
    fit_weights = np.ones(len(fit_frequencies), dtype=float)
    fit_weights[len(frequencies) :] = auxiliary_weight_factor
    basis, _ = _basis(2j * np.pi * fit_frequencies, selected_poles, 3)
    basis_columns = list(range(local_columns))
    if "constant" in dynamic_columns:
        basis_columns.append(local_columns)
    if "proportional" in dynamic_columns:
        basis_columns.append(local_columns + 1)
    coordinate_count = len(basis_columns)
    rows, columns = _matlab_lower_triangle_indices(model.ports)
    if bandwidth is not None:
        within_band = rows - columns <= bandwidth
        rows = rows[within_band]
        columns = columns[within_band]
    qr_blocks: list[NDArray[np.float64]] = []
    column_scales: list[NDArray[np.float64]] = []
    for row, column in zip(rows, columns, strict=True):
        weighted_basis = fit_weights[:, None] * basis[:, basis_columns]
        design = np.concatenate((weighted_basis.real, weighted_basis.imag), axis=0)
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
        if np.linalg.matrix_rank(r) < coordinate_count:
            raise ValueError("residue QR block is rank deficient")
        qr_blocks.append(r)
        column_scales.append(scale)
    if qr_reference is not None:
        if (
            qr_reference.coordinate_count != coordinate_count
            or not np.array_equal(qr_reference.lower_rows, rows)
            or not np.array_equal(qr_reference.lower_columns, columns)
        ):
            raise ValueError("QR reference does not match the current RP coordinate layout")
        qr_blocks = list(qr_reference.qr_blocks)
        column_scales = list(qr_reference.column_scales)
    gradients = np.zeros((len(extrema), len(rows) * coordinate_count), dtype=float)
    rhs = np.zeros(len(extrema), dtype=float)
    signs = np.full(len(extrema), -1.0 if parameter_type == "S" else 1.0)
    for index, extremum in enumerate(extrema):
        s = 2j * np.pi * extremum.frequency_hz
        local_basis, _ = _basis(np.asarray([s]), selected_poles, 3)
        for element, (row, column) in enumerate(zip(rows, columns, strict=True)):
            for coordinate, basis_column in enumerate(basis_columns):
                derivative = np.zeros((model.ports, model.ports), dtype=complex)
                derivative[row, column] = local_basis[0, basis_column]
                derivative[column, row] = local_basis[0, basis_column]
                if parameter_type == "S":
                    assert extremum.right_vector is not None
                    sensitivity = float(np.real(np.vdot(extremum.left_vector, derivative @ extremum.right_vector)))
                else:
                    sensitivity = float(np.real(np.vdot(extremum.left_vector, derivative @ extremum.left_vector)))
                gradients[index, element * coordinate_count + coordinate] = sensitivity
        if parameter_type == "S":
            rhs[index] = -(passivity_tolerance + alpha * max(extremum.value - 1.0, 0.0))
        else:
            # MATLAB RP_QRNNLS_Y: c=-TOLG+alpha*lambda_min.
            rhs[index] = -passivity_tolerance + alpha * extremum.value
            if rhs[index] > 0.0:
                rhs[index] = (passivity_tolerance + rhs[index]) / alpha
                rhs[index] = (2.0 - alpha) * rhs[index] - passivity_tolerance
    asymptotic_gradients: list[NDArray[np.float64]] = []
    asymptotic_rhs: list[float] = []
    if "constant" in dynamic_columns:
        constant_coordinate = local_columns + dynamic_columns.index("constant")
        if parameter_type == "S":
            left, values, right_h = np.linalg.svd(model.constant)
            modes = ((values[index], left[:, index], right_h[index].conj()) for index in range(model.ports))
        else:
            values, vectors = np.linalg.eigh(0.5 * (model.constant + model.constant.conj().T))
            modes = ((values[index], vectors[:, index], None) for index in range(model.ports))
        for value, left_vector, right_vector in modes:
            row_gradient = np.zeros(len(rows) * coordinate_count, dtype=float)
            for element, (row, column) in enumerate(zip(rows, columns, strict=True)):
                derivative = np.zeros((model.ports, model.ports), dtype=complex)
                derivative[row, column] = derivative[column, row] = 1.0
                sensitivity = (
                    float(np.real(np.vdot(left_vector, derivative @ right_vector)))
                    if right_vector is not None
                    else float(np.real(np.vdot(left_vector, derivative @ left_vector)))
                )
                row_gradient[element * coordinate_count + constant_coordinate] = sensitivity
            if parameter_type == "S":
                excess = float(value - 1.0)
                asymptotic_rhs.append(-passivity_tolerance + (alpha * excess if excess > 0.0 else excess))
            else:
                asymptotic_rhs.append(-passivity_tolerance + (alpha * float(value) if value < 0.0 else float(value)))
            asymptotic_gradients.append(row_gradient)
    if "proportional" in dynamic_columns:
        proportional_coordinate = local_columns + dynamic_columns.index("proportional")
        values, vectors = np.linalg.eigh(0.5 * (model.proportional + model.proportional.conj().T))
        for index, value in enumerate(values):
            vector = vectors[:, index]
            row_gradient = np.zeros(len(rows) * coordinate_count, dtype=float)
            for element, (row, column) in enumerate(zip(rows, columns, strict=True)):
                derivative = np.zeros((model.ports, model.ports), dtype=complex)
                derivative[row, column] = derivative[column, row] = 1.0
                row_gradient[element * coordinate_count + proportional_coordinate] = float(np.real(np.vdot(vector, derivative @ vector)))
            asymptotic_gradients.append(row_gradient)
            asymptotic_rhs.append(-proportional_tolerance + alpha * float(value))
    if asymptotic_gradients:
        gradients = np.vstack((gradients, np.asarray(asymptotic_gradients)))
        rhs = np.concatenate((rhs, np.asarray(asymptotic_rhs)))
        signs = np.concatenate((signs, np.ones(len(asymptotic_gradients))))
    transformed = np.zeros_like(gradients)
    for element, block in enumerate(qr_blocks):
        start = element * coordinate_count
        stop = start + coordinate_count
        scaled_gradient = gradients[:, start:stop] / column_scales[element]
        transformed[:, start:stop] = solve_triangular(block.T, scaled_gradient.T, lower=True).T
    constraint_matrix = signs[:, None] * transformed
    return PerturbationSystem(
        constraint_matrix=constraint_matrix,
        constraint_rhs=rhs,
        qr_blocks=tuple(qr_blocks),
        column_scales=tuple(column_scales),
        pair_index=pair_index,
        lower_rows=rows,
        lower_columns=columns,
        pole_indices=selected_indices,
        active_column_count=int(np.count_nonzero(np.any(np.abs(transformed) > 0.0, axis=0))),
        fit_frequencies_hz=fit_frequencies,
        fit_weights=fit_weights,
        dynamic_columns=dynamic_columns,
        coordinate_count=coordinate_count,
    )


def _recover_delta(system: PerturbationSystem, xbar: NDArray[np.float64]) -> NDArray[np.float64]:
    local_columns = system.coordinate_count
    delta = np.empty_like(xbar)
    for element, block in enumerate(system.qr_blocks):
        start = element * local_columns
        stop = start + local_columns
        delta[start:stop] = solve_triangular(block, xbar[start:stop], lower=False) / system.column_scales[element]
    return delta


def _apply_residue_delta(model: PoleResidueModel, system: PerturbationSystem, delta: NDArray[np.float64]) -> PoleResidueModel:
    residues = np.array(model.residues, copy=True)
    local_columns = system.coordinate_count
    residue_columns = len(system.pair_index)
    for element, (row, column) in enumerate(zip(system.lower_rows, system.lower_columns, strict=True)):
        values = delta[element * local_columns : (element + 1) * local_columns]
        for pole_column, kind in enumerate(system.pair_index):
            if kind == 0:
                original_column = system.pole_indices[pole_column]
                residues[row, column, original_column] += values[pole_column]
                if row != column:
                    residues[column, row, original_column] += values[pole_column]
            elif kind == 1:
                change = values[pole_column] + 1j * values[pole_column + 1]
                original_column = system.pole_indices[pole_column]
                conjugate_column = system.pole_indices[pole_column + 1]
                residues[row, column, original_column] += change
                if row != column:
                    residues[column, row, original_column] += change
                residues[row, column, conjugate_column] += change.conjugate()
                if row != column:
                    residues[column, row, conjugate_column] += change.conjugate()
    constant = np.array(model.constant, copy=True)
    proportional = np.array(model.proportional, copy=True)
    for element, (row, column) in enumerate(zip(system.lower_rows, system.lower_columns, strict=True)):
        values = delta[element * local_columns : (element + 1) * local_columns]
        for offset, dynamic in enumerate(system.dynamic_columns, start=residue_columns):
            target = constant if dynamic == "constant" else proportional
            target[row, column] += values[offset]
            if row != column:
                target[column, row] += values[offset]
    return PoleResidueModel(model.poles, residues, constant, proportional)


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
        excess_before = excess
        if excess <= 1.0e-6:
            break
        base_system: PerturbationSystem | None = None
        accumulated_matrix: NDArray[np.float64] | None = None
        accumulated_rhs: NDArray[np.float64] | None = None
        inner_count = 0
        accepted = False
        candidate_excess = excess
        solution = None
        for _ in range(config.inner_iterations):
            system = build_residue_perturbation_system(
                current,
                frequencies,
                parameter_type=config.parameter_type,
                local_violations=config.local_violations,
                passivity_tolerance=config.passivity_tolerance,
                alpha=config.alpha,
                pole_indices=config.pole_indices,
                bandwidth=config.bandwidth,
                auxiliary_weight_factor=config.auxiliary_weight_factor,
                proportional_tolerance=config.proportional_tolerance,
                qr_reference=base_system,
            )
            if not len(system.constraint_rhs):
                break
            base_system = system if base_system is None else base_system
            accumulated_matrix = system.constraint_matrix if accumulated_matrix is None else np.vstack((accumulated_matrix, system.constraint_matrix))
            accumulated_rhs = system.constraint_rhs if accumulated_rhs is None else np.concatenate((accumulated_rhs, system.constraint_rhs))
            solution = solve_homogeneous_nnls(accumulated_matrix, accumulated_rhs, tolerance=config.tolerance)
            delta = _recover_delta(base_system, solution.x)
            candidate = _apply_residue_delta(current, base_system, delta)
            candidate_assessment = _assessment(candidate, frequencies, config.parameter_type)
            candidate_excess = _metric_excess(candidate_assessment.worst_value, config.parameter_type)
            inner_count += 1
            if not np.isfinite(candidate_excess) or candidate_excess >= excess:
                break
            accepted = True
            current = candidate
            assessment = candidate_assessment
            excess = candidate_excess
            if excess <= 1.0e-6:
                break
        history.append(
            {
                "iteration": iteration + 1,
                "constraint_count": 0 if base_system is None else int(len(base_system.constraint_rhs)),
                "accumulated_constraint_count": 0 if accumulated_rhs is None else int(len(accumulated_rhs)),
                "inner_iterations": inner_count,
                "kkt_stationarity_inf_norm": float("nan") if solution is None else solution.kkt_stationarity_inf_norm,
                "excess_before": excess_before,
                "excess_after": candidate_excess,
                "accepted": accepted,
            }
        )
        if not accepted:
            break
    response = evaluate(current, 2j * np.pi * frequencies)
    rms = float(np.sqrt(np.mean(np.abs(response - reference) ** 2)))
    return MFTResult(
        current,
        MFTDiagnostics("passivity_enforcement", iterations=len(history), details={"history": history, "final_assessment": assessment}),
        rms,
    )
