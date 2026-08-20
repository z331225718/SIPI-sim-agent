"""Fail closed on the P5-04f sampled-signal PDF stage port.

The charter fixes the stage scope; the source map records the MIT
function mapping; the cross-check evidence binds product and oracle
PDF outputs. The verifier binds charter, source map, evidence, Rust
tokens, and the PLAN P5-04f row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04f-sampled-signal-pdf-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04f-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04f-sampled-signal-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "sampled_signal_pdf_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04f.sampled-signal-pdf-stage.v1"
POLICY = "sipi.p5-04f.sampled-signal-pdf-v1.direct-and-sparse-pam"


class SampledPdfStageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SampledPdfStageError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "sampled_signal_pdf_stage_ported":
        raise SampledPdfStageError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("residual_channel_pdf") is not False:
        raise SampledPdfStageError("admission_drift")
    if admission.get("channel_selection") is not False or admission.get("equalizer_search") is not False:
        raise SampledPdfStageError("search_scope_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 5:
        raise SampledPdfStageError("source_map_mapping_drift")
    if "residual_channel_pdf" not in source_map.get("not_ported", []):
        raise SampledPdfStageError("source_map_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn sampled_signal_pdf_v1",
        "pub fn from_values_v1",
        "pub fn accelerated_sampled_signal_pdf_v1",
        "pub fn sparse_pam_component_v1",
        "pub const PAM4_SYMBOL_VALUES",
        "pub const SAMPLED_SIGNAL_PDF_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise SampledPdfStageError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-04f.sampled-signal-crosscheck-evidence.v1":
        raise SampledPdfStageError("evidence_schema_invalid")
    if evidence.get("status") != "sampled_signal_pdf_crosscheck_matched":
        raise SampledPdfStageError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 12 or any(not entry.get("matched") for entry in entries):
        raise SampledPdfStageError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04f" not in plan_text:
        raise SampledPdfStageError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except SampledPdfStageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
