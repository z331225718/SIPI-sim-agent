"""Keep required clean-room evidence headings from silently drifting."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = {
    "docs/clean-room/templates/observation-spec.v1.md": ["## Identity", "## Permitted Inputs", "## Observable Contract", "## Comparison Scope", "## Seal"],
    "docs/clean-room/templates/implementation-commit.v1.md": ["## Identity", "## Independent Design Record", "## Change Boundary", "## Verification", "## Audit Request"],
    "docs/clean-room/templates/comparison-report.v1.md": ["## Identity", "## Input Lineage", "## Results", "## Non-Claims"],
}
FORBIDDEN = ("```", "PyBERT source", "copy this source")


def verify(root: Path = ROOT) -> dict:
    blockers: list[str] = []
    for relative, headings in TEMPLATES.items():
        path = root / relative
        if not path.is_file():
            blockers.append(f"missing template: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        if any(text.count(heading) != 1 for heading in headings):
            blockers.append(f"{relative}: required headings are missing or duplicated")
        if any(token in text for token in FORBIDDEN):
            blockers.append(f"{relative}: prohibited implementation material marker")
    return {"valid": not blockers, "template_count": len(TEMPLATES), "blockers": blockers}


if __name__ == "__main__":
    report = verify()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["valid"] else 1)
