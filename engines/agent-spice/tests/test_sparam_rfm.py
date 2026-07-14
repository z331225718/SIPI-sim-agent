from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from agent_spice.sparam.artifacts import evaluate_fitted_s, write_cadence_rfm
from agent_spice.sparam.rfm import RfmParseError, parse_cadence_rfm


class _ProjectRfmSource:
    def __init__(self) -> None:
        self.network = SimpleNamespace(nports=2)
        self.poles = np.array([-2.0 + 0.0j, -3.0 + 4.0j])
        self.residues = np.array(
            [
                [1.0 + 0.0j, 0.20 + 0.30j],
                [0.5 + 0.0j, 0.10 - 0.20j],
                [0.4 + 0.0j, 0.05 + 0.10j],
                [0.8 + 0.0j, 0.30 - 0.10j],
            ]
        )
        self.constant_coeff = np.array([0.1, 0.2, 0.3, 0.4], dtype=complex)
        self.proportional_coeff = np.zeros(4, dtype=complex)


def test_parse_project_generated_rfm_reconstructs_all_responses_without_refit(tmp_path: Path) -> None:
    source = _ProjectRfmSource()
    rfm = tmp_path / "project_generated.rfm"
    write_cadence_rfm(source, rfm, z0=50.0)

    imported = parse_cadence_rfm(rfm)
    frequencies = np.array([0.0, 0.25, 1.0, 10.0])

    assert imported.nports == 2
    assert imported.z0 == 50.0
    assert imported.effective_order == 3
    np.testing.assert_allclose(imported.poles, source.poles)
    np.testing.assert_allclose(imported.residues, source.residues)
    np.testing.assert_allclose(imported.evaluate_s(frequencies), evaluate_fitted_s(source, frequencies))


def test_parse_rfm_unions_response_specific_poles_with_zero_residues(tmp_path: Path) -> None:
    rfm = tmp_path / "response_specific.rfm"
    rfm.write_text(
        """VERSION 200600
NPORT 2
MATRIX_TYPE S
Z0 50
BEGIN 1 1
Const 0
BEGIN_REAL 1
  2 1
BEGIN_COMPLEX 0
END
BEGIN 1 2
Const 0
BEGIN_REAL 0
BEGIN_COMPLEX 1
  3 4 0.2 0.3
END
BEGIN 2 1
Const 0
BEGIN_REAL 0
BEGIN_COMPLEX 0
END
BEGIN 2 2
Const 0
BEGIN_REAL 1
  2 0.5
BEGIN_COMPLEX 0
END
""",
        encoding="ascii",
    )

    imported = parse_cadence_rfm(rfm)

    np.testing.assert_allclose(imported.poles, [-2.0 + 0.0j, -3.0 + 4.0j])
    np.testing.assert_allclose(
        imported.residues,
        [[1.0, 0.0], [0.0, 0.2 + 0.3j], [0.0, 0.0], [0.5, 0.0]],
    )


def test_imported_rfm_uses_existing_spice_exporter_without_calling_fit(tmp_path: Path, monkeypatch) -> None:
    source = _ProjectRfmSource()
    rfm = tmp_path / "project_generated.rfm"
    write_cadence_rfm(source, rfm, z0=50.0)
    imported = parse_cadence_rfm(rfm)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("RFM import must not run vector fitting")

    monkeypatch.setattr("agent_spice.sparam.native_vf.NativeVectorFitting.vector_fit", fail_if_called)
    output = imported.write_spice_subcircuit(tmp_path / "converted" / "model.sp")

    text = output.read_text(encoding="utf-8")
    assert text.startswith("* EQUIVALENT CIRCUIT FOR NATIVE VECTOR FITTED S-MATRIX")
    assert ".SUBCKT rfm_imported p1 p2\n" in text
    assert "* State networks driven by port 2" in text
    assert text.endswith(".ENDS rfm_imported\n")


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("MATRIX_TYPE Y", "only MATRIX_TYPE S"),
        ("VERSION 200500", "unsupported RFM VERSION"),
        ("  0 1", "damping must be positive"),
    ],
)
def test_parse_rfm_rejects_unsupported_or_unstable_input(
    tmp_path: Path, replacement: str, message: str
) -> None:
    text = """VERSION 200600
NPORT 1
MATRIX_TYPE S
Z0 50
BEGIN 1 1
Const 0
BEGIN_REAL 1
  2 1
BEGIN_COMPLEX 0
END
"""
    if replacement.startswith("MATRIX_TYPE"):
        text = text.replace("MATRIX_TYPE S", replacement)
    elif replacement.startswith("VERSION"):
        text = text.replace("VERSION 200600", replacement)
    else:
        text = text.replace("  2 1", replacement)
    rfm = tmp_path / "invalid.rfm"
    rfm.write_text(text, encoding="ascii")

    with pytest.raises(RfmParseError, match=message):
        parse_cadence_rfm(rfm)


def test_parse_rfm_reports_missing_matrix_block(tmp_path: Path) -> None:
    rfm = tmp_path / "missing.rfm"
    rfm.write_text(
        """VERSION 200600
NPORT 2
MATRIX_TYPE S
Z0 50
BEGIN 1 1
Const 0
BEGIN_REAL 0
BEGIN_COMPLEX 0
END
""",
        encoding="ascii",
    )

    with pytest.raises(RfmParseError, match="missing response block"):
        parse_cadence_rfm(rfm)
