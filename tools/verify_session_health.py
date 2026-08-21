"""One-command session health check.

Runs every top-level state-keeping gate and meta-gate of the session and
reports a single health verdict:

- coverage gate sweep (52 gates, BAD=0 required)
- session slice reference audit
- PLAN reference audit
- owner-input request ledger binding
- remaining-items ledger
- open-item gate coverage

Exit code is 1 if any check fails, else 0.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.session-health.v1"

CHECKS = [
    # sweep reports totals and exits 0 only when BAD=0; no "valid" key.
    ("coverage-gate-sweep", "tools/sweep_coverage_gates.py", [], "exit_only"),
    ("slice-reference-audit", "tools/audit_slice_references.py", []),
    ("plan-reference-audit", "tools/audit_plan_references.py", []),
    ("owner-input-request", "tools/verify_owner_input_request.py", []),
    ("owner-input-request-current-reconciliation", "tools/verify_owner_decision_reconciliation_v2.py", []),
    ("remaining-items-ledger", "tools/verify_plan_remaining_items_ledger.py", []),
    ("open-item-gate-coverage", "tools/verify_plan_open_items_gate_coverage.py", []),
]


class HealthError(RuntimeError):
    pass


def check_list() -> list[dict]:
    checks = []
    for name, tool, args, *mode in CHECKS:
        if not (ROOT / tool).is_file():
            raise HealthError(f"tool_missing:{name}:{tool}")
        checks.append({"name": name, "tool": tool, "args": args, "mode": mode[0] if mode else "valid_key"})
    return checks


def run_health() -> dict:
    checks = check_list()
    results = []
    failed = 0
    for check in checks:
        completed = subprocess.run(
            [sys.executable, check["tool"]] + check["args"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        ok = completed.returncode == 0 and (
            check["mode"] == "exit_only" or '"valid": true' in completed.stdout
        )
        if not ok:
            failed += 1
        results.append({
            "name": check["name"],
            "ok": ok,
            "exit": completed.returncode,
            "summary": completed.stdout.strip()[-160:],
        })
    return {"schema": SCHEMA, "valid": failed == 0, "checks": len(results), "failed": failed, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        report = run_health()
    except HealthError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
