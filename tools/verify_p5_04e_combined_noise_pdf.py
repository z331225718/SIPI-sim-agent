"""Fail closed on the P5-04e combined noise PDF stage port.

The charter fixes the combination scope; the source map records the MIT
mapping. The verifier binds charter, source map, Rust tokens, and the
PLAN P5-04e row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04e-combined-noise-pdf-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04e-mit-source-map.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "combined_noise_pdf_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04e.combined-noise-pdf-stage.v1"
POLICY = "sipi.p5-04e.combined-noise-pdf-v1.eq-93a-45-order"


class CombinedPdfError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CombinedPdfError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "combined_noise_pdf_stage_ported":
        raise CombinedPdfError("charter_schema_or_status_invalid")
    if charter.get("admission", {}).get("sampled_signal_pdf") is not False:
        raise CombinedPdfError("admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 2:
        raise CombinedPdfError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn combine_r480_noise_pdf_v1",
        "pub struct CombinedNoisePdfV1",
        "pub const COMBINED_NOISE_PDF_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise CombinedPdfError("implementation_binding_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04e" not in plan_text:
        raise CombinedPdfError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except CombinedPdfError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
