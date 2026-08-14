"""Verify the hash-only ADS passivity action-surface observation evidence."""

from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-ads-passivity-action-surface-observation-evidence.v1.yaml"
COMMIT = "37e795310f7832dacff8603d115928fc54d7d89e"
TREE = "a81e84d4834070489b660762c27290ee77d372a3"
INVENTORY = {
    "tools/run_p3c_external_ads_fixed_pulse_operator.py": "806147101f559a865c14cc89290ad596d4dce91aad8048d35f33a8f97654d360",
    "tools/run_p3c_external_ads_fixed_pulse_passivity_surface.py": "dd5c60b8364d2b9ad6f17dafdfd1c55cc4be4dcae11aa495a024337f5b4e723f",
    "tools/observe_p3c_ads_fixed_pulse_passivity_surface.py": "7d2521f78b0416f8d20fb10d2a97d5f48e57264da1161d94c41e25d87fdd9dfa",
}
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def fail(condition: bool, reason: str) -> None:
    if condition:
        raise VerificationError(reason)


def digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and not (set(value) - HEX)


def inventory() -> dict[str, str]:
    result = subprocess.run(["git", "archive", "--format=tar", "HEAD", "--", *sorted(INVENTORY)], cwd=ROOT, check=False, capture_output=True)
    if result.returncode:
        raise VerificationError("source_drift")
    with tempfile.TemporaryDirectory() as directory:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            archive.extractall(directory, filter="data")
        return {path: hashlib.sha256((Path(directory) / path).read_bytes()).hexdigest() for path in INVENTORY}


def verify(document: object, current: bool = True) -> dict[str, object]:
    fail(not isinstance(document, dict), "shape")
    required = {"schema", "status", "authority", "predecessor", "external_observation", "independent_audit", "admission", "blockers", "non_claims"}
    fail(set(document) != required, "shape")
    fail(document["schema"] != "sipi.p3c-ads-passivity-action-surface-observation-evidence.v1", "schema")
    fail(document["status"] != "external_ads_passivity_action_surface_observed_correction_magnitude_unevaluated", "status")
    fail(document["authority"] != {"actor": "user", "decision_ref": "user-authorized-passivity-action-surface-2026-08-14", "scope": "one_fixed_external_ads_dataset_action_surface_observation_only"}, "authority")
    fail(document["predecessor"] != {"path": "docs/baselines/p3c-ads-fixed-pulse-operator-observation-evidence.v1.yaml", "result": "fixed_pulse_operator_delta_observed_without_cause_identification"}, "predecessor")
    observation = document["external_observation"]
    exact = {
        "schema": "sipi.p3c.ads-fixed-pulse-passivity-surface-observation.v1", "custody": "external_only", "report_path_retained": False,
        "report_byte_length": 1307, "report_content_sha256": "a5490faa415012cfc9312c3be4360669d7e343ce7c704ce24160e10812397c84",
        "clean_archive_commit": COMMIT, "clean_archive_tree": TREE, "source_byte_length": 1834156,
        "source_sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47",
        "ads_help_byte_length": 150522, "ads_help_sha256": "45372e9c7c79492bf6023a4e860f05a20caf0ef5e2a083407c119909afc187bf",
        "runner_source_sha256": INVENTORY["tools/run_p3c_external_ads_fixed_pulse_passivity_surface.py"],
        "observer_source_sha256": INVENTORY["tools/observe_p3c_ads_fixed_pulse_passivity_surface.py"],
        "predecessor_runner_sha256": INVENTORY["tools/run_p3c_external_ads_fixed_pulse_operator.py"],
        "fresh_runs": 2, "ads_netlist_byte_length": 1760,
        "ads_netlist_sha256": "6f720d8375726b1d7b0c42fbc7579372c1fea0ca5929c21d9823ccae4c2838e8",
        "passivity_surface": {"vectorset_count": 65, "s0_vectorset_count": 16, "vectorset_identity_sha256": "d8a2e18a8237e81b7f0ce559b26116bae2aa82b5672a54e81a948bb8c07b3087"},
        "cleanup_status": "complete",
    }
    fail(observation != exact, "observation")
    tree = subprocess.run(["git", "rev-parse", f"{COMMIT}^{{tree}}"], cwd=ROOT, check=False, capture_output=True, text=True)
    fail(tree.returncode != 0 or tree.stdout.strip() != TREE, "archive")
    if current:
        fail(inventory() != INVENTORY, "source_drift")
    audit = document["independent_audit"]
    fail(audit != {"reviewer": "Orca_reused_OpenCode_terminal", "terminal": "term_2de7cb74-b803-4e20-bb5b-4803777c24f8", "status": "completed", "result": "no_high_or_critical_findings_low_test_hardening_applied"}, "audit")
    true = {"ads_passivity_action_surface_documented", "selected_run_passivity_action_observability_evaluated", "documented_pre_correction_surface_observed"}
    false = {"correction_magnitude_evaluated", "passivity_algorithm_or_repair_implemented", "waveform_mismatch_cause_identified", "candidate_waveform_accepted", "release_ledger_promoted"}
    admission = document["admission"]
    fail(not isinstance(admission, dict) or set(admission) != true | false or any(admission[key] is not True for key in true) or any(admission[key] is not False for key in false), "gates")
    fail(document["blockers"] != ["correction_magnitude_not_evaluated", "ads_passivity_algorithm_not_observed_or_ported", "waveform_mismatch_cause_not_identified"], "blockers")
    forbidden = ("file://", "http://", "https://", "c:\\", "spectrum: [", "waveform: [", "log:")
    fail(any(token in str(document).lower() for token in forbidden), "leak")
    return {"valid": True, "accepted": False, "correction_magnitude_evaluated": False}


if __name__ == "__main__":
    try:
        print(verify(yaml.safe_load(PATH.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_ads_passivity_action_surface_observation_failed:{error}")
        raise SystemExit(1)
