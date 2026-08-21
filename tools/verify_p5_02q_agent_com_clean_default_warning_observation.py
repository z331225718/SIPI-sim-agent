"""Verify the additive P5-02q clean default and warning observation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p5-02q-agent-com-clean-default-warning-observation.v1.yaml"
AUDIT = ROOT / "docs" / "baselines" / "audits" / "2026-08-21-p5-02q-agent-com-clean-default-warning-observation.md"
SCHEMA = "sipi.p5-02q.agent-com-clean-default-warning-observation.v1"
AUDIT_BINDING = {
    "path": "docs/baselines/audits/2026-08-21-p5-02q-agent-com-clean-default-warning-observation.md",
    "sha256": "da74456948b6c6ace2040ec2e37afdd0ab53ef6ee9572311af66991ff1aae6f4",
}
COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
SOURCE_ALLOWLIST = [
    {"path": "matlab_src/com_ieee8023_480.m", "git_blob": "2e226d785c1ed2403f6d0a11288bf75939021814", "bytes": 458971, "normalized_sha256": "88db14d7d82dab980d223a5be02a28013c11e0d0239e0e97e36c9d36fef55596"},
    {"path": "src/agent_com/config/excel.py", "git_blob": "1cce4365b64f3bb0ef1f7617107d2df4c929afc7", "bytes": 12218, "normalized_sha256": "2886e9986b9c3a7c1fbdc6179878679ae26bb92f511c6b0689644f9a6c053c4d"},
]
ABSOLUTE = re.compile(r"(?:^|[^A-Za-z0-9])[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:home|Users|private|tmp|mnt)/")


class ObservationError(RuntimeError):
    """Raised when the observation record is not exact."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ObservationError(reason)


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


def _git(source_root: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(["git", "-C", str(source_root), *args], capture_output=True, check=False)
    _require(result.returncode == 0, "git_object_lookup_failed")
    return result.stdout if binary else result.stdout.decode("ascii").strip()


def _verify_source_objects(source_root: Path) -> None:
    _require(source_root.is_dir(), "source_root_invalid")
    _require(_git(source_root, "rev-parse", f"{COMMIT}^{{commit}}") == COMMIT, "commit_mismatch")
    _require(_git(source_root, "rev-parse", f"{COMMIT}^{{tree}}") == TREE, "tree_mismatch")
    for item in SOURCE_ALLOWLIST:
        ref = f"{COMMIT}:{item['path']}"
        _require(_git(source_root, "rev-parse", ref) == item["git_blob"], f"blob_mismatch:{item['path']}")
        payload = _git(source_root, "cat-file", "blob", ref, binary=True)
        assert isinstance(payload, bytes)
        _require(len(payload) == item["bytes"], f"byte_count_mismatch:{item['path']}")
        _require(hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest() == item["normalized_sha256"], f"content_hash_mismatch:{item['path']}")


def validate_document(document: dict[str, Any] | None = None, source_root: Path | str | None = None) -> dict[str, Any]:
    document = _load(EVIDENCE) if document is None else document
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == "clean_default_warning_observed_blocked", "status_invalid")
    _require(document.get("authority") == "pinned_external_observation_only", "authority_invalid")
    invocation = document.get("invocation", {})
    _require(invocation.get("commit") == COMMIT and invocation.get("tree") == TREE, "source_identity_invalid")
    _require(invocation.get("profile") == "r480", "profile_invalid")
    _require(invocation.get("overrides") == {"COMPUTE_TDILN": 1}, "override_invalid")
    _require(document.get("source_allowlist") == SOURCE_ALLOWLIST, "source_allowlist_invalid")
    _require(document.get("source_lines") == {"defaults": [8915, 8926, 8927, 8930, 9222], "warning_surface": "R480-CONFIG-CONSUMPTION-PARTIAL"}, "source_lines_invalid")
    inputs = document.get("inputs", {})
    _require(inputs.get("workbook_sha256") == "e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925", "workbook_hash_invalid")
    runs = document.get("runs", {})
    _require(runs.get("count") == 2 and runs.get("repeatability") == "byte_identical_payloads", "run_shape_invalid")
    payloads = runs.get("payloads", [])
    _require(len(payloads) == 2, "payload_count_invalid")
    _require({item.get("bytes") for item in payloads} == {1211}, "payload_bytes_invalid")
    _require({item.get("sha256") for item in payloads} == {"4563a0fee6a96098717a347263323ae4a4e6fdc5fc41287d5f05f1dfd53e610c"}, "payload_hash_invalid")
    values = document.get("observed_values", {})
    _require(values.get("materialized_parameters") == {"DER_CDR": 0.01, "Q_budget_adj": 0.0, "R_LM": 0.95, "samples_per_ui": 32, "trunc": 128.0}, "materialized_parameters_invalid")
    _require(values.get("materialized_options") == {"CDR": "MM", "COMPUTE_TDILN": 1}, "materialized_options_invalid")
    _require(values.get("source_default_semantics") == {"DER_CDR": "fallback_literal", "trunc": "fallback_literal", "N_tc": "prior_value_alias_to_trunc", "Q_budget_adj": "fallback_literal", "CDR": "fallback_literal"}, "default_semantics_invalid")
    warning = document.get("warning", {})
    _require(warning == {"code": "R480-CONFIG-CONSUMPTION-PARTIAL", "severity": "WARNING", "observed_in_both_runs": True, "complete_cross_runtime_warning_contract": False}, "warning_invalid")
    _require(document.get("audit") == AUDIT_BINDING, "audit_binding_invalid")
    _require(AUDIT.is_file(), "audit_missing")
    _require(hashlib.sha256(AUDIT.read_bytes()).hexdigest() == AUDIT_BINDING["sha256"], "audit_hash_invalid")
    _require(not any(ABSOLUTE.search(value) for value in _walk(document)), "absolute_path_in_document")
    _require(not ABSOLUTE.search(AUDIT.read_text(encoding="utf-8")), "absolute_path_in_audit")
    if source_root is not None:
        _verify_source_objects(Path(source_root))
    return {"schema": SCHEMA, "valid": True, "warning_code": warning["code"], "source_object_checked": source_root is not None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(validate_document(source_root=args.source_root), sort_keys=True))
        return 0
    except (OSError, UnicodeError, yaml.YAMLError, ObservationError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
