"""Read Cadence Broadband SPICE RFM pole/residue models without refitting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from .artifacts import evaluate_fitted_s
from .native_vf import NativeVectorFitting


class RfmParseError(ValueError):
    """Raised when an RFM file cannot be represented by the current importer."""


@dataclass(frozen=True)
class _SourceLine:
    number: int
    text: str


@dataclass(frozen=True)
class RfmModel:
    """Canonical S-matrix pole/residue data read from an RFM file."""

    version: int
    nports: int
    matrix_type: str
    z0: float
    poles: np.ndarray
    residues: np.ndarray
    constant_coeff: np.ndarray
    source_path: Path

    @property
    def proportional_coeff(self) -> np.ndarray:
        return np.zeros(self.nports * self.nports, dtype=float)

    @property
    def effective_order(self) -> int:
        return int(np.sum((self.poles.imag != 0.0) + 1))

    def evaluate_s(self, frequencies_hz: Any) -> np.ndarray:
        """Reconstruct ``S(j*2*pi*f)`` directly from imported coefficients."""

        return evaluate_fitted_s(self, frequencies_hz)

    def write_spice_subcircuit(
        self,
        path: str | Path,
        *,
        subcircuit_name: str = "rfm_imported",
        create_reference_pins: bool = False,
    ) -> Path:
        """Route imported coefficients through the existing Native SPICE exporter."""

        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        network = SimpleNamespace(
            nports=self.nports,
            z0=np.full((1, self.nports), complex(self.z0), dtype=complex),
        )
        vector_fit = NativeVectorFitting(network)
        vector_fit.poles = np.asarray(self.poles, dtype=complex).copy()
        vector_fit.residues = np.asarray(self.residues, dtype=complex).copy()
        # RFM Const is real-only. Preserve a real dtype because the existing
        # exporter writes coefficients directly into numeric SPICE fields.
        vector_fit.constant_coeff = np.asarray(self.constant_coeff.real, dtype=float).copy()
        vector_fit.proportional_coeff = self.proportional_coeff
        vector_fit.write_spice_subcircuit_s(
            str(output),
            fitted_model_name=subcircuit_name,
            create_reference_pins=create_reference_pins,
        )
        return output


def _data_lines(path: Path) -> list[_SourceLine]:
    try:
        text = path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise RfmParseError(f"Cannot read ASCII RFM file '{path}': {exc}") from exc
    lines: list[_SourceLine] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith(("*", "!", "#")):
            continue
        lines.append(_SourceLine(number=number, text=stripped))
    if not lines:
        raise RfmParseError(f"RFM file '{path}' is empty")
    return lines


def _float_token(token: str, *, path: Path, line: _SourceLine, label: str) -> float:
    try:
        value = float(token.replace("D", "E").replace("d", "e"))
    except ValueError as exc:
        raise RfmParseError(f"{path}:{line.number}: invalid {label} '{token}'") from exc
    if not np.isfinite(value):
        raise RfmParseError(f"{path}:{line.number}: {label} must be finite")
    return value


def _integer_token(token: str, *, path: Path, line: _SourceLine, label: str) -> int:
    try:
        value = int(token)
    except ValueError as exc:
        raise RfmParseError(f"{path}:{line.number}: invalid {label} '{token}'") from exc
    return value


def _expect_tokens(
    lines: list[_SourceLine],
    index: int,
    keyword: str,
    count: int,
    *,
    path: Path,
) -> tuple[_SourceLine, list[str], int]:
    if index >= len(lines):
        raise RfmParseError(f"{path}: expected {keyword}, reached end of file")
    line = lines[index]
    tokens = line.text.split()
    if len(tokens) != count or tokens[0].upper() != keyword:
        raise RfmParseError(f"{path}:{line.number}: expected '{keyword}' with {count - 1} value(s)")
    return line, tokens, index + 1


def parse_cadence_rfm(path: str | Path) -> RfmModel:
    """Parse a project-compatible ``VERSION 200600`` S-parameter RFM.

    Response blocks may use different pole sets. They are losslessly promoted
    into one union pole basis with zero residues for absent response terms.
    """

    source = Path(path)
    lines = _data_lines(source)
    index = 0
    headers: dict[str, tuple[_SourceLine, str]] = {}
    required_headers = {"VERSION", "NPORT", "MATRIX_TYPE", "Z0"}
    while index < len(lines) and lines[index].text.split()[0].upper() != "BEGIN":
        line = lines[index]
        tokens = line.text.split()
        if len(tokens) != 2:
            raise RfmParseError(f"{source}:{line.number}: expected a two-token RFM header")
        key = tokens[0].upper()
        if key not in required_headers:
            raise RfmParseError(f"{source}:{line.number}: unsupported RFM header '{tokens[0]}'")
        if key in headers:
            raise RfmParseError(f"{source}:{line.number}: duplicate RFM header '{tokens[0]}'")
        headers[key] = (line, tokens[1])
        index += 1

    missing_headers = sorted(required_headers - headers.keys())
    if missing_headers:
        raise RfmParseError(f"{source}: missing RFM header(s): {', '.join(missing_headers)}")

    version_line, version_token = headers["VERSION"]
    version = _integer_token(version_token, path=source, line=version_line, label="VERSION")
    if version != 200600:
        raise RfmParseError(f"{source}:{version_line.number}: unsupported RFM VERSION {version}")
    nport_line, nport_token = headers["NPORT"]
    nports = _integer_token(nport_token, path=source, line=nport_line, label="NPORT")
    if nports <= 0:
        raise RfmParseError(f"{source}:{nport_line.number}: NPORT must be positive")
    matrix_line, matrix_type = headers["MATRIX_TYPE"]
    matrix_type = matrix_type.upper()
    if matrix_type != "S":
        raise RfmParseError(
            f"{source}:{matrix_line.number}: only MATRIX_TYPE S is supported; got {matrix_type}"
        )
    z0_line, z0_token = headers["Z0"]
    z0 = _float_token(z0_token, path=source, line=z0_line, label="Z0")
    if z0 <= 0.0:
        raise RfmParseError(f"{source}:{z0_line.number}: Z0 must be positive")

    response_count = nports * nports
    constants = np.zeros(response_count, dtype=complex)
    response_terms: list[list[tuple[complex, complex]] | None] = [None] * response_count
    pole_order: list[complex] = []
    pole_indices: dict[complex, int] = {}

    while index < len(lines):
        begin_line, begin_tokens, index = _expect_tokens(lines, index, "BEGIN", 3, path=source)
        row = _integer_token(begin_tokens[1], path=source, line=begin_line, label="BEGIN row")
        column = _integer_token(begin_tokens[2], path=source, line=begin_line, label="BEGIN column")
        if not (1 <= row <= nports and 1 <= column <= nports):
            raise RfmParseError(f"{source}:{begin_line.number}: BEGIN indices are outside 1..{nports}")
        response_index = (row - 1) * nports + (column - 1)
        if response_terms[response_index] is not None:
            raise RfmParseError(f"{source}:{begin_line.number}: duplicate BEGIN {row} {column} block")

        const_line, const_tokens, index = _expect_tokens(lines, index, "CONST", 2, path=source)
        constants[response_index] = _float_token(
            const_tokens[1], path=source, line=const_line, label="Const"
        )
        terms: list[tuple[complex, complex]] = []

        # IdEM emits these optional RFM fields even when both are zero.  The
        # current state-space importer has no representation for a non-zero
        # proportional term or delay, so accept the lossless zero form and
        # reject any behaviour we cannot preserve.
        if index < len(lines) and lines[index].text.split()[0].upper() == "C":
            c_line, c_tokens, index = _expect_tokens(lines, index, "C", 2, path=source)
            c_value = _float_token(c_tokens[1], path=source, line=c_line, label="C")
            if c_value != 0.0:
                raise RfmParseError(f"{source}:{c_line.number}: non-zero C is not supported")
        if index < len(lines) and lines[index].text.split()[0].upper() == "DELAY":
            delay_line, delay_tokens, index = _expect_tokens(lines, index, "DELAY", 2, path=source)
            delay = _float_token(delay_tokens[1], path=source, line=delay_line, label="DELAY")
            if delay != 0.0:
                raise RfmParseError(f"{source}:{delay_line.number}: non-zero DELAY is not supported")

        real_line, real_tokens, index = _expect_tokens(lines, index, "BEGIN_REAL", 2, path=source)
        real_count = _integer_token(
            real_tokens[1], path=source, line=real_line, label="BEGIN_REAL count"
        )
        if real_count < 0:
            raise RfmParseError(f"{source}:{real_line.number}: BEGIN_REAL count must be non-negative")
        for _ in range(real_count):
            if index >= len(lines):
                raise RfmParseError(f"{source}: truncated BEGIN_REAL block")
            line = lines[index]
            tokens = line.text.split()
            if len(tokens) != 2:
                raise RfmParseError(f"{source}:{line.number}: real pole row requires damping and residue")
            damping = _float_token(tokens[0], path=source, line=line, label="real-pole damping")
            residue = _float_token(tokens[1], path=source, line=line, label="real-pole residue")
            if damping <= 0.0:
                raise RfmParseError(f"{source}:{line.number}: real-pole damping must be positive")
            terms.append((complex(-damping, 0.0), complex(residue, 0.0)))
            index += 1

        complex_line, complex_tokens, index = _expect_tokens(
            lines, index, "BEGIN_COMPLEX", 2, path=source
        )
        complex_count = _integer_token(
            complex_tokens[1], path=source, line=complex_line, label="BEGIN_COMPLEX count"
        )
        if complex_count < 0:
            raise RfmParseError(f"{source}:{complex_line.number}: BEGIN_COMPLEX count must be non-negative")
        for _ in range(complex_count):
            if index >= len(lines):
                raise RfmParseError(f"{source}: truncated BEGIN_COMPLEX block")
            line = lines[index]
            tokens = line.text.split()
            if len(tokens) != 4:
                raise RfmParseError(
                    f"{source}:{line.number}: complex pole row requires damping, omega, residue real and residue imag"
                )
            damping = _float_token(tokens[0], path=source, line=line, label="complex-pole damping")
            omega = _float_token(tokens[1], path=source, line=line, label="complex-pole omega")
            residue_real = _float_token(tokens[2], path=source, line=line, label="complex residue real")
            residue_imag = _float_token(tokens[3], path=source, line=line, label="complex residue imag")
            if damping <= 0.0 or omega == 0.0:
                raise RfmParseError(
                    f"{source}:{line.number}: complex-pole damping must be positive and omega must be non-zero"
                )
            pole = complex(-damping, omega)
            residue = complex(residue_real, residue_imag)
            # Normalize to the native positive-imaginary representative.  IdEM
            # exports the negative member while older RFM producers may export
            # the positive one; both represent the same conjugate pair.
            if pole.imag < 0.0:
                pole = pole.conjugate()
                residue = residue.conjugate()
            terms.append((pole, residue))
            index += 1

        _, _, index = _expect_tokens(lines, index, "END", 1, path=source)
        response_terms[response_index] = terms
        for pole, _ in terms:
            if pole not in pole_indices:
                pole_indices[pole] = len(pole_order)
                pole_order.append(pole)

    missing_blocks = [
        f"{row + 1},{column + 1}"
        for row in range(nports)
        for column in range(nports)
        if response_terms[row * nports + column] is None
    ]
    if missing_blocks:
        raise RfmParseError(f"{source}: missing response block(s): {', '.join(missing_blocks)}")

    poles = np.asarray(pole_order, dtype=complex)
    residues = np.zeros((response_count, len(pole_order)), dtype=complex)
    for response_index, terms in enumerate(response_terms):
        assert terms is not None
        for pole, residue in terms:
            residues[response_index, pole_indices[pole]] += residue

    return RfmModel(
        version=version,
        nports=nports,
        matrix_type=matrix_type,
        z0=z0,
        poles=poles,
        residues=residues,
        constant_coeff=constants,
        source_path=source,
    )
