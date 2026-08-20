"""Audit every relative markdown link in PLAN.md against the workspace.

The plan binds evidence, charters, verifiers and audits by relative path;
a dangling reference would silently break the audit trail. This gate
parses every markdown link whose target does not start with http/https/#
and fails closed when any target path does not exist in the workspace.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.plan.reference-audit.v1"
PLAN = ROOT / "PLAN.md"
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


class PlanReferenceError(RuntimeError):
    pass


def validate(root: Path = ROOT) -> dict:
    plan_text = PLAN.read_text(encoding="utf-8")
    missing = []
    total = 0
    for _text, target in LINK_RE.findall(plan_text):
        if target.startswith(("http://", "https://", "#")) or target.startswith("`"):
            continue
        path = target.split("#", 1)[0]
        if not path:
            continue
        total += 1
        if not (root / path).exists() and not (root / path).is_file() and not (root / path).is_dir():
            missing.append(path)
    if missing:
        raise PlanReferenceError("missing_plan_reference:" + ",".join(sorted(set(missing))))
    return {"valid": True, "links_checked": total, "missing": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except PlanReferenceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
