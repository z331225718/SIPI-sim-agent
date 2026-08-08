from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from agent_spice.backend.base import BackendResult
from agent_spice.backend.ngspice import NgspiceBackend
from agent_spice.cli import main
from agent_spice.hspice.results import write_ngspice_waveform_csv
from agent_spice.sparam.artifacts import write_cadence_rfm
from agent_spice.sparam.rfm import parse_cadence_rfm
from agent_spice.sparam.rfm_ngspice import (
    execute_rfm_run,
    prepare_rfm_run,
    write_xspice_rfm_wrapper,
)


class _OnePortSource:
    nports = 1
    poles = np.array([-2.0 + 0.0j, -3.0 + 4.0j])
    residues = np.array([[0.5 + 0.0j, 0.2 + 0.1j]])
    constant_coeff = np.array([0.1])
    proportional_coeff = np.zeros(1)


class _AcComplexSource:
    nports = 1
    poles = np.array([-2.0e9 + 0.0j, -3.0e9 + 4.0e9j])
    residues = np.array([[0.5e9 + 0.0j, 0.2e9 + 0.3e9j]])
    constant_coeff = np.array([0.1])
    proportional_coeff = np.zeros(1)


def test_prepare_rfm_run_preserves_inputs_and_does_not_refit(tmp_path: Path) -> None:
    rfm = tmp_path / "source.rfm"
    deck = tmp_path / "source.sp"
    write_cadence_rfm(_OnePortSource(), rfm, z0=50.0)
    deck.write_text("Rload out 0 50\nXchannel out 0 rfm_direct\n.tran 1p 10p\n.end\n", encoding="ascii")

    artifacts = prepare_rfm_run(deck, rfm, output_root=tmp_path / "runs")
    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))

    assert artifacts.source_deck_path.read_bytes() == deck.read_bytes()
    assert artifacts.source_rfm_path.read_bytes() == rfm.read_bytes()
    assert manifest["refit_performed"] is False
    assert manifest["runtime_rfm"]["reconstruction_max"] < 1e-12
    assert ".include 'rfm_direct_wrapper.sp'\n.end" in artifacts.deck_path.read_text(encoding="utf-8")
    assert "Arfm %gd[p1 ref] rfm_direct_rfm_model" in artifacts.wrapper_path.read_text(encoding="ascii")
    np.testing.assert_allclose(
        parse_cadence_rfm(artifacts.runtime_rfm_path).evaluate_s([0.0, 1.0]),
        parse_cadence_rfm(rfm).evaluate_s([0.0, 1.0]),
    )


def test_prepare_rfm_run_normalizes_response_specific_poles(tmp_path: Path) -> None:
    rfm = tmp_path / "specific.rfm"
    rfm.write_text(
        """VERSION 200600
NPORT 1
MATRIX_TYPE S
Z0 50
BEGIN 1 1
Const 0
BEGIN_REAL 1
2 0.5
BEGIN_COMPLEX 0
END
""",
        encoding="ascii",
    )
    deck = tmp_path / "case.sp"
    deck.write_text("X1 p 0 rfm_direct\n.end\n", encoding="ascii")

    artifacts = prepare_rfm_run(deck, rfm, output_root=tmp_path / "out")

    assert artifacts.runtime_rfm_path.read_text(encoding="ascii").count("BEGIN_REAL 1") == 1


def test_prepare_rfm_run_stages_nested_relative_includes(tmp_path: Path) -> None:
    rfm = tmp_path / "source.rfm"
    write_cadence_rfm(_OnePortSource(), rfm, z0=50.0)
    library = tmp_path / "models"
    library.mkdir()
    (library / "nested.sp").write_text("Rnested a 0 1k\n", encoding="ascii")
    (library / "top.sp").write_text(".include 'nested.sp'\n", encoding="ascii")
    deck = tmp_path / "source.sp"
    deck.write_text(".include 'models/top.sp'\nX1 a 0 rfm_direct\n.end\n", encoding="ascii")

    artifacts = prepare_rfm_run(deck, rfm, output_root=tmp_path / "runs")
    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))

    assert (artifacts.run_dir / "models" / "top.sp").is_file()
    assert (artifacts.run_dir / "models" / "nested.sp").is_file()
    assert manifest["artifacts"]["staged_dependencies"] == [
        "models/nested.sp",
        "models/top.sp",
    ]


def test_xspice_wrapper_uses_dynamic_vector_and_explicit_reference(tmp_path: Path) -> None:
    rfm = tmp_path / "two.rfm"
    source = _OnePortSource()
    source.nports = 2
    source.residues = np.tile(source.residues, (4, 1))
    source.constant_coeff = np.zeros(4)
    source.proportional_coeff = np.zeros(4)
    write_cadence_rfm(source, rfm, z0=50.0)
    model = parse_cadence_rfm(rfm)

    wrapper = write_xspice_rfm_wrapper(
        model,
        tmp_path / "wrapper.sp",
        rfm_filename="model.runtime.rfm",
        subcircuit_name="channel",
    )
    text = wrapper.read_text(encoding="ascii")

    assert ".subckt channel p1 p2 ref" in text
    assert "Arfm %gd[p1 ref p2 ref] channel_rfm_model" in text
    assert 'nport_rfm(rfm_file="model.runtime.rfm")' in text


def test_ngspice_backend_creates_run_local_spinit_for_code_model(
    tmp_path: Path, monkeypatch
) -> None:
    deck = tmp_path / "case.cir"
    model = tmp_path / "rfm.cm"
    deck.write_text(".end\n", encoding="ascii")
    model.write_bytes(b"code-model")
    recorded: dict[str, object] = {}

    def fake_run(command, **kwargs):
        recorded["command"] = command
        recorded["environment"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = NgspiceBackend(executable="ngspice", code_models=(model,)).run(deck, cwd=tmp_path)

    assert result.ok
    spinit = tmp_path / ".ngspice-scripts" / "spinit"
    staged = tmp_path / ".ngspice-code-models" / "000-rfm.cm"
    assert f"codemodel {staged.resolve().as_posix()}" in spinit.read_text(encoding="ascii")
    assert staged.read_bytes() == model.read_bytes()
    assert recorded["environment"]["SPICE_SCRIPTS"] == str(spinit.parent)


def test_execute_rfm_run_promotes_code_model_error_to_failure(tmp_path: Path, monkeypatch) -> None:
    rfm = tmp_path / "source.rfm"
    deck = tmp_path / "source.sp"
    code_model = tmp_path / "rfm.cm"
    write_cadence_rfm(_OnePortSource(), rfm, z0=50.0)
    deck.write_text("X1 p 0 rfm_direct\n.end\n", encoding="ascii")
    code_model.write_bytes(b"code-model")
    artifacts = prepare_rfm_run(deck, rfm, output_root=tmp_path / "runs")

    monkeypatch.setattr(
        NgspiceBackend,
        "run",
        lambda self, deck_path, cwd=None: BackendResult(
            returncode=0,
            stdout="nport_rfm ERROR: singular companion matrix\n",
            stderr="",
        ),
    )
    result = execute_rfm_run(artifacts, code_model=code_model)
    summary = json.loads((artifacts.run_dir / "run_summary.json").read_text(encoding="utf-8"))

    assert result.returncode == 2
    assert summary["ok"] is False


def test_run_rfm_cli_prepares_without_execution(tmp_path: Path) -> None:
    rfm = tmp_path / "source.rfm"
    deck = tmp_path / "source.sp"
    write_cadence_rfm(_OnePortSource(), rfm, z0=50.0)
    deck.write_text("X1 p 0 channel\n.end\n", encoding="ascii")

    status = main(
        [
            "run-rfm",
            str(deck),
            "--rfm",
            str(rfm),
            "--subckt-name",
            "channel",
            "--output-root",
            str(tmp_path / "runs"),
        ]
    )

    assert status == 0
    assert (tmp_path / "runs" / "source" / "rfm_direct" / "case.cir").is_file()


def test_run_rfm_cli_executes_native_backend_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rfm = tmp_path / "source.rfm"
    deck = tmp_path / "source.sp"
    write_cadence_rfm(_OnePortSource(), rfm, z0=50.0)
    deck.write_text("X1 p 0 channel\n.end\n", encoding="ascii")
    calls: list[str] = []

    def execute_native(artifacts, **kwargs):
        calls.append("native")
        return BackendResult(returncode=0, stdout="{}", stderr="")

    def execute_ngspice(artifacts, **kwargs):
        calls.append("ngspice")
        return BackendResult(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "agent_spice.sparam.rfm_ngspice.execute_native_rfm_run",
        execute_native,
    )
    monkeypatch.setattr(
        "agent_spice.sparam.rfm_ngspice.execute_rfm_run",
        execute_ngspice,
    )

    status = main(
        [
            "run-rfm",
            str(deck),
            "--rfm",
            str(rfm),
            "--subckt-name",
            "channel",
            "--output-root",
            str(tmp_path / "runs"),
            "--execute",
        ]
    )

    assert status == 0
    assert calls == ["native"]


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")
def test_bundled_xspice_model_matches_rfm_complex_pair_in_ac(tmp_path: Path) -> None:
    rfm = tmp_path / "complex.rfm"
    deck = tmp_path / "complex.sp"
    write_cadence_rfm(_AcComplexSource(), rfm, z0=50.0)
    deck.write_text(
        """RFM complex-pair AC regression
.option numdgt=15
Vdrive p 0 ac 1
Xchannel p 0 rfm_direct
.ac lin 1 1g 1g
.print ac real(i(Vdrive)) imag(i(Vdrive))
.end
""",
        encoding="ascii",
    )

    artifacts = prepare_rfm_run(deck, rfm, output_root=tmp_path / "runs")
    result = execute_rfm_run(artifacts)

    assert result.ok, result.stdout + result.stderr
    with (artifacts.run_dir / "waveform.csv").open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    actual = complex(float(row["real(i(vdrive))"]), float(row["imag(i(vdrive))"]))
    s11 = artifacts.model.evaluate_s([1.0e9])[0, 0, 0]
    expected = -(1.0 - s11) / (1.0 + s11) / artifacts.model.z0

    np.testing.assert_allclose(actual, expected, rtol=5e-6, atol=1e-12)


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")
def test_bundled_xspice_model_matches_spice_macro_in_transient(tmp_path: Path) -> None:
    rfm = tmp_path / "complex.rfm"
    direct_deck = tmp_path / "direct.sp"
    macro_deck = tmp_path / "macro.sp"
    macro = tmp_path / "complex_macro.sp"
    write_cadence_rfm(_AcComplexSource(), rfm, z0=50.0)
    model = parse_cadence_rfm(rfm)
    model.write_spice_subcircuit(macro, subcircuit_name="rfm_macro")
    analysis = """Vsrc src 0 PULSE(0 1 100p 20p 20p 500p 1n)
Rsrc src p 50
Rload p 0 50
.tran 2p 2n 0 2p
.print tran v(p)
.end
"""
    direct_deck.write_text(
        "Direct RFM transient\nXchannel p 0 rfm_direct\n" + analysis,
        encoding="ascii",
    )
    macro_deck.write_text(
        f"SPICE macro transient\n.include '{macro.as_posix()}'\nXchannel p rfm_macro\n" + analysis,
        encoding="ascii",
    )

    artifacts = prepare_rfm_run(direct_deck, rfm, output_root=tmp_path / "runs")
    direct_result = execute_rfm_run(artifacts)
    macro_result = NgspiceBackend().run(macro_deck, cwd=tmp_path)

    assert direct_result.ok, direct_result.stdout + direct_result.stderr
    assert macro_result.ok, macro_result.stdout + macro_result.stderr
    macro_csv = tmp_path / "macro.csv"
    assert write_ngspice_waveform_csv(macro_result.stdout, macro_csv) > 0
    direct_wave = np.genfromtxt(artifacts.run_dir / "waveform.csv", delimiter=",", names=True)
    macro_wave = np.genfromtxt(macro_csv, delimiter=",", names=True)
    macro_voltage = np.interp(direct_wave["time"], macro_wave["time"], macro_wave["vp"])
    np.testing.assert_allclose(direct_wave["vp"], macro_voltage, rtol=2e-4, atol=2e-6)
