"""Mutation coverage for additive d3154093 PB-01/PB-02 evidence."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from aggregate_pb_d3154093 import aggregate
from verify_pb_d3154093 import ROWS, verify, verify_report


MANIFESTS = {
    "PB-01": ROOT / "docs/baselines/pb-01-legacy-leaf-current-d3154093.v1.yaml",
    "PB-02": ROOT / "docs/baselines/pb-02-direct-current-d3154093.v1.yaml",
}


def load_manifest(row: str) -> dict:
    return yaml.safe_load(MANIFESTS[row].read_text(encoding="utf-8"))


def load_report(row: str, index: int = 0) -> dict:
    manifest = load_manifest(row)
    binding = manifest["evidence"]["reports"][index]
    return json.loads((ROOT / binding["path"]).read_text(encoding="utf-8"))


class VerifyPbD3154093Tests(unittest.TestCase):
    def test_both_additive_manifests_verify(self) -> None:
        for row in MANIFESTS:
            with self.subTest(row=row):
                result = verify(load_manifest(row), ROOT)
                self.assertTrue(result["valid"], (row, result))

    def test_candidate_identity_mutation_is_rejected(self) -> None:
        document = load_manifest("PB-01")
        document["source"]["candidate_commit"] = "0" * 40
        self.assertFalse(verify(document, ROOT)["valid"])

    def test_report_digest_mutation_is_rejected(self) -> None:
        document = load_manifest("PB-02")
        document["evidence"]["reports"][0]["sha256"] = "0" * 64
        self.assertFalse(verify(document, ROOT)["valid"])

    def test_overlay_source_mode_and_archive_fixture_mutations_are_rejected(self) -> None:
        document = load_manifest("PB-01")
        report = load_report("PB-01")
        expected = {
            "fixture_sha256": document["fixture"]["sha256"],
            "toolchain_sha256": document["toolchain_sha256"],
        }

        mutated = copy.deepcopy(report)
        mutated["candidate"]["working_tree_overlay"] = {"src/lib.rs": "0" * 64}
        blockers: list[str] = []
        verify_report("PB-01", mutated, expected, blockers, "overlay")
        self.assertTrue(any("overlay" in item for item in blockers), blockers)

        mutated = copy.deepcopy(report)
        mutated["source_mode"] = "git_archive_plus_lane_worktree"
        blockers = []
        verify_report("PB-01", mutated, expected, blockers, "source-mode")
        self.assertTrue(any("source mode" in item for item in blockers), blockers)

        mutated = copy.deepcopy(report)
        mutated["fixture"]["archive_present"] = False
        blockers = []
        verify_report("PB-01", mutated, expected, blockers, "fixture")
        self.assertTrue(any("fixture archive presence" in item for item in blockers), blockers)

    def test_pb01_12_array_mutation_is_rejected(self) -> None:
        document = load_manifest("PB-01")
        report = load_report("PB-01")
        report["replay"]["comparison"]["arrays"][0]["passed"] = False
        blockers: list[str] = []
        verify_report(
            "PB-01",
            report,
            {"fixture_sha256": document["fixture"]["sha256"], "toolchain_sha256": document["toolchain_sha256"]},
            blockers,
            "pb01-array",
        )
        self.assertTrue(any("array parity" in item for item in blockers), blockers)

    def test_pb02_11_member_mutation_is_rejected(self) -> None:
        document = load_manifest("PB-02")
        report = load_report("PB-02")
        report["replay"]["parity"]["array_member_names"].append("unbound.npy")
        blockers: list[str] = []
        verify_report(
            "PB-02",
            report,
            {"fixture_sha256": document["fixture"]["sha256"], "toolchain_sha256": document["toolchain_sha256"]},
            blockers,
            "pb02-member",
        )
        self.assertTrue(any("11-member" in item for item in blockers), blockers)

    def test_aggregate_cross_replay_toolchain_mutation_is_rejected(self) -> None:
        manifest = load_manifest("PB-02")
        first_binding, second_binding = manifest["evidence"]["reports"]
        first_path = ROOT / first_binding["path"]
        second_value = json.loads((ROOT / second_binding["path"]).read_text(encoding="utf-8"))
        second_value["toolchain"]["timeout_seconds"] += 1
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            directory = Path(temporary)
            first = directory / "first.json"
            second = directory / "second.json"
            output = directory / "aggregate.json"
            first.write_bytes(first_path.read_bytes())
            second.write_text(json.dumps(second_value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "immutable identity drift"):
                aggregate(first, second, output, "PB-02", ROOT)


if __name__ == "__main__":
    unittest.main()
