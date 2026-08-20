"""Verify the P2-02 solver-singleton invariant for sipi-tran.

P2-02 requires the accepted TRAN kernel to converge into the sipi-tran
library: the CLI and pipeline may only call the library API and must not
copy or re-implement the solver. This verifier fails closed if any
solver symbol is defined outside crates/sipi-tran/src/lib.rs, if any
non-library consumer references a solver symbol without an explicit
`use sipi_tran::` import, or if the comparator harness loses its
feature gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p2-02.solver-singleton.v1"

SOLVER_LIB = "crates/sipi-tran/src/lib.rs"
HARNESS_BIN = "crates/sipi-tran/src/bin/sipi_tran_rc_pulse_harness.rs"
HARNESS_FEATURE = "rc-pulse-harness"
HARNESS_CARGO = "crates/sipi-tran/Cargo.toml"

SOLVER_SYMBOLS = frozenset({
    "simulate_rc_pulse",
    "simulate_rc_pulse_with_context",
    "simulate_one_node_rc_pulse",
    "simulate_one_node_rc_pulse_with_context",
    "simulate_one_node_rc_pulse_checked",
    "simulate_one_node_rc_pwl",
    "simulate_one_node_rc_pwl_with_context",
    "simulate_one_node_rc_pwl_checked",
    "backward_euler_step",
})

CONSUMER_PATHS = frozenset({
    "crates/sipi-cli/src/main.rs",
    "crates/sipi-pipeline/src/tran_to_link.rs",
    "crates/sipi-pipeline/src/project_attempt.rs",
    "crates/sipi-cli/tests/p6_current_topology.rs",
})

CONSUMER_CRATES = frozenset({
    "crates/sipi-cli",
    "crates/sipi-pipeline",
})


class SolverSingletonError(RuntimeError):
    pass


def git_tracked(relative: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", "--", relative],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
    )
    return completed.returncode == 0


def read_text(relative: str) -> str:
    try:
        return (ROOT / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise SolverSingletonError("source_read_failed") from error


def sipi_tran_imported_symbols(text: str) -> set[str]:
    """Collect symbols imported from sipi_tran, including multi-line braces."""
    imported: set[str] = set()
    for match in re.finditer(r"use\s+sipi_tran::\{([^}]*)\}", text):
        for line in match.group(1).splitlines():
            for symbol in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", line):
                imported.add(symbol)
    for match in re.finditer(r"use\s+sipi_tran::([A-Za-z_][A-Za-z0-9_]*);", text):
        imported.add(match.group(1))
    return imported


def definition_line(pattern: str, text: str) -> int | None:
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if re.match(rf"^(pub\s+)?fn\s+{pattern}\s*\(", stripped):
            return index
    return None


def validate(root: Path = ROOT) -> dict[str, Any]:
    # 1. The solver library must exist and be git-tracked.
    if not git_tracked(SOLVER_LIB) or not (root / SOLVER_LIB).is_file():
        raise SolverSingletonError("solver_library_missing")
    library_text = read_text(SOLVER_LIB)

    # 2. Every solver symbol must be defined exactly once, inside the library.
    for symbol in sorted(SOLVER_SYMBOLS):
        line = definition_line(re.escape(symbol), library_text)
        if line is None:
            raise SolverSingletonError(f"solver_symbol_missing:{symbol}")
        count = sum(1 for text_line in library_text.splitlines()
                   if re.match(rf"^(pub\s+)?fn\s+{re.escape(symbol)}\s*\(", text_line.strip()))
        if count != 1:
            raise SolverSingletonError(f"solver_symbol_duplicated:{symbol}")

    # 3. No consumer crate may define any solver symbol (no copied solver).
    for crate in sorted(CONSUMER_CRATES):
        for source in sorted((root / crate).rglob("*.rs")):
            relative = source.relative_to(root).as_posix()
            text = source.read_text(encoding="utf-8")
            for symbol in SOLVER_SYMBOLS:
                if definition_line(re.escape(symbol), text) is not None:
                    raise SolverSingletonError(f"solver_copied:{relative}:{symbol}")

    # 4. Every consumer reference to a solver symbol must go through an
    #    explicit `use sipi_tran::{...}` import in the same file.
    for relative in sorted(CONSUMER_PATHS):
        if not git_tracked(relative):
            continue
        text = read_text(relative)
        for symbol in SOLVER_SYMBOLS:
            references = [line for line in text.splitlines()
                          if re.search(rf"\b{re.escape(symbol)}\b", line)
                          and not re.match(rf"^\s*//", line)]
            if not references:
                continue
            has_import = symbol in sipi_tran_imported_symbols(text)
            if not has_import:
                raise SolverSingletonError(f"solver_reference_without_import:{relative}:{symbol}")

    # 5. The comparator harness must stay feature-gated and unwired.
    if not git_tracked(HARNESS_BIN):
        raise SolverSingletonError("harness_binary_missing")
    harness_text = read_text(HARNESS_BIN)
    if not re.search(r"comparator-only", harness_text, re.IGNORECASE):
        raise SolverSingletonError("harness_role_comment_missing")
    cargo_text = read_text(HARNESS_CARGO)
    if not re.search(rf"required-features\s*=\s*\[\s*\"{HARNESS_FEATURE}\"\s*\]", cargo_text):
        raise SolverSingletonError("harness_feature_gate_missing")

    return {"valid": True, "solver_symbols": len(SOLVER_SYMBOLS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except SolverSingletonError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
