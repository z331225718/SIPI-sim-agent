from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from verify_m1_rule_ledger import _snapshot_matches, _source_repositories
from verify_m1_conformance import _pybert_results


class ExternalSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.authority = json.loads((ROOT / "schemas" / "authority.v1.yaml").read_text(encoding="utf-8"))
        self.contract = next(
            contract
            for contract in self.authority["external_contracts"]
            if contract["identifier"]["value"] == "pybert.simulation.v1"
        )
        self.repositories = _source_repositories(self.authority)
        repository = self.repositories["py-bert-agent"]
        self.evidence = {
            "source_snapshot": {
                "repository": "py-bert-agent",
                "revision": repository["head"],
                "tree": repository["tree"],
            }
        }

    def test_external_snapshot_requires_authority_pinned_head_and_tree(self):
        self.assertTrue(_snapshot_matches(self.evidence, self.contract, self.repositories))
        wrong_revision = {"source_snapshot": {**self.evidence["source_snapshot"], "revision": "0" * 40}}
        wrong_tree = {"source_snapshot": {**self.evidence["source_snapshot"], "tree": "0" * 40}}
        self.assertFalse(_snapshot_matches(wrong_revision, self.contract, self.repositories))
        self.assertFalse(_snapshot_matches(wrong_tree, self.contract, self.repositories))

    def test_external_snapshot_rejects_unknown_repository(self):
        missing_repository = {"source_snapshot": {**self.evidence["source_snapshot"], "repository": "missing"}}
        self.assertFalse(_snapshot_matches(missing_repository, self.contract, self.repositories))


class SuiteRoutingTests(unittest.TestCase):
    def setUp(self):
        self.suite = json.loads((ROOT / "fixtures" / "contracts" / "v1" / "suite.json").read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "fixtures" / "contracts" / "v1" / "suite.schema.json").read_text(encoding="utf-8"))
        self.validator = Draft202012Validator(schema)

    def test_local_case_cannot_claim_external_runner(self):
        suite = deepcopy(self.suite)
        case = next(item for item in suite["cases"] if item["id"] == "run-request.strict.good")
        case.update({"runner": "pybert_core_rust", "probe": "producer_serializes"})
        with self.assertRaises(ValidationError):
            self.validator.validate(suite)

    def test_external_case_requires_authoritative_origin(self):
        suite = deepcopy(self.suite)
        case = next(item for item in suite["cases"] if item["id"] == "external.pybert-simulation.producer.accept")
        case["origin"]["kind"] = "synthetic_contract"
        with self.assertRaises(ValidationError):
            self.validator.validate(suite)


class ExternalProbeLineageTests(unittest.TestCase):
    def test_accepted_consumer_must_receive_producer_bytes(self):
        cases = [
            {"id": "producer", "probe": "producer_serializes"},
            {"id": "consumer", "probe": "consumer_deserializes"},
            {"id": "version", "probe": "consumer_version_rejects"},
        ]
        output = {
            "runner": "pybert_core_rust",
            "observed_source_snapshot": {
                "repository": "py-bert-agent",
                "revision": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe",
                "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24",
            },
            "results": [
                {
                    "probe": "producer_serializes",
                    "base_payload_sha256": "a" * 64,
                    "consumed_payload_sha256": "b" * 64,
                },
                {
                    "probe": "consumer_deserializes",
                    "base_payload_sha256": "a" * 64,
                    "consumed_payload_sha256": "b" * 64,
                },
                {
                    "probe": "consumer_version_rejects",
                    "base_payload_sha256": "a" * 64,
                    "consumed_payload_sha256": "c" * 64,
                    "derived_from": "producer_serializes",
                },
            ],
        }
        failures: list[str] = []
        with patch("verify_m1_conformance._json_output", return_value=output):
            _pybert_results(cases, failures)
        self.assertIn("pybert_core_rust:payload_hash_lineage", failures)

    def test_rejecting_consumer_must_report_variant_bytes(self):
        cases = [
            {"id": "producer", "probe": "producer_serializes"},
            {"id": "consumer", "probe": "consumer_deserializes"},
            {"id": "version", "probe": "consumer_version_rejects"},
        ]
        output = {
            "runner": "pybert_core_rust",
            "observed_source_snapshot": {
                "repository": "py-bert-agent",
                "revision": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe",
                "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24",
            },
            "results": [
                {
                    "probe": "producer_serializes",
                    "base_payload_sha256": "a" * 64,
                    "consumed_payload_sha256": "a" * 64,
                },
                {
                    "probe": "consumer_deserializes",
                    "base_payload_sha256": "a" * 64,
                    "consumed_payload_sha256": "a" * 64,
                },
                {
                    "probe": "consumer_version_rejects",
                    "base_payload_sha256": "a" * 64,
                    "derived_from": "producer_serializes",
                },
            ],
        }
        failures: list[str] = []
        with patch("verify_m1_conformance._json_output", return_value=output):
            _pybert_results(cases, failures)
        self.assertIn("pybert_core_rust:payload_hash_lineage", failures)

if __name__ == "__main__":
    unittest.main()
