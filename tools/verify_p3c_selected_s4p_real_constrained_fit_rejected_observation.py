"""Verify the immutable external negative result for the selected P3C fit."""

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
DEFAULT = ROOT / "docs/baselines/p3c-selected-s4p-real-constrained-fit-rejected-observation.v1.yaml"
SCHEMA = "sipi.p3c-selected-s4p-real-constrained-fit-rejected-observation.v1"
INVENTORY = {"Cargo.lock", "crates/sipi-artifacts/src/lib.rs", "crates/sipi-channel/src/p3c_fixed_four_port_bench_v1.rs", "crates/sipi-channel/src/p3c_real_constrained_fixed_pole_fit_v1.rs", "crates/sipi-p3c/Cargo.toml", "crates/sipi-p3c/src/lib.rs", "crates/sipi-p3c/tests/p3c_sealed_s4p_external_fit_runner.rs", "crates/sipi-touchstone/src/selected_four_port_v1.rs"}

class VerificationError(ValueError): pass

def digest(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def archive_inventory() -> dict[str, str]:
    completed = subprocess.run(["git", "archive", "--format=tar", "HEAD", "--", *sorted(INVENTORY)], cwd=ROOT, capture_output=True, check=False)
    if completed.returncode: raise VerificationError("rejected_fit_product_source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        try:
            with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive: archive.extractall(temporary, filter="data")
        except tarfile.TarError as error: raise VerificationError("rejected_fit_product_source_drift") from error
        return {path: digest(Path(temporary) / path) for path in INVENTORY}

def verify(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or document.get("status") != "external_only_selected_s4p_real_constrained_fit_rejected_no_order_meets_admission": raise VerificationError("rejected_fit_schema_or_status_invalid")
    observation = document.get("external_observation")
    expected = {"schema": "sipi.p3c.sealed-selected-s4p-real-constrained-fit-observation.v1", "status": "rejected", "reason": "no_order_meets_admission", "custody": "external_only", "report_path_retained": False, "report_byte_length": 2026, "report_content_sha256": "81e0c4fb254a4e6660124f20b81feae226f6f670ab7732da3e6aaa1a797170da", "clean_archive_commit": "848df45bbe866d50d92878adc23beffd7652fc89", "selected_source": {"byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"}, "source_identity_checks": "before_stage_after_equal", "fresh_custody_runs": 2, "manifest_sha256s": ["7245dae9b9503dff80cb6e2da57008a05dddca2209f65f369cb3c87c7018432e", "fd2f2a044f3c9dff53a3146c6b09b64c0b31b61a0a05936f08182a662bf11d62"], "record_count": 2002, "cleanup_status": "complete", "runner": {"source_sha256": "4e07f1be742b7dbbe269525af2bf27cf5c16b39c2f786c45c7166689ba5b3a67", "report_sha256": "37f8c26f61daec54debe1c4e0bb84227038098e5c2eefe36b7d6d46e88284312"}}
    if observation != expected: raise VerificationError("rejected_fit_observation_invalid")
    if archive_inventory() != {key: expected_hash for key, expected_hash in {"Cargo.lock": "d1248e7537ad15263b84b41f172ed73090faf6da7e5fbf3c7afac60e1e3e4583", "crates/sipi-artifacts/src/lib.rs": "85b475ec865779dbe3e21b54759ca9075b8a4516714d7192ba4b214075861997", "crates/sipi-channel/src/p3c_fixed_four_port_bench_v1.rs": "248bf24c494d9c956a96e2781f35f546d5de9f70f6157457da7a54aeb60baa70", "crates/sipi-channel/src/p3c_real_constrained_fixed_pole_fit_v1.rs": "b47f4e7d446ce557173bae1e8148927b28e7d95bd1c93835c8c1976f3f5d6c1c", "crates/sipi-p3c/Cargo.toml": "ef5e9a8951ffccbbd83472dbda8b4fad0a5ca3714bb7975755c0f85d59c0d8d8", "crates/sipi-p3c/src/lib.rs": "aaf4b40fcc17d4ff2ae4ab512ecf7d68416dea6aaa8c4254521ae1ab57813b36", "crates/sipi-p3c/tests/p3c_sealed_s4p_external_fit_runner.rs": "4e07f1be742b7dbbe269525af2bf27cf5c16b39c2f786c45c7166689ba5b3a67", "crates/sipi-touchstone/src/selected_four_port_v1.rs": "53b11a0cf08b0505c190b244c47f13e22f7b2b3c1f6ea712b6aba533a8805f80"}.items()}: raise VerificationError("rejected_fit_product_source_drift")
    admission = document.get("admission", {})
    if admission.get("real_constrained_fit_invoked") is not True or admission.get("real_constrained_fit_admitted") is not False or any(admission.get(key) is not False for key in ("analytic_stepping_implemented", "candidate_waveform_generated", "external_reference_binding_evaluated", "candidate_metric_acceptance_evaluated", "accepted_receiver", "product_runtime_invoked", "p4b_ami_runtime_invoked", "release_ledger_promoted")): raise VerificationError("rejected_fit_promotion_invalid")
    return {"valid": True, "fit_admitted": False, "reason": "no_order_meets_admission"}

def main() -> int:
    try: print(verify(yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError) as error: print(f"selected_s4p_rejected_fit_failed:{error}", file=sys.stderr); return 1
    return 0
if __name__ == "__main__": raise SystemExit(main())
