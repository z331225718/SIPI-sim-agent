"""Fail closed on the P5-04h noise-PDF build stage port.

The charter fixes the stage scope; the source map records the MIT
function mapping; the cross-check evidence binds product and oracle
PDF surfaces. The verifier binds charter, source map, evidence, Rust
tokens, and the PLAN P5-04h row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04h-build-noise-pdf-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04h-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04h-noise-pdf-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "build_noise_pdf_v1.rs"
ERF_SOURCE = ROOT / "crates" / "sipi-com" / "src" / "erf_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04h.build-noise-pdf-stage.v1"
POLICY = "sipi.p5-04h.build-noise-pdf-v1.gaussian-dual-dirac"
ERF_POLICY = "sipi.p5-04h.erf-v1.as7-series-newton"


class NoisePdfStageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NoisePdfStageError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "build_noise_pdf_stage_ported":
        raise NoisePdfStageError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("mmse_path") is not False:
        raise NoisePdfStageError("admission_drift")
    if admission.get("equalizer_search") is not False:
        raise NoisePdfStageError("search_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise NoisePdfStageError("source_map_mapping_drift")
    if "search_r480_mmse / MMSE path" not in source_map.get("not_ported", []):
        raise NoisePdfStageError("source_map_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    erf_source = ERF_SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn build_r480_noise_pdf_v1",
        "pub struct R480NoisePdfV1",
        "pub const BUILD_NOISE_PDF_POLICY_V1",
        POLICY,
    )
    erf_tokens = ("pub fn erfcinv_v1", "pub const ERF_POLICY_V1", ERF_POLICY)
    if any(token not in source for token in required_tokens):
        raise NoisePdfStageError("implementation_binding_drift")
    if any(token not in erf_source for token in erf_tokens):
        raise NoisePdfStageError("erf_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-04h.noise-pdf-crosscheck-evidence.v1":
        raise NoisePdfStageError("evidence_schema_invalid")
    if evidence.get("status") != "noise_pdf_crosscheck_matched":
        raise NoisePdfStageError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 4 or any(not entry.get("matched") for entry in entries):
        raise NoisePdfStageError("evidence_entry_mismatch")
    for entry in entries:
        if abs(entry["ber_q_product"] - entry["ber_q_oracle"]) > 1e-11:
            raise NoisePdfStageError("evidence_ber_q_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04h" not in plan_text:
        raise NoisePdfStageError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except NoisePdfStageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
