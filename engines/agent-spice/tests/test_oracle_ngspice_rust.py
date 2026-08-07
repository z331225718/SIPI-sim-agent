"""Rust-vs-ngspice differential oracle (independent of the .NET lane).

Opt-in via ``--run-oracle=ngspice``; also gated by tool availability in
``pytestmark`` (missing ngspice/Rust skips rather than fails). ngspice is a
locally-downloaded OSS tool, not a project dependency. Tolerances follow
``tests/test_native_engine.py`` (rel=2e-3, abs=2e-5).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from oracles import ngspice_executable, rust_engine

DIVIDER_DECK = """\
*divider
V1 in 0 5
R1 in out 1k
R2 out 0 1k
.op
.end
"""


def _ngspice_op_voltages(stdout: str) -> dict[str, float]:
    """Parse the ngspice ``Node Voltage`` OP table into {node: voltage}."""
    result: dict[str, float] = {}
    in_table = False
    for line in stdout.splitlines():
        if "Node" in line and "Voltage" in line:
            in_table = True
            continue
        if not in_table:
            continue
        if "SourceCurrent" in line or line.strip().startswith("model"):
            break
        fields = line.split()
        if not fields:
            if result:
                break
            continue
        if len(fields) >= 2:
            try:
                result[fields[0].lower()] = float(fields[-1])
            except ValueError:
                pass
    return result


pytestmark = pytest.mark.skipif(
    ngspice_executable() is None or rust_engine() is None,
    reason="ngspice and a built Rust engine are both required",
)


def _run_rust(deck: Path) -> dict:
    engine = rust_engine()
    completed = subprocess.run(
        [str(engine), str(deck), "--log", os.devnull],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def _run_ngspice(deck: Path) -> str:
    completed = subprocess.run(
        [ngspice_executable(), "-b", str(deck)],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


@pytest.mark.oracle("ngspice")
def test_rust_op_matches_ngspice_divider(tmp_path: Path):
    deck = tmp_path / "divider.cir"
    deck.write_text(DIVIDER_DECK, encoding="ascii")
    native = _run_rust(deck)
    oracle = _ngspice_op_voltages(_run_ngspice(deck))
    rust_op = next(point for point in native["points"] if point["analysis"] == "op")
    for node in ("in", "out"):
        assert node in oracle, f"ngspice OP table missing node {node}"
        assert rust_op["values"][node] == pytest.approx(oracle[node], rel=2e-3, abs=2e-5)
