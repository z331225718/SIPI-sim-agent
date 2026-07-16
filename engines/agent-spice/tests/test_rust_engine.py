from __future__ import annotations

import json
import math
from pathlib import Path
import subprocess

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
        ".param rval=1k $ parameter comment\n"
        ".subckt branch in out params: r=rval $ subcircuit comment\n"
        "Rbranch in out {r} $ element comment\n"
        ".ends branch $ end comment\n"
        "V1 in 0 1 $ source comment\n"
        "Xload in out branch $ instance comment\n"
        ".inc 'load$part.inc' $ quoted dollar is part of the path\n"
        ".op $ analysis comment\n"
        ".end $ final comment\n",
        encoding="utf-8",
    )

    result = run(deck)

    assert result["points"][0]["analysis"] == "op"
    assert result["points"][0]["values"]["out"] == pytest.approx(0.5)


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
