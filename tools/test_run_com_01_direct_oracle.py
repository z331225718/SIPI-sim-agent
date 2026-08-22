import copy
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_com_01_direct_oracle import (
    SCHEMA,
    _artifact_summary,
    compare_scenario,
    scenario_set_sha256,
    load_corpus,
    prepare,
)


class Com01DifferentialRunnerTests(unittest.TestCase):
    def test_pinned_corpus_is_nonempty_and_stable(self):
        corpus = load_corpus()
        self.assertEqual(corpus["schema"], "sipi.com-01-direct-port-corpus.v1")
        self.assertEqual(len(corpus["scenarios"]), 14)
        self.assertEqual(
            scenario_set_sha256(corpus),
            hashlib.sha256(
                json.dumps(corpus["scenarios"], sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        )
        self.assertEqual(
            corpus["fixture_policy"],
            "owner_supplied_external_fixture_plus_derived_temp_package_fixture",
        )

    def test_preparation_exposes_materialized_two_stage_boundary(self):
        report = prepare(agent_com_root=Path(r"C:\Users\z3312\code\COM"))
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["status"], "implementation_materialized_open")
        self.assertEqual(
            report["stages"]["stage_1_source_and_candidate_archive"]["status"],
            "ready",
        )
        self.assertEqual(
            report["stages"]["stage_2_two_run_differential_execution"]["status"],
            "ready_with_external_fixture",
        )

    def test_source_identity_is_pinned(self):
        report = prepare(agent_com_root=Path(r"C:\Users\z3312\code\COM"))
        self.assertEqual(
            report["source"]["commit"],
            "5272ffe74702cd585054d975559b06f8afae7b6e",
        )
        self.assertEqual(
            report["source"]["tree"],
            "7094ab6e84989b218730c52432c70da10261f8ea",
        )
        self.assertEqual(len(report["source"]["source_paths"]), 11)

    def test_report_round_trip_does_not_require_local_paths(self):
        report = prepare(agent_com_root=Path(r"C:\Users\z3312\code\COM"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
            loaded = json.loads(path.read_text(encoding="utf-8"))
        text = json.dumps(loaded)
        self.assertNotIn("C:\\Users\\z3312", text)
        self.assertEqual(loaded["corpus"]["path"], "docs/baselines/com-01-direct-port-corpus.v1.json")

    def test_corpus_mutation_changes_digest(self):
        corpus = copy.deepcopy(load_corpus())
        original = scenario_set_sha256(corpus)
        corpus["scenarios"][0]["output"] = "mutated"
        self.assertNotEqual(original, scenario_set_sha256(corpus))

    def test_materialized_projection_excludes_only_fingerprint(self):
        oracle = {
            "materialized_fingerprint": "a" * 64,
            "materialized": {"parameters": {"secret": 1}, "options": {"flag": True}},
        }
        candidate = {**oracle, "materialized_fingerprint": "b" * 64}
        with patch(
            "run_com_01_direct_oracle._run",
            side_effect=[
                (0, json.dumps(oracle), ""),
                (0, json.dumps(candidate), ""),
            ],
        ):
            result = compare_scenario(
                {"id": "materialized", "fixture_role": "primary_xlsx", "output": "materialized_json"},
                Path("fixture.xlsx"),
                Path("agent-com"),
                Path("candidate.exe"),
            )
        self.assertEqual(result["comparison"], "values_equal_fingerprint_drift")
        self.assertTrue(result["value_match"])
        self.assertEqual(result["difference_keys"], [])
        self.assertNotIn("secret", json.dumps(result["oracle_summary"]))

    def test_error_match_requires_exit_and_category(self):
        with patch(
            "run_com_01_direct_oracle._run",
            side_effect=[
                (3, "", "invalid profile"),
                (3, "", "invalid package"),
            ],
        ):
            result = compare_scenario(
                {"id": "error", "fixture_role": "primary_xlsx", "output": "json"},
                Path("fixture.xlsx"),
                Path("agent-com"),
                Path("candidate.exe"),
            )
        self.assertEqual(result["comparison"], "error_code_mismatch")
        self.assertFalse(result["value_match"])

    def test_artifact_summary_contains_hashes_counts_and_no_values(self):
        value = {
            "materialized_fingerprint": "a" * 64,
            "materialized": {"parameters": {"secret": 123}, "options": {"flag": True}},
            "config_consumption": {"summary": {"total": 2}},
        }
        summary = _artifact_summary(value, Path("fixture.xlsx"), json.dumps(value), "", None)
        self.assertEqual(summary["materialized"]["parameter_count"], 1)
        self.assertNotIn("secret", json.dumps(summary))
        self.assertRegex(summary["projection_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
