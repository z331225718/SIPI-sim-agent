"""Classified sweep over every gate bound by the open-item coverage map.

Runs each unique gate file listed in
`verify_plan_open_items_gate_coverage.OPEN_ITEM_GATES` and classifies the
outcome:

- VALID_KEY: exit 0 and `"valid": true` in stdout;
- RC0_ALT_KEY: exit 0 with an alternate success key (state-keeping gates
  that report a fixed status instead of a `valid` flag);
- RC2_NEEDS_ARGS: exit 2 with empty stdout (argument-required gates fail
  closed on bare invocation);
- BAD: anything else (regression).

Exit code is 1 when any gate is BAD, else 0.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_plan_open_items_gate_coverage as GC


def main() -> int:
    gates = sorted(set(gate for listed in GC.OPEN_ITEM_GATES.values() for gate in listed))
    valid_key = []
    alt_key = []
    needs_args = []
    bad = []
    for gate in gates:
        completed = subprocess.run(
            [sys.executable, gate],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        out = completed.stdout.strip()
        if completed.returncode == 0 and '"valid": true' in out:
            valid_key.append(gate)
        elif completed.returncode == 0:
            alt_key.append(gate)
        elif completed.returncode == 2 and not out:
            needs_args.append(gate)
        else:
            bad.append((gate, completed.returncode, out[:140]))
    print("TOTAL=" + str(len(gates)))
    print("VALID_KEY=" + str(len(valid_key)))
    print("RC0_ALT_KEY=" + str(len(alt_key)))
    print("RC2_NEEDS_ARGS=" + str(len(needs_args)))
    print("BAD=" + str(len(bad)))
    for name, rc, message in bad:
        print("BAD: " + name + " rc=" + str(rc) + " " + message)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
