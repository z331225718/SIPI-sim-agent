"""Verify the additive P3B-02 pinned-PyBERT profile blocker."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs/baselines/p3b-02-pybert-profile-source-audit.v1.yaml"
PREDECESSOR = ROOT / "docs/baselines/p3b-02-named-fir-prerequisite.v2.yaml"
FIR = ROOT / "crates/sipi-link/src/rx_named_fir_v1.rs"
SCHEMA = "sipi.p3b-02.pybert-profile-source-audit.v1"
COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
PREDECESSOR_SHA256 = "7de82872cc4a07dfee91c96b64173fd806048000c2815ae784d414319077d5bf"
FIR_SHA256 = "30d87038569cc5277c994f4309e1702ba274cb1c56df699bcf14cf468b949e9e"
SOURCE_OBJECTS = {
    "src/pybert/pybert.py": "1af665c4595fff1ff5fb30341fe063bd10e5cd89",
    "src/pybert/models/bert.py": "f04340c1028078175b26d7882efeeaf96f001abf",
    "src/pybert/models/tx_tap.py": "5fe0384712a0128ced0f6860e482aa71beb567e9",
    "src/pybert_web/models.py": "ec69a14ed97dbb500e57e378c4d8f39d359aaf20",
    "src/pybert_web/engine_adapter.py": "8cdb9fb612635b58cf2e071a9e90d07d272faa61",
    "native/pybert-core/src/equalization.rs": "ae91583c5675a82fe229918c41602b8531fb775d",
    "native/pybert-core/src/input.rs": "ae6d1883b65640d1719022df2c9e8b0763636dc0",
    "native/pybert-core/src/simulation.rs": "1f19bff64315e0042bab89d67e9131c289f5e583",
}


class ProfileAuditError(ValueError):
    pass


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProfileAuditError("record_invalid") from error
    if not isinstance(value, dict):
        raise ProfileAuditError("record_invalid")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema") != SCHEMA or document.get("status") != "blocked_no_mechanically_unique_fixed_profile":
        raise ProfileAuditError("identity_invalid")
    if document.get("predecessor") != {"path": "docs/baselines/p3b-02-named-fir-prerequisite.v2.yaml", "sha256": PREDECESSOR_SHA256, "unchanged": True}:
        raise ProfileAuditError("predecessor_invalid")
    source = document.get("external_source")
    if not isinstance(source, dict) or source.get("commit") != COMMIT or source.get("tree") != TREE:
        raise ProfileAuditError("source_identity_invalid")
    if source.get("custody") != "external_only_hash_bound" or source.get("license") != {"spdx": "BSD-3-Clause", "path": "LICENSE", "git_blob": "64d198ba43675ede5fbdef1ec918a63954951640"}:
        raise ProfileAuditError("source_license_invalid")
    objects = source.get("objects")
    if objects != SOURCE_OBJECTS:
        raise ProfileAuditError("source_objects_invalid")
    candidates = document.get("candidates")
    if not isinstance(candidates, dict) or set(candidates) != {"legacy_desktop", "web_adapter", "native_default"}:
        raise ProfileAuditError("candidates_invalid")
    if candidates["legacy_desktop"]["ctle"]["peak_magnitude_db"] != 1.7 or candidates["web_adapter"]["ctle"]["peak_magnitude_db"] != 4.0:
        raise ProfileAuditError("ctle_conflict_missing")
    if candidates["legacy_desktop"]["ffe"]["actual_tuner_count"] != 20 or candidates["legacy_desktop"]["ffe"]["declared_tap_count"] != 15:
        raise ProfileAuditError("ffe_count_conflict_missing")
    if candidates["native_default"] != {"native_ctle_enabled": True, "ctle": None, "result": "MissingCtleConfiguration", "ffe": {"enabled": False, "weights": [], "cursor_position": 0}}:
        raise ProfileAuditError("native_default_invalid")
    conflicts = document.get("conflicts")
    if not isinstance(conflicts, list) or len(conflicts) != 5 or len(set(conflicts)) != 5:
        raise ProfileAuditError("conflicts_invalid")
    decision = document.get("decision")
    if decision != {"unique_fixed_profile": False, "selected_profile": None, "selection_by_oracle_closeness": False, "product_change": "none", "wire_v1_changed": False, "reason": "pinned source contains multiple conflicting defaults and no mechanical precedence rule"}:
        raise ProfileAuditError("decision_invalid")
    product = document.get("current_product")
    if product != {"named_fir_path": "crates/sipi-link/src/rx_named_fir_v1.rs", "named_fir_sha256": FIR_SHA256, "status": "prerequisite_only_not_ctle_or_ffe_profile"}:
        raise ProfileAuditError("product_boundary_invalid")
    non_claims = document.get("non_claims")
    if not isinstance(non_claims, list) or len(non_claims) != 4:
        raise ProfileAuditError("non_claims_invalid")
    return {"valid": True, "status": document["status"], "unique_fixed_profile": False}


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="strict", timeout=60)
    if completed.returncode != 0:
        raise ProfileAuditError("external_git_object_unavailable")
    return completed.stdout.strip()


def verify(root: Path = ROOT, pybert_root: Path | None = None) -> dict[str, Any]:
    result = validate_document(load(root / RECORD.relative_to(ROOT)))
    if sha256(root / PREDECESSOR.relative_to(ROOT)) != PREDECESSOR_SHA256:
        raise ProfileAuditError("predecessor_hash_drift")
    if sha256(root / FIR.relative_to(ROOT)) != FIR_SHA256:
        raise ProfileAuditError("named_fir_hash_drift")
    if pybert_root is not None:
        document = load(root / RECORD.relative_to(ROOT))
        if git(pybert_root, "rev-parse", f"{COMMIT}^{{tree}}") != TREE:
            raise ProfileAuditError("external_tree_drift")
        for path, blob in document["external_source"]["objects"].items():
            if git(pybert_root, "rev-parse", f"{COMMIT}:{path}") != blob:
                raise ProfileAuditError("external_source_object_drift")
        if git(pybert_root, "rev-parse", f"{COMMIT}:LICENSE") != document["external_source"]["license"]["git_blob"]:
            raise ProfileAuditError("external_license_object_drift")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--pybert-root", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps({"schema": SCHEMA, **verify(args.root, args.pybert_root)}, sort_keys=True))
        return 0
    except (OSError, ProfileAuditError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
