"""Fail closed on the P5-04c COM metrics stage port.

The charter fixes the scalar metrics scope; the source map records the
MIT function mapping. The verifier binds charter, source map, Rust
tokens, and the PLAN P5-04c row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04c-com-metrics-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04c-mit-source-map.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "com_metrics_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04c.com-metrics-stage.v1"
POLICY = "sipi.p5-04c.com-metrics-v1.scalar-cdf-metrics"


class MetricsError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MetricsError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "com_metrics_scalar_stage_ported_no_pdf":
        raise MetricsError("charter_schema_or_status_invalid")
    if charter.get("outputs") != ["com_db", "vec_db", "veo_mv"]:
        raise MetricsError("outputs_drift")
    if charter.get("admission", {}).get("discrete_pdf_construction") is not False:
        raise MetricsError("admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 3:
        raise MetricsError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn calculate_com_metrics_v1",
        "pub struct ComMetricsV1",
        "pub const COM_METRICS_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise MetricsError("implementation_binding_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04c" not in plan_text:
        raise MetricsError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except MetricsError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
