"""Verify P3B-02 explicit stage semantics and hash-bound PyBERT observation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from observe_p3b_02_pybert_semantics import COMMIT, LICENSE_BLOB, OBJECT_MARKERS, SCHEMA, TREE
except ImportError:  # pragma: no cover
    from tools.observe_p3b_02_pybert_semantics import COMMIT, LICENSE_BLOB, OBJECT_MARKERS, SCHEMA, TREE


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs/baselines/p3b-02-pybert-source-semantic-observation.v1.yaml"
PRODUCT = ROOT / "crates/sipi-link/src/rx_ctle_ffe_v1.rs"
WIRE_SCHEMA = ROOT / "crates/sipi-contracts/schemas/sipi.link-plan.v1.schema.json"
CONTRACT = ROOT / "crates/sipi-contracts/src/lib.rs"

EXPECTED_BLOBS = {
    "src/pybert/models/bert.py": "f04340c1028078175b26d7882efeeaf96f001abf",
    "src/pybert/pybert.py": "1af665c4595fff1ff5fb30341fe063bd10e5cd89",
    "src/pybert_web/models.py": "ec69a14ed97dbb500e57e378c4d8f39d359aaf20",
    "src/pybert_web/engine_adapter.py": "8cdb9fb612635b58cf2e071a9e90d07d272faa61",
    "native/pybert-core/src/equalization.rs": "ae91583c5675a82fe229918c41602b8531fb775d",
    "native/pybert-core/src/input.rs": "ae6d1883b65640d1719022df2c9e8b0763636dc0",
    "native/pybert-core/src/simulation.rs": "1f19bff64315e0042bab89d67e9131c289f5e583",
}
API_MARKERS = (
    "pub enum CtleNormalizationV1",
    "pub enum CtleStateV1",
    "pub struct CtleTransferV1",
    "pub enum FfeTapOrderV1",
    "pub enum FfeCursorConventionV1",
    "pub enum FfeTapUnitsV1",
    "pub enum FfeTapSignV1",
    "pub enum FfeSamplingV1",
    "pub enum FfeStateV1",
    "pub struct RxCtleFfeProfileV1",
    "pub fn apply_rx_ctle_ffe_v1",
    "apply_rx_named_fir_prerequisite_v1",
)


class SemanticsEvidenceError(ValueError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SemanticsEvidenceError("record_invalid") from error
    if not isinstance(value, dict):
        raise SemanticsEvidenceError("record_invalid")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise SemanticsEvidenceError("product_source_missing") from error


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
    )
    if result.returncode != 0:
        raise SemanticsEvidenceError("external_git_object_unavailable")
    return result.stdout.strip()


def _stage_kinds(schema: dict[str, Any], name: str) -> list[str]:
    try:
        return [
            choice["properties"]["kind"]["const"]
            for choice in schema["$defs"][name]["oneOf"]
        ]
    except (KeyError, IndexError, TypeError) as error:
        raise SemanticsEvidenceError(f"wire_{name}_shape_invalid") from error


def _enum_variants(source: str, name: str) -> list[str]:
    match = re.search(
        rf"pub\s+enum\s+{re.escape(name)}\s*\{{(?P<body>.*?)\}}",
        source,
        flags=re.DOTALL,
    )
    if match is None:
        raise SemanticsEvidenceError(f"rust_{name}_missing")
    return re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*,", match.group("body"), re.MULTILINE)


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema") != SCHEMA:
        raise SemanticsEvidenceError("schema_invalid")
    if document.get("status") != "observed_product_semantics_external_profile_required":
        raise SemanticsEvidenceError("status_invalid")
    product = document.get("product")
    if not isinstance(product, dict) or product != {
        "path": "crates/sipi-link/src/rx_ctle_ffe_v1.rs",
        "sha256": product.get("sha256") if isinstance(product, dict) else None,
        "policy": "sipi.p3b-02.rx-ctle-ffe-explicit-semantics-v1",
        "wire_v1": "bypass_only_unchanged",
        "runtime_surface": "in_memory_caller_supplied_only",
    }:
        raise SemanticsEvidenceError("product_boundary_invalid")
    semantics = document.get("semantics")
    if not isinstance(semantics, dict) or semantics.get("chain_order") != ["RX CTLE", "RX FFE"]:
        raise SemanticsEvidenceError("chain_order_invalid")
    if semantics.get("stage_selection") != "explicit_per_stage_bypass_or_caller_profile":
        raise SemanticsEvidenceError("stage_selection_invalid")
    expected_ctle = {
        "transfer_representation": "caller_supplied_causal_time_domain_impulse",
        "grid": "explicit_uniform_sample_interval_count_and_input_sample_zero_origin",
        "normalization": "explicit_none_unit_sum_or_peak_abs_target",
        "state": "explicit_zero_initial",
    }
    expected_ffe = {
        "tap_order": "explicit_ascending_or_descending_time",
        "cursor": "explicit_index_and_output_origin_convention",
        "units": "explicit_normalized_voltage_ratio",
        "sign": "explicit_direct_or_negated",
        "domain": "explicit_sample_spaced_or_ui_spaced",
        "state": "explicit_zero_initial",
    }
    if semantics.get("ctle") != expected_ctle:
        raise SemanticsEvidenceError("ctle_semantics_invalid")
    if semantics.get("ffe") != expected_ffe:
        raise SemanticsEvidenceError("ffe_semantics_invalid")
    default_conflict = document.get("source_observations", {}).get("default_conflict", {})
    if default_conflict != {
        "legacy_peak_magnitude_db": 1.7,
        "web_peak_magnitude_db": 4.0,
        "web_rx_cursor_position": 5.0,
        "profile_selection": None,
        "selection_by_oracle_closeness": False,
    }:
        raise SemanticsEvidenceError("source_conflict_invalid")
    source = document.get("external_source")
    if not isinstance(source, dict) or source.get("commit") != COMMIT or source.get("tree") != TREE:
        raise SemanticsEvidenceError("source_identity_invalid")
    if source.get("custody") != "external_only_hash_bound":
        raise SemanticsEvidenceError("source_custody_invalid")
    if source.get("license") != {"spdx": "BSD-3-Clause", "path": "LICENSE", "git_blob": LICENSE_BLOB}:
        raise SemanticsEvidenceError("source_license_invalid")
    objects = source.get("objects")
    if not isinstance(objects, dict) or set(objects) != set(OBJECT_MARKERS):
        raise SemanticsEvidenceError("source_objects_invalid")
    for path, markers in OBJECT_MARKERS.items():
        entry = objects[path]
        if not isinstance(entry, dict) or entry.get("git_blob_sha1") != EXPECTED_BLOBS[path] or entry.get("markers") != list(markers) or entry.get("marker_presence_verified") is not True:
            raise SemanticsEvidenceError(f"source_object_invalid:{path}")
    profile = document.get("profile_status")
    if not isinstance(profile, dict) or profile.get("selected_profile") is not None or profile.get("required") != "external_asset_oracle" or "conflicting defaults" not in profile.get("reason", ""):
        raise SemanticsEvidenceError("profile_status_invalid")
    non_claims = document.get("non_claims")
    if not isinstance(non_claims, list) or len(non_claims) != 4 or any(not isinstance(item, str) for item in non_claims):
        raise SemanticsEvidenceError("non_claims_invalid")
    return {"valid": True, "status": document["status"], "profile_required": "external_asset_oracle"}


def verify_document(
    document: dict[str, Any], root: Path = ROOT, pybert_root: Path | None = None
) -> dict[str, Any]:
    result = validate_document(document)
    product = root / PRODUCT.relative_to(ROOT)
    if _sha256(product) != document["product"]["sha256"]:
        raise SemanticsEvidenceError("product_source_hash_drift")
    product_source = product.read_text(encoding="utf-8")
    for marker in API_MARKERS:
        if marker not in product_source:
            raise SemanticsEvidenceError(f"typed_api_marker_missing:{marker}")
    if "impl Default for" in product_source:
        raise SemanticsEvidenceError("typed_api_default_forbidden")
    try:
        schema = json.loads((root / WIRE_SCHEMA.relative_to(ROOT)).read_text(encoding="utf-8"))
        contract = (root / CONTRACT.relative_to(ROOT)).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SemanticsEvidenceError("wire_surface_missing") from error
    if _stage_kinds(schema, "WireCtleStageV1") != ["bypass"]:
        raise SemanticsEvidenceError("wire_ctle_non_bypass_admitted")
    if _stage_kinds(schema, "WireFfeStageV1") != ["bypass"]:
        raise SemanticsEvidenceError("wire_ffe_non_bypass_admitted")
    if _enum_variants(contract, "WireCtleStageV1") != ["Bypass"]:
        raise SemanticsEvidenceError("rust_wire_ctle_non_bypass_admitted")
    if _enum_variants(contract, "WireFfeStageV1") != ["Bypass"]:
        raise SemanticsEvidenceError("rust_wire_ffe_non_bypass_admitted")
    if pybert_root is not None:
        try:
            pybert_root.resolve().relative_to(root.resolve())
        except ValueError:
            pass
        else:
            raise SemanticsEvidenceError("external_repo_must_not_be_inside_repository")
        if _git(pybert_root, "rev-parse", f"{COMMIT}^{{tree}}") != TREE:
            raise SemanticsEvidenceError("external_tree_drift")
        if _git(pybert_root, "rev-parse", f"{COMMIT}:LICENSE") != LICENSE_BLOB:
            raise SemanticsEvidenceError("external_license_object_drift")
        for path, expected in EXPECTED_BLOBS.items():
            if _git(pybert_root, "rev-parse", f"{COMMIT}:{path}") != expected:
                raise SemanticsEvidenceError(f"external_source_object_drift:{path}")
            source = subprocess.run(
                ["git", "-C", str(pybert_root), "show", f"{COMMIT}:{path}"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=60,
            ).stdout
            if any(marker not in source for marker in OBJECT_MARKERS[path]):
                raise SemanticsEvidenceError(f"external_source_marker_drift:{path}")
    return result


def verify(root: Path = ROOT, pybert_root: Path | None = None) -> dict[str, Any]:
    return verify_document(_load(root / RECORD.relative_to(ROOT)), root, pybert_root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--pybert-root", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps({"schema": SCHEMA, **verify(args.root, args.pybert_root)}, sort_keys=True))
        return 0
    except (OSError, SemanticsEvidenceError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
