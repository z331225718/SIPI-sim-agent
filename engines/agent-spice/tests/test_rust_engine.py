from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENGINE = (
    ROOT / "native" / "agent-spice-sim" / "target" / "release" / "agent-spice-sim.exe"
)


pytestmark = pytest.mark.skipif(not ENGINE.is_file(), reason="Rust engine is not built")


def run(deck: Path, *arguments: str | Path) -> dict:
    completed = subprocess.run(
        [str(ENGINE), str(deck), *(str(argument) for argument in arguments)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def test_rust_engine_reports_progress_and_writes_final_streamed_waveform(
    tmp_path: Path,
) -> None:
    deck = tmp_path / "live_output.sp"
    result_json = tmp_path / "result.json"
    waveform_csv = tmp_path / "waveform.csv"
    deck.write_text(
        "live output\n"
        "V1 out 0 1\n"
        "R1 out 0 1k\n"
        ".probe tran v(out)\n"
        ".tran 1n 10n\n"
        ".end\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            str(ENGINE),
            str(deck),
            "--output-json",
            str(result_json),
            "--waveform-csv",
            str(waveform_csv),
        ],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "AGENT_SPICE_PROFILE": "1"},
    )

    assert json.loads(completed.stdout) == {"ok": True, "waveformRows": 11}
    assert result_json.is_file()
    assert len(waveform_csv.read_text(encoding="utf-8").splitlines()) == 12
    assert "TRAN started: 11 output point(s)" in completed.stderr
    assert "TRAN 11/11 (100.0%)" in completed.stderr
    assert "simulation completed" in completed.stderr
    assert "[agent-spice-profile]" in completed.stderr


def test_rust_engine_flushes_waveform_while_transient_is_running(
    tmp_path: Path,
) -> None:
    deck = tmp_path / "interruptible.sp"
    result_json = tmp_path / "result.json"
    waveform_csv = tmp_path / "waveform.csv"
    deck.write_text(
        "interruptible live output\n"
        "V1 out 0 1\n"
        "R1 out 0 1k\n"
        ".probe tran v(out)\n"
        ".tran 1p 10u\n"
        ".end\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [
            str(ENGINE),
            str(deck),
            "--output-json",
            str(result_json),
            "--waveform-csv",
            str(waveform_csv),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    live_lines = []
    try:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if waveform_csv.is_file() and waveform_csv.stat().st_size > 1024:
                live_lines = waveform_csv.read_text(encoding="utf-8").splitlines()
                if len(live_lines) > 10:
                    break
            assert process.poll() is None, "simulation completed before live output was observed"
            time.sleep(0.02)
        assert len(live_lines) > 10, "waveform CSV was not flushed during simulation"
        assert process.poll() is None
    finally:
        if process.poll() is None:
            process.terminate()
        _, stderr = process.communicate(timeout=10)

    assert live_lines[0].startswith("time,")
    assert not result_json.exists()
    assert "streaming waveform CSV" in stderr
    assert "TRAN started" in stderr


def test_rust_engine_streams_waveform_without_full_json(tmp_path: Path) -> None:
    deck = tmp_path / "waveform_only.sp"
    waveform_csv = tmp_path / "waveform.csv"
    deck.write_text(
        "waveform only\n"
        "V1 out 0 1\n"
        "R1 out 0 1k\n"
        ".probe tran v(out)\n"
        ".tran 1n 10n\n"
        ".end\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [str(ENGINE), str(deck), "--waveform-csv", str(waveform_csv)],
        capture_output=True,
        text=True,
        check=True,
    )

    summary = json.loads(completed.stdout)
    assert summary["ok"] is True
    assert summary["waveformRows"] == 11
    assert "points" not in summary
    assert summary["statistics"]["acceptedTransientSteps"] == 10
    assert len(waveform_csv.read_text(encoding="utf-8").splitlines()) == 12
    assert "full waveform points are not retained" in completed.stderr


def test_rust_engine_reuses_dyadic_transient_factors(tmp_path: Path) -> None:
    deck = tmp_path / "factor_cache.sp"
    waveform_csv = tmp_path / "waveform.csv"
    deck.write_text(
        "Transient factor cache regression\n"
        "Vdrive supply 0 PULSE(0 1 0 0.2n 0.2n 40n 100n)\n"
        "L1 supply n1 1n\n"
        "R1 n1 n2 10m\n"
        "C1 n2 0 100p\n"
        "L2 n2 n3 2n\n"
        "R2 n3 n4 20m\n"
        "C2 n4 0 200p\n"
        "Rload n4 0 2\n"
        ".tran 1n 100n\n"
        ".probe tran v(n2) v(n4)\n"
        ".end\n",
        encoding="utf-8",
    )

    result = run(deck, "--waveform-csv", waveform_csv)

    assert result["waveformRows"] == 101
    statistics = result["statistics"]
    assert statistics["acceptedTransientSteps"] > 100
    assert statistics["sparseSymbolicFactorizations"] == 1
    assert statistics["sparseNumericRefactorizations"] <= 32


def test_rust_engine_operating_point_and_dc_sweep() -> None:
    result = run(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "divider.cir")
    operating_point = result["points"][0]
    assert operating_point["analysis"] == "op"
    assert operating_point["values"] == pytest.approx(
        {"in": 5.0, "out": 2.5, "V1": -2.5e-3}
    )
    sweep = [point for point in result["points"] if point["analysis"] == "dc"]
    assert [point["x"] for point in sweep] == pytest.approx(range(6))
    assert [point["values"]["out"] for point in sweep] == pytest.approx(
        [0.5 * value for value in range(6)]
    )
    assert result["statistics"]["sparseNumericRefactorizations"] == 1


def test_rust_engine_pi_op_dc_ac_and_tran_match_equations_and_hspice_gate() -> None:
    result = run(ROOT / "tests" / "fixtures" / "hspice" / "rust_linear_pi.sp")
    points = result["points"]
    operating_point = next(point for point in points if point["analysis"] == "op")
    assert operating_point["values"]["load"] == pytest.approx(0.7998, abs=1e-13)

    dc = min(
        (point for point in points if point["analysis"] == "dc"),
        key=lambda point: abs(point["x"] - 0.8),
    )
    assert dc["values"]["load"] == pytest.approx(0.7998, abs=1e-13)

    ac = min(
        (point for point in points if point["analysis"] == "ac"),
        key=lambda point: abs(point["x"] - 1e6),
    )
    actual = complex(ac["complex"]["load"]["re"], ac["complex"]["load"]["im"])
    omega = 2.0 * math.pi * 1e6
    capacitor_impedance = 1.0 / complex(0.0, omega * 100e-6)
    expected = capacitor_impedance / (
        2e-3 + complex(0.0, omega * 500e-12) + capacitor_impedance
    )
    assert actual == pytest.approx(expected, rel=2e-12, abs=2e-12)

    transient = [point for point in points if point["analysis"] == "tran"]
    assert len(transient) == 501
    assert transient[-1]["x"] == pytest.approx(5e-9)
    minimum = min(
        point["values"]["load"] for point in transient if point["x"] >= 1e-9
    )
    assert minimum == pytest.approx(0.7994879, abs=2e-6)
    assert result["statistics"]["acceptedTransientSteps"] >= 500
    assert result["statistics"]["deviceTruncationEvaluations"] >= 500
    assert result["statistics"]["sparseSymbolicFactorizations"] == 2
    measurements = {item["name"]: item["value"] for item in result["measurements"]}
    assert measurements == pytest.approx(
        {
            "dc_load": 0.7998,
            "ac_load_mag": 0.6289857315365447,
            "ac_load_phase": -127.77645789461688,
            "min_vload": 0.7994879636993573,
        }
    )


def test_rust_engine_resolves_relative_include_for_pi_deck() -> None:
    result = run(
        ROOT
        / "tests"
        / "fixtures"
        / "hspice"
        / "corpus"
        / "vrm_decap_pdn"
        / "vrm_decap_pdn.sp"
    )
    assert result["nodes"] == ["load", "vdd", "rail"]
    assert len(result["points"]) == 501
    assert result["statistics"]["sparseSymbolicFactorizations"] == 1


def test_rust_engine_accepts_native_hspice_directives_without_conversion(
    tmp_path: Path,
) -> None:
    models = tmp_path / "models"
    models.mkdir()
    (models / "load.inc").write_text("Rload out 0 1k\n", encoding="utf-8")
    deck = tmp_path / "native_hspice.sp"
    deck.write_text(
        "native HSPICE syntax\n"
        ".inc 'models/load.inc'\n"
        "V1 out 0 PULSE(0 1 2p 1p 1p 4p 10p)\n"
        ".option post=2 nomod method=gear\n"
        ".probe tran v(out)\n"
        ".tran 1p 10p\n"
        ".end\n",
        encoding="utf-8",
    )

    result = run(deck)

    points = [point for point in result["points"] if point["analysis"] == "tran"]
    assert len(points) == 11
    assert points[0]["values"] == {"out": pytest.approx(0.0)}
    assert points[4]["values"] == {"out": pytest.approx(1.0)}


def test_rust_engine_accepts_hspice_dollar_comments(tmp_path: Path) -> None:
    (tmp_path / "load$part.inc").write_text(
        "Rground out 0 1k $ comment in included deck\n",
        encoding="utf-8",
    )
    deck = tmp_path / "dollar_comments.sp"
    deck.write_text(
        "native HSPICE dollar comments $ title comment\n"
        "$ full-line comment containing .fft v(out)\n"
        ".param vddc      =       1    rval   =    1k $ spaced HSPICE assignments\n"
        ".subckt branch in out params: r      =      rval $ subcircuit comment\n"
        "Rbranch in out {r} $ element comment\n"
        ".ends branch $ end comment\n"
        "V1 in 0 {vddc} $ source comment\n"
        "Xload in out branch r        =        2k $ instance override comment\n"
        ".inc 'load$part.inc' $ quoted dollar is part of the path\n"
        ".op $ analysis comment\n"
        ".end $ final comment\n",
        encoding="utf-8",
    )

    result = run(deck)

    assert result["points"][0]["analysis"] == "op"
    assert result["points"][0]["values"]["out"] == pytest.approx(1.0 / 3.0)


def test_rust_engine_accepts_hspice_string_params_and_conditionals(
    tmp_path: Path,
) -> None:
    deck = tmp_path / "string_params_and_conditionals.sp"
    deck.write_text(
        "native HSPICE string parameters and conditionals\n"
        ".param num_nop_vdda=1 num_nop_vddio1=1 len_nop=100n\n"
        ".if ( ('num_nop_vdda*len_nop' < 200n) && "
        "('num_nop_vddio1*len_nop' < 200n) )\n"
        ".param delay1=200n\n"
        ".param vdda_read10ns      =      "
        "str('FF_125deg_0p935_0p44_VDDA_read10ns_delay200ns.csv')\n"
        ".param branch_resistance=1k\n"
        ".else\n"
        ".param delay1=400n\n"
        ".param vdda_read10ns=str('wrong_branch.csv')\n"
        ".param branch_resistance=2k\n"
        ".endif\n"
        "V1 in 0 1\n"
        "Rseries in out branch_resistance\n"
        "Rload out 0 1k\n"
        ".op\n"
        ".end\n",
        encoding="utf-8",
    )

    result = run(deck)

    assert result["points"][0]["values"]["out"] == pytest.approx(0.5)


def test_rust_engine_evaluates_subcircuit_local_hspice_conditionals(
    tmp_path: Path,
) -> None:
    deck = tmp_path / "subcircuit_conditionals.sp"
    deck.write_text(
        "subcircuit-local HSPICE conditionals\n"
        ".param selected_mode=2\n"
        ".subckt branch in out params: mode=selected_mode\n"
        ".if ('mode' = 1)\n"
        ".param resistance=1k source_file=str('mode1.csv')\n"
        ".elseif ('mode' = 2)\n"
        ".param resistance=2k source_file=str('mode2.csv')\n"
        ".else\n"
        ".param resistance=4k source_file=str('fallback.csv')\n"
        ".endif\n"
        "Rbranch in out resistance\n"
        ".ends branch\n"
        "V1 in 0 1\n"
        "Xbranch in out branch\n"
        "Rload out 0 1k\n"
        ".op\n"
        ".end\n",
        encoding="utf-8",
    )

    result = run(deck)

    assert result["points"][0]["values"]["out"] == pytest.approx(1.0 / 3.0)


@pytest.mark.parametrize(
    ("option", "expected"),
    [
        ("", 1.0 / (1.0 + 1e-5)),
        (".option resmin=100m\n", 1.0 / 1.1),
    ],
)
def test_rust_engine_applies_hspice_resmin_to_zero_ohm_dummy_resistors(
    tmp_path: Path,
    option: str,
    expected: float,
) -> None:
    deck = tmp_path / "zero_ohm_dummy.sp"
    deck.write_text(
        "HSPICE zero-ohm dummy resistor\n"
        f"{option}"
        ".subckt branch in out params: random=0\n"
        "Ran in out 'random'\n"
        ".ends branch\n"
        "V1 in 0 1\n"
        "Xdummy in out branch\n"
        "Rload out 0 1\n"
        ".op\n"
        ".end\n",
        encoding="utf-8",
    )

    result = run(deck)

    assert result["points"][0]["values"]["out"] == pytest.approx(expected)


def test_rust_engine_accepts_hspice_named_passive_values(tmp_path: Path) -> None:
    deck = tmp_path / "named_passive_values.sp"
    deck.write_text(
        "HSPICE named passive values\n"
        ".subckt branch in out params: resistance=2k capacitance=1p inductance=1n\n"
        "Rinline in middle r='resistance'\n"
        "Rspaced middle out r   =   'resistance'\n"
        "Cnamed middle 0 c='capacitance'\n"
        "Lnamed middle sense l = 'inductance'\n"
        "Rsense sense 0 1e18\n"
        ".ends branch\n"
        "V1 in 0 1\n"
        "Xbranch in out branch\n"
        "Rload out 0 4k\n"
        ".op\n"
        ".end\n",
        encoding="utf-8",
    )

    result = run(deck)

    assert result["points"][0]["values"]["out"] == pytest.approx(0.5)


def test_rust_engine_resolves_top_parameter_declared_after_instance(
    tmp_path: Path,
) -> None:
    child = tmp_path / "connector.spi"
    child.write_text(
        ".subckt connector in out\n"
        "Rconnector in out connector_resistance\n"
        ".ends connector\n",
        encoding="utf-8",
    )
    deck = tmp_path / "forward_parameter.sp"
    deck.write_text(
        "HSPICE forward parameter declaration\n"
        ".include 'connector.spi'\n"
        "Xconnector in out connector\n"
        ".param connector_resistance=2k\n"
        "V1 in 0 1\n"
        "Rload out 0 2k\n"
        ".op\n"
        ".end\n",
        encoding="utf-8",
    )

    result = run(deck)

    assert result["points"][0]["values"]["out"] == pytest.approx(0.5)


def test_rust_engine_resolves_local_parameter_declared_after_element(
    tmp_path: Path,
) -> None:
    deck = tmp_path / "forward_local_parameter.sp"
    deck.write_text(
        "HSPICE forward subcircuit parameter declaration\n"
        ".subckt leaf in out\n"
        "Rleaf in out connector_resistance\n"
        ".ends leaf\n"
        ".subckt connector in out\n"
        "Xleaf in out leaf\n"
        ".param connector_resistance=2k\n"
        ".ends connector\n"
        "Xconnector in out connector\n"
        "V1 in 0 1\n"
        "Rload out 0 2k\n"
        ".op\n"
        ".end\n",
        encoding="utf-8",
    )

    result = run(deck)

    assert result["points"][0]["values"]["out"] == pytest.approx(0.5)


def test_rust_engine_audits_all_native_compatibility_issues_at_once(
    tmp_path: Path,
) -> None:
    child = tmp_path / "child.inc"
    child.write_text(
        ".param child_value=1\n"
        "Dunsupported out 0 diode_model\n"
        "Vunsupported out 0 SIN(0 1 1k)\n"
        ".fft v(out)\n",
        encoding="utf-8",
    )
    (tmp_path / "drive.csv").write_text("0,0\n1n,1\n", encoding="utf-8")
    deck = tmp_path / "audit.sp"
    deck.write_text(
        "native compatibility audit\n"
        ".include 'child.inc'\n"
        ".if (1 = 1)\n"
        "Vdrive in 0 PWL PWLFILE='drive.csv' M=1 TD=0 R=0\n"
        ".endif\n"
        "Rload in 0 1k\n"
        ".tran 1p 1n\n"
        ".end\n",
        encoding="utf-8",
    )
    report_path = tmp_path / "native_compatibility.json"

    completed = subprocess.run(
        [str(ENGINE), str(deck), "--audit-json", str(report_path)],
        capture_output=True,
        text=True,
        check=True,
    )

    summary = json.loads(completed.stdout)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert summary == {
        "ok": True,
        "compatible": False,
        "issues": 3,
        "scannedFiles": 2,
    }
    assert {issue["reason"] for issue in report["issues"]} == {
        "unsupported_directive",
        "unsupported_element",
        "unsupported_source_function",
    }
    assert report["statementCounts"][".if"] == 1
    assert report["statementCounts"]["element:V"] == 2


def test_rust_engine_reads_hspice_pwlfile_with_multiplier_delay_and_repeat(
    tmp_path: Path,
) -> None:
    (tmp_path / "drive.csv").write_text(
        "* time,value\n0,0\n1n,1\n2n,0\n",
        encoding="utf-8",
    )
    deck = tmp_path / "pwlfile.sp"
    deck.write_text(
        "native HSPICE PWLFILE\n"
        ".param waveform_file=str('drive.csv')\n"
        ".param repeat_start=0\n"
        "Vdrive out 0 PWL PWLFILE=str(waveform_file) M=2 TD=1n R = 'repeat_start'\n"
        "Rload out 0 1\n"
        ".tran 500p 4n\n"
        ".end\n",
        encoding="utf-8",
    )

    result = run(deck)

    transient = [point for point in result["points"] if point["analysis"] == "tran"]
    samples = {round(point["x"] / 1e-9, 6): point["values"]["out"] for point in transient}
    assert samples[1.0] == pytest.approx(0.0)
    assert samples[2.0] == pytest.approx(2.0)
    assert samples[3.0] == pytest.approx(0.0)
    assert samples[4.0] == pytest.approx(2.0)


def test_rust_engine_reports_included_file_line_statement_and_expansion(
    tmp_path: Path,
) -> None:
    child = tmp_path / "child.inc"
    child.write_text(
        ".subckt branch out\n"
        "Vbad out 0 missing_value\n"
        ".ends branch\n",
        encoding="utf-8",
    )
    deck = tmp_path / "source_location.sp"
    deck.write_text(
        "native source diagnostics\n"
        ".include 'child.inc'\n"
        "Xbad out branch\n"
        "Rload out 0 1\n"
        ".op\n"
        ".end\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [str(ENGINE), str(deck)], capture_output=True, text=True, check=False
    )

    assert completed.returncode != 0
    assert f"{child.resolve()}:2: unknown parameter 'missing_value'" in completed.stderr
    assert "statement: Vbad out 0 missing_value" in completed.stderr
    assert "expanded: Vbad:Xbad out 0 missing_value" in completed.stderr


def test_rust_engine_keeps_source_location_for_late_element_validation(
    tmp_path: Path,
) -> None:
    child = tmp_path / "controlled.inc"
    child.write_text(
        ".subckt controlled out\n"
        "Fbad out 0 Vmissing 1\n"
        ".ends controlled\n",
        encoding="utf-8",
    )
    deck = tmp_path / "late_validation.sp"
    deck.write_text(
        "native late validation diagnostics\n"
        ".include 'controlled.inc'\n"
        "Xbad out controlled\n"
        "Rload out 0 1\n"
        ".op\n"
        ".end\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [str(ENGINE), str(deck)], capture_output=True, text=True, check=False
    )

    assert completed.returncode != 0
    assert f"{child.resolve()}:2: controlling branch 'Vmissing:Xbad' was not found" in completed.stderr
    assert "statement: Fbad out 0 Vmissing 1" in completed.stderr
    assert "expanded: Fbad:Xbad out 0 Vmissing:Xbad 1" in completed.stderr


def test_rust_engine_evaluates_hspice_measurement_operations(tmp_path: Path) -> None:
    deck = tmp_path / "measurements.sp"
    deck.write_text(
        "native HSPICE measurements\n"
        "V1 out 0 0\n"
        ".dc V1 0 4 1\n"
        ".measure dc find_v find v(out) at=2\n"
        ".measure dc min_v min v(out) from=1 to=3\n"
        ".measure dc max_v max v(out) from=1 to=3\n"
        ".measure dc avg_v avg v(out) from=1 to=3\n"
        ".measure dc rms_v rms v(out) from=1 to=3\n"
        ".end\n",
        encoding="utf-8",
    )

    result = run(deck)

    measurements = {item["name"]: item["value"] for item in result["measurements"]}
    assert measurements == pytest.approx(
        {
            "find_v": 2.0,
            "min_v": 1.0,
            "max_v": 3.0,
            "avg_v": 2.0,
            "rms_v": math.sqrt(4.5),
        }
    )


def test_rust_engine_evaluates_hspice_event_measurements() -> None:
    result = run(
        ROOT / "tests" / "fixtures" / "hspice" / "rust_measure_events.sp"
    )
    measurements = {item["name"]: item["value"] for item in result["measurements"]}
    assert measurements == pytest.approx(
        {
            "when_rise": 2.5e-9,
            "when_fall": 1.5e-9,
            "when_cross": 3.5e-9,
            "when_last": 3.5e-9,
            "when_td": 2.5e-9,
            "sampled": 2.5,
            "delay": 1.5e-9,
            "delay_at": 1.0e-9,
            "param_norm": 1.0,
            "param_chain": 3.5,
            "param_func": 2.5,
            "param_si": 3.0,
            "deriv_at": 1.0e9,
            "deriv_when": 1.0e9,
            "integ_target": 4.0e-9,
            "integ_signal": 2.0e-9,
        },
        abs=1e-15,
        rel=1e-12,
    )
    transient = next(point for point in result["points"] if point["analysis"] == "tran")
    assert "signal" in transient["values"]


def test_rust_engine_reports_missing_hspice_measurement_event(tmp_path: Path) -> None:
    deck = tmp_path / "missing_event.sp"
    deck.write_text(
        "missing event diagnostic\n"
        "V1 out 0 PWL(0 0 1n 1)\n"
        ".tran 100p 1n\n"
        ".measure tran missing WHEN v(out)=2 RISE=1\n"
        ".end\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [str(ENGINE), str(deck)], capture_output=True, text=True, check=False
    )

    assert completed.returncode != 0
    assert "did not find RISE=1" in completed.stderr


def test_rust_engine_rejects_forward_measurement_param_reference(tmp_path: Path) -> None:
    deck = tmp_path / "forward_measurement_param.sp"
    deck.write_text(
        "forward PARAM diagnostic\n"
        "V1 out 0 1\n"
        ".op\n"
        ".measure op first PARAM='second+1'\n"
        ".measure op second PARAM='1'\n"
        ".end\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [str(ENGINE), str(deck)], capture_output=True, text=True, check=False
    )

    assert completed.returncode != 0
    assert ".measure 'first' PARAM expression failed" in completed.stderr
    assert "unknown parameter 'second'" in completed.stderr


def test_rust_engine_rejects_duplicate_measurement_name(tmp_path: Path) -> None:
    deck = tmp_path / "duplicate_measurement.sp"
    deck.write_text(
        "duplicate measurement diagnostic\n"
        "V1 out 0 1\n"
        ".op\n"
        ".measure op result FIND v(out)\n"
        ".measure op RESULT PARAM='1'\n"
        ".end\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [str(ENGINE), str(deck)], capture_output=True, text=True, check=False
    )

    assert completed.returncode != 0
    assert "duplicate .measure name 'RESULT'" in completed.stderr


def test_rust_engine_controlled_sources_cover_all_analyses() -> None:
    result = run(ROOT / "tests" / "fixtures" / "hspice" / "rust_controlled_sources.sp")
    expected = {"eout": 3.0, "gout": -2.0, "fout": -2.0, "hout": 0.5}
    dc = min(
        (point for point in result["points"] if point["analysis"] == "dc"),
        key=lambda point: abs(point["x"] - 1.0),
    )
    assert {name: dc["values"][name] for name in expected} == pytest.approx(expected)

    ac = min(
        (point for point in result["points"] if point["analysis"] == "ac"),
        key=lambda point: abs(point["x"] - 1e6),
    )
    assert {name: ac["complex"][name]["re"] for name in expected} == pytest.approx(expected)
    assert all(ac["complex"][name]["im"] == pytest.approx(0.0) for name in expected)

    transient = min(
        (point for point in result["points"] if point["analysis"] == "tran"),
        key=lambda point: abs(point["x"] - 1.2e-9),
    )
    assert {name: transient["values"][name] for name in expected} == pytest.approx(expected)
    assert result["statistics"]["sparseSymbolicFactorizations"] == 2


def test_rust_engine_rfm_ac_and_transient_match_reference_model() -> None:
    rfm = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "one_port.rfm"
    ac = run(
        ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "rfm_ac.cir",
        "--rfm",
        rfm,
    )
    sample = ac["points"][0]["complex"]["Vdrive"]
    actual_current = complex(sample["re"], sample["im"])
    frequency = 1e9
    s = 2j * math.pi * frequency
    s11 = (
        0.1
        + 0.5e9 / (s + 2e9)
        + (0.2e9 + 0.3e9j) / (s - (-3e9 + 4e9j))
        + (0.2e9 - 0.3e9j) / (s - (-3e9 - 4e9j))
    )
    expected_current = -(1.0 - s11) / (1.0 + s11) / 50.0
    assert actual_current == pytest.approx(expected_current, rel=2e-12, abs=1e-14)

    transient = run(
        ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "rfm_tran.cir",
        "--rfm",
        rfm,
    )
    points = transient["points"]
    assert len(points) == 1001
    # Values are cross-checked against the established C# RFM implementation.
    references = {
        60: 0.35669493772084676,
        100: 0.3680274624648327,
        310: 0.38152246317051225,
        500: 0.0046197231239702066,
        1000: 0.006769103008000894,
    }
    for index, expected_voltage in references.items():
        assert points[index]["values"]["p"] == pytest.approx(
            expected_voltage, abs=2e-4
        )


def test_rust_engine_runs_hspice_s_model_with_relative_rfmfile(
    tmp_path: Path,
) -> None:
    source_rfm = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "one_port.rfm"
    shutil.copy2(source_rfm, tmp_path / "channel.rfm")
    deck = tmp_path / "native_s_model.sp"
    deck.write_text(
        "HSPICE native S model\n"
        ".model channel_offdie s n=1 rfmfile='channel.rfm'\n"
        "Vreference ref 0 0.3\n"
        "Vdrive p ref AC 1\n"
        "Schannel_offdie p ref mname=channel_offdie\n"
        ".ac lin 1 1g 1g\n"
        ".end\n",
        encoding="utf-8",
    )

    native = run(deck)
    command_line = run(
        ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "rfm_ac.cir",
        "--rfm",
        source_rfm,
    )

    assert native["points"][0]["complex"]["Vdrive"] == pytest.approx(
        command_line["points"][0]["complex"]["Vdrive"]
    )

    transient_deck = tmp_path / "native_s_model_tran.sp"
    transient_deck.write_text(
        "HSPICE native S model transient\n"
        ".model channel_offdie s n=1 rfmfile='channel.rfm'\n"
        "Vreference ref 0 0.2\n"
        "Schannel_offdie p ref mname=channel_offdie\n"
        "Vsrc src ref PULSE(0 1 100p 20p 20p 500p 1n)\n"
        "Rsrc src p 50\n"
        "Rload p ref 50\n"
        ".tran 2p 2n\n"
        ".end\n",
        encoding="utf-8",
    )
    native_transient = run(transient_deck)
    command_line_transient = run(
        ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "rfm_tran.cir",
        "--rfm",
        source_rfm,
    )

    for index in (60, 310, 1000):
        native_point = native_transient["points"][index]["values"]
        assert native_point["p"] - native_point["ref"] == pytest.approx(
            command_line_transient["points"][index]["values"]["p"],
            abs=1e-12,
        )


def test_rust_engine_accepts_hspice_s_model_common_reference_ports(
    tmp_path: Path,
) -> None:
    blocks = []
    for row in range(1, 3):
        for column in range(1, 3):
            constant = 0.1 if row == column else 0.0
            blocks.extend(
                (
                    f"BEGIN {row} {column}",
                    f"CONST {constant:.12e}",
                    "C 0.000000000000e+00",
                    "DELAY 0.000000000000e+00",
                    "BEGIN_REAL 0",
                    "BEGIN_COMPLEX 0",
                    "END",
                )
            )
    (tmp_path / "two_port.rfm").write_text(
        "\n".join(
            (
                "VERSION 200600",
                "NPORT 2",
                "MATRIX_TYPE S",
                "Z0 5.000000000000e+01",
                *blocks,
                "",
            )
        ),
        encoding="ascii",
    )

    def write_deck(path: Path, s_nodes: str) -> None:
        path.write_text(
            "HSPICE two-port common reference\n"
            ".model channel s n=2 rfmfile='two_port.rfm'\n"
            "Vdrive p1 0 AC 1\n"
            f"Schannel {s_nodes} mname=channel\n"
            ".ac lin 1 1g 1g\n"
            ".end\n",
            encoding="utf-8",
        )

    paired = tmp_path / "paired.sp"
    common = tmp_path / "common.sp"
    write_deck(paired, "p1 0 p2 0")
    write_deck(common, "p1 p2 0")

    paired_result = run(paired)
    common_result = run(common)

    assert common_result["points"][0]["complex"]["Vdrive"] == pytest.approx(
        paired_result["points"][0]["complex"]["Vdrive"]
    )


def test_rust_engine_rfm_gear2_matches_migration_oracle() -> None:
    rfm = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "one_port.rfm"
    result = run(
        ROOT / "tests" / "fixtures" / "hspice" / "rust_rfm_gear.sp",
        "--rfm",
        rfm,
    )
    points = [point for point in result["points"] if point["analysis"] == "tran"]
    references = {
        60: 0.35669493772084676,
        100: 0.368027697082876,
        310: 0.38152267753818636,
        500: 0.004619170424146765,
        821: 0.029776288388650898,
        1000: 0.006768559147507262,
    }
    for index, expected_voltage in references.items():
        assert points[index]["values"]["p"] == pytest.approx(
            expected_voltage, abs=2e-4
        )
    assert result["statistics"]["acceptedTransientSteps"] >= 1000
    assert result["statistics"]["rejectedTransientSteps"] >= 1
    assert result["statistics"]["deviceTruncationEvaluations"] > 1000


def test_rust_engine_rfm_strict_lte_rejects_and_rolls_back(tmp_path: Path) -> None:
    source = ROOT / "tests" / "fixtures" / "hspice" / "rust_rfm_gear.sp"
    strict_deck = tmp_path / "strict_rfm_gear.sp"
    strict_deck.write_text(
        source.read_text(encoding="utf-8").replace(
            ".options method=gear",
            ".options method=gear reltol=1e-5 trtol=1",
        ),
        encoding="utf-8",
    )
    rfm = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "one_port.rfm"
    baseline = run(source, "--rfm", rfm)
    strict = run(strict_deck, "--rfm", rfm)
    baseline_points = [
        point for point in baseline["points"] if point["analysis"] == "tran"
    ]
    strict_points = [
        point for point in strict["points"] if point["analysis"] == "tran"
    ]
    assert [point["x"] for point in strict_points] == pytest.approx(
        [point["x"] for point in baseline_points]
    )
    assert strict["statistics"]["rejectedTransientSteps"] > baseline["statistics"][
        "rejectedTransientSteps"
    ]
    assert max(
        abs(strict_point["values"]["p"] - baseline_point["values"]["p"])
        for strict_point, baseline_point in zip(strict_points, baseline_points, strict=True)
    ) < 2e-6


def test_rust_engine_gear2_schedules_off_grid_pwl_breakpoints() -> None:
    result = run(
        ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "pwl_tran_gear.cir"
    )
    points = result["points"]
    assert len(points) == 31
    assert result["statistics"]["acceptedTransientSteps"] >= 33
    assert result["statistics"]["rejectedTransientSteps"] >= 1
    assert result["statistics"]["breakpointTransientSteps"] == 4
    assert points[-1]["values"]["output"] == pytest.approx(
        0.41144319287035147, abs=5e-3
    )


def test_rust_engine_flattens_nested_parameterized_subcircuits() -> None:
    result = run(
        ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "subckt_param.cir"
    )
    points = result["points"]
    operating_point = next(point for point in points if point["analysis"] == "op")
    dc = min(
        (point for point in points if point["analysis"] == "dc"),
        key=lambda point: abs(point["x"] - 1.0),
    )
    ac = max(
        (point for point in points if point["analysis"] == "ac"),
        key=lambda point: point["x"],
    )
    transient = max(
        (point for point in points if point["analysis"] == "tran"),
        key=lambda point: point["x"],
    )
    assert operating_point["values"]["output"] == pytest.approx(7.0 / 15.0)
    assert dc["values"]["output"] == pytest.approx(5.0 / 3.0)
    assert ac["complex"]["output"] == pytest.approx({"re": 1.6, "im": 0.0})
    assert transient["values"]["output"] == pytest.approx(7.0 / 15.0)
    assert "Xamplifier:Xinner:buffer" in result["nodes"]


def test_rust_engine_selects_relative_library_section_and_flattens_include() -> None:
    result = run(
        ROOT
        / "tests"
        / "fixtures"
        / "hspice"
        / "corpus"
        / "include_lib_subckt"
        / "include_lib_subckt.sp"
    )
    points = [point for point in result["points"] if point["analysis"] == "tran"]
    assert len(points) == 1001
    assert result["nodes"] == ["rail"]
    assert all(point["values"]["rail"] == pytest.approx(0.8) for point in points)
