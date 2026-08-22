"""One-command session health check.

Runs every top-level state-keeping gate and meta-gate of the session and
reports a single health verdict:

- coverage gate sweep (52 gates, BAD=0 required)
- session slice reference audit
- PLAN reference audit
- owner-input request ledger binding
- active upstream migration and deferred release ledgers
- three pinned upstream adapter contracts and the 15-route CLI boundary
- current Rust-candidate coverage for all 15 upstream rows
- historical v0.2 remaining-items ledger
- historical v0.2 open-item gate coverage
- closed P5-05 parameter ingestion consumer
- closed P5-09 wording boundary

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
    ("upstream-migration-inventory", "tools/verify_upstream_migration_inventory.py", []),
    ("agent-spice-upstream-adapter", "tools/verify_as_upstream_adapters.py", [], "exit_only"),
    ("pybert-upstream-adapter", "tools/verify_pb_upstream_workflows.py", []),
    ("agent-com-upstream-adapter", "tools/verify_com_upstream_adapter.py", [], "exit_only"),
    ("upstream-cli-integration", "tools/verify_upstream_cli_integration.py", []),
    ("upstream-rust-candidate-coverage", "tools/verify_upstream_rust_candidate_coverage.py", []),
    ("release-capability-publication-live", "tools/verify_release_capability_publication.py", []),
    ("historical-v0.2-remaining-items-ledger", "tools/verify_plan_remaining_items_ledger.py", []),
    ("historical-v0.2-open-item-gate-coverage", "tools/verify_plan_open_items_gate_coverage.py", []),
    ("p5-05-parameter-ingestion", "tools/verify_p5_05g_parameter_ingestion.py", []),
    (
        "p5-09-wording-retirement",
        "tools/verify_p5_09b_com_behavior_replica_wording_retirement.py",
        [],
    ),
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
