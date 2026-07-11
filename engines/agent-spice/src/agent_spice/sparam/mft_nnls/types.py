"""Immutable public data contracts for the MFT-NNLS backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray


ComplexArray = NDArray[np.complex128]


def _complex_array(value: NDArray[Any] | list[Any], *, name: str, ndim: int) -> ComplexArray:
    array = np.asarray(value, dtype=complex)
    if array.ndim != ndim:
        raise ValueError(f"{name} must have {ndim} dimensions")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class MFTConfig:
    """Subset of MFT-NNLS settings shared by the later fitting stages."""

    parameter_type: Literal["S", "Y"] = "S"
    fit_constant: bool = True
    fit_proportional: bool = False
    enforce_symmetry: bool = False
    tolerance: float = 1.0e-8
    order: int = 8
    pole_type: Literal["lincmplx", "logcmplx", "linlogcmplx"] = "linlogcmplx"
    diagonal_iterations: int = 1
    matrix_iterations: int = 1
    weight_mode: int = 1

    def __post_init__(self) -> None:
        if self.parameter_type not in {"S", "Y"}:
            raise ValueError("parameter_type must be 'S' or 'Y'")
        if not np.isfinite(self.tolerance) or self.tolerance <= 0.0:
            raise ValueError("tolerance must be finite and positive")
        if self.order < 1:
            raise ValueError("order must be at least one")
        if self.pole_type not in {"lincmplx", "logcmplx", "linlogcmplx"}:
            raise ValueError("pole_type must be a supported MFT pole distribution")
        if self.diagonal_iterations < 0 or self.matrix_iterations < 0:
            raise ValueError("relocation iteration counts must be non-negative")
        if self.diagonal_iterations + self.matrix_iterations == 0:
            raise ValueError("at least one diagonal or matrix iteration is required")
        if self.weight_mode not in {1, 2, 3, 4, 5}:
            raise ValueError("weight_mode must be between 1 and 5")


@dataclass(frozen=True)
class PoleResidueModel:
    """A matrix pole-residue model with arrays shaped `(ports, ports, poles)`."""

    poles: ComplexArray
    residues: ComplexArray
    constant: ComplexArray
    proportional: ComplexArray

    def __post_init__(self) -> None:
        poles = _complex_array(self.poles, name="poles", ndim=1)
        residues = _complex_array(self.residues, name="residues", ndim=3)
        constant = _complex_array(self.constant, name="constant", ndim=2)
        proportional = _complex_array(self.proportional, name="proportional", ndim=2)
        ports = constant.shape[0]
        if constant.shape != (ports, ports) or proportional.shape != (ports, ports):
            raise ValueError("constant and proportional must be square port matrices")
        if residues.shape != (ports, ports, len(poles)):
            raise ValueError("residues shape must be (ports, ports, poles)")
        object.__setattr__(self, "poles", poles)
        object.__setattr__(self, "residues", residues)
        object.__setattr__(self, "constant", constant)
        object.__setattr__(self, "proportional", proportional)

    @property
    def ports(self) -> int:
        return self.constant.shape[0]


@dataclass(frozen=True)
class MFTDiagnostics:
    """Small, serializable diagnostics without embedding dense solver matrices."""

    stage: str
    iterations: int = 0
    rank: int | None = None
    condition_number: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MFTResult:
    """Result returned by an MFT-NNLS fitting or passivity stage."""

    model: PoleResidueModel
    diagnostics: MFTDiagnostics
    rms_error: float

    def __post_init__(self) -> None:
        if not np.isfinite(self.rms_error) or self.rms_error < 0.0:
            raise ValueError("rms_error must be finite and non-negative")
