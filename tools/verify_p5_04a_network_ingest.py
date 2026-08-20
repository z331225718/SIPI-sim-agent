"""Fail closed on the P5-04a network-ingest (mixed-mode) port.

The charter fixes the ported stage scope; the source map records the
MIT function mapping. The verifier binds charter, source map, Rust
tokens, and the PLAN P5-04a row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04a-network-ingest.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04a-mit-source-map.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "mixed_mode_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04a.network-ingest.v1"
POLICY = "sipi.p5-04a.network-ingest-v1.mixed-mode-transform-only"


class IngestError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise IngestError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "network_ingest_mixed_mode_ported_no_computation":
        raise IngestError("charter_schema_or_status_invalid")
    if charter.get("admission", {}).get("com_metric_computation") is not False:
        raise IngestError("admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 3:
        raise IngestError("source_map_mapping_drift")
    if not SOURCE.is_file():
        raise IngestError("source_missing")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn com_mixed_mode_v1",
        "pub fn sdd21_v1",
        "pub fn com_t_v1",
        "pub const NETWORK_INGEST_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise IngestError("implementation_binding_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04a" not in plan_text:
        raise IngestError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except IngestError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
