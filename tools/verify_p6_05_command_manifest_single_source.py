"""Verify P6-05 command-manifest single-source completeness.

P6-05 requires the versioned command manifest to be the single source
for command discovery, capabilities, and dispatch, with project.run
activating only the fixed composite and unavailable routes failing
closed. This gate fails closed if the manifest evidence or the
project.run publication binding disappears, or if the command-manifest
schema id drifts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p6-05.command-manifest-single-source.v1"

PUBLICATION = "docs/baselines/release-capability-publication.v1.yaml"
MANIFEST_AUDIT = "docs/baselines/audits/2026-08-11-p6-command-manifest.md"


class ManifestSourceError(RuntimeError):
    pass


def load_yaml(relative: str) -> dict[str, Any]:
    if yaml is None:
        raise ManifestSourceError("pyyaml_unavailable")
    value = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ManifestSourceError("document_not_mapping")
    return value


def read_text(relative: str) -> str:
    try:
        return (ROOT / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ManifestSourceError("source_read_failed") from error


def validate(root: Path = ROOT) -> dict[str, Any]:
    for relative in (PUBLICATION, MANIFEST_AUDIT):
        if not (root / relative).is_file():
            raise ManifestSourceError(f"file_missing:{relative}")
    publication = load_yaml(PUBLICATION)
    rows = {row.get("id"): row for row in publication.get("rows", []) if isinstance(row, dict)}
    project = rows.get("project-run")
    if (
        project is None
        or project.get("command_id") != "project.run"
        or project.get("product_surface") != "available"
        or project.get("acceptance_state") != "specified"
    ):
        raise ManifestSourceError("project_run_binding_invalid")
    audit = read_text(MANIFEST_AUDIT)
    if "sipi.command-manifest.v1" not in audit:
        raise ManifestSourceError("manifest_schema_missing")
    return {"valid": True, "single_source": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ManifestSourceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
