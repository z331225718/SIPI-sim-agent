"""Verify the P4B-02 typed host-forwarded AMI subset adapter selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import verify_p4b_02_parameter_selection as selection_gate

ROOT = TOOLS.parent
EVIDENCE = ROOT / "docs/baselines/p4b-02-production-parameter-adapter-selection.v1.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p4b-02-production-parameter-adapter-selection.md"
SCHEMA = "sipi.p4b-02.production-parameter-adapter-selection.v1"
EXPECTED_FILES = {
    "selection_charter": (
        "docs/baselines/p4b-02-parameter-selection-charter.v1.yaml",
        "ae5abb548c38d69935ce8f724adc7072c38d1a2d6284636cee1a4046592ccaf8",
    ),
    "worker": (
        "crates/sipi-ami-worker/src/lib.rs",
        "074f3c6669a2db100739376c1b12b8b1a0bbea2c5aa9a8dcaa1b17d0c90a6e5c",
    ),
    "host": (
        "crates/sipi-ami-host/src/lib.rs",
        "b1905b62962148844f4576dc323dc13cd6a71a8f38cc3633d13b42cb51050b71",
    ),
    "text_core": (
        "crates/sipi-ami-text/src/lib.rs",
        "d7a85027984207a65ad96257b2e349767ca9550402f38f0f5632d832a503e114",
    ),
    "typed_adapter": (
        "crates/sipi-ami-text/src/ami_parameter_subset_v1.rs",
        "774770abce9b6aea3d80630753edcc1afad4c9e09782f369222f03cc0f303c1c",
    ),
    "observation": (
        "docs/baselines/p4b-02-ads-pcie-gen5-parameter-subset-observation.v1.json",
        "705be3f1bd41d17505f46a787ab1373e16afbaacde8e3fe6bff6c762b2900367",
    ),
}
AUDIT_REF = "docs/baselines/audits/2026-08-21-p4b-02-production-parameter-adapter-selection.md"
AUDIT_SHA256 = "89cba0a9480c92de19d49040d2d9109371b0a0081241d416486707ed4026483f"


class AdapterSelectionError(RuntimeError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise AdapterSelectionError(reason)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise AdapterSelectionError(f"load_failed:{path}") from error
    _require(isinstance(value, dict), f"document_not_mapping:{path}")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise AdapterSelectionError(f"read_failed:{path}") from error


def validate(root: Path = ROOT) -> dict[str, Any]:
    document = _load(EVIDENCE)
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(
        document.get("status") == "external_asset_oracle",
        "status_invalid",
    )
    charter = document.get("selection_charter")
    _require(
        charter
        == {
            "path": EXPECTED_FILES["selection_charter"][0],
            "sha256": EXPECTED_FILES["selection_charter"][1],
        },
        "selection_charter_binding_invalid",
    )
    for _, (relative, digest) in EXPECTED_FILES.items():
        path = root / relative
        _require(path.is_file(), f"bound_file_missing:{relative}")
        _require(_sha256(path) == digest, f"bound_file_hash_drift:{relative}")

    adapter = document.get("production_adapter")
    _require(isinstance(adapter, dict), "production_adapter_missing")
    _require(
        adapter.get("representation") == "AmiForwardedParameterSubsetV1",
        "adapter_representation_invalid",
    )
    _require(
        adapter.get("selection") == "bounded_typed_host_forwarded_subset",
        "adapter_selection_invalid",
    )
    _require(adapter.get("selected_semantic_helper_modules") == [], "semantic_helper_selection_not_empty")
    _require(
        adapter.get("worker")
        == {
            "path": EXPECTED_FILES["worker"][0],
            "sha256": EXPECTED_FILES["worker"][1],
            "consumer": "prepare_forwarded_parameter_subset_v1",
            "parse_symbol": "parse_and_bind_v1",
        },
        "worker_binding_invalid",
    )
    _require(
        adapter.get("host")
        == {
            "path": EXPECTED_FILES["host"][0],
            "sha256": EXPECTED_FILES["host"][1],
            "consumer": "AmiHostV1::initialize_forwarded_subset",
            "verify_symbol": "AmiForwardedParameterSubsetV1::verify_binding_v1",
            "abi_sink": "AMI_Init",
        },
        "host_binding_invalid",
    )
    _require(
        adapter.get("text_core")
        == {"path": EXPECTED_FILES["text_core"][0], "sha256": EXPECTED_FILES["text_core"][1]},
        "text_core_binding_invalid",
    )
    _require(
        adapter.get("typed_adapter")
        == {
            "path": EXPECTED_FILES["typed_adapter"][0],
            "sha256": EXPECTED_FILES["typed_adapter"][1],
            "policy": "sipi.p4b-02.ami-parameter-subset.v1.host-forwarded-only",
            "selected_profiles": ["tx", "rx"],
            "explicit_values": True,
            "defaults_or_auto_tune": False,
        },
        "typed_adapter_binding_invalid",
    )
    _require(
        adapter.get("observation")
        == {
            "path": EXPECTED_FILES["observation"][0],
            "sha256": EXPECTED_FILES["observation"][1],
            "fresh_reads_per_profile": 2,
        },
        "observation_binding_invalid",
    )

    worker = (root / EXPECTED_FILES["worker"][0]).read_text(encoding="utf-8")
    host = (root / EXPECTED_FILES["host"][0]).read_text(encoding="utf-8")
    for token in (
        "pub fn prepare_forwarded_parameter_subset_v1",
        "parse_and_bind_v1(parameters, parse_limits)",
        "pub fn run_one_job",
        "parse_and_bind_v1(&parameters, limits)",
        "parameters: FileIdentityV1",
    ):
        _require(token in worker, f"worker_consumer_missing:{token}")
    for token in (
        "pub fn initialize",
        "pub fn initialize_forwarded_subset",
        ".verify_binding_v1(binding)",
        "verify_binding_v1(binding.raw().bytes(), binding, limits)",
        "CString::new(binding.raw().bytes())",
        "(self.init)",
    ):
        _require(token in host, f"host_consumer_missing:{token}")

    inventory = document.get("inventory")
    _require(
        inventory
        == {
            "total_feature_quarantined_modules": 193,
            "keep_for_product": 0,
            "quarantine_pending_requirement": 34,
            "delete_candidate": 159,
            "default_parameter_consumers": 0,
        },
        "inventory_invalid",
    )
    current = selection_gate.validate(root)
    _require(current.get("selection_counts") == {
        "keep_for_product": 0,
        "quarantine_pending_requirement": 34,
        "delete_candidate": 159,
    }, "selection_gate_counts_drift")
    _require(current.get("default_parameter_consumers") == 0, "default_parameter_consumers_drift")

    _require(
        document.get("deletion_plan")
        == {
            "status": "separate_batch_not_executed",
            "candidate_count": 159,
            "prerequisite": "owner_scoped_same_batch_source_export_test_and_gate_removal",
            "bulk_deletion_performed": False,
        },
        "deletion_plan_invalid",
    )
    _require(
        document.get("blockers")
        == {
            "quarantine_requires": [
                "authorized_ami_profile",
                "explicit_parameter_requirement",
                "live_typed_consumer",
                "independent_oracle",
            ],
            "external_acceptance": [
                "vendor_rights",
                "dynamic_dependency_closure",
                "isolated_vendor_runtime",
                "external_waveform_parity",
            ],
        },
        "blockers_invalid",
    )
    _require(
        document.get("non_claims")
        == [
            "typed_subset_identity_only",
            "no_quarantined_helper_promoted",
            "no_delete_candidate_removed",
            "not_vendor_model_acceptance",
            "not_dll_internal_parameter_consumption",
            "not_external_runtime_or_waveform_parity",
            "not_release_evidence",
        ],
        "non_claims_invalid",
    )
    _require(
        document.get("audit") == {"path": AUDIT_REF, "sha256": AUDIT_SHA256}
        and _sha256(AUDIT) == AUDIT_SHA256,
        "audit_binding_invalid",
    )
    return {
        "schema": SCHEMA,
        "valid": True,
        "adapter": "bounded_typed_host_forwarded_subset",
        "selected_semantic_helper_count": 0,
        "quarantine_count": 34,
        "delete_candidate_count": 159,
        "bulk_deletion_performed": False,
    }


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        print(json.dumps(validate(), sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, yaml.YAMLError, selection_gate.SelectionError, AdapterSelectionError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
