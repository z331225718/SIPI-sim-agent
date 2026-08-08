"""HSPICE differential oracle (opt-in, commercial license).

Run with: ``pytest --run-oracle=hspice``. Wraps the existing
``scripts/compare_rust_hspice_*.py`` comparison scripts (no numerical
re-implementation) so tolerances stay authoritative in one place.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from oracles import hspice_executable, rust_engine

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

pytestmark = pytest.mark.skipif(
    hspice_executable() is None or rust_engine() is None,
    reason="HSPICE and a built Rust engine are both required",
)


@pytest.mark.oracle("hspice")
def test_rust_hspice_pi_matches():
    script = SCRIPTS / "compare_rust_hspice_pi.py"
    completed = subprocess.run(
        ["python", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"compare_rust_hspice_pi.py exited {completed.returncode}:\n"
        f"{completed.stdout}\n{completed.stderr}"
    )
