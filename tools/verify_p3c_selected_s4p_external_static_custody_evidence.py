"""Verify current hash-only evidence for selected P3C S4P static custody."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-selected-s4p-external-static-custody-evidence.v1.yaml"
CONTRACT = ROOT / "docs" / "baselines" / "p3c-selected-s4p-external-static-custody-observation-contract.v1.yaml"
AMENDMENT = ROOT / "docs" / "baselines" / "p3c-selected-four-port-lexical-amendment.v1.yaml"
SCHEMA = "sipi.p3c-selected-s4p-external-static-custody-evidence.v1"


class VerificationError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_archive_inventory(paths: set[str]) -> dict[str, str]:
    completed = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)], cwd=ROOT, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise VerificationError("static_custody_evidence_product_source_drift")
    with tempfile.TemporaryDirectory(prefix="sipi-p3c-current-inventory-") as temporary:
        destination = Path(temporary)
        try:
            with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
                archive.extractall(destination, filter="data")
        except tarfile.TarError as error:
            raise VerificationError("static_custody_evidence_product_source_drift") from error
        inventory = {relative: sha256(destination / relative) for relative in paths}
    return inventory


def verify(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("static_custody_evidence_schema_invalid")
    if document.get("status") != "external_only_selected_s4p_static_custody_observed_v2_fit_and_stepping_blocked":
        raise VerificationError("static_custody_evidence_status_invalid")
    if document.get("contract_sha256") != sha256(CONTRACT) or document.get("lexical_amendment_sha256") != sha256(AMENDMENT):
        raise VerificationError("static_custody_evidence_contract_drift")
    observation = document.get("external_observation")
    expected_observation = {
        "schema": "sipi.p3c.sealed-selected-s4p-custody-observation.v1", "status": "observed",
        "custody": "external_only", "report_path_retained": False, "report_byte_length": 1839,
        "report_content_sha256": "f14110a4d0137620e5ae6ecf17aa8057e8f191fc05704f5eef99f10ce98e0c57",
        "clean_archive_commit": "6e6668443aab6dc0a0af51f494eb3ff95068d28e",
        "selected_source": {"byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"},
        "source_identity_checks": "before_stage_after_equal", "fresh_custody_runs": 2,
        "manifest_sha256s": ["e29a16282de0c3650bb327c4852af5694280f96ae4e0ff7bc92fb3737a43576f", "f722622178a6ee3112b9e2bb5a7e5e2fabbf47831f133b083f477ff272863fd6"],
        "record_count": 2002, "cleanup_status": "complete",
        "runner": {
            "source_sha256": "9d8a32ff671a7b68a4c2b069e72205e1799aa1633c8f438af5e7ec9e3ccb3a70",
            "report_sha256": "4b3cd530c5dba101b47fd00365ba12601b938612bed472961d2e882e1e297aa4",
        },
    }
    if not isinstance(observation, dict) or any(observation.get(key) != value for key, value in expected_observation.items()):
        raise VerificationError("static_custody_evidence_observation_invalid")
    inventory = document.get("product_source_inventory")
    allowed_inventory = {
        "Cargo.lock", "crates/sipi-artifacts/src/lib.rs", "crates/sipi-channel/src/p3c_fixed_four_port_bench_v1.rs",
        "crates/sipi-p3c/Cargo.toml", "crates/sipi-p3c/src/lib.rs",
        "crates/sipi-p3c/tests/p3c_sealed_s4p_external_runner.rs", "crates/sipi-touchstone/src/selected_four_port_v1.rs",
    }
    if not isinstance(inventory, dict) or set(inventory) != allowed_inventory:
        raise VerificationError("static_custody_evidence_product_source_drift")
    current_inventory = current_archive_inventory(allowed_inventory)
    if any(
        not isinstance(expected, str) or len(expected) != 64 or current_inventory[relative] != expected
        for relative, expected in inventory.items()
    ):
        raise VerificationError("static_custody_evidence_product_source_drift")
    expected_admission = {
        "external_static_custody_observed": True, "selected_external_s4p_static_admitted": True,
        "real_constrained_fit_invoked": False, "analytic_stepping_implemented": False,
        "candidate_waveform_generated": False, "external_reference_binding_evaluated": False,
        "candidate_metric_acceptance_evaluated": False, "accepted_receiver": False,
        "product_runtime_invoked": False, "p4b_ami_runtime_invoked": False,
        "release_ledger_promoted": False,
    }
    if document.get("admission") != expected_admission:
        raise VerificationError("static_custody_evidence_promotion_invalid")
    forbidden_blockers = {"two_fresh_external_sealed_s4p_v2_custody_observations_missing", "two_fresh_external_sealed_s4p_custody_observations_missing"}
    if forbidden_blockers & set(document.get("blockers", [])):
        raise VerificationError("static_custody_evidence_stale_blocker")
    return {"valid": True, "external_static_custody_observed": True, "record_count": observation["record_count"]}


def main() -> int:
    try:
        print(verify(yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"selected_s4p_static_custody_evidence_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
