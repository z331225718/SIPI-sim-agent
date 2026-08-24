"""Mutation tests for the PB-03 ed7b12d2 immutable gate."""

from __future__ import annotations

import copy
import json
import sys
from unittest import mock
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_pb_03_direct_ed7b12d2_current as verifier  # noqa: E402


MANIFEST = verifier.ROOT / verifier.MANIFEST_PATH


def load_manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def test_current_manifest_is_valid() -> None:
    result = verifier.verify(load_manifest())
    assert result["valid"], result


def test_manifest_extra_promotion_claim_is_rejected() -> None:
    value = load_manifest()
    value["claims"]["promotion"] = True
    result = verifier.verify(value)
    assert not result["valid"]


def test_manifest_report_binding_drift_is_rejected() -> None:
    value = load_manifest()
    value["evidence"]["reports"][0]["run_id"] = "coordinated-run"
    result = verifier.verify(value)
    assert not result["valid"]


def test_manifest_source_scope_and_policy_drift_are_rejected() -> None:
    value = load_manifest()
    value["replay_policy"]["source_mode"] = "working_tree"
    result = verifier.verify(value)
    assert not result["valid"]
    value = load_manifest()
    value["replay_policy"]["fresh_runs_required"] = 1
    result = verifier.verify(value)
    assert not result["valid"]


def test_stable_member_payload_mutation_is_rejected() -> None:
    report = json.loads((verifier.ROOT / verifier.REPORTS[0]["path"]).read_text(encoding="utf-8"))
    mutated = copy.deepcopy(report)
    member = mutated["replay"]["candidate_artifact"]["arrays"]["logical_members"][verifier.STABLE_NAMES[0]]
    member["f64_sha256"] = "0" * 64
    errors: list[str] = []
    verifier.verify_member_map(mutated, errors, "mutation")
    assert errors


def test_malformed_audit_and_claims_fail_closed() -> None:
    value = load_manifest()
    value["audit"] = None
    result = verifier.verify(value)
    assert not result["valid"]
    value = load_manifest()
    value["non_claims"] = []
    result = verifier.verify(value)
    assert not result["valid"]


def test_coordinated_distinct_run_and_inventory_forge_is_rejected() -> None:
    value = load_manifest()
    value["evidence"]["reports"][0]["run_id"] = "forge-run-01"
    value["evidence"]["reports"][0]["fresh_run_nonce"] = "1" * 32
    value["evidence"]["reports"][1]["run_id"] = "forge-run-02"
    value["evidence"]["reports"][1]["fresh_run_nonce"] = "2" * 32
    value["inventory"]["canonical_sha256"] = "f" * 64
    value["inventory"]["names"] = list(reversed(value["inventory"]["names"]))
    result = verifier.verify(value)
    assert not result["valid"]


def test_coordinated_toolchain_harness_and_claim_forge_is_rejected() -> None:
    value = load_manifest()
    value["claims"]["payload_scope"] = "whole_payload"
    value["non_claims"] = []
    value["harness"]["runner"]["path"] = "tools/evil.py"
    value["harness"]["runner"]["sha256"] = "e" * 64
    value["replay_policy"]["fresh_runs_required"] = 1
    result = verifier.verify(value)
    assert not result["valid"]


def test_malformed_harness_and_shape_are_blocked_without_exception() -> None:
    value = load_manifest()
    value["harness"] = None
    result = verifier.verify(value)
    assert not result["valid"]
    report = json.loads((verifier.ROOT / verifier.REPORTS[0]["path"]).read_text(encoding="utf-8"))
    report["replay"]["candidate_artifact"]["arrays"]["logical_members"][verifier.STABLE_NAMES[0]]["shape"] = [None]
    errors: list[str] = []
    verifier.verify_member_map(report, errors, "shape-mutation")
    assert errors


def test_audit_and_harness_path_coordinated_drift_is_rejected() -> None:
    value = load_manifest()
    value["audit"]["path"] = value["evidence"]["aggregate"]["path"]
    result = verifier.verify(value)
    assert not result["valid"]
    value = load_manifest()
    value["harness"]["verifier"]["path"] = verifier.MUTATION_TEST_PATH
    result = verifier.verify(value)
    assert not result["valid"]


def test_malformed_physical_report_is_blocked_without_keyerror() -> None:
    original_report = json.loads((verifier.ROOT / verifier.REPORTS[0]["path"]).read_text(encoding="utf-8"))
    malformed = copy.deepcopy(original_report)
    malformed.pop("build")
    original_loader = verifier.load_json

    def load(relative, errors, label):
        if relative == verifier.REPORTS[0]["path"]:
            return malformed, verifier.REPORTS[0]["sha256"]
        return original_loader(relative, errors, label)

    with mock.patch.object(verifier, "load_json", side_effect=load):
        result = verifier.verify(load_manifest())
    assert not result["valid"]


def test_aggregate_workflow_semantics_mutation_is_rejected() -> None:
    original_aggregate = json.loads((verifier.ROOT / verifier.AGGREGATE["path"]).read_text(encoding="utf-8"))
    mutated = copy.deepcopy(original_aggregate)
    mutated["workflow_semantics"]["payload_is_not_status_only"] = False
    original_loader = verifier.load_json

    def load(relative, errors, label):
        if relative == verifier.AGGREGATE["path"]:
            return mutated, verifier.AGGREGATE["sha256"]
        return original_loader(relative, errors, label)

    with mock.patch.object(verifier, "load_json", side_effect=load):
        result = verifier.verify(load_manifest())
    assert not result["valid"]
