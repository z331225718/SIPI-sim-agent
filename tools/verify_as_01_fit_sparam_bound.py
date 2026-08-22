"""Verify the bounded AS-01 immutable-source replay evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/baselines/as-01-fit-sparam-bound.v2.yaml"
CANDIDATE_COMMIT = "8bcfd1d1bc511461615f19338e453f0148e5dcb1"
CANDIDATE_TREE = "ed221a36f2d3325b0aac3f3336a9c8a14d13e99a"
UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
REPORTS = [
    (
        "docs/baselines/as-01-fit-sparam-bound-run-01.v1.json",
        "81d54d64b8880add9b11788e8cca158092f2fffd417fc846279bc83b4751a0b8",
        "as01-bound-20260823-01",
        "4fab0a10a7390d99e5ada060a7e5b9701818e2e87741ac389fafaf3fda8b9e8b",
    ),
    (
        "docs/baselines/as-01-fit-sparam-bound-run-02.v1.json",
        "c01d070881f874711c96d1a4782068279a4fbc50ba71faee5a10ee40a4bb1c6c",
        "as01-bound-20260823-02",
        "1f3160abfd337bc619f1d7a14f7936d1fce098d5392147ac539fee127b2a9b01",
    ),
]
AGGREGATE = (
    "docs/baselines/as-01-fit-sparam-bound-aggregate.v1.json",
    "f7067810af8455fb2c1a861f3e73c8e03f95ff5acb210b4ce15fa80220886fec",
)
FILES = {
    "runner": (
        "tools/run_as_01_fit_sparam_bound.py",
        "308a7bb462b17bf31ca5b6e3dc482358d4434980ce56a8522fce8166516e152a",
        "5c01016735a8a36d2c681c5701c48c5feaac019e",
    ),
    "aggregator": (
        "tools/aggregate_as_01_fit_sparam_bound.py",
        "5abb8b1ade63d867aaf967e1d68b0cad578d6f5213815c17da369ce5108e273f",
        "a381de12c82b54e92ade50343c09e98fd1868e99",
    ),
    "oracle_lock": (
        "docs/baselines/as-01-agent-spice-oracle-windows-py312.lock",
        "06df254491d64ba2dc870e2807b34b44fbacb36c17f88e7caeb09bbead43dabd",
        "1851fb0e80ab9a9ea0d1ce09cb6f49c416e1e0b0",
    ),
    "audit": (
        "docs/baselines/audits/2026-08-23-as-01-fit-sparam-bound.md",
        "83d0d91c8115e532bcc5377c745e6cd1bf4a5939e55c81ba20c1113b7befbce6",
        "a48f55c314ba528d38314c98a1b3447d98cd26fb",
    ),
}
EXPECTED = {
    "candidate_archive": "aceb1c2c5498baa8424c0d28af759cc98e7f0b430912a889836157976b8e7276",
    "candidate_inventory": "93c6806627f66ecac6274849df5b5d366331461d6f7b0a5b28a3e2debafb6fc5",
    "cargo_lock": "7d1acce2bffd2ed3fcbf0ddb793fa1410123d1cbde7a7778a11bca43e78fe342",
    "binary": "a632369a302124efaba3d3a684c2a99c7d976245737fb7fe260efce0e4ba07c3",
    "upstream_archive": "282265e1c7b987407875a5c77fd1f2f0542cea9487407bb14b967a97b1ad6128",
    "upstream_inventory": "fbb2ef16cae6b23634fb2afc2d0394265ee0e99250650d03aa11773aff2c6622",
    "license": "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2",
    "fixture": "c10ebbb82a3cee4918831e11abe9e318df673d11c256bd114e1aed49eeb9b257",
    "scenario": "ceebf8f1e89cc134d62afa551cc3e6a2e2e20d20f50739c09cd9b34951c9db3f",
    "comparison": "df8f88848a201c07d891dbc5aec9d5007e408363f0df7179976cad9b53745be6",
    "frequency": "99ea2084035238e80f7016fea5a8b676009a619c98d0bd52e910a9d5038cb11c",
    "upstream_touchstone": "59cbd8308a38a5e40c5613af23906327c4d61bcdb94dbee14883dcee73279bca",
    "candidate_touchstone": "794b0107158330bf1d4d62cf1e8ad8141b8a366f047c480659b7e056960e9d0b",
}
REPORT_KEYS = {
    "archived_preparation_runner", "bound_oracle_lock", "bound_runner", "build",
    "candidate", "comparison", "custody_valid", "fixture_sha256", "fresh_run_nonce",
    "harness_source_mode", "non_claims", "numeric_mismatch_open", "oracle_environment",
    "parity_claim", "replay", "run_id", "scenario_set_sha256", "schema", "source_mode",
    "status", "toolchain", "upstream",
}
AGGREGATE_KEYS = {
    "acceptance_tolerance", "archived_preparation_runner", "binary_sha256", "blockers",
    "bound_oracle_lock", "bound_runner", "candidate", "comparison", "custody_valid",
    "fixture_sha256", "non_claims", "numeric_mismatch_open", "oracle_environment",
    "parity_claim", "reports", "scenario_set_sha256", "schema", "status", "toolchain",
    "upstream",
}


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob(path: Path) -> str:
    try:
        return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise VerificationError(f"cannot hash Git blob {path}: {error}") from error


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot read strict JSON {path}: {error}") from error
    require(isinstance(value, dict), f"JSON root is not a mapping: {path}")
    return value


def no_nonfinite(value: Any, context: str = "root") -> None:
    if isinstance(value, float):
        require(math.isfinite(value), f"non-finite number at {context}")
    elif isinstance(value, dict):
        for key, child in value.items():
            no_nonfinite(child, f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            no_nonfinite(child, f"{context}[{index}]")


def no_path_leak(value: Any, context: str) -> None:
    text = json.dumps(value, sort_keys=True)
    for pattern in (r"[A-Za-z]:\\Users\\", r"/Users/", r"/home/", r"\\\\[^\\]+\\[^\\]+"):
        require(re.search(pattern, text) is None, f"absolute path leak in {context}")


def scenario(document: dict[str, Any], name: str) -> dict[str, Any]:
    rows = document["comparison"]["scenarios"]
    matches = [row for row in rows if row.get("id") == name]
    require(len(matches) == 1, f"scenario cardinality drift: {name}")
    return matches[0]


def verify_report(document: dict[str, Any], *, run_id: str, nonce: str) -> None:
    require(set(document) == REPORT_KEYS, "report top-level key drift")
    require(document["schema"] == "sipi.agent-spice-as-01-bound-replay.v1", "report schema drift")
    require(document["status"] == "completed_numeric_mismatch", "report status overclaim/drift")
    require(document["run_id"] == run_id, "report run ID drift")
    require(document["fresh_run_nonce"] == nonce and re.fullmatch(r"[0-9a-f]{64}", nonce) is not None, "report nonce drift")
    require(document["custody_valid"] is True, "report custody invalid")
    require(document["parity_claim"] is False, "report parity overclaim")
    require(document["numeric_mismatch_open"] is True, "report mismatch improperly closed")
    require(document["comparison"]["acceptance_tolerance"] is None, "acceptance tolerance invented")
    require(document["comparison"]["numeric_parity"] is False, "numeric parity overclaim")
    require(document["comparison"]["complete_contract_parity_claim"] is False, "contract parity overclaim")
    require(document["comparison"]["scenario_count"] == 10, "scenario count drift")
    require(document["comparison"]["sha256"] == EXPECTED["comparison"], "comparison digest drift")
    require(document["fixture_sha256"] == EXPECTED["fixture"], "fixture drift")
    require(document["scenario_set_sha256"] == EXPECTED["scenario"], "scenario set drift")
    require(document["build"]["exit_code"] == 0 and document["build"]["binary_present"] is True, "candidate build failed")
    require(document["build"]["binary_sha256"] == EXPECTED["binary"], "candidate binary drift")
    candidate = document["candidate"]
    require((candidate["commit"], candidate["tree"]) == (CANDIDATE_COMMIT, CANDIDATE_TREE), "candidate source drift")
    require(candidate["archive_sha256"] == EXPECTED["candidate_archive"], "candidate archive drift")
    require(candidate["inventory"]["sha256"] == EXPECTED["candidate_inventory"], "candidate inventory drift")
    require(candidate["cargo_lock_sha256"] == EXPECTED["cargo_lock"], "Cargo lock drift")
    upstream = document["upstream"]
    require((upstream["commit"], upstream["tree"]) == (UPSTREAM_COMMIT, UPSTREAM_TREE), "upstream source drift")
    require(upstream["archive_sha256"] == EXPECTED["upstream_archive"], "upstream archive drift")
    require(upstream["inventory"]["sha256"] == EXPECTED["upstream_inventory"], "upstream inventory drift")
    require(upstream["license_sha256"] == EXPECTED["license"], "upstream license drift")
    require(document["bound_runner"]["sha256"] == FILES["runner"][1], "bound runner drift")
    require(document["bound_oracle_lock"]["sha256"] == FILES["oracle_lock"][1], "oracle lock drift")
    lock = document["oracle_environment"]["lock"]
    require(lock["sha256"] == FILES["oracle_lock"][1] and lock["require_hashes"] is True, "oracle lock policy drift")
    require(len(document["oracle_environment"]["installed"]["distributions"]) == 22, "installed distribution inventory drift")
    common = scenario(document, "full_band_defaults")
    require(common["upstream_summary"]["best_effort_final_mean_rms"] == 0.030266038995446727, "upstream RMS drift")
    require(common["candidate_summary"]["rms_error"] == 0.37790224348580714, "candidate RMS drift")
    require(common["rms_abs_delta"] == 0.3476362044903604, "RMS delta drift")
    up_fit = common["upstream_fitted_touchstone"]
    rust_fit = common["candidate_fitted_touchstone"]
    require(up_fit["logical_sha256"] == EXPECTED["upstream_touchstone"], "upstream fitted Touchstone drift")
    require(rust_fit["logical_sha256"] == EXPECTED["candidate_touchstone"], "candidate fitted Touchstone drift")
    require(up_fit["frequency_f64_sha256"] == rust_fit["frequency_f64_sha256"] == EXPECTED["frequency"], "frequency grid drift")
    require(up_fit["independent_metrics"]["full_band_rms"] == 0.030266038995446727, "upstream independent RMS drift")
    require(rust_fit["independent_metrics"]["full_band_rms"] == 0.18895112174290357, "candidate independent RMS drift")
    require(up_fit["independent_metrics"]["sample_grid_sigma_max"] == 0.5, "upstream sampled sigma drift")
    require(rust_fit["independent_metrics"]["sample_grid_sigma_max"] == 0.566611420285334, "candidate sampled sigma drift")
    duplicate = scenario(document, "target_failure_and_success")
    require(duplicate["coverage_note"] == "duplicate_of_full_band_defaults", "duplicate noncoverage drift")
    require(document["non_claims"] and all(isinstance(x, str) for x in document["non_claims"]), "report non-claims missing")
    no_nonfinite(document)
    no_path_leak(document, run_id)


def verify(manifest_path: Path = DEFAULT_MANIFEST, *, repo_root: Path = ROOT) -> dict[str, Any]:
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise VerificationError(f"cannot read manifest: {error}") from error
    require(isinstance(manifest, dict), "manifest must be a mapping")
    require(manifest["schema"] == "sipi.agent-spice-as-01-fit-sparam-bound.v2", "manifest schema drift")
    require(manifest["status"] == "completed_numeric_mismatch", "manifest status overclaim/drift")
    scope = manifest["scope"]
    require(scope == {
        "work_item": "AS-01", "upstream_entrypoint": "fit-sparam",
        "bounded_leaf": "two_port_fitted_touchstone_json_log", "custody_valid": True,
        "numeric_mismatch_open": True, "parity_claim": False, "acceptance_tolerance": None,
        "migration_row_closed": False, "product_capability_promoted": False,
    }, "manifest scope drift")
    sources = manifest["sources"]
    require(sources["candidate"] == {
        "commit": CANDIDATE_COMMIT, "tree": CANDIDATE_TREE,
        "archive_sha256": EXPECTED["candidate_archive"], "inventory_sha256": EXPECTED["candidate_inventory"],
        "cargo_lock_sha256": EXPECTED["cargo_lock"], "binary_sha256": EXPECTED["binary"],
    }, "manifest candidate binding drift")
    require(sources["upstream"] == {
        "commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE,
        "archive_sha256": EXPECTED["upstream_archive"], "inventory_sha256": EXPECTED["upstream_inventory"],
        "license_sha256": EXPECTED["license"],
    }, "manifest upstream binding drift")
    for key, (relative, digest, blob) in FILES.items():
        path = repo_root / relative
        require(path.is_file(), f"missing bound file: {relative}")
        require(sha256(path) == digest, f"bound file hash drift: {relative}")
        require(git_blob(path) == blob, f"bound file Git blob drift: {relative}")
    harness = manifest["harness"]
    require(harness["source_mode"] == "content_addressed_worktree_pending_owner_commit", "harness custody overclaim")
    for key in ("runner", "aggregator", "oracle_lock"):
        relative, digest, blob = FILES[key]
        item = harness[key]
        require(item["path"] == relative and item["sha256"] == digest and item["git_blob_sha1"] == blob, f"manifest {key} binding drift")
    require(harness["fixture_sha256"] == EXPECTED["fixture"], "manifest fixture drift")
    require(harness["scenario_set_sha256"] == EXPECTED["scenario"], "manifest scenario drift")
    require(harness["comparison_sha256"] == EXPECTED["comparison"], "manifest comparison drift")
    report_documents = []
    require(len(manifest["formal_reports"]) == 2, "formal report cardinality drift")
    resolved = []
    for index, (relative, digest, run_id, nonce) in enumerate(REPORTS):
        item = manifest["formal_reports"][index]
        require(item == {"path": relative, "sha256": digest, "run_id": run_id, "fresh_run_nonce": nonce}, "manifest report binding drift")
        path = repo_root / relative
        require(path.is_file() and sha256(path) == digest, f"formal report hash drift: {relative}")
        resolved.append(path.resolve(strict=True))
        report = read_json(path)
        verify_report(report, run_id=run_id, nonce=nonce)
        report_documents.append(report)
    require(resolved[0] != resolved[1], "formal report path alias")
    relative, digest = AGGREGATE
    require(manifest["aggregate"] == {"path": relative, "sha256": digest, "status": "completed_numeric_mismatch"}, "manifest aggregate binding drift")
    aggregate_path = repo_root / relative
    require(aggregate_path.is_file() and sha256(aggregate_path) == digest, "aggregate hash drift")
    aggregate = read_json(aggregate_path)
    require(set(aggregate) == AGGREGATE_KEYS, "aggregate top-level key drift")
    require(aggregate["schema"] == "sipi.agent-spice-as-01-bound-aggregate.v1", "aggregate schema drift")
    require(aggregate["status"] == "completed_numeric_mismatch" and aggregate["blockers"] == [], "aggregate did not complete custody")
    require(aggregate["custody_valid"] is True and aggregate["parity_claim"] is False, "aggregate claim drift")
    require(aggregate["numeric_mismatch_open"] is True and aggregate["acceptance_tolerance"] is None, "aggregate mismatch/acceptance drift")
    require(aggregate["binary_sha256"] == EXPECTED["binary"], "aggregate binary drift")
    require(aggregate["comparison"] == report_documents[0]["comparison"] == report_documents[1]["comparison"], "semantic replay drift")
    require(aggregate["reports"] == [
        {"path": relative, "sha256": digest, "run_id": run_id, "fresh_run_nonce": nonce}
        for relative, digest, run_id, nonce in REPORTS
    ], "aggregate report binding drift")
    require(manifest["semantic_observation"] == {
        "scenario_count": 10,
        "numerical_scenarios": ["full_band_defaults", "priority_band_only", "target_failure_and_success"],
        "duplicate_noncoverage": {"target_failure_and_success": "duplicate_of_full_band_defaults"},
        "common_leaf": {
            "upstream_report_rms": 0.030266038995446727,
            "candidate_report_rms": 0.37790224348580714,
            "report_rms_abs_delta": 0.3476362044903604,
            "upstream_independent_touchstone_rms": 0.030266038995446727,
            "candidate_independent_touchstone_rms": 0.18895112174290357,
            "upstream_sampled_sigma_max": 0.5,
            "candidate_sampled_sigma_max": 0.566611420285334,
            "frequency_f64_sha256": EXPECTED["frequency"],
            "upstream_fitted_touchstone_logical_sha256": EXPECTED["upstream_touchstone"],
            "candidate_fitted_touchstone_logical_sha256": EXPECTED["candidate_touchstone"],
        },
        "excluded_upstream_only_artifacts": ["spice_subcircuit", "rfm", "rfm_wrapper", "html_report"],
    }, "manifest semantic observation drift")
    require(manifest["supersession"] == {
        "prior_manifest": "docs/baselines/as-01-fit-sparam-direct-port.v1.yaml",
        "supersedes_preparation_only": True,
        "supersedes_no_external_oracle_evidence_for_this_bounded_corpus_only": True,
        "does_not_supersede_open_migration_or_non_parity_claims": True,
    }, "supersession scope drift")
    require(manifest["audit"] == {"path": FILES["audit"][0], "sha256": FILES["audit"][1]}, "audit binding drift")
    required_non_claims = {
        "no_complete_fit_sparam_parity", "no_acceptance_tolerance", "no_continuous_passivity_claim",
        "no_upstream_only_artifact_parity", "no_product_capability_promotion", "no_migration_row_close",
        "no_release_approval", "no_license_admission_change",
    }
    require(set(manifest["non_claims"]) == required_non_claims, "manifest non-claims drift")
    no_nonfinite(manifest)
    no_nonfinite(aggregate)
    no_path_leak(aggregate, "aggregate")
    return {
        "status": aggregate["status"], "candidate_commit": CANDIDATE_COMMIT,
        "candidate_tree": CANDIDATE_TREE, "report_sha256": [row[1] for row in REPORTS],
        "aggregate_sha256": AGGREGATE[1], "numeric_mismatch_open": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.manifest, repo_root=args.repo_root), sort_keys=True))
    except VerificationError as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
