"""Mutation coverage for immutable PB current-bound manifests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_pb_current_bound import verify, verify_report
from aggregate_pb_current_bound import aggregate


MANIFESTS = {
    "PB-01": ROOT / "docs/baselines/pb-01-legacy-leaf.current-bound.v1.yaml",
    "PB-02": ROOT / "docs/baselines/pb-02-direct-port.current-bound.v1.yaml",
    "PB-03": ROOT / "docs/baselines/pb-03-direct-port.current-bound.v1.yaml",
    "PB-04": ROOT / "docs/baselines/pb-04-direct-port.current-bound.v1.yaml",
    "PB-05": ROOT / "docs/baselines/pb-05-direct-port.current-bound.v1.yaml",
}


def load(row: str) -> dict:
    return yaml.safe_load(MANIFESTS[row].read_text(encoding="utf-8"))


class VerifyPbCurrentBoundTests(unittest.TestCase):
    def test_all_current_bound_manifests_verify(self) -> None:
        for row in MANIFESTS:
            with self.subTest(row=row):
                result = verify(load(row), ROOT)
                self.assertTrue(result["valid"], (row, result))

    def test_candidate_commit_mutation_is_rejected(self) -> None:
        document = load("PB-03")
        document["source"]["candidate_commit"] = "0" * 40
        self.assertFalse(verify(document, ROOT)["valid"])

    def test_report_digest_mutation_is_rejected(self) -> None:
        document = load("PB-05")
        document["evidence"]["reports"][0]["sha256"] = "0" * 64
        self.assertFalse(verify(document, ROOT)["valid"])

    def test_selection_and_reference_semantics_are_fail_closed(self) -> None:
        document = load("PB-04")
        report_path = ROOT / document["evidence"]["reports"][0]["path"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["replay"]["selection"]["candidate"]["rust_only"] = True
        document["evidence"]["reports"][0]["sha256"] = "0" * 64
        self.assertFalse(verify(document, ROOT)["valid"])

    def test_no_reference_self_compare_semantics_are_bound(self) -> None:
        document = load("PB-05")
        document["evidence"]["aggregate"]["sha256"] = "0" * 64
        self.assertFalse(verify(document, ROOT)["valid"])

    def test_report_overlay_and_archive_fixture_mutations_are_rejected(self) -> None:
        document = load("PB-03")
        report_path = ROOT / document["evidence"]["reports"][0]["path"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        expected = dict(document["source"])
        expected["fixture_path"] = document["fixture"]["path"]
        expected["fixture_sha256"] = document["fixture"]["sha256"]
        expected["toolchain_sha256"] = document["toolchain_sha256"]

        report["candidate"]["working_tree_overlay"] = {"crates/sipi-pybert-direct/src/lib.rs": "0" * 64}
        blockers: list[str] = []
        verify_report("PB-03", report, expected, blockers, "mutated-overlay")
        self.assertTrue(any("overlay claim" in item for item in blockers), blockers)

        report["candidate"].pop("working_tree_overlay", None)
        report["source_mode"] = "git_archive_plus_lane_worktree"
        blockers = []
        verify_report("PB-03", report, expected, blockers, "mutated-source-mode")
        self.assertTrue(any("source mode drift" in item for item in blockers), blockers)

        report["source_mode"] = "git_archive_at_immutable_commit"
        report["candidate"].pop("working_tree_overlay", None)
        report["fixture"]["archive_present"] = False
        blockers = []
        verify_report("PB-03", report, expected, blockers, "mutated-fixture")
        self.assertTrue(any("not present in candidate archive" in item for item in blockers), blockers)

    def test_aggregate_cross_report_toolchain_mutation_is_rejected(self) -> None:
        first_path = ROOT / load("PB-03")["evidence"]["reports"][0]["path"]
        second_path = ROOT / load("PB-03")["evidence"]["reports"][1]["path"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.json"
            second = root / "second.json"
            output = root / "aggregate.json"
            first.write_bytes(first_path.read_bytes())
            second_value = json.loads(second_path.read_text(encoding="utf-8"))
            second_value["toolchain"]["timeout_seconds"] += 1
            second.write_text(json.dumps(second_value, sort_keys=True), encoding="utf-8")
            result = aggregate(first, second, output, "PB-03")
        self.assertFalse(result["status"] == "passed")
        self.assertIn("immutable identity drift", result["blockers"])


if __name__ == "__main__":
    unittest.main()
