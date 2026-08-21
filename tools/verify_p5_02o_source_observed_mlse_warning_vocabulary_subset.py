"""Verify the evidence-only P5-02o MLSE warning vocabulary subset."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/baselines/p5-02o-source-observed-mlse-warning-vocabulary-subset.v1.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p5-02o-source-observed-mlse-warning-vocabulary-subset.md"
WARNING_OBSERVATION = ROOT / "docs/baselines/p5-r480-warning-observation.v1.yaml"
PINNED_CANDIDATE = ROOT / "docs/baselines/p5-06-pinned-source-external-matlab-oracle-candidate-run.v1.yaml"
COM_LIB = ROOT / "crates/sipi-com/src/lib.rs"
REMOVED_RUST_MODULE = ROOT / "crates/sipi-com/src/source_warning_catalog_v1.rs"

SCHEMA = "sipi.p5-02o.source-observed-mlse-warning-vocabulary-subset.v1"
WARNING_OBSERVATION_SHA256 = "862f1c930d1aff2463815273ba048dcb80edd52b8e80b56a4ec7eaa063f530b4"
PINNED_CANDIDATE_SHA256 = "294984a6ef9f8ad756435dd133afc953866537326f623858c90890f7de3e43d4"
SOURCE = {
    "repository": "https://github.com/z331225718/agent-com.git",
    "commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
    "tree": "7094ab6e84989b218730c52432c70da10261f8ea",
    "path": "matlab_src/com_ieee8023_480.m",
    "git_blob_oid_sha1": "2e226d785c1ed2403f6d0a11288bf75939021814",
    "normalized_content_sha256": "88db14d7d82dab980d223a5be02a28013c11e0d0239e0e97e36c9d36fef55596",
}
ENTRIES = [
    {
        "id": "mlse_not_applied_noise_gt_signal",
        "source_line": 2109,
        "message": "MLSE not applied because there is more noise than signal",
        "message_sha256": "7ef227d851fd018df49b13f66288f55ef883860c52c4087a6c690eda8fcec2b3",
    },
    {
        "id": "mlse_truncation_failed",
        "source_line": 2228,
        "message": "MLSE truncation failed. Try increasing trunc",
        "message_sha256": "78a0a41cd1e30adbd346d3581812d758f27a1fcb98de692a347495571aab0e80",
    },
    {
        "id": "mlse_not_applied_der_below_cdr_lock",
        "source_line": 2238,
        "message": "MLSE not applied because the DER is less than that required for the CDR to lock",
        "message_sha256": "f45085e6b7cb0411746d15f46bbda4a68332aa7979bc8bf41229164d4cf5ef2b",
    },
]
EXCLUDED = {
    "source_line": 2230,
    "callable": "msgbox",
    "kind": "ui_warning_dialog_not_warning_function",
    "message": "MLSE truncation failed. Try increasing N_tc",
    "message_sha256": "4b7455dabb83012ed25cf378aa4184cddd37b0538204ab03651aa0102ca3f485",
}
NON_CLAIMS = [
    "not_complete_warning_catalog",
    "not_runtime_warning_detection",
    "not_matlab_execution",
    "not_mlse_der_cdr_trigger_semantics",
    "not_checkpoint_alignment",
    "not_metric_tolerance",
    "not_external_oracle",
    "not_acceptance",
    "not_release",
]


class VocabularyError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VocabularyError("document_not_mapping")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise VocabularyError(reason)


def validate(document: dict[str, Any] | None = None) -> dict[str, Any]:
    document = _load(EVIDENCE) if document is None else document
    _require(set(document) == {"schema", "status", "source", "inherited_records", "selection", "entries", "excluded_callsite", "scope", "non_claims"}, "shape_invalid")
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == "inherited_pinned_source_observation", "status_invalid")
    _require(document.get("source") == SOURCE, "source_identity_invalid")
    _require(document.get("inherited_records") == [
        {"path": "docs/baselines/p5-r480-warning-observation.v1.yaml", "sha256": WARNING_OBSERVATION_SHA256},
        {"path": "docs/baselines/p5-06-pinned-source-external-matlab-oracle-candidate-run.v1.yaml", "sha256": PINNED_CANDIDATE_SHA256},
    ], "inherited_records_invalid")
    _require(_sha256(WARNING_OBSERVATION) == WARNING_OBSERVATION_SHA256, "warning_observation_drift")
    _require(_sha256(PINNED_CANDIDATE) == PINNED_CANDIDATE_SHA256, "pinned_candidate_drift")

    warning_observation = _load(WARNING_OBSERVATION)
    _require(warning_observation.get("warning_call_count") == 25, "warning_observation_count_invalid")
    observed = warning_observation.get("warnings")
    _require(isinstance(observed, list), "warning_observation_entries_invalid")
    by_line = {entry.get("line"): entry for entry in observed if isinstance(entry, dict)}
    for expected in ENTRIES:
        _require(by_line.get(expected["source_line"]) == {
            "line": expected["source_line"], "kind": "warning", "message": expected["message"]
        }, f"inherited_warning_entry_invalid:{expected['source_line']}")
    _require(by_line.get(2230) == {"line": 2230, "kind": "msgbox_warning", "message": EXCLUDED["message"]}, "inherited_exclusion_invalid")

    pinned = _load(PINNED_CANDIDATE).get("source")
    _require(isinstance(pinned, dict), "pinned_source_missing")
    matlab_source = pinned.get("matlab_source")
    _require(
        pinned.get("canonical_origin") == SOURCE["repository"]
        and pinned.get("commit") == SOURCE["commit"]
        and pinned.get("tree") == SOURCE["tree"]
        and isinstance(matlab_source, dict)
        and matlab_source.get("path") == SOURCE["path"]
        and matlab_source.get("git_blob") == SOURCE["git_blob_oid_sha1"]
        and matlab_source.get("git_blob_sha256") == SOURCE["normalized_content_sha256"],
        "pinned_source_identity_invalid",
    )

    _require(document.get("selection") == {
        "scope": "mlse_region_warning_function_calls_only",
        "included_callable": "warning",
        "excluded_callable": "msgbox",
        "entry_count": 3,
    }, "selection_invalid")
    _require(document.get("entries") == ENTRIES, "entries_invalid")
    _require(document.get("excluded_callsite") == EXCLUDED, "excluded_callsite_invalid")
    for entry in ENTRIES + [EXCLUDED]:
        _require(hashlib.sha256(entry["message"].encode("utf-8")).hexdigest() == entry["message_sha256"], "message_digest_invalid")
    _require(document.get("scope") == {
        "product_rust_api_added": False,
        "runtime_detector": "not_implemented",
        "matlab_execution": "not_performed",
        "source_reverification": "inherited_records_only",
    }, "scope_invalid")
    _require(document.get("non_claims") == NON_CLAIMS, "non_claims_invalid")
    _require(AUDIT.is_file() and "Line 2230" in AUDIT.read_text(encoding="utf-8"), "audit_binding_invalid")
    _require(not REMOVED_RUST_MODULE.exists(), "product_rust_module_present")
    public_text = COM_LIB.read_text(encoding="utf-8")
    _require(not any(token in public_text for token in ("SourceWarningV1", "SOURCE_WARNING_CATALOG_V1", "AGENT_COM_SOURCE_")), "product_public_api_present")
    return {"schema": SCHEMA, "valid": True, "entry_count": 3, "inherited_warning_count": 25}


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        print(json.dumps(validate(), sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, yaml.YAMLError, VocabularyError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
