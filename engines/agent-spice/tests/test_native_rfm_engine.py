from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from agent_spice.cli import main
from agent_spice.sparam.artifacts import write_cadence_rfm
from agent_spice.sparam.rfm import parse_cadence_rfm
from agent_spice.sparam.rfm_ngspice import (
    execute_native_rfm_run,
    execute_rfm_run,
    prepare_rfm_run,
)


ROOT = Path(__file__).resolve().parents[1]
DLL = ROOT / "native" / "AgentSpice.Engine" / "bin" / "Release" / "net8.0" / "AgentSpice.Engine.dll"


class _ComplexOnePort:
    nports = 1
    poles = np.array([-2.0e9 + 0.0j, -3.0e9 + 4.0e9j])
    residues = np.array([[0.5e9 + 0.0j, 0.2e9 + 0.3e9j]])
    constant_coeff = np.array([0.1])
    proportional_coeff = np.zeros(1)


class _HighQReflectiveOnePort:
    nports = 1
    poles = np.array([-5.0e7 + 4.0e9j])
    residues = np.array([[5.0e6 + 2.0e6j]])
    constant_coeff = np.array([-0.8])
    proportional_coeff = np.zeros(1)


def _has_sdk() -> bool:
    dotnet = shutil.which("dotnet")
    if dotnet is None or not DLL.is_file():
        return False
    result = subprocess.run([dotnet, "--list-sdks"], capture_output=True, text=True, check=False)
    return bool(result.stdout.strip())


pytestmark = pytest.mark.skipif(not _has_sdk(), reason="native .NET engine is not built")


def _run_native(deck: Path, rfm: Path) -> dict:
    completed = subprocess.run(
        [shutil.which("dotnet") or "dotnet", str(DLL), str(deck), "--rfm", str(rfm)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def test_native_rfm_ac_matches_analytic_model_and_ngspice(tmp_path: Path) -> None:
    rfm = tmp_path / "complex.rfm"
    deck = tmp_path / "complex.sp"
    write_cadence_rfm(_ComplexOnePort(), rfm, z0=50.0)
    deck.write_text(
        """RFM native AC differential
Vdrive p 0 ac 1
Xchannel p 0 rfm_direct
.ac lin 1 1g 1g
.print ac real(i(Vdrive)) imag(i(Vdrive))
.end
""",
        encoding="ascii",
    )

    artifacts = prepare_rfm_run(deck, rfm, output_root=tmp_path / "runs")
    native_result = execute_native_rfm_run(
        artifacts,
        engine_path=DLL,
        dotnet_executable=shutil.which("dotnet") or "dotnet",
    )
    assert native_result.ok, native_result.stdout + native_result.stderr
    native = json.loads((artifacts.run_dir / "native_result.json").read_text(encoding="utf-8"))
    native_current = native["points"][0]["complex"]["Vdrive"]
    native_current = complex(native_current["re"], native_current["im"])

    s11 = artifacts.model.evaluate_s([1.0e9])[0, 0, 0]
    expected = -(1.0 - s11) / (1.0 + s11) / artifacts.model.z0
    np.testing.assert_allclose(native_current, expected, rtol=2e-12, atol=1e-14)

    ngspice = execute_rfm_run(artifacts)
    assert ngspice.ok, ngspice.stdout + ngspice.stderr
    with (artifacts.run_dir / "waveform.csv").open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    ngspice_current = complex(float(row["real(i(vdrive))"]), float(row["imag(i(vdrive))"]))
    np.testing.assert_allclose(native_current, ngspice_current, rtol=5e-6, atol=1e-12)


def test_native_rfm_transient_matches_ngspice_code_model(tmp_path: Path) -> None:
    rfm = tmp_path / "complex.rfm"
    deck = tmp_path / "complex.sp"
    write_cadence_rfm(_ComplexOnePort(), rfm, z0=50.0)
    deck.write_text(
        """RFM native transient differential
Xchannel p 0 rfm_direct
Vsrc src 0 PULSE(0 1 100p 20p 20p 500p 1n)
Rsrc src p 50
Rload p 0 50
.tran 2p 2n 0 2p
.print tran v(p)
.end
""",
        encoding="ascii",
    )

    artifacts = prepare_rfm_run(deck, rfm, output_root=tmp_path / "runs")
    native = _run_native(artifacts.deck_path, artifacts.runtime_rfm_path)
    native_time = np.array([point["x"] for point in native["points"]], dtype=float)
    native_voltage = np.array([point["values"]["p"] for point in native["points"]], dtype=float)

    ngspice = execute_rfm_run(artifacts)
    assert ngspice.ok, ngspice.stdout + ngspice.stderr
    ngspice_wave = np.genfromtxt(artifacts.run_dir / "waveform.csv", delimiter=",", names=True)
    expected_voltage = np.interp(native_time, ngspice_wave["time"], ngspice_wave["vp"])

    np.testing.assert_allclose(native_voltage, expected_voltage, rtol=2e-3, atol=2e-4)


def test_native_rfm_gear2_matches_ngspice_expanded_state_model(tmp_path: Path) -> None:
    rfm = tmp_path / "complex.rfm"
    deck = tmp_path / "complex_gear.sp"
    macro = tmp_path / "complex_macro.sp"
    oracle_deck = tmp_path / "complex_gear_oracle.sp"
    oracle_waveform = tmp_path / "complex_gear_oracle.dat"
    write_cadence_rfm(_ComplexOnePort(), rfm, z0=50.0)
    model = parse_cadence_rfm(rfm)
    model.write_spice_subcircuit(macro, subcircuit_name="rfm_macro")
    common = """Vsrc src 0 PULSE(0 1 100p 20p 20p 500p 1n)
Rsrc src p 50
Rload p 0 50
.options method=gear reltol=1e-5 trtol=1
.tran 2p 2n 0 2p
"""
    deck.write_text(
        "RFM native variable-step Gear2 differential\n"
        "Xchannel p 0 rfm_direct\n"
        f"{common}.print tran v(p)\n.end\n",
        encoding="ascii",
    )
    oracle_deck.write_text(
        "RFM expanded-state ngspice Gear2 oracle\n"
        f".include '{macro.as_posix()}'\n"
        "Xchannel p rfm_macro\n"
        f"{common}.control\n"
        "set wr_singlescale\n"
        "set wr_vecnames\n"
        "run\n"
        f"wrdata '{oracle_waveform.as_posix()}' time v(p)\n"
        "quit\n"
        ".endc\n"
        ".end\n",
        encoding="ascii",
    )

    native = _run_native(deck, rfm)
    native_time = np.asarray([point["x"] for point in native["points"]], dtype=float)
    native_voltage = np.asarray(
        [point["values"]["p"] for point in native["points"]],
        dtype=float,
    )
    completed = subprocess.run(
        [shutil.which("ngspice") or "ngspice", "-b", str(oracle_deck)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    oracle = np.genfromtxt(oracle_waveform, names=True)
    oracle_voltage = np.interp(native_time, oracle["time"], oracle["vp"])

    np.testing.assert_allclose(native_voltage, oracle_voltage, rtol=2e-3, atol=2e-5)
    assert native["statistics"]["acceptedTransientSteps"] > native_time.size
    assert native["statistics"]["rejectedTransientSteps"] > 0
    assert native["statistics"]["deviceTruncationEvaluations"] > 0


def test_native_rfm_high_q_reflection_gear2_converges_under_step_halving(
    tmp_path: Path,
) -> None:
    rfm = tmp_path / "high_q.rfm"
    write_cadence_rfm(_HighQReflectiveOnePort(), rfm, z0=50.0)

    def run(name: str, step: str) -> dict:
        deck = tmp_path / f"{name}.sp"
        deck.write_text(
            "RFM high-Q reflective Gear2 timestep convergence\n"
            "Xchannel p 0 rfm_direct\n"
            "Vsrc src 0 PULSE(0 1 100p 20p 20p 500p 1n)\n"
            "Rsrc src p 50\n"
            "Rload p 0 50\n"
            ".options method=gear reltol=1e-4 trtol=2\n"
            f".tran {step} 2n 0 {step}\n"
            ".print tran v(p)\n"
            ".end\n",
            encoding="ascii",
        )
        return _run_native(deck, rfm)

    coarse = run("coarse", "5p")
    fine = run("fine", "2.5p")
    coarse_time = np.asarray([point["x"] for point in coarse["points"]], dtype=float)
    coarse_voltage = np.asarray(
        [point["values"]["p"] for point in coarse["points"]],
        dtype=float,
    )
    fine_time = np.asarray([point["x"] for point in fine["points"]], dtype=float)
    fine_voltage = np.asarray(
        [point["values"]["p"] for point in fine["points"]],
        dtype=float,
    )
    aligned_fine = np.interp(coarse_time, fine_time, fine_voltage)

    assert np.all(np.isfinite(coarse_voltage))
    assert np.max(np.abs(coarse_voltage - aligned_fine)) < 2e-4
    assert coarse["statistics"]["deviceTruncationEvaluations"] > coarse_time.size


def test_run_rfm_cli_executes_native_backend_without_code_model(tmp_path: Path) -> None:
    rfm = tmp_path / "complex.rfm"
    deck = tmp_path / "complex.sp"
    write_cadence_rfm(_ComplexOnePort(), rfm, z0=50.0)
    deck.write_text(
        """RFM native CLI
Vdrive p 0 ac 1
Xchannel p 0 rfm_direct
.ac lin 1 1g 1g
.end
""",
        encoding="ascii",
    )

    status = main(
        [
            "run-rfm",
            str(deck),
            "--rfm",
            str(rfm),
            "--backend",
            "native",
            "--native-engine",
            str(DLL),
            "--dotnet",
            shutil.which("dotnet") or "dotnet",
            "--output-root",
            str(tmp_path / "runs"),
            "--execute",
        ]
    )

    assert status == 0
    run_dir = tmp_path / "runs" / "complex" / "rfm_direct"
    summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["backend"] == "agent-spice-native-rfm"
    assert summary["ok"] is True
    assert summary["waveform_rows"] == 1
    assert (run_dir / "native_result.json").is_file()
