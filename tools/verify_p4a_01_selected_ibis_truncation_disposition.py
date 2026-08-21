"""Verify the exact P4A-01 tracked-prefix disposition against external custody."""

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
MANIFEST = ROOT / "docs/baselines/p4a-01-selected-ibis-truncation-disposition.v1.yaml"
ASSET = ROOT / "fixtures/ibis/as4c512m16md4v-053bin.ibs"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p4a-01-selected-ibis-truncation-disposition.md"
OFFICIAL_SOURCE = Path(
    r"C:\Users\z3312\code\.sipi-p4a-official-asset-20260821\as4c512m16md4v-053bin.ibs"
)
SCHEMA = "sipi.p4a-01.selected-ibis-truncation-disposition.v1"


class DispositionError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    canonical = data.replace(b"\r\n", b"\n")
    header = f"blob {len(canonical)}\0".encode("ascii")
    return hashlib.sha1(header + canonical).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DispositionError("manifest_not_mapping")
    return value


def observe(data: bytes) -> dict[str, Any]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as error:
        raise DispositionError("asset_not_ascii") from error
    models: set[str] = set()
    selectors: dict[str, list[str]] = {}
    current_selector: str | None = None
    for raw in text.splitlines():
        line = raw.split("|", 1)[0].strip()
        if not line:
            continue
        keyword = re.match(r"^\[([^\]]+)\]\s*(.*)$", line)
        if keyword:
            name, payload = keyword.group(1).strip(), keyword.group(2).strip()
            current_selector = None
            if name == "Model":
                models.add(payload)
            elif name == "Model Selector":
                current_selector = payload
                selectors[current_selector] = []
            continue
        if current_selector:
            selectors[current_selector].append(line.split()[0])
    unknown = [
        (selector, model)
        for selector, branches in selectors.items()
        for model in branches
        if model not in models
    ]
    return {
        "models": models,
        "model_count": len(models),
        "selector_count": len(selectors),
        "unknown": unknown,
        "end_count": len(re.findall(r"(?mi)^\s*\[End\]\s*(?:\|.*)?$", text)),
    }


def validate(root: Path = ROOT, official_source: Path = OFFICIAL_SOURCE) -> dict[str, Any]:
    manifest_path = root / MANIFEST.relative_to(ROOT)
    asset_path = root / ASSET.relative_to(ROOT)
    manifest = load_yaml(manifest_path)
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "exact_unusable_profile_disposition":
        raise DispositionError("schema_or_status_drift")
    if manifest.get("promotion_eligible") is not False:
        raise DispositionError("promotion_boundary_drift")

    audit = manifest.get("audit", {})
    if audit.get("path") != AUDIT.relative_to(ROOT).as_posix():
        raise DispositionError("audit_path_drift")
    audit_path = root / Path(audit["path"])
    if sha256(audit_path.read_bytes()) != audit.get("sha256"):
        raise DispositionError("audit_hash_drift")
    audit_text = audit_path.read_text(encoding="utf-8")
    for token in ("exact strict byte prefix", "unusable for a semantic or electrical profile", "must not be\nsynthesized"):
        if token not in audit_text:
            raise DispositionError("audit_content_drift")

    tracked = asset_path.read_bytes()
    official = official_source.read_bytes()
    tracked_spec = manifest.get("selected_tracked_object", {})
    official_spec = manifest.get("official_external_object", {})
    if len(tracked) != tracked_spec.get("byte_length") or sha256(tracked) != tracked_spec.get("sha256"):
        raise DispositionError("tracked_identity_drift")
    if git_blob_sha1(tracked) != tracked_spec.get("git_blob_sha1"):
        raise DispositionError("tracked_git_blob_drift")
    if tracked[-8:].hex() != tracked_spec.get("final_8_bytes_hex"):
        raise DispositionError("tracked_tail_drift")
    if len(official) != official_spec.get("byte_length") or sha256(official) != official_spec.get("sha256"):
        raise DispositionError("official_identity_drift")
    if not official.startswith(tracked) or len(official) == len(tracked):
        raise DispositionError("strict_prefix_proof_failed")
    proof = manifest.get("strict_prefix_proof", {})
    if len(official) - len(tracked) != proof.get("missing_byte_count"):
        raise DispositionError("missing_byte_count_drift")
    if official[len(tracked) : len(tracked) + 64].hex() != proof.get("first_64_suffix_bytes_hex"):
        raise DispositionError("suffix_boundary_drift")

    tracked_obs, official_obs = observe(tracked), observe(official)
    for observed, spec, label in (
        (tracked_obs, tracked_spec, "tracked"),
        (official_obs, official_spec, "official"),
    ):
        for field in ("end_count", "model_count", "selector_count"):
            spec_name = {"model_count": "model_block_count", "selector_count": "model_selector_count"}.get(field, "end_record_count")
            if observed[field] != spec.get(spec_name):
                raise DispositionError(f"{label}_{field}_drift")
    missing = manifest.get("selector_observation", {}).get("first_tracked_missing_branch", {})
    if not tracked_obs["unknown"] or tracked_obs["unknown"][0] != (missing.get("selector"), missing.get("model")):
        raise DispositionError("tracked_selector_gap_drift")
    if official_obs["unknown"] or "CKE_PIN" not in official_obs["models"]:
        raise DispositionError("official_linkage_closure_drift")

    disposition = manifest.get("disposition", {})
    if disposition.get("selected_tracked_asset_profile") != "unusable_for_semantic_or_electrical_profile":
        raise DispositionError("disposition_drift")
    if disposition.get("allowed_use") != "exact_structural_prefix_observation_only":
        raise DispositionError("allowed_use_drift")
    if disposition.get("synthesize_missing_model") != "forbidden":
        raise DispositionError("synthesis_boundary_drift")
    rights = manifest.get("rights_boundary", {})
    if rights.get("official_rights_status") != "unverified" or any(
        rights.get(field) is not False
        for field in ("redistribution_authorized", "git_asset", "product_fixture", "runtime_input", "acceptance_profile", "release_input")
    ):
        raise DispositionError("rights_boundary_drift")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": manifest["status"],
        "tracked_byte_length": len(tracked),
        "official_byte_length": len(official),
        "missing_byte_count": len(official) - len(tracked),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--official-source", type=Path, default=OFFICIAL_SOURCE)
    args = parser.parse_args()
    try:
        report = validate(args.root, args.official_source)
    except (OSError, yaml.YAMLError, DispositionError) as error:
        report = {"schema": SCHEMA, "valid": False, "reason": str(error)}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
