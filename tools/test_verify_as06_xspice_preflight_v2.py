"""Mutation gate for AS-06 blocked preflight evidence."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from verify_as06_xspice_preflight_v2 import (
    AUDIT_REL,
    MANIFEST_REL,
    REPORT_REL,
    VerificationError,
    load,
    verify_bundle,
    verify_data,
)

ROOT = Path(__file__).resolve().parents[1]


def expect_blocked(report: dict, manifest: dict, audit: dict) -> None:
    try:
        verify_data(report, manifest, audit)
    except VerificationError:
        return
    raise AssertionError("mutation was accepted")


def main() -> int:
    report = load(ROOT / REPORT_REL)
    manifest = load(ROOT / MANIFEST_REL)
    audit = load(ROOT / AUDIT_REL)
    verify_bundle(ROOT / REPORT_REL, ROOT / MANIFEST_REL, ROOT / AUDIT_REL)
    mutations: list[tuple[str, callable]] = []

    def mutate_candidate(value: dict) -> None:
        value["candidate"]["archive_sha256"] = "0" * 64

    def mutate_claim(value: dict) -> None:
        value["scope"]["parity"] = True

    def mutate_promotion(value: dict) -> None:
        value["scope"]["release"] = True

    def mutate_path(value: dict) -> None:
        value["report"]["path"] = "C:\\escape.json"

    def mutate_tool(value: dict) -> None:
        value["toolchain_sha256"] = "1" * 64

    def mutate_asset(value: dict) -> None:
        value["source_asset_sha256"] = "2" * 64

    def mutate_runner(value: dict) -> None:
        value["runner"]["sha256"] = "3" * 64

    def mutate_audit(value: dict) -> None:
        value["candidate"]["tree"] = "4" * 40

    def mutate_gate(value: dict) -> None:
        value["mutation_tests"]["path"] = "tools/other.py"

    def mutate_report(value: dict) -> None:
        value["run_id"] = "other"

    def mutate_candidate_observation(value: dict) -> None:
        value["candidate"]["archive_observation"]["extracted"] = False

    def mutate_upstream_observation(value: dict) -> None:
        value["upstream"]["materialization"] = "caller_archive"

    def mutate_runner_path_policy(value: dict) -> None:
        value["candidate"]["runner_member"]["path_redacted"] = False

    def mutate_runner_overflow(value: dict) -> None:
        value["candidate"]["runner_member"]["member_overflow"] = True

    def mutate_asset_sha(value: dict) -> None:
        value["source_asset_sha256"] = "not-missing"

    mutations.extend([
        ("candidate_hash", mutate_candidate),
        ("claim", mutate_claim),
        ("promotion", mutate_promotion),
        ("path", mutate_path),
        ("toolchain", mutate_tool),
        ("asset", mutate_asset),
        ("runner", mutate_runner),
        ("audit", mutate_audit),
        ("gate", mutate_gate),
        ("run_id", mutate_report),
        ("candidate_observation", mutate_candidate_observation),
        ("upstream_observation", mutate_upstream_observation),
        ("runner_path_policy", mutate_runner_path_policy),
        ("runner_overflow", mutate_runner_overflow),
        ("asset_sha", mutate_asset_sha),
    ])
    for name, mutation in mutations:
        mutated_report = copy.deepcopy(report)
        mutated_manifest = copy.deepcopy(manifest)
        mutated_audit = copy.deepcopy(audit)
        target = mutated_report if name in {"run_id", "candidate_observation", "upstream_observation", "runner_path_policy", "runner_overflow"} else mutated_audit if name in {"audit", "asset_sha"} else mutated_manifest
        mutation(target)
        expect_blocked(mutated_report, mutated_manifest, mutated_audit)
    print(f"valid: baseline plus {len(mutations)} mutations blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
