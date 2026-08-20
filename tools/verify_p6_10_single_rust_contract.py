"""Verify P6-10 single-Rust-contract invariant for the product CLI.

P6-10 requires future service/GUI layers to call the same Rust contract
and never create a second platform semantic surface. The product CLI must
therefore stay free of python invocation, subprocess spawning, and legacy
engine fallbacks. This gate fails closed if any of those appear in the
CLI source tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p6-10.single-rust-contract.v1"

CLI_MAIN = "crates/sipi-cli/src/main.rs"

FORBIDDEN_PATTERNS = {
    "python": re.compile(r"\bpython\b", re.IGNORECASE),
    "process_spawn": re.compile(r"Command::new|process::Command|std::process"),
    "legacy_fallback": re.compile(r"legacy.*fallback|old engine|fallback.*legacy", re.IGNORECASE),
    "pip_invoke": re.compile(r"pip\s+(install|download)", re.IGNORECASE),
}


class SingleContractError(RuntimeError):
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
        raise SingleContractError("source_read_failed") from error


def validate(root: Path = ROOT) -> dict[str, Any]:
    if not (root / CLI_MAIN).is_file():
        raise SingleContractError("cli_main_missing")
    text = read_text(CLI_MAIN)
    hits: list[str] = []
    for name, pattern in sorted(FORBIDDEN_PATTERNS.items()):
        match = pattern.search(text)
        if match is not None:
            hits.append(f"{name}:{match.group(0)}")
    if hits:
        raise SingleContractError("forbidden_reference:" + ",".join(hits))
    return {"valid": True, "patterns_checked": len(FORBIDDEN_PATTERNS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except SingleContractError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
