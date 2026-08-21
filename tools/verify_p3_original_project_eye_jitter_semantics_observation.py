"""Verify pinned PyBERT/Agent-COM source facts without admitting semantics."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/baselines/p3-original-project-eye-jitter-semantics-observation.v1.yaml"
SCHEMA = "sipi.p3-original-project-eye-jitter-semantics-observation.v1"
SOURCE_FACTS = {
    "pybert": {
        "commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe",
        "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24",
        "files": {
            "src/pybert/utility/jitter.py": ("467cd706906352883d9784ff29b17610034aede5", 22543),
            "src/pybert/utility/statistical_eye.py": ("195f87f48cecc55bf7bcda371c4c51b17111ea21", 38893),
            "native/pybert-core/src/jitter.rs": ("92e0fd6e6b2d40590b967f5f5d057a3de2969672", 24270),
        },
        "license": ("LICENSE", "64d198ba43675ede5fbdef1ec918a63954951640", 1466),
    },
    "agent-com": {
        "commit": "034b21b2f293b2ef97cb8be269b1bf2be38e0086",
        "tree": "dc6e5529612d7272f23547a796b53e1456cc49cb",
        "files": {
            "src/agent_com/metrics/eye.py": ("e0f9eb617e98ece73d2b710e49b2f2c826f3281f", 4054),
            "src/agent_com/equalization/apply.py": ("07534980f64cbe86b6ceff3c2f5f9107d4fd7b24", 4246),
        },
        "license": None,
    },
}
SOURCE_FUNCTIONS = {
    ("pybert", "src/pybert/utility/jitter.py"): ["find_crossing_times", "find_crossings", "calc_jitter"],
    ("pybert", "src/pybert/utility/statistical_eye.py"): ["calculate_statistical_eye", "_periodic_jitter_kernel", "_phase_samples"],
    ("pybert", "native/pybert-core/src/jitter.rs"): ["find_crossing_times", "calculate_dual_dirac_jitter"],
    ("agent-com", "src/agent_com/metrics/eye.py"): ["center_of_ui", "eye_cdf", "ber_contour", "find_eye_width"],
    ("agent-com", "src/agent_com/equalization/apply.py"): ["apply_r480_equalization"],
}


class EvidenceError(RuntimeError):
    pass


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load() -> dict[str, Any]:
    try:
        value = yaml.safe_load(DOCUMENT.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise EvidenceError("document_invalid") from error
    if not isinstance(value, dict):
        raise EvidenceError("document_invalid")
    return value


def _git(repository: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(repository), *args], check=True, capture_output=True).stdout.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise EvidenceError("source_git_unavailable") from error


def _git_exists(repository: Path, object_name: str) -> bool:
    try:
        return subprocess.run(["git", "-C", str(repository), "cat-file", "-e", object_name], capture_output=True, check=False).returncode == 0
    except OSError as error:
        raise EvidenceError("source_git_unavailable") from error


def _verify_external_source(root_ref: str, repository: Path) -> None:
    facts = SOURCE_FACTS[root_ref]
    commit = facts["commit"]
    if _git(repository, "cat-file", "-t", commit) != "commit" or _git(repository, "rev-parse", f"{commit}^{{tree}}") != facts["tree"]:
        raise EvidenceError(f"{root_ref}_identity_invalid")
    for relative, (blob, size) in facts["files"].items():
        if _git(repository, "cat-file", "-t", f"{commit}:{relative}") != "blob" or _git(repository, "rev-parse", f"{commit}:{relative}") != blob or int(_git(repository, "cat-file", "-s", f"{commit}:{relative}")) != size:
            raise EvidenceError(f"{root_ref}_source_blob_invalid")
    license_fact = facts["license"]
    if license_fact is not None:
        relative, blob, size = license_fact
        if _git(repository, "cat-file", "-t", f"{commit}:{relative}") != "blob" or _git(repository, "rev-parse", f"{commit}:{relative}") != blob or int(_git(repository, "cat-file", "-s", f"{commit}:{relative}")) != size:
            raise EvidenceError(f"{root_ref}_license_material_invalid")
    elif _git_exists(repository, f"{commit}:LICENSE"):
        raise EvidenceError("agent_com_license_binding_invalid")


def validate(document: dict[str, Any]) -> None:
    if set(document) != {"schema", "kind", "captured_at_utc", "sources", "observed_semantics", "decision_surface", "strict_waveform_reference", "admission", "non_claims", "audit_ref"}:
        raise EvidenceError("document_shape_invalid")
    if document["schema"] != SCHEMA or document["kind"] != "external_original_source_semantics_observation_not_product_admission":
        raise EvidenceError("document_identity_invalid")
    sources = document["sources"]
    if not isinstance(sources, list) or {item.get("root_ref") for item in sources if isinstance(item, dict)} != set(SOURCE_FACTS):
        raise EvidenceError("source_set_invalid")
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"root_ref", "commit", "tree", "files", "license_material"}:
            raise EvidenceError("source_schema_invalid")
        root_ref = source["root_ref"]
        facts = SOURCE_FACTS.get(root_ref)
        if facts is None or source["commit"] != facts["commit"] or source["tree"] != facts["tree"]:
            raise EvidenceError("source_identity_invalid")
        files = source["files"]
        if not isinstance(files, list) or {item.get("path") for item in files if isinstance(item, dict)} != set(facts["files"]):
            raise EvidenceError("source_file_set_invalid")
        for item in files:
            if not isinstance(item, dict) or set(item) != {"path", "git_blob_sha1", "bytes", "functions"} or facts["files"].get(item["path"]) != (item["git_blob_sha1"], item["bytes"]):
                raise EvidenceError("source_file_binding_invalid")
            if item["functions"] != SOURCE_FUNCTIONS.get((root_ref, item["path"])):
                raise EvidenceError("source_function_inventory_invalid")
        if facts["license"] is None:
            if source["license_material"] != {"path": None, "status": "absent_at_pinned_commit", "conclusion": "NOASSERTION"}:
                raise EvidenceError("license_material_binding_invalid")
        else:
            path, blob, size = facts["license"]
            if source["license_material"] != {"path": path, "git_blob_sha1": blob, "bytes": size, "conclusion": "NOASSERTION"}:
                raise EvidenceError("license_material_binding_invalid")
    if document["decision_surface"] != {"p3b_05_jitter_observable": "pending_required_profile_observables_and_tolerance", "p3c_02_eye_folding_bins": "pending_owner_decision", "equalizer_subset": "pending_link_profile_and_independent_semantics"}:
        raise EvidenceError("decision_surface_invalid")
    strict = document["strict_waveform_reference"]
    if strict != {"evidence_path": "docs/baselines/p3c-original-project-channel-semantics-observation.v1.yaml", "evidence_sha256": "6eda7ddfa1a37e7e02351881530ae61b0615293c0ce2cb91d8a66d83b712a836", "full_chain_nrmse": 0.02911956313297956, "fixed_limit": 0.01, "source_only_interior_nrmse": 0.0, "conclusion": "source_only_boundary_observed_full_chain_root_cause_unresolved"}:
        raise EvidenceError("strict_waveform_reference_invalid")
    try:
        if _sha256((ROOT / strict["evidence_path"]).read_bytes()) != strict["evidence_sha256"]:
            raise EvidenceError("strict_waveform_reference_hash_invalid")
    except OSError as error:
        raise EvidenceError("strict_waveform_reference_missing") from error
    if document["admission"] != {"product_semantics_implemented": False, "external_source_promoted": False, "release_promoted": False}:
        raise EvidenceError("admission_invalid")
    if document["non_claims"] != ["source_function_names_and_literals_do_not_select_product_semantics", "no_PyBERT_or_Agent_COM_code_was_copied", "no_alignment_gain_dc_polarity_tolerance_or_oracle_fit_was_used", "license_material_observation_is_not_a_legal_conclusion", "strict_waveform_mismatch_cause_remains_unresolved"]:
        raise EvidenceError("non_claims_invalid")
    audit_ref = document["audit_ref"]
    if not isinstance(audit_ref, str) or not audit_ref.startswith("docs/baselines/audits/") or not (ROOT / audit_ref).is_file():
        raise EvidenceError("audit_reference_invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pybert-root", type=Path)
    parser.add_argument("--agent-com-root", type=Path)
    args = parser.parse_args()
    try:
        document = _load()
        validate(document)
        roots = {"pybert": args.pybert_root, "agent-com": args.agent_com_root}
        if any(value is not None for value in roots.values()) and any(value is None for value in roots.values()):
            raise EvidenceError("all_external_roots_required")
        if all(value is not None for value in roots.values()):
            for root_ref, repository in roots.items():
                _verify_external_source(root_ref, repository)
        print(json.dumps({"schema": SCHEMA, "valid": True, "external_sources_verified": all(value is not None for value in roots.values())}, sort_keys=True))
        return 0
    except EvidenceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
