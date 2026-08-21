"""Verify the additive P3C-03c same-checkpoint comparison boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-03c-com-metric-checkpoint-boundary.v1.yaml"
AUDIT = ROOT / "docs" / "baselines" / "audits" / "2026-08-21-p3c-03c-com-metric-checkpoint-boundary.md"
SCHEMA = "sipi.p3c-03c.com-metric-checkpoint-boundary.v1"
AUDIT_BINDING = {
    "path": "docs/baselines/audits/2026-08-21-p3c-03c-com-metric-checkpoint-boundary.md",
    "sha256": "aa6319054e81926db429bd77312071a918df50396897713d02a93bb04af0c489",
}
SOURCE_SHA256 = "55e4021f7df51b9b7c936d8f7f144451b6d8cd3dfd93a3aedbdaf9c4d09a28ca"
PUBLIC_SHA256 = "92d18708db1c8251dca4118c4e3abf01fb00a02722351938d5886310ca6c48ca"
ABSOLUTE = re.compile(r"(?:^|[^A-Za-z0-9])[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:home|Users|private|tmp|mnt)/")


class BoundaryError(RuntimeError):
    """Raised when the boundary record is not exact."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise BoundaryError(reason)


def _walk(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(key)
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "document_not_mapping")
    return value


def validate_document(document: dict[str, Any] | None = None) -> dict[str, Any]:
    document = _load(EVIDENCE) if document is None else document
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == "same_checkpoint_compare_surface_implemented_acceptance_open", "status_invalid")
    _require(document.get("authority") == "product_comparison_policy_only", "authority_invalid")
    implementation = document.get("implementation", {})
    _require(implementation.get("source") == {"path": "crates/sipi-compare/src/com_metric_checkpoint_v1.rs", "sha256": SOURCE_SHA256}, "source_binding_invalid")
    _require(implementation.get("public_surface") == {"path": "crates/sipi-compare/src/lib.rs", "sha256": PUBLIC_SHA256}, "public_binding_invalid")
    for binding in (implementation["source"], implementation["public_surface"]):
        path = ROOT / binding["path"]
        _require(path.is_file(), f"implementation_missing:{binding['path']}")
        _require(hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"], f"implementation_hash_invalid:{binding['path']}")
    _require(implementation.get("entrypoint") == "compare_com_metric_checkpoint_v1", "entrypoint_invalid")
    _require(implementation.get("metrics") == ["COM_dB", "ERL_dB", "TD_ILN_dB"], "metric_surface_invalid")
    _require(implementation.get("all_values_finite_required") is True, "finite_policy_invalid")
    comparison = document.get("comparison", {})
    _require(comparison.get("alignment_policy") == "strict_same_checkpoint_no_alignment", "alignment_policy_invalid")
    _require(comparison.get("interpolation") is False and comparison.get("unit_conversion") is False, "alignment_shortcut_invalid")
    _require(comparison.get("icn_alias") is False, "icn_alias_invalid")
    _require(comparison.get("owner_absolute_tolerance_db") == {"COM_dB": 0.1, "ERL_dB": 0.1, "TD_ILN_dB": 0.1}, "absolute_tolerance_invalid")
    _require(comparison.get("owner_relative_tolerance") == 0.0, "relative_tolerance_invalid")
    _require(comparison.get("mismatched_checkpoint") == "rejected", "checkpoint_mismatch_policy_invalid")
    _require(document.get("tests", {}).get("focused_unit_tests") == 5, "focused_test_count_invalid")
    _require(document.get("audit") == AUDIT_BINDING, "audit_binding_invalid")
    _require(AUDIT.is_file(), "audit_missing")
    _require(hashlib.sha256(AUDIT.read_bytes()).hexdigest() == AUDIT_BINDING["sha256"], "audit_hash_invalid")
    _require(not any(ABSOLUTE.search(value) for value in _walk(document)), "absolute_path_in_document")
    _require(not ABSOLUTE.search(AUDIT.read_text(encoding="utf-8")), "absolute_path_in_audit")
    return {"schema": SCHEMA, "valid": True, "source_sha256": SOURCE_SHA256}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        print(json.dumps(validate_document(), sort_keys=True))
        return 0
    except (OSError, UnicodeError, yaml.YAMLError, BoundaryError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
