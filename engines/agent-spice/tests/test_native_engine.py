from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
DLL = ROOT / "native" / "AgentSpice.Engine" / "bin" / "Release" / "net8.0" / "AgentSpice.Engine.dll"


def _has_sdk() -> bool:
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        return False
    result = subprocess.run([dotnet, "--list-sdks"], capture_output=True, text=True, check=False)
    return bool(result.stdout.strip())


pytestmark = pytest.mark.skipif(not _has_sdk() or not DLL.exists(), reason="native engine is not built")


def _run(deck: str) -> dict:
    return _run_path(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / deck)


def _run_path(deck: Path) -> dict:
    result = subprocess.run(
        [shutil.which("dotnet") or "dotnet", str(DLL), str(deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _run_path_with_environment(deck: Path, **overrides: str) -> dict:
    environment = dict(os.environ)
    environment.update(overrides)
    result = subprocess.run(
        [shutil.which("dotnet") or "dotnet", str(DLL), str(deck)],
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    )
    return json.loads(result.stdout)


def _single_analysis_deck(tmp_path: Path, fixture: str, analysis: str) -> Path:
    source = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / fixture
    target = tmp_path / f"{source.stem}-{analysis}.cir"
    analyses = {".op", ".dc", ".ac", ".tran"}
    lines = []
    for line in source.read_text(encoding="ascii").splitlines():
        fields = line.lower().split()
        head = fields[0] if fields else ""
        if head in analyses and head != f".{analysis}":
            continue
        if head == ".print" and fields[1] != analysis:
            continue
        lines.append(line)
    target.write_text("\n".join(lines) + "\n", encoding="ascii")
    return target


def _ngspice_columns(stdout: str, analysis: str) -> dict[str, list[tuple[float, complex]]]:
    lines = stdout.splitlines()
    columns: dict[str, list[tuple[float, complex]]] = {}
    axis_names = {"frequency", "time", "v-sweep"}
    for line_index, line in enumerate(lines):
        fields = line.split()
        if not fields or fields[0] != "Index":
            continue
        headers = [field.lower() for field in fields[1:]]
        has_axis = bool(headers and headers[0] in axis_names)
        value_headers = headers[1:] if has_axis else headers
        for header in value_headers:
            columns.setdefault(header, [])
        saw_row = False
        for row in lines[line_index + 1 :]:
            row_fields = row.split()
            if not row_fields or not row_fields[0].isdigit():
                if saw_row:
                    break
                continue
            numeric = [float(field.rstrip(",")) for field in row_fields[1:]]
            axis = numeric[0] if has_axis else 0.0
            values = numeric[1:] if has_axis else numeric
            if analysis == "ac":
                assert len(values) >= 2 * len(value_headers)
                for index, header in enumerate(value_headers):
                    columns[header].append((axis, complex(values[2 * index], values[2 * index + 1])))
            else:
                assert len(values) >= len(value_headers)
                for index, header in enumerate(value_headers):
                    columns[header].append((axis, complex(values[index], 0.0)))
            saw_row = True
    return columns


def _interpolate_complex(waveform: list[tuple[float, complex]], x: float) -> complex:
    for left, right in zip(waveform, waveform[1:]):
        if right[0] >= x:
            fraction = (x - left[0]) / (right[0] - left[0])
            return left[1] + fraction * (right[1] - left[1])
    return waveform[-1][1]


def _write_pdn_mesh_deck(path: Path, analysis: str, *, side: int = 8, points: int = 13) -> tuple[str, ...]:
    source = "Vdrive supply 0 ac 1" if analysis == "ac" else (
        "Vdrive supply 0 PULSE(0 1 0 0.2n 0.2n 40n 100n)"
    )
    lines = [
        f"Native regression {side}x{side} branched RLC PDN mesh",
        source,
        *(f"Lrow{row} supply row{row} 1n" for row in range(side)),
        *(f"Rentry{row} row{row} n{row}_0 5m" for row in range(side)),
    ]
    resistor = 0
    for row in range(side):
        for column in range(side):
            node = f"n{row}_{column}"
            capacitance_pf = 50 + 25 * ((row * 3 + column * 5) % 5)
            lines.append(f"C{row}_{column} {node} 0 {capacitance_pf}p")
            if column + 1 < side:
                resistance_milliohms = 15 + ((row + column) % 4) * 5
                lines.append(f"Rh{resistor} {node} n{row}_{column + 1} {resistance_milliohms}m")
                resistor += 1
            if row + 1 < side:
                resistance_milliohms = 20 + ((row * 2 + column) % 4) * 5
                lines.append(f"Rv{resistor} {node} n{row + 1}_{column} {resistance_milliohms}m")
                resistor += 1
        lines.append(f"Rload{row} n{row}_{side - 1} 0 {2 + row % 5}")
    probes = (f"n0_{side - 1}", f"n{side // 2}_{side // 2}", f"n{side - 1}_{side - 1}")
    print_nodes = " ".join(f"v({node})" for node in probes)
    if analysis == "ac":
        lines.extend([f".ac lin {points} 1k 1g", f".print ac {print_nodes}"])
    else:
        lines.extend([f".tran 1n {points - 1}n", f".print tran {print_nodes}"])
    lines.extend([".end", ""])
    path.write_text("\n".join(lines), encoding="ascii")
    return probes


def test_native_dc_divider_matches_hand_calculation() -> None:
    result = _run("divider.cir")
    op = result["points"][0]
    assert op["values"]["in"] == pytest.approx(5.0)
    assert op["values"]["out"] == pytest.approx(2.5)
    dc = [point for point in result["points"] if point["analysis"] == "dc"]
    assert dc[0]["values"]["out"] == pytest.approx(0.0)
    assert dc[-1]["values"]["out"] == pytest.approx(2.5)


def test_native_rc_ac_and_transient_are_finite() -> None:
    result = _run("rc.cir")
    ac = [point for point in result["points"] if point["analysis"] == "ac"]
    tran = [point for point in result["points"] if point["analysis"] == "tran"]
    assert len(ac) == 3
    assert len(tran) == 4
    assert all(point["complex"]["out"]["im"] <= 0.0 for point in ac)
    assert tran[-1]["values"]["out"] > tran[0]["values"]["out"]


def test_native_sparse_mna_solves_large_resistor_ladder(tmp_path: Path) -> None:
    sections = 256
    deck = tmp_path / "ladder.cir"
    lines = [
        "Sparse MNA resistor ladder",
        "Vdrive n0 0 1",
        *(f"R{index + 1} n{index} n{index + 1} 1" for index in range(sections)),
        f"Rload n{sections} 0 1",
        ".op",
        f".print op v(n{sections})",
        ".end",
        "",
    ]
    deck.write_text("\n".join(lines), encoding="ascii")

    completed = subprocess.run(
        [shutil.which("dotnet") or "dotnet", str(DLL), str(deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(completed.stdout)

    assert result["points"][0]["values"][f"n{sections}"] == pytest.approx(1.0 / (sections + 1))


def test_native_sparse_ac_reuses_symbolic_fill_without_changing_results(tmp_path: Path) -> None:
    sections = 80
    deck = tmp_path / "sparse-rc-ac.cir"
    lines = [
        "Sparse AC symbolic reuse",
        "Vdrive n0 0 ac 1",
        *(f"R{index + 1} n{index} n{index + 1} 10" for index in range(sections)),
        *(f"C{index} n{index} 0 1p" for index in range(1, sections + 1)),
        f"Rload n{sections} 0 1k",
        ".ac lin 17 1k 10meg",
        f".print ac v(n{sections})",
        ".end",
        "",
    ]
    deck.write_text("\n".join(lines), encoding="ascii")

    cached = _run_path(deck)
    uncached_environment = dict(os.environ)
    uncached_environment["AGENT_SPICE_NATIVE_DISABLE_SYMBOLIC_REUSE"] = "1"
    completed = subprocess.run(
        [shutil.which("dotnet") or "dotnet", str(DLL), str(deck)],
        capture_output=True,
        text=True,
        check=True,
        env=uncached_environment,
    )
    uncached = json.loads(completed.stdout)

    statistics = cached["statistics"]
    assert statistics["sparseSymbolicFactorizations"] == 1
    assert statistics["sparseNumericRefactorizations"] == 16
    assert statistics["sparsePlanFallbacks"] == 0
    assert statistics["acMatrixAssemblyReplays"] == 15
    output = f"n{sections}"
    assert [point["x"] for point in cached["points"]] == pytest.approx(
        [point["x"] for point in uncached["points"]],
        rel=1e-14,
    )
    assert [
        complex(point["complex"][output]["re"], point["complex"][output]["im"])
        for point in cached["points"]
    ] == pytest.approx(
        [
            complex(point["complex"][output]["re"], point["complex"][output]["im"])
            for point in uncached["points"]
        ],
        rel=2e-12,
        abs=1e-13,
    )

    ngspice = shutil.which("ngspice")
    if ngspice is None:
        return
    oracle_run = subprocess.run(
        [ngspice, "-b", str(deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(oracle_run.stdout, "ac")[f"v({output})"]
    assert [point["x"] for point in cached["points"]] == pytest.approx(
        [point[0] for point in oracle],
        rel=2e-6,
    )
    assert [
        complex(point["complex"][output]["re"], point["complex"][output]["im"])
        for point in cached["points"]
    ] == pytest.approx([point[1] for point in oracle], rel=3e-5, abs=2e-6)


def test_native_sparse_transient_reuses_real_symbolic_fill(tmp_path: Path) -> None:
    branches = 64
    deck = tmp_path / "sparse-rc-tran.cir"
    lines = [
        "Sparse transient symbolic reuse",
        "Vdrive input 0 PWL(0 0 0.7n 0 1.3n 1 2.6n 0.2 4n 0.8)",
        *(f"R{index} input n{index} 1k" for index in range(1, branches + 1)),
        *(f"C{index} n{index} 0 1p" for index in range(1, branches + 1)),
        ".options reltol=1e-4 vntol=1e-8 abstol=1e-12",
        ".tran 0.2n 4n",
        f".print tran v(n{branches})",
        ".end",
        "",
    ]
    deck.write_text("\n".join(lines), encoding="ascii")

    cached = _run_path(deck)
    uncached_environment = dict(os.environ)
    uncached_environment["AGENT_SPICE_NATIVE_DISABLE_SYMBOLIC_REUSE"] = "1"
    completed = subprocess.run(
        [shutil.which("dotnet") or "dotnet", str(DLL), str(deck)],
        capture_output=True,
        text=True,
        check=True,
        env=uncached_environment,
    )
    uncached = json.loads(completed.stdout)

    statistics = cached["statistics"]
    assert statistics["sparseSymbolicFactorizations"] >= 1
    assert statistics["sparseNumericRefactorizations"] > statistics["sparseSymbolicFactorizations"]
    assert statistics["sparsePlanFallbacks"] == 0
    output = f"n{branches}"
    assert [point["x"] for point in cached["points"]] == pytest.approx(
        [point["x"] for point in uncached["points"]],
        abs=1e-18,
    )
    assert [point["values"][output] for point in cached["points"]] == pytest.approx(
        [point["values"][output] for point in uncached["points"]],
        rel=2e-10,
        abs=1e-12,
    )


def test_native_sparse_pdn_ac_plan_and_node_ordering_preserve_results(tmp_path: Path) -> None:
    deck = tmp_path / "pdn-mesh-ac.cir"
    probes = _write_pdn_mesh_deck(deck, "ac")

    cached = _run_path(deck)
    uncached = _run_path_with_environment(deck, AGENT_SPICE_NATIVE_DISABLE_SYMBOLIC_REUSE="1")
    unordered = _run_path_with_environment(deck, AGENT_SPICE_NATIVE_DISABLE_NODE_ORDERING="1")

    statistics = cached["statistics"]
    assert statistics["sparseSymbolicFactorizations"] == 1
    assert statistics["sparseNumericRefactorizations"] == len(cached["points"]) - 1
    assert statistics["sparsePlanFallbacks"] == 0
    assert statistics["acMatrixAssemblyReplays"] >= len(cached["points"]) - 2
    assert [point["x"] for point in cached["points"]] == pytest.approx(
        [point["x"] for point in uncached["points"]],
        rel=1e-14,
    )
    for probe in probes:
        expected = [
            complex(point["complex"][probe]["re"], point["complex"][probe]["im"])
            for point in cached["points"]
        ]
        for comparison in (uncached, unordered):
            actual = [
                complex(point["complex"][probe]["re"], point["complex"][probe]["im"])
                for point in comparison["points"]
            ]
            assert actual == pytest.approx(expected, rel=1e-9, abs=2e-11)

    ngspice = shutil.which("ngspice")
    if ngspice is None:
        return
    oracle_run = subprocess.run(
        [ngspice, "-b", str(deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(oracle_run.stdout, "ac")
    for probe in probes:
        native_values = [
            complex(point["complex"][probe]["re"], point["complex"][probe]["im"])
            for point in cached["points"]
        ]
        assert native_values == pytest.approx(
            [value for _, value in oracle[f"v({probe})"]],
            rel=1e-5,
            abs=1e-7,
        )


def test_native_sparse_pdn_transient_cache_preserves_adaptive_waveform(tmp_path: Path) -> None:
    deck = tmp_path / "pdn-mesh-tran.cir"
    probes = _write_pdn_mesh_deck(deck, "tran", points=11)

    cached = _run_path(deck)
    uncached = _run_path_with_environment(deck, AGENT_SPICE_NATIVE_DISABLE_SYMBOLIC_REUSE="1")
    step_doubling = _run_path_with_environment(
        deck,
        AGENT_SPICE_NATIVE_USE_STEP_DOUBLING_LTE="1",
    )

    statistics = cached["statistics"]
    assert statistics["sparseSymbolicFactorizations"] >= 1
    assert statistics["sparseNumericRefactorizations"] > statistics["sparseSymbolicFactorizations"]
    assert statistics["acceptedTransientSteps"] > len(cached["points"])
    assert statistics["deviceTruncationEvaluations"] > 0
    assert statistics["stepDoublingEvaluations"] == 0
    assert step_doubling["statistics"]["deviceTruncationEvaluations"] == 0
    assert step_doubling["statistics"]["stepDoublingEvaluations"] > 0
    assert statistics["deviceTruncationEvaluations"] < (
        3 * step_doubling["statistics"]["stepDoublingEvaluations"]
    )
    assert [point["x"] for point in cached["points"]] == pytest.approx(
        [point["x"] for point in uncached["points"]],
        abs=1e-18,
    )
    for probe in probes:
        assert [point["values"][probe] for point in cached["points"]] == pytest.approx(
            [point["values"][probe] for point in uncached["points"]],
            rel=2e-8,
            abs=2e-10,
        )
        assert [point["values"][probe] for point in cached["points"]] == pytest.approx(
            [point["values"][probe] for point in step_doubling["points"]],
            rel=3e-3,
            abs=2e-3,
        )

    ngspice = shutil.which("ngspice")
    if ngspice is None:
        return
    oracle_run = subprocess.run(
        [ngspice, "-b", str(deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(oracle_run.stdout, "tran")
    for probe in probes:
        native_values = [point["values"][probe] for point in cached["points"]]
        oracle_values = [
            _interpolate_complex(oracle[f"v({probe})"], point["x"]).real
            for point in cached["points"]
        ]
        assert native_values == pytest.approx(oracle_values, rel=3.5e-2, abs=1e-4)


def test_native_sparse_newton_reuses_symbolic_fill(tmp_path: Path) -> None:
    branches = 64
    deck = tmp_path / "sparse-diode-op.cir"
    lines = [
        "Sparse Newton symbolic reuse",
        "Vdrive input 0 1",
        *(f"R{index} input n{index} 1k" for index in range(1, branches + 1)),
        *(f"D{index} n{index} 0 clamp" for index in range(1, branches + 1)),
        ".model clamp D(IS=1e-12 N=1)",
        ".op",
        f".print op v(n{branches})",
        ".end",
        "",
    ]
    deck.write_text("\n".join(lines), encoding="ascii")

    cached = _run_path(deck)
    uncached_environment = dict(os.environ)
    uncached_environment["AGENT_SPICE_NATIVE_DISABLE_SYMBOLIC_REUSE"] = "1"
    completed = subprocess.run(
        [shutil.which("dotnet") or "dotnet", str(DLL), str(deck)],
        capture_output=True,
        text=True,
        check=True,
        env=uncached_environment,
    )
    uncached = json.loads(completed.stdout)

    statistics = cached["statistics"]
    assert statistics["sparseSymbolicFactorizations"] == 1
    assert statistics["sparseNumericRefactorizations"] > 0
    assert statistics["sparsePlanFallbacks"] == 0
    output = f"n{branches}"
    assert cached["points"][0]["values"][output] == pytest.approx(
        uncached["points"][0]["values"][output],
        rel=2e-12,
        abs=1e-13,
    )


@pytest.mark.parametrize("analysis", ["op", "dc", "ac", "tran"])
@pytest.mark.parametrize(
    ("fixture", "outputs"),
    [
        ("controlled_sources.cir", ("eout", "gout", "fout", "hout")),
        ("subckt_param.cir", ("output",)),
    ],
)
def test_native_hierarchical_parameters_and_controlled_sources_match_ngspice(
    tmp_path: Path,
    fixture: str,
    outputs: tuple[str, ...],
    analysis: str,
) -> None:
    deck = _single_analysis_deck(tmp_path, fixture, analysis)
    native = _run_path(deck)
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, analysis)

    for output in outputs:
        waveform = oracle[f"v({output})"]
        if analysis == "tran":
            for point in native["points"]:
                assert point["values"][output] == pytest.approx(
                    _interpolate_complex(waveform, point["x"]).real,
                    rel=2e-5,
                    abs=2e-6,
                )
            continue
        assert [point["x"] for point in native["points"]] == pytest.approx(
            [point[0] for point in waveform],
            rel=2e-6,
            abs=1e-15,
        )
        if analysis == "ac":
            assert [
                complex(point["complex"][output]["re"], point["complex"][output]["im"])
                for point in native["points"]
            ] == pytest.approx([point[1] for point in waveform], rel=2e-5, abs=2e-6)
        else:
            assert [point["values"][output] for point in native["points"]] == pytest.approx(
                [point[1].real for point in waveform],
                rel=2e-5,
                abs=2e-6,
            )

    if fixture == "controlled_sources.cir" and analysis == "op":
        values = native["points"][0]["values"]
        assert values["Evcvs"] == pytest.approx(oracle["evcvs#branch"][0][1].real, abs=2e-9)
        assert values["Hccvs"] == pytest.approx(oracle["hccvs#branch"][0][1].real, abs=2e-9)


def test_native_parameterized_local_subcircuit_models_match_ngspice() -> None:
    native = _run("subckt_local_model.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "subckt_local_model.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "op")
    values = native["points"][0]["values"]
    assert values["weak"] == pytest.approx(oracle["v(weak)"][0][1].real, rel=2e-6, abs=2e-7)
    assert values["strong"] == pytest.approx(oracle["v(strong)"][0][1].real, rel=2e-6, abs=2e-7)
    assert values["strong"] > values["weak"]


def test_native_numeric_expression_precedence_conditionals_and_forward_references(
    tmp_path: Path,
) -> None:
    deck = tmp_path / "expressions.cir"
    deck.write_text(
        "\n".join(
            [
                "Numeric expression grammar",
                ".param selected={power_value==512 ? 3 : 0}",
                ".param power_value={2^3^2}",
                ".param signed_value={-2^2+5}",
                "Vdrive input 0 1",
                "Eresult output 0 input 0 {selected*signed_value}",
                "Rload output 0 1k",
                ".op",
                ".print op v(output)",
                ".end",
                "",
            ]
        ),
        encoding="ascii",
    )
    result = _run_path(deck)
    assert result["points"][0]["values"]["output"] == pytest.approx(3.0)


def test_native_recursive_include_and_selected_library_section_match_ngspice() -> None:
    deck = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "include_case" / "top.cir"
    native = _run_path(deck)
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "op")
    assert native["points"][0]["values"]["output"] == pytest.approx(
        oracle["v(output)"][0][1].real,
        rel=3e-6,
        abs=2e-7,
    )


@pytest.mark.parametrize(
    ("deck", "maximum_rms", "maximum_error"),
    [
        ("pwl_tran.cir", 5e-4, 2e-3),
        ("pwl_tran_gear.cir", 2e-3, 5e-3),
        ("sin_tran.cir", 2e-3, 4e-3),
        ("exp_tran.cir", 2e-3, 5e-3),
    ],
)
def test_native_pwl_sin_and_exp_transients_track_ngspice(
    deck: str,
    maximum_rms: float,
    maximum_error: float,
) -> None:
    native = _run(deck)
    statistics = native["statistics"]
    assert statistics["breakpointTransientSteps"] > 0
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "tran")["v(output)"]
    errors = [
        point["values"]["output"] - _interpolate_complex(oracle, point["x"]).real
        for point in native["points"]
    ]
    assert math.sqrt(sum(error * error for error in errors) / len(errors)) < maximum_rms
    assert max(abs(error) for error in errors) < maximum_error

    def input_at(time: float) -> float:
        point = min(native["points"], key=lambda candidate: abs(candidate["x"] - time))
        assert point["x"] == pytest.approx(time, abs=1e-18)
        return point["values"]["input"]

    if deck in {"pwl_tran.cir", "pwl_tran_gear.cir"}:
        assert input_at(1.6e-9) == pytest.approx(0.7, abs=1e-12)
    elif deck == "sin_tran.cir":
        time = 4e-9
        local = time - 1.3e-9
        expected = 0.2 + 0.8 * math.exp(-20e6 * local) * math.sin(2 * math.pi * 200e6 * local)
        assert input_at(time) == pytest.approx(expected, abs=1e-12)
    else:
        time = 7e-9
        expected = 0.1 + 0.9 * (1 - math.exp(-(time - 1.3e-9) / 0.5e-9))
        expected -= 0.9 * (1 - math.exp(-(time - 5.2e-9) / 0.8e-9))
        assert input_at(time) == pytest.approx(expected, abs=1e-12)


def test_native_pwl_duplicate_time_is_a_right_continuous_discontinuity(tmp_path: Path) -> None:
    deck = tmp_path / "pwl-jump.cir"
    deck.write_text(
        "\n".join(
            [
                "PWL discontinuity",
                "Vdrive input 0 PWL(0 0 1n 0 1n 1 2n 1)",
                "Rsource input output 100",
                "Cload output 0 20p",
                ".options reltol=1e-4 vntol=1e-8 abstol=1e-12",
                ".tran 0.25n 2n",
                ".print tran v(input) v(output)",
                ".end",
                "",
            ]
        ),
        encoding="ascii",
    )
    native = _run_path(deck)
    assert native["statistics"]["discontinuityTransientEvents"] == 1
    at_edge = min(native["points"], key=lambda point: abs(point["x"] - 1e-9))
    after_edge = min(native["points"], key=lambda point: abs(point["x"] - 1.25e-9))
    assert at_edge["values"]["input"] == pytest.approx(0.0)
    assert after_edge["values"]["input"] == pytest.approx(1.0)


def test_native_gear_rebuilds_the_linear_matrix_after_startup(tmp_path: Path) -> None:
    deck = tmp_path / "gear-linear-startup.cir"
    deck.write_text(
        "\n".join(
            [
                "Gear linear startup matrix",
                "Vdrive input 0 0.2",
                "Rsource input output 100",
                "Cload output 0 20p",
                ".options method=gear reltol=1e-4 vntol=1e-8 abstol=1e-12",
                ".tran 0.2n 2n",
                ".print tran v(output)",
                ".end",
                "",
            ]
        ),
        encoding="ascii",
    )

    native = _run_path(deck)
    assert native["points"]
    assert [point["values"]["output"] for point in native["points"]] == pytest.approx(
        [0.2] * len(native["points"]),
        abs=1e-12,
    )


def test_native_dependency_failures_are_explicit(tmp_path: Path) -> None:
    def run(deck: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [shutil.which("dotnet") or "dotnet", str(DLL), str(deck)],
            capture_output=True,
            text=True,
            check=False,
        )

    cycle = tmp_path / "cycle"
    cycle.mkdir()
    main = cycle / "main.cir"
    child = cycle / "child.inc"
    main.write_text('Dependency cycle\n.include "child.inc"\nV1 in 0 1\n.end\n', encoding="ascii")
    child.write_text('.include "main.cir"\n', encoding="ascii")
    completed = run(main)
    assert completed.returncode != 0
    assert "recursive netlist dependency" in completed.stderr

    missing_section = tmp_path / "missing-section"
    missing_section.mkdir()
    main = missing_section / "main.cir"
    library = missing_section / "models.lib"
    main.write_text('Missing section\n.lib "models.lib" ff\nV1 in 0 1\n.end\n', encoding="ascii")
    library.write_text(".lib tt\n.param gain=1\n.endl tt\n", encoding="ascii")
    completed = run(main)
    assert completed.returncode != 0
    assert "library section 'ff' was not found" in completed.stderr

    included_end = tmp_path / "included-end"
    included_end.mkdir()
    main = included_end / "main.cir"
    child = included_end / "child.inc"
    main.write_text('Included end\n.include "child.inc"\nV1 in 0 1\n.end\n', encoding="ascii")
    child.write_text("R1 in 0 1k\n.end\n", encoding="ascii")
    completed = run(main)
    assert completed.returncode != 0
    assert "must not contain .end" in completed.stderr


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            "V1 in 0 1\n.param a={b+1} b={a+1}\nR1 in 0 {a}\n.op",
            "cyclic parameter definition",
        ),
        (
            "V1 in 0 1\nR1 in 0 {missing}\n.op",
            "undefined parameter 'missing'",
        ),
        (
            "V1 in 0 1\nXtop in out loop\n.subckt loop a b\nXagain a b loop\n.ends loop\n.op",
            "recursive subcircuit expansion",
        ),
        (
            "V1 in 0 1\nX1 in out cell missing=2\n.subckt cell a b params: gain=1\nE1 b 0 a 0 {gain}\n.ends cell\n.op",
            "overrides unknown parameter 'missing'",
        ),
        (
            "V1 in 0 1\nF1 out 0 Vmissing 2\nR1 out 0 1k\n.op",
            "undefined controlling voltage source 'Vmissing'",
        ),
    ],
)
def test_native_parameter_and_hierarchy_errors_are_explicit(
    tmp_path: Path,
    body: str,
    message: str,
) -> None:
    deck = tmp_path / "invalid.cir"
    deck.write_text(f"Invalid hierarchy fixture\n{body}\n.end\n", encoding="ascii")
    completed = subprocess.run(
        [shutil.which("dotnet") or "dotnet", str(DLL), str(deck)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert message in completed.stderr


def test_native_diode_newton_matches_equation_and_ngspice() -> None:
    result = _run("diode_op.cir")
    voltage = result["points"][0]["values"]["out"]
    assert 0 < result["statistics"]["newtonIterations"] < 30
    assert result["statistics"]["maximumConvergedResidualRatio"] <= 1.0
    thermal_voltage = 0.025864925786
    resistor_current = (1.0 - voltage) / 1000.0
    diode_current = 1e-12 * (math.exp(voltage / thermal_voltage) - 1.0)
    assert resistor_current == pytest.approx(diode_current, rel=2e-6, abs=1e-12)

    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "diode_op.cir")],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = completed.stdout.splitlines()
    header = next(index for index, line in enumerate(lines) if line.split() == ["Index", "v(out)"])
    ngspice_voltage = next(
        float(fields[1])
        for line in lines[header + 1 :]
        if len(fields := line.split()) == 2 and fields[0].isdigit()
    )
    assert voltage == pytest.approx(ngspice_voltage, rel=5e-6, abs=5e-7)


def test_native_diode_dc_sweep_uses_converged_warm_start() -> None:
    result = _run("diode.cir")
    operating_point = result["points"][0]["values"]["out"]
    sweep = [point["values"]["out"] for point in result["points"] if point["analysis"] == "dc"]

    assert sweep == sorted(sweep)
    assert sweep[-1] == pytest.approx(operating_point, rel=2e-9)


def test_native_diode_dc_curve_matches_ngspice() -> None:
    native = _run("diode_dc.cir")
    native_voltage = [point["values"]["out"] for point in native["points"]]
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "diode_dc.cir")],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = completed.stdout.splitlines()
    header = next(
        index for index, line in enumerate(lines)
        if line.split() == ["Index", "v-sweep", "v(out)"]
    )
    ngspice_voltage = [
        float(fields[2])
        for line in lines[header + 1 :]
        if len(fields := line.split()) == 3 and fields[0].isdigit()
    ]

    assert native_voltage == pytest.approx(ngspice_voltage, rel=5e-6, abs=5e-7)


def test_native_diode_ac_small_signal_matches_ngspice() -> None:
    native = _run("diode_ac.cir")
    native_voltage = native["points"][0]["complex"]["out"]
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "diode_ac.cir")],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = completed.stdout.splitlines()
    header = next(
        index for index, line in enumerate(lines)
        if line.split() == ["Index", "frequency", "real(v(out))", "imag(v(out))"]
    )
    fields = next(
        fields
        for line in lines[header + 1 :]
        if len(fields := line.split()) == 4 and fields[0].isdigit()
    )

    assert native_voltage["re"] == pytest.approx(float(fields[2]), rel=5e-6, abs=1e-8)
    assert native_voltage["im"] == pytest.approx(float(fields[3]), abs=1e-12)


@pytest.mark.parametrize(
    ("deck", "collector_current", "base_current"),
    [
        ("bjt_npn_op.cir", lambda voltage: (5.0 - voltage) / 1000.0, lambda current: -current),
        ("bjt_pnp_op.cir", lambda voltage: voltage / 1000.0, lambda current: current),
    ],
)
def test_native_level1_bjt_operating_point_matches_ngspice(
    deck: str,
    collector_current,
    base_current,
) -> None:
    native = _run(deck)
    values = native["points"][0]["values"]
    ic = collector_current(values["collector"])
    ib = base_current(values["Vbase"])

    assert ic / ib == pytest.approx(100.0, rel=1e-8)
    assert native["statistics"]["newtonIterations"] < 10
    assert native["statistics"]["maximumConvergedResidualRatio"] <= 1.0

    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = completed.stdout.splitlines()
    header = next(
        index for index, line in enumerate(lines)
        if line.split() == ["Index", "v(collector)", "vbase#branch"]
    )
    fields = next(
        fields
        for line in lines[header + 1 :]
        if len(fields := line.split()) == 3 and fields[0].isdigit()
    )

    assert values["collector"] == pytest.approx(float(fields[1]), rel=2e-5, abs=1e-7)
    assert values["Vbase"] == pytest.approx(float(fields[2]), rel=2e-5, abs=1e-10)


def test_native_level1_bjt_dc_curve_matches_ngspice() -> None:
    native = _run("bjt_npn_dc.cir")
    native_voltage = [point["values"]["collector"] for point in native["points"]]
    assert native_voltage == sorted(native_voltage, reverse=True)
    assert native["statistics"]["newtonIterations"] < 250
    assert native["statistics"]["maximumConvergedResidualRatio"] <= 1.0

    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "bjt_npn_dc.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = completed.stdout.splitlines()
    header = next(
        index for index, line in enumerate(lines)
        if line.split() == ["Index", "v-sweep", "v(collector)", "vbase#branch"]
    )
    ngspice_voltage = [
        float(fields[2])
        for line in lines[header + 1 :]
        if len(fields := line.split()) == 4 and fields[0].isdigit()
    ]

    assert native_voltage == pytest.approx(ngspice_voltage, rel=5e-5, abs=2e-7)


def test_native_level1_bjt_ac_small_signal_matches_ngspice() -> None:
    native = _run("bjt_npn_ac.cir")
    values = native["points"][0]["complex"]
    assert values["collector"]["re"] / values["Vbase"]["re"] == pytest.approx(100_000.0)
    assert values["collector"]["im"] == pytest.approx(0.0)
    assert values["Vbase"]["im"] == pytest.approx(0.0)

    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "bjt_npn_ac.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = completed.stdout.splitlines()

    def ac_row(marker: str) -> list[str]:
        header = next(index for index, line in enumerate(lines) if marker in line.lower())
        return next(
            fields
            for line in lines[header + 1 :]
            if len(fields := line.split()) == 4 and fields[0].isdigit()
        )

    voltage = ac_row("real(v(collect")
    current = ac_row("real(i(vbase))")
    assert values["collector"]["re"] == pytest.approx(float(voltage[2]), rel=2e-5, abs=1e-9)
    assert values["collector"]["im"] == pytest.approx(float(voltage[3]), abs=1e-12)
    assert values["Vbase"]["re"] == pytest.approx(float(current[2]), rel=2e-5, abs=1e-12)
    assert values["Vbase"]["im"] == pytest.approx(float(current[3]), abs=1e-12)


def test_native_level1_bjt_early_effect_curve_matches_ngspice() -> None:
    native = _run("bjt_early_dc.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "bjt_early_dc.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = completed.stdout.splitlines()
    header = next(index for index, line in enumerate(lines) if "v-sweep" in line.lower())
    oracle = [
        (float(fields[2]), float(fields[3]))
        for line in lines[header + 1 :]
        if len(fields := line.split()) == 4 and fields[0].isdigit()
    ]

    collector_current = [point["values"]["Vcollector"] for point in native["points"]]
    base_current = [point["values"]["Vbase"] for point in native["points"]]
    assert collector_current == pytest.approx(
        [point[0] for point in oracle],
        rel=2e-5,
        abs=5e-11,
    )
    assert base_current == pytest.approx(
        [point[1] for point in oracle],
        rel=2e-5,
        abs=5e-13,
    )


def test_native_level1_bjt_dynamic_ac_curve_matches_ngspice() -> None:
    native = _run("bjt_dynamic_ac.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "bjt_dynamic_ac.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = completed.stdout.splitlines()

    def ac_table(marker: str) -> list[tuple[float, float]]:
        header = next(index for index, line in enumerate(lines) if marker in line.lower())
        return [
            (float(fields[2]), float(fields[3]))
            for line in lines[header + 1 :]
            if len(fields := line.split()) == 4 and fields[0].isdigit()
        ][: len(native["points"])]

    collector = ac_table("real(v(collect")
    base_current = ac_table("real(i(vbase))")
    assert [point["complex"]["collector"]["re"] for point in native["points"]] == pytest.approx(
        [point[0] for point in collector],
        rel=5e-5,
        abs=2e-7,
    )
    assert [point["complex"]["collector"]["im"] for point in native["points"]] == pytest.approx(
        [point[1] for point in collector],
        rel=5e-5,
        abs=2e-8,
    )
    assert [point["complex"]["Vbase"]["re"] for point in native["points"]] == pytest.approx(
        [point[0] for point in base_current],
        rel=5e-5,
        abs=2e-10,
    )
    assert [point["complex"]["Vbase"]["im"] for point in native["points"]] == pytest.approx(
        [point[1] for point in base_current],
        rel=5e-5,
        abs=2e-10,
    )


@pytest.mark.parametrize(
    "deck",
    [
        "bjt_dynamic_tran.cir",
        "bjt_dynamic_tran_gear.cir",
        "bjt_dynamic_pnp_tran.cir",
    ],
)
def test_native_level1_bjt_dynamic_transient_tracks_ngspice(deck: str) -> None:
    native = _run(deck)
    statistics = native["statistics"]
    assert 0 < statistics["acceptedTransientSteps"] < 300
    assert statistics["rejectedTransientSteps"] > 0
    assert statistics["maximumConvergedResidualRatio"] <= 1.0

    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = [
        (float(fields[1]), float(fields[2]), float(fields[3]))
        for line in completed.stdout.splitlines()
        if len(fields := line.split()) == 4 and fields[0].isdigit()
    ]

    def interpolate(time: float, value_index: int) -> float:
        for left, right in zip(oracle, oracle[1:]):
            if right[0] >= time:
                fraction = (time - left[0]) / (right[0] - left[0])
                return left[value_index] + fraction * (right[value_index] - left[value_index])
        return oracle[-1][value_index]

    collector_errors = [
        point["values"]["collector"] - interpolate(point["x"], 1)
        for point in native["points"]
    ]
    assert math.sqrt(sum(error * error for error in collector_errors) / len(collector_errors)) < 0.02
    assert max(abs(error) for error in collector_errors) < 0.06

    transition_endpoints = (2.2e-9, 12.4e-9, 22.2e-9, 32.4e-9)
    base_current_errors = [
        point["values"]["Vbase"] - interpolate(point["x"], 2)
        for point in native["points"]
        if min(abs(point["x"] - endpoint) for endpoint in transition_endpoints) > 1e-12
    ]
    assert math.sqrt(
        sum(error * error for error in base_current_errors) / len(base_current_errors)
    ) < 2e-5
    assert max(abs(error) for error in base_current_errors) < 5e-5


def test_native_level1_bjt_dynamic_equilibrium_has_no_charge_drift() -> None:
    native = _run("bjt_dynamic_bias_tran.cir")
    first = native["points"][0]["values"]
    for point in native["points"][1:]:
        assert point["values"]["collector"] == pytest.approx(first["collector"], abs=1e-12)
        assert point["values"]["Vbase"] == pytest.approx(first["Vbase"], abs=1e-14)


def test_native_diode_junction_and_diffusion_capacitance_match_ngspice() -> None:
    native = _run("diode_cap_ac.cir")
    native_voltage = native["points"][0]["complex"]["out"]
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "diode_cap_ac.cir")],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = completed.stdout.splitlines()
    header = next(
        index for index, line in enumerate(lines)
        if line.split() == ["Index", "frequency", "real(v(out))", "imag(v(out))"]
    )
    fields = next(
        fields
        for line in lines[header + 1 :]
        if len(fields := line.split()) == 4 and fields[0].isdigit()
    )

    assert native_voltage["re"] == pytest.approx(float(fields[2]), rel=2e-4, abs=2e-6)
    assert native_voltage["im"] == pytest.approx(float(fields[3]), rel=2e-4, abs=2e-6)


def test_native_dynamic_diode_matches_ngspice_with_device_lte() -> None:
    native = _run("diode_tran.cir")
    statistics = native["statistics"]
    assert 0 < statistics["acceptedTransientSteps"] < 150
    assert statistics["deviceTruncationEvaluations"] >= statistics["acceptedTransientSteps"]
    assert statistics["stepDoublingEvaluations"] == 0

    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "diode_tran.cir")],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[0].isdigit():
            oracle.append((float(fields[1]), float(fields[3])))

    def interpolate(time: float) -> float:
        for index in range(1, len(oracle)):
            if oracle[index][0] >= time:
                left_time, left_value = oracle[index - 1]
                right_time, right_value = oracle[index]
                fraction = (time - left_time) / (right_time - left_time)
                return left_value + fraction * (right_value - left_value)
        return oracle[-1][1]

    errors = [point["values"]["out"] - interpolate(point["x"]) for point in native["points"]]
    rms_error = math.sqrt(sum(error * error for error in errors) / len(errors))
    assert rms_error < 1e-3
    assert max(abs(error) for error in errors) < 3e-3


def test_native_transient_predictor_reduces_newton_work_without_changing_waveform() -> None:
    predicted = _run("diode_tran.cir")
    unpredicted = _run("diode_tran_nopredictor.cir")

    assert predicted["statistics"]["predictorInitializations"] > 0
    assert predicted["statistics"]["newtonIterations"] < 0.9 * unpredicted["statistics"]["newtonIterations"]
    for predicted_point, unpredicted_point in zip(predicted["points"], unpredicted["points"], strict=True):
        assert predicted_point["x"] == unpredicted_point["x"]
        assert predicted_point["values"]["out"] == pytest.approx(
            unpredicted_point["values"]["out"],
            abs=6e-6,
        )


def test_native_zero_pulse_edges_follow_ngspice_tstep_transition_semantics() -> None:
    native = _run("pulse_zero_edge_rc.cir")
    statistics = native["statistics"]
    assert statistics["discontinuityTransientEvents"] == 0
    assert statistics["rejectedTransientSteps"] > 0
    assert statistics["deviceTruncationEvaluations"] > statistics["acceptedTransientSteps"]
    assert native["points"][3]["values"]["in"] == pytest.approx(1.0)
    assert native["points"][7]["values"]["in"] == pytest.approx(1.0)
    assert native["points"][8]["values"]["in"] == pytest.approx(0.0)

    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "pulse_zero_edge_rc.cir")],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[0].isdigit():
            oracle.append((float(fields[1]), float(fields[3])))

    def interpolate(time: float) -> float:
        for left, right in zip(oracle, oracle[1:]):
            if right[0] >= time:
                fraction = (time - left[0]) / (right[0] - left[0])
                return left[1] + fraction * (right[1] - left[1])
        return oracle[-1][1]

    errors = [point["values"]["out"] - interpolate(point["x"]) for point in native["points"]]
    assert math.sqrt(sum(error * error for error in errors) / len(errors)) < 4e-4
    assert max(abs(error) for error in errors) < 8e-4


def test_native_transient_lands_on_pulse_breakpoints_between_output_points() -> None:
    coarse = _run("diode_breakpoint.cir")
    fine = _run("diode_tran.cir")

    assert coarse["statistics"]["breakpointTransientSteps"] >= 3
    assert coarse["statistics"]["acceptedTransientSteps"] <= fine["statistics"]["acceptedTransientSteps"]
    for coarse_point in coarse["points"]:
        fine_point = min(fine["points"], key=lambda point: abs(point["x"] - coarse_point["x"]))
        assert coarse_point["x"] == pytest.approx(fine_point["x"], abs=1e-18)
        assert coarse_point["values"]["out"] == pytest.approx(
            fine_point["values"]["out"],
            abs=6e-5,
        )


def test_native_diode_reverse_recovery_tracks_ngspice_event_timing() -> None:
    native = _run("diode_reverse_recovery.cir")
    statistics = native["statistics"]
    assert statistics["breakpointTransientSteps"] > 0
    assert statistics["lineSearchBacktracks"] > 0
    assert statistics["maximumConvergedResidualRatio"] <= 1.0

    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "diode_reverse_recovery.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[0].isdigit():
            oracle.append((float(fields[1]), float(fields[3])))
    native_waveform = [(point["x"], point["values"]["out"]) for point in native["points"]]

    def crossing_time(waveform: list[tuple[float, float]], level: float) -> float:
        for left, right in zip(waveform, waveform[1:]):
            if right[0] <= 20e-9 or (left[1] - level) * (right[1] - level) > 0.0:
                continue
            fraction = (level - left[1]) / (right[1] - left[1])
            return left[0] + fraction * (right[0] - left[0])
        raise AssertionError(f"waveform never crossed {level}")

    for level in (0.5, 0.0, -0.5):
        assert crossing_time(native_waveform, level) == pytest.approx(
            crossing_time(oracle, level),
            abs=0.25e-9,
        )
    assert native_waveform[-1][1] == pytest.approx(oracle[-1][1], abs=1e-5)


def test_native_variable_step_gear2_tracks_ngspice_reverse_recovery() -> None:
    native = _run("diode_reverse_recovery_gear.cir")
    statistics = native["statistics"]
    assert 0 < statistics["acceptedTransientSteps"] < 300
    assert statistics["predictorInitializations"] > 0
    assert statistics["maximumConvergedResidualRatio"] <= 1.0

    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "diode_reverse_recovery_gear.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[0].isdigit():
            oracle.append((float(fields[1]), float(fields[3])))
    native_waveform = [(point["x"], point["values"]["out"]) for point in native["points"]]

    def crossing_time(waveform: list[tuple[float, float]], level: float) -> float:
        for left, right in zip(waveform, waveform[1:]):
            if right[0] <= 20e-9 or (left[1] - level) * (right[1] - level) > 0.0:
                continue
            fraction = (level - left[1]) / (right[1] - left[1])
            return left[0] + fraction * (right[0] - left[0])
        raise AssertionError(f"waveform never crossed {level}")

    for level in (0.5, 0.0, -0.5):
        assert crossing_time(native_waveform, level) == pytest.approx(
            crossing_time(oracle, level),
            abs=0.3e-9,
        )
    assert native_waveform[-1][1] == pytest.approx(oracle[-1][1], abs=1e-5)


def test_native_level1_mos_nonlinear_operating_point_matches_ngspice() -> None:
    native = _run("mos1_nmos_op.cir")
    statistics = native["statistics"]
    assert 0 < statistics["newtonIterations"] < 10
    assert statistics["maximumConvergedResidualRatio"] <= 1.0

    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "mos1_nmos_op.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "op")
    point = native["points"][0]
    assert point["values"]["out"] == pytest.approx(
        oracle["v(out)"][0][1].real,
        rel=2e-6,
        abs=2e-6,
    )
    assert point["values"]["Vgate"] == pytest.approx(
        oracle["vgate#branch"][0][1].real,
        abs=1e-13,
    )
    assert point["values"]["Vbulk"] == pytest.approx(
        oracle["vbulk#branch"][0][1].real,
        abs=5e-12,
    )


@pytest.mark.parametrize("deck", ["mos1_nmos_dc.cir", "mos1_pmos_dc.cir"])
def test_native_level1_mos_nmos_and_pmos_dc_curves_match_ngspice(deck: str) -> None:
    native = _run(deck)
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "dc")
    drain_current = oracle["vdrain#branch"]
    gate_current = oracle["vgate#branch"]
    assert len(native["points"]) == len(drain_current)
    for point, drain, gate in zip(native["points"], drain_current, gate_current, strict=True):
        assert point["x"] == pytest.approx(drain[0], abs=2e-12)
        assert point["values"]["Vdrain"] == pytest.approx(
            drain[1].real,
            rel=3e-5,
            abs=3e-12,
        )
        assert point["values"]["Vgate"] == pytest.approx(gate[1].real, abs=1e-13)


def test_native_level1_cmos_inverter_dc_transfer_matches_ngspice() -> None:
    native = _run("mos1_cmos_inverter_dc.cir")
    assert native["statistics"]["maximumConvergedResidualRatio"] <= 1.0
    assert native["statistics"]["newtonIterations"] < 100
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "mos1_cmos_inverter_dc.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "dc")
    assert [point["values"]["out"] for point in native["points"]] == pytest.approx(
        [value.real for _, value in oracle["v(out)"]],
        rel=3e-6,
        abs=2e-6,
    )
    assert [point["values"]["Vdd"] for point in native["points"]] == pytest.approx(
        [value.real for _, value in oracle["vdd#branch"]],
        rel=3e-6,
        abs=5e-9,
    )


def test_native_level1_mos_overlap_and_junction_ac_matches_ngspice() -> None:
    native = _run("mos1_dynamic_ac.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "mos1_dynamic_ac.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "ac")
    native_output = [
        complex(point["complex"]["out"]["re"], point["complex"]["out"]["im"])
        for point in native["points"]
    ]
    native_gate_current = [
        complex(point["complex"]["Vgate"]["re"], point["complex"]["Vgate"]["im"])
        for point in native["points"]
    ]
    assert [point["x"] for point in native["points"]] == pytest.approx(
        [axis for axis, _ in oracle["v(out)"]],
        rel=2e-6,
    )
    assert native_output == pytest.approx(
        [value for _, value in oracle["v(out)"]],
        rel=5e-4,
        abs=3e-6,
    )
    assert native_gate_current == pytest.approx(
        [value for _, value in oracle["vgate#branch"]],
        rel=5e-4,
        abs=5e-10,
    )


@pytest.mark.parametrize(
    "deck",
    ["mos1_series_direct_dc.cir", "mos1_series_sheet_dc.cir"],
)
def test_native_level1_mos_series_resistance_matches_ngspice(deck: str) -> None:
    native = _run(deck)
    assert all("__agent_spice_" not in node for node in native["nodes"])
    assert all(
        "__agent_spice_" not in name
        for point in native["points"]
        for name in point["values"]
    )
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "dc")
    for native_name, oracle_name in (("Vdrain", "vdrain#branch"), ("Vsource", "vsource#branch")):
        assert [point["values"][native_name] for point in native["points"]] == pytest.approx(
            [value.real for _, value in oracle[oracle_name]],
            rel=5e-5,
            abs=5e-10,
        )


def test_native_level1_mos_series_internal_nodes_are_not_public(tmp_path: Path) -> None:
    deck = tmp_path / "mos-series-no-print.cir"
    deck.write_text(
        """MOS1 internal node visibility regression
Vgate gate 0 2
Vdrain drain 0 1
Vsource source 0 0
M1 drain gate source 0 nch L=1u W=20u
.model nch nmos (level=1 vto=0.7 kp=200u rd=100 rs=50)
.op
.end
""",
        encoding="ascii",
    )
    native = _run_path(deck)
    assert set(native["nodes"]) == {"gate", "drain", "source"}
    assert set(native["points"][0]["values"]) == {
        "gate",
        "drain",
        "source",
        "Vgate",
        "Vdrain",
        "Vsource",
    }


def test_native_level1_mos_zero_direct_resistance_overrides_sheet_resistance(
    tmp_path: Path,
) -> None:
    deck = tmp_path / "mos-zero-rd-precedence.cir"
    deck.write_text(
        """MOS1 zero direct resistance precedence regression
Vgate gate 0 2
Vdrain drain 0 1
Vsource source 0 0
M1 drain gate source 0 nch L=1u W=20u NRD=2 NRS=0
.model nch nmos (level=1 vto=0.7 kp=200u rsh=40 rd=0)
.op
.print op i(Vdrain) i(Vsource)
.end
""",
        encoding="ascii",
    )
    native = _run_path(deck)
    point = native["points"][0]
    assert point["values"]["Vdrain"] == pytest.approx(0.0, abs=1e-15)
    assert point["values"]["Vsource"] == pytest.approx(0.0, abs=1e-15)


def test_native_level1_mos_meyer_ac_matches_ngspice() -> None:
    native = _run("mos1_meyer_ac.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "mos1_meyer_ac.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "ac")
    native_output = [
        complex(point["complex"]["out"]["re"], point["complex"]["out"]["im"])
        for point in native["points"]
    ]
    native_gate_current = [
        complex(point["complex"]["Vgate"]["re"], point["complex"]["Vgate"]["im"])
        for point in native["points"]
    ]
    assert native_output == pytest.approx(
        [value for _, value in oracle["v(out)"]],
        rel=8e-4,
        abs=5e-6,
    )
    assert native_gate_current == pytest.approx(
        [value for _, value in oracle["vgate#branch"]],
        rel=8e-4,
        abs=2e-9,
    )


@pytest.mark.parametrize(
    "deck",
    ["mos1_meyer_pmos_ac.cir", "mos1_meyer_reverse_ac.cir"],
)
def test_native_level1_mos_meyer_pmos_and_reverse_ac_match_ngspice(deck: str) -> None:
    native = _run(deck)
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "ac")
    for native_name, oracle_name in (
        ("Vgate", "vgate#branch"),
        ("Vdrain", "vdrain#branch"),
        ("Vsource", "vsource#branch"),
    ):
        native_values = [
            complex(point["complex"][native_name]["re"], point["complex"][native_name]["im"])
            for point in native["points"]
        ]
        assert native_values == pytest.approx(
            [value for _, value in oracle[oracle_name]],
            rel=1e-3,
            abs=2e-9,
        )


@pytest.mark.parametrize(
    ("deck", "maximum_output_rms", "maximum_output_error"),
    [
        ("mos1_dynamic_tran.cir", 0.015, 0.06),
        ("mos1_dynamic_tran_gear.cir", 0.01, 0.04),
    ],
)
def test_native_level1_mos_dynamic_transient_tracks_ngspice(
    deck: str,
    maximum_output_rms: float,
    maximum_output_error: float,
) -> None:
    native = _run(deck)
    statistics = native["statistics"]
    assert 0 < statistics["acceptedTransientSteps"] < 600
    assert statistics["rejectedTransientSteps"] > 0
    assert statistics["deviceTruncationEvaluations"] >= statistics["acceptedTransientSteps"]
    assert statistics["maximumConvergedResidualRatio"] <= 1.0

    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [ngspice, "-b", str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "tran")
    output_errors = [
        point["values"]["out"] -
        _interpolate_complex(oracle["v(out)"], point["x"]).real
        for point in native["points"]
    ]
    gate_current_errors = [
        point["values"]["Vgate"] -
        _interpolate_complex(oracle["vgate#branch"], point["x"]).real
        for point in native["points"]
    ]
    assert math.sqrt(
        sum(error * error for error in output_errors) / len(output_errors)
    ) < maximum_output_rms
    assert max(abs(error) for error in output_errors) < maximum_output_error
    assert math.sqrt(
        sum(error * error for error in gate_current_errors) / len(gate_current_errors)
    ) < 2.5e-4
    assert max(abs(error) for error in gate_current_errors) < 2.5e-3


def test_native_level1_cmos_inverter_transient_tracks_ngspice() -> None:
    native = _run("mos1_cmos_inverter_tran.cir")
    statistics = native["statistics"]
    assert 0 < statistics["acceptedTransientSteps"] < 700
    assert statistics["rejectedTransientSteps"] > 0
    assert statistics["maximumConvergedResidualRatio"] <= 1.0
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(
                ROOT /
                "native" /
                "AgentSpice.Engine" /
                "fixtures" /
                "mos1_cmos_inverter_tran.cir"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "tran")

    def errors(native_name: str, oracle_name: str) -> list[float]:
        return [
            point["values"][native_name] -
            _interpolate_complex(oracle[oracle_name], point["x"]).real
            for point in native["points"]
        ]

    output_errors = errors("out", "v(out)")
    input_current_errors = errors("Vin", "vin#branch")
    supply_current_errors = errors("Vdd", "vdd#branch")
    assert math.sqrt(
        sum(error * error for error in output_errors) / len(output_errors)
    ) < 3e-3
    assert max(abs(error) for error in output_errors) < 0.02
    assert math.sqrt(
        sum(error * error for error in input_current_errors) / len(input_current_errors)
    ) < 2e-3
    assert max(abs(error) for error in input_current_errors) < 0.02
    assert math.sqrt(
        sum(error * error for error in supply_current_errors) / len(supply_current_errors)
    ) < 3e-3
    assert max(abs(error) for error in supply_current_errors) < 0.04


def test_native_level1_mos_meyer_transient_tracks_ngspice() -> None:
    native = _run("mos1_meyer_tran.cir")
    assert native["statistics"]["maximumConvergedResidualRatio"] <= 1.0
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "mos1_meyer_tran.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "tran")

    def errors(native_name: str, oracle_name: str) -> list[float]:
        return [
            point["values"][native_name] -
            _interpolate_complex(oracle[oracle_name], point["x"]).real
            for point in native["points"]
        ]

    output_errors = errors("out", "v(out)")
    gate_current_errors = errors("Vgate", "vgate#branch")
    assert math.sqrt(sum(error * error for error in output_errors) / len(output_errors)) < 0.01
    assert max(abs(error) for error in output_errors) < 0.07
    assert math.sqrt(
        sum(error * error for error in gate_current_errors) / len(gate_current_errors)
    ) < 1e-3
    assert max(abs(error) for error in gate_current_errors) < 0.01


def test_native_level1_mos_global_model_and_instance_temperatures_match_ngspice() -> None:
    native = _run("mos1_temperature_op.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "mos1_temperature_op.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "op")
    point = native["points"][0]
    for native_name, oracle_name in (
        ("Vdglobal", "vdglobal#branch"),
        ("Vddelta", "vddelta#branch"),
        ("Vdexp", "vdexp#branch"),
    ):
        assert point["values"][native_name] == pytest.approx(
            oracle[oracle_name][0][1].real,
            rel=5e-5,
            abs=5e-10,
        )


def test_native_level1_mos_temperature_adjusted_ac_matches_ngspice() -> None:
    native = _run("mos1_temperature_ac.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "mos1_temperature_ac.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "ac")
    for native_name, oracle_name in (
        ("out", "v(out)"),
        ("Vgate", "vgate#branch"),
        ("Vdd", "vdd#branch"),
    ):
        native_values = [
            complex(point["complex"][native_name]["re"], point["complex"][native_name]["im"])
            for point in native["points"]
        ]
        assert native_values == pytest.approx(
            [value for _, value in oracle[oracle_name]],
            rel=1e-3,
            abs=2e-9,
        )


def test_native_level1_mos_temperature_adjusted_transient_tracks_ngspice() -> None:
    native = _run("mos1_temperature_tran.cir")
    assert native["statistics"]["maximumConvergedResidualRatio"] <= 1.0
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "mos1_temperature_tran.cir"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "tran")

    def errors(native_name: str, oracle_name: str) -> list[float]:
        return [
            point["values"][native_name] -
            _interpolate_complex(oracle[oracle_name], point["x"]).real
            for point in native["points"]
        ]

    output_errors = errors("out", "v(out)")
    gate_current_errors = errors("Vgate", "vgate#branch")
    assert math.sqrt(sum(error * error for error in output_errors) / len(output_errors)) < 0.012
    assert max(abs(error) for error in output_errors) < 0.08
    assert math.sqrt(
        sum(error * error for error in gate_current_errors) / len(gate_current_errors)
    ) < 1.5e-3
    assert max(abs(error) for error in gate_current_errors) < 0.012


def test_native_level1_mos_substrate_parameters_derive_model_like_ngspice() -> None:
    native = _run("mos1_substrate_derived_op.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    completed = subprocess.run(
        [
            ngspice,
            "-b",
            str(
                ROOT /
                "native" /
                "AgentSpice.Engine" /
                "fixtures" /
                "mos1_substrate_derived_op.cir"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "op")
    point = native["points"][0]
    for native_name, oracle_name in (
        ("Vdn", "vdn#branch"),
        ("Vsn", "vsn#branch"),
        ("Vdp", "vdp#branch"),
        ("Vsp", "vsp#branch"),
    ):
        assert point["values"][native_name] == pytest.approx(
            oracle[oracle_name][0][1].real,
            rel=5e-5,
            abs=5e-10,
        )


def test_native_level1_mos_subcircuit_parameters_and_local_model_are_scoped(tmp_path: Path) -> None:
    deck = tmp_path / "mos-subckt.cir"
    deck.write_text(
        """MOS1 hierarchical parameter regression
.param width_scale=2
.subckt mosload drain gate source bulk params: unit_width=10u
.model local_nch nmos (level=1 vto=0.7 kp=200u lambda=0.02)
Mdevice drain gate source bulk local_nch L=1u W={unit_width}
.ends mosload
Vdd supply 0 5
Rload supply out 1k
Vgate gate 0 1.5
Xload out gate 0 0 mosload unit_width={width_scale*10u}
.op
.print op v(out)
.end
""",
        encoding="ascii",
    )

    native = _run_path(deck)
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        assert native["points"][0]["values"]["out"] == pytest.approx(3.6271451, rel=2e-6)
        return
    completed = subprocess.run(
        [ngspice, "-b", str(deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "op")
    assert native["points"][0]["values"]["out"] == pytest.approx(
        oracle["v(out)"][0][1].real,
        rel=2e-6,
        abs=2e-6,
    )


@pytest.mark.parametrize(
    ("model", "instance", "message"),
    [
        (".model nch nmos (level=2)", "L=1u W=10u", "requires LEVEL=1"),
        (".model nch nmos (level=1 tox=20n nsub=1e5)", "L=1u W=10u", "NSUB must exceed"),
        (".model nch nmos (level=1 kf=1e-24)", "L=1u W=10u", "unsupported MOS1 model parameter 'kf'"),
    ],
)
def test_native_mos_rejects_unimplemented_model_contracts(
    tmp_path: Path,
    model: str,
    instance: str,
    message: str,
) -> None:
    deck = tmp_path / "unsupported-mos.cir"
    deck.write_text(
        "\n".join(
            [
                "Unsupported MOS contract",
                "Vgate gate 0 1",
                f"M1 out gate 0 0 nch {instance}",
                model,
                ".op",
                ".print op v(out)",
                ".end",
                "",
            ]
        ),
        encoding="ascii",
    )

    completed = subprocess.run(
        [shutil.which("dotnet") or "dotnet", str(DLL), str(deck)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert message in completed.stderr


def test_native_diode_area_multiplicity_and_temperatures_match_ngspice() -> None:
    native = _run("diode_temperature_op.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    fixture = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "diode_temperature_op.cir"
    completed = subprocess.run(
        [ngspice, "-b", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "op")
    point = native["points"][0]
    for native_name, oracle_name in (
        ("Vglobal", "vglobal#branch"),
        ("Vdelta", "vdelta#branch"),
        ("Vexplicit", "vexplicit#branc"),
        ("Vdefault", "vdefault#branch"),
    ):
        assert point["values"][native_name] == pytest.approx(
            oracle[oracle_name][0][1].real,
            rel=2e-5,
            abs=1e-10,
        )


def test_native_diode_series_resistance_is_area_scaled_and_internal(tmp_path: Path) -> None:
    native = _run("diode_series_dc.cir")
    assert native["nodes"] == ["drive"]
    assert all(set(point["values"]) == {"Vdrive"} for point in native["points"])
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    fixture = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "diode_series_dc.cir"
    completed = subprocess.run(
        [ngspice, "-b", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "dc")["vdrive#branch"]
    assert [point["values"]["Vdrive"] for point in native["points"]] == pytest.approx(
        [value.real for _, value in oracle],
        rel=3e-5,
        abs=5e-13,
    )


def test_native_diode_reverse_breakdown_matches_ngspice() -> None:
    native = _run("diode_breakdown_dc.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    fixture = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "diode_breakdown_dc.cir"
    completed = subprocess.run(
        [ngspice, "-b", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "dc")["vreverse#branch"]
    for point, (_, expected) in zip(native["points"], oracle, strict=True):
        actual = point["values"]["Vreverse"]
        assert abs(actual - expected.real) <= 3e-5 * max(abs(expected.real), 1e-12)


def test_native_diode_breakdown_and_series_resistance_match_ngspice() -> None:
    native = _run("diode_breakdown_series_op.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    fixture = (
        ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "diode_breakdown_series_op.cir"
    )
    completed = subprocess.run(
        [ngspice, "-b", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "op")
    point = native["points"][0]["values"]
    assert point["cathode"] == pytest.approx(oracle["v(cathode)"][0][1].real, rel=2e-6)
    assert point["Vreverse"] == pytest.approx(
        oracle["vreverse#branch"][0][1].real,
        rel=2e-6,
    )


def test_native_temperature_adjusted_diode_ac_matches_ngspice() -> None:
    native = _run("diode_temperature_ac.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    fixture = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "diode_temperature_ac.cir"
    completed = subprocess.run(
        [ngspice, "-b", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "ac")
    for native_name, oracle_name in (("out", "v(out)"), ("Vdrive", "vdrive#branch")):
        actual = [
            complex(point["complex"][native_name]["re"], point["complex"][native_name]["im"])
            for point in native["points"]
        ]
        assert actual == pytest.approx(
            [value for _, value in oracle[oracle_name]],
            rel=2e-5,
            abs=2e-9,
        )


def test_native_temperature_adjusted_diode_transient_tracks_ngspice() -> None:
    native = _run("diode_temperature_tran.cir")
    assert native["statistics"]["maximumConvergedResidualRatio"] <= 1.0
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    fixture = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "diode_temperature_tran.cir"
    completed = subprocess.run(
        [ngspice, "-b", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "tran")

    def errors(native_name: str, oracle_name: str) -> list[float]:
        return [
            point["values"][native_name] -
            _interpolate_complex(oracle[oracle_name], point["x"]).real
            for point in native["points"]
        ]

    output_errors = errors("out", "v(out)")
    drive_current_errors = errors("Vdrive", "vdrive#branch")
    assert math.sqrt(sum(error * error for error in output_errors) / len(output_errors)) < 4e-4
    assert max(abs(error) for error in output_errors) < 2e-3
    assert math.sqrt(
        sum(error * error for error in drive_current_errors) / len(drive_current_errors)
    ) < 4e-6
    assert max(abs(error) for error in drive_current_errors) < 2e-5


@pytest.mark.parametrize(
    ("model", "instance", "message"),
    [
        (".model d D(IS=1e-12 KF=1e-24)", "", "unsupported diode model parameter 'KF'"),
        (".model d D(IS=1e-12)", "AREA=0", "diode AREA and M must be positive"),
        (".model d D(IS=1e-12)", "TEMP=-300", "must be above absolute zero"),
        (".model d D(IS=1e-12)", "OFF", "unsupported diode instance parameter 'OFF'"),
        (".model d D(IS=1e-12 BV=0)", "", "diode BV, IBV, and NBV must be positive"),
    ],
)
def test_native_diode_rejects_unimplemented_or_invalid_contracts(
    tmp_path: Path,
    model: str,
    instance: str,
    message: str,
) -> None:
    deck = tmp_path / "unsupported-diode.cir"
    deck.write_text(
        "\n".join(
            [
                "Unsupported diode contract",
                "Vdrive drive 0 0.6",
                f"D1 drive 0 d {instance}".rstrip(),
                model,
                ".op",
                ".print op i(Vdrive)",
                ".end",
                "",
            ]
        ),
        encoding="ascii",
    )
    completed = subprocess.run(
        [shutil.which("dotnet") or "dotnet", str(DLL), str(deck)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert message.lower() in completed.stderr.lower()


def test_native_bjt_area_multiplicity_and_temperatures_match_ngspice() -> None:
    native = _run("bjt_temperature_op.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    fixture = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "bjt_temperature_op.cir"
    completed = subprocess.run(
        [ngspice, "-b", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "op")
    point = native["points"][0]["values"]
    for source in ("Vcg", "Vbg", "Vcd", "Vbd", "Vce", "Vbe", "Vcp", "Vbp"):
        assert point[source] == pytest.approx(
            oracle[f"{source.lower()}#branch"][0][1].real,
            rel=2e-5,
            abs=2e-11,
        )


def test_native_bjt_series_resistances_are_area_scaled_and_internal() -> None:
    native = _run("bjt_series_dc.cir")
    assert set(native["nodes"]) == {"collector", "base", "emitter"}
    assert all(set(point["values"]) == {"Vc", "Vb", "Ve"} for point in native["points"])
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    fixture = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "bjt_series_dc.cir"
    completed = subprocess.run(
        [ngspice, "-b", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "dc")
    for source in ("Vc", "Vb", "Ve"):
        assert [point["values"][source] for point in native["points"]] == pytest.approx(
            [value.real for _, value in oracle[f"{source.lower()}#branch"]],
            rel=3e-5,
            abs=5e-11,
        )


def test_native_bjt_high_injection_roll_off_matches_ngspice() -> None:
    native = _run("bjt_high_injection_dc.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    fixture = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "bjt_high_injection_dc.cir"
    completed = subprocess.run(
        [ngspice, "-b", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "dc")
    for source in ("Vc", "Vb", "Ve"):
        assert [point["values"][source] for point in native["points"]] == pytest.approx(
            [value.real for _, value in oracle[f"{source.lower()}#branch"]],
            rel=3e-5,
            abs=2e-11,
        )


def test_native_bjt_composite_leakage_currents_follow_spice_equations() -> None:
    native = _run("bjt_leakage_dc.cir")
    assert native["statistics"]["maximumConvergedResidualRatio"] <= 1.0

    thermal_voltage = 1.380649e-23 / 1.602176634e-19 * 300.15

    def junction_current(saturation_current: float, voltage: float, emission_voltage: float) -> float:
        if voltage >= -3.0 * emission_voltage:
            return saturation_current * math.expm1(voltage / emission_voltage)
        argument = 3.0 * emission_voltage / (voltage * math.e)
        return -saturation_current * (1.0 + argument**3)

    for base_voltage in (-0.2, 0.6):
        point = min(native["points"], key=lambda candidate: abs(candidate["x"] - base_voltage))
        forward = junction_current(2e-30, base_voltage, thermal_voltage)
        reverse = junction_current(2e-30, base_voltage - 0.2, thermal_voltage)
        base_emitter_leakage = junction_current(
            2e-12,
            base_voltage,
            1.7 * thermal_voltage,
        )
        base_collector_leakage = junction_current(
            4e-12,
            base_voltage - 0.2,
            2.1 * thermal_voltage,
        )
        collector = forward - reverse - reverse / 1e12 - base_collector_leakage
        base = (
            forward / 1e12 + base_emitter_leakage + reverse / 1e12 +
            base_collector_leakage
        )
        emitter = -collector - base
        for source, expected in zip(
            ("Vc", "Vb", "Ve"),
            (-3.0 * collector, -3.0 * base, -3.0 * emitter),
            strict=True,
        ):
            assert point["values"][source] == pytest.approx(expected, rel=2e-12, abs=1e-18)


def test_native_bjt_composite_leakage_dc_curve_matches_ngspice() -> None:
    native = _run("bjt_leakage_dc.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    fixture = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "bjt_leakage_dc.cir"
    completed = subprocess.run(
        [ngspice, "-b", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "dc")
    for source in ("Vc", "Vb", "Ve"):
        assert [point["values"][source] for point in native["points"]] == pytest.approx(
            [value.real for _, value in oracle[f"{source.lower()}#branch"]],
            rel=3e-5,
            abs=2e-13,
        )


def test_native_bjt_composite_leakage_temperature_and_polarity_match_ngspice() -> None:
    native = _run("bjt_leakage_temperature_op.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    fixture = (
        ROOT / "native" / "AgentSpice.Engine" / "fixtures" /
        "bjt_leakage_temperature_op.cir"
    )
    completed = subprocess.run(
        [ngspice, "-b", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "op")
    point = native["points"][0]["values"]
    for source in ("Vcn", "Vbn", "Ven", "Vcp", "Vbp", "Vep"):
        assert point[source] == pytest.approx(
            oracle[f"{source.lower()}#branch"][0][1].real,
            rel=3e-5,
            abs=2e-13,
        )


def test_native_bjt_composite_leakage_ac_conductance_matches_ngspice() -> None:
    native = _run("bjt_leakage_ac.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    fixture = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "bjt_leakage_ac.cir"
    completed = subprocess.run(
        [ngspice, "-b", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "ac")
    for source in ("Vc", "Vb", "Ve"):
        actual = [
            complex(point["complex"][source]["re"], point["complex"][source]["im"])
            for point in native["points"]
        ]
        assert actual == pytest.approx(
            [value for _, value in oracle[f"{source.lower()}#branch"]],
            rel=3e-5,
            abs=2e-13,
        )


def test_native_temperature_adjusted_bjt_ac_matches_ngspice() -> None:
    native = _run("bjt_temperature_ac.cir")
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    fixture = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "bjt_temperature_ac.cir"
    completed = subprocess.run(
        [ngspice, "-b", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "ac")
    for native_name, oracle_name in (
        ("out", "v(out)"),
        ("Vbase", "vbase#branch"),
        ("Vdd", "vdd#branch"),
    ):
        actual = [
            complex(point["complex"][native_name]["re"], point["complex"][native_name]["im"])
            for point in native["points"]
        ]
        assert actual == pytest.approx(
            [value for _, value in oracle[oracle_name]],
            rel=2e-4,
            abs=2e-7,
        )


def test_native_temperature_adjusted_bjt_transient_tracks_ngspice() -> None:
    native = _run("bjt_temperature_tran.cir")
    assert native["statistics"]["maximumConvergedResidualRatio"] <= 1.0
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice oracle is not installed")
    fixture = ROOT / "native" / "AgentSpice.Engine" / "fixtures" / "bjt_temperature_tran.cir"
    completed = subprocess.run(
        [ngspice, "-b", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    oracle = _ngspice_columns(completed.stdout, "tran")

    def errors(native_name: str, oracle_name: str) -> list[float]:
        return [
            point["values"][native_name] -
            _interpolate_complex(oracle[oracle_name], point["x"]).real
            for point in native["points"]
        ]

    output_errors = errors("out", "v(out)")
    base_current_errors = errors("Vbase", "vbase#branch")
    supply_current_errors = errors("Vdd", "vdd#branch")
    assert math.sqrt(sum(error * error for error in output_errors) / len(output_errors)) < 0.035
    assert max(abs(error) for error in output_errors) < 0.07
    assert math.sqrt(
        sum(error * error for error in base_current_errors) / len(base_current_errors)
    ) < 0.004
    assert max(abs(error) for error in base_current_errors) < 0.025
    assert math.sqrt(
        sum(error * error for error in supply_current_errors) / len(supply_current_errors)
    ) < 4e-5
    assert max(abs(error) for error in supply_current_errors) < 7e-5


@pytest.mark.parametrize(
    ("model", "instance", "message"),
    [
        (".model qmod NPN(IS=1e-15 RBM=10)", "", "unsupported BJT model parameter 'RBM'"),
        (".model qmod NPN(IS=1e-15)", "AREA=0", "BJT AREA and M must be positive"),
        (".model qmod NPN(IS=1e-15)", "TEMP=-300", "must be above absolute zero"),
        (".model qmod NPN(IS=1e-15)", "OFF", "unsupported BJT instance parameter 'OFF'"),
        (".model qmod NPN(IS=1e-15 IKF=-1)", "", "IKF, IKR, RC, RB, and RE"),
        (".model qmod NPN(IS=1e-15 ISE=-1)", "", "ISE and ISC must be non-negative"),
        (".model qmod NPN(IS=1e-15 ISC=-1)", "", "ISE and ISC must be non-negative"),
        (".model qmod NPN(IS=1e-15 NE=0)", "", "NE and NC must be positive"),
        (".model qmod NPN(IS=1e-15 NC=0)", "", "NE and NC must be positive"),
    ],
)
def test_native_bjt_rejects_unimplemented_or_invalid_contracts(
    tmp_path: Path,
    model: str,
    instance: str,
    message: str,
) -> None:
    deck = tmp_path / "unsupported-bjt.cir"
    deck.write_text(
        "\n".join(
            [
                "Unsupported BJT contract",
                "Vc collector 0 2",
                "Vb base 0 0.6",
                f"Q1 collector base 0 qmod {instance}".rstrip(),
                model,
                ".op",
                ".print op i(Vc) i(Vb)",
                ".end",
                "",
            ]
        ),
        encoding="ascii",
    )
    completed = subprocess.run(
        [shutil.which("dotnet") or "dotnet", str(DLL), str(deck)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert message.lower() in completed.stderr.lower()
