"""Verify the P3B-02 link kernel-singleton and bypass-only invariant.

P3B-02a/02b require: sipi-link implements only the product-owned causal
FIR full linear convolution; CTLE/FFE stages remain bypass-only; explicit
limits and overflow fail closed. This gate fails closed if the convolution
kernel is defined outside sipi-link/src/lib.rs, if an equalizer (CTLE/FFE)
implementation exists, or if the bypass-only assertion is lost.
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
SCHEMA = "sipi.p3b-02.link-kernel-singleton.v1"

LINK_LIB = "crates/sipi-link/src/lib.rs"
LINK_RECEIVER = "crates/sipi-link/src/receiver.rs"
LINK_SOURCES = ("crates/sipi-link/src/lib.rs", "crates/sipi-link/src/receiver.rs")

CONVOLUTION_SYMBOLS = frozenset({
    "convolve_causal_fir_v1",
    "convolve_causal_fir_with_context_v1",
    "convolve_causal_fir_checked",
})

CONSUMER_PATHS = frozenset({
    "crates/sipi-cli/src/main.rs",
    "crates/sipi-pipeline/src/tran_to_link.rs",
    "crates/sipi-pipeline/src/project_attempt.rs",
})


class LinkKernelError(RuntimeError):
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
        raise LinkKernelError("source_read_failed") from error


def definition_line(pattern: str, text: str) -> int | None:
    for index, line in enumerate(text.splitlines(), start=1):
        if re.match(rf"^(pub\s+)?fn\s+{pattern}\s*\(", line.strip()):
            return index
    return None


def sipi_link_imported_symbols(text: str) -> set[str]:
    imported: set[str] = set()
    for match in re.finditer(r"use\s+sipi_link::\{([^}]*)\}", text):
        for line in match.group(1).splitlines():
            for symbol in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", line):
                imported.add(symbol)
    for match in re.finditer(r"use\s+sipi_link::([A-Za-z_][A-Za-z0-9_]*);", text):
        imported.add(match.group(1))
    return imported


def validate(root: Path = ROOT) -> dict[str, Any]:
    # 1. The kernel library must exist and be git-tracked.
    if not git_tracked(LINK_LIB) or not (root / LINK_LIB).is_file():
        raise LinkKernelError("link_library_missing")
    library_text = read_text(LINK_LIB)

    # 2. Every convolution symbol must be defined exactly once, in the library.
    for symbol in sorted(CONVOLUTION_SYMBOLS):
        line = definition_line(re.escape(symbol), library_text)
        if line is None:
            raise LinkKernelError(f"kernel_symbol_missing:{symbol}")
        count = sum(1 for text_line in library_text.splitlines()
                   if re.match(rf"^(pub\s+)?fn\s+{re.escape(symbol)}\s*\(", text_line.strip()))
        if count != 1:
            raise LinkKernelError(f"kernel_symbol_duplicated:{symbol}")

    # 3. No consumer may define a convolution symbol (no copied kernel).
    for relative in CONSUMER_PATHS:
        if not git_tracked(relative):
            continue
        text = read_text(relative)
        for symbol in CONVOLUTION_SYMBOLS:
            if definition_line(re.escape(symbol), text) is not None:
                raise LinkKernelError(f"kernel_copied:{relative}:{symbol}")

    # 4. Consumer references must go through an explicit sipi_link import.
    for relative in CONSUMER_PATHS:
        if not git_tracked(relative):
            continue
        text = read_text(relative)
        imported = sipi_link_imported_symbols(text)
        for symbol in CONVOLUTION_SYMBOLS:
            references = [line for line in text.splitlines()
                          if re.search(rf"\b{re.escape(symbol)}\b", line)
                          and not line.strip().startswith("//")
                          and "use sipi_link" not in line]
            if references and symbol not in imported:
                raise LinkKernelError(f"kernel_reference_without_import:{relative}:{symbol}")

    # 5. CTLE/FFE must remain bypass-only: no stage implementation exists.
    if not re.search(r"RxStagesV1::bypass\(\)\.ctle\(\),\s*CtleStageV1::Bypass", library_text):
        raise LinkKernelError("bypass_assertion_missing")
    # An equalizer implementation would be a stage selection that is not Bypass.
    for relative in LINK_SOURCES:
        text = read_text(relative).lower()
        if re.search(r"ctle[a-z0-9_]*::(?!bypass)[a-z0-9_]+", text) or re.search(r"ffe[a-z0-9_]*::(?!bypass)[a-z0-9_]+", text):
            raise LinkKernelError("equalizer_stage_implemented")

    return {"valid": True, "kernel_symbols": len(CONVOLUTION_SYMBOLS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except LinkKernelError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
