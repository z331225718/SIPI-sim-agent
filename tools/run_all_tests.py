"""One-command unit-test gate for SIPI-sim-agent.

Default mode runs every unittest module in ``tests/`` and ``tools/``.
``--full`` additionally runs the M1 rule-ledger and conformance verifiers,
including the external Rust/Python probes (slow, requires source snapshots).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_FILES = sorted([*ROOT.glob("tests/**/test_*.py"), *ROOT.glob("tools/test_*.py")])
FULL_VERIFIERS = [
    ROOT / "tools" / "verify_m1_rule_ledger.py",
    ROOT / "tools" / "verify_m1_conformance.py",
]


def run(program: Path, args: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-B", str(program), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + result.stderr


def main() -> int:
    full = "--full" in sys.argv[1:]
    failures: list[tuple[str, str]] = []
    for test_file in TEST_FILES:
        code, output = run(test_file, [])
        status = "PASS" if code == 0 else "FAIL"
        print(f"{status}  {test_file.relative_to(ROOT).as_posix()}")
        if code != 0:
            failures.append((test_file.name, output))
    if full:
        for verifier in FULL_VERIFIERS:
            code, output = run(verifier, [])
            status = "PASS" if code == 0 else "FAIL"
            print(f"{status}  {verifier.relative_to(ROOT).as_posix()}")
            if code != 0:
                failures.append((verifier.name, output))
    print(f"\n{len(TEST_FILES) + (len(FULL_VERIFIERS) if full else 0)} runs, {len(failures)} failed")
    for name, output in failures:
        print(f"\n===== {name} =====")
        print("\n".join(output.splitlines()[-30:]))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
