"""Prep-stage schema, shared-helper, and mutation tests for COM-03."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aggregate_com_03_current_candidate import VerificationError as AggregateError, aggregate
from run_com_01_current_candidate import SHARED_HELPER_SCHEMA, _atomic_json_create
from run_com_03_current_candidate import COM03_BINARY_BASENAME, COM03_PAYLOAD_CONTRACT, COM03_RESULT_CONTRACT, COM03_SCENARIO_CONTRACT, EXPECTED_SCENARIO_SET_SHA256, _build_environment_receipt, _validate_com03_report
from test_verify_com_01_current_candidate import prepared_report as common_report


def prepared_report() -> dict:
    common = common_report()
    common["candidate"]["build"]["environment"] = _build_environment_receipt()
    for key in ("binary_pre", "binary_post", "cargo_source_pre", "cargo_source_post"):
        common["candidate"]["build"][key]["basename"] = COM03_BINARY_BASENAME
    scenarios = []
    for scenario_id, (mode, outcome) in COM03_SCENARIO_CONTRACT.items():
        payloads = {}
        for role, (size, sha) in zip(("golden", "result"), COM03_PAYLOAD_CONTRACT[scenario_id]):
            payloads[role] = {"basename": f"{scenario_id}.{role}.json", "bytes": size, "sha256": sha, "path_redacted": True}
        atol = -1.0 if scenario_id == "negative_atol" else 0.001 if scenario_id == "numeric_within_absolute_atol" else 0.0 if scenario_id == "numeric_and_nested_mismatch" else 1e-12
        if outcome == "matched": key = "success"
        elif scenario_id in {"numeric_and_nested_mismatch", "object_key_mismatch", "array_length_mismatch", "scalar_string_mismatch", "malformed_json", "negative_atol"}: key = scenario_id
        elif scenario_id in {"missing_golden", "missing_result"}: key = "missing"
        else: key = "invalid"
        observed = COM03_RESULT_CONTRACT[key]
        command = {"exit_code": observed[0], "stderr_category": observed[1], "stdout_bytes": observed[2], "stdout_sha256": observed[3]}
        scenarios.append({"id": scenario_id, "mode": mode, "atol": atol, "payloads": payloads, "oracle": command, "candidate": copy.deepcopy(command), "semantic_match": True, "outcome": outcome, "independent_payload_paths": True})
    files = ["tools/run_com_01_current_candidate.py", "tools/run_com_03_current_candidate.py", "tools/aggregate_com_03_current_candidate.py", "tools/verify_com_03_current_candidate.py", "tools/test_verify_com_03_current_candidate.py"]
    source = {"commit": "c" * 40, "tree": "d" * 40, "files": [{"path": path, "bytes": 1, "sha256": "e" * 64} for path in files], "shared_helper_schema": SHARED_HELPER_SCHEMA}
    return {"schema": "sipi.com-03.current-candidate-replay.v1", "status": "scoped_current_candidate_observed", "work_item": "COM-03", "leaf": "compare", "run_id": "d" * 64, "nonce": "e" * 64, "candidate": common["candidate"], "upstream": {key: value for key, value in common["upstream"].items() if key != "source"}, "toolchain": common["toolchain"], "harness": {"runner": "tools/run_com_03_current_candidate.py", "semantic_runner": "tools/run_com_03_direct_oracle.py", "result_schema": "sipi.com-03-direct-port-oracle.v2", "scenario_count": 23, "scenario_set_sha256": EXPECTED_SCENARIO_SET_SHA256, "independent_payload_paths": True, "same_crate_self_comparison": False, "report_policy": "bounded", "timeout_seconds": 30, "source": source, "shared_com01_helper": {"schema": SHARED_HELPER_SCHEMA, "path": files[0], "sha256": "e" * 64}}, "outcomes": {"error_match": 16, "matched": 7}, "scenario_count": 23, "semantic_match_count": 23, "scenarios": scenarios, "blockers": [], "matched": False, "acceptance": False, "non_claims": ["no_complete_com_parity"]}


class Com03PrepTests(unittest.TestCase):
    def test_reference_graph_and_shared_helper_are_exact(self):
        _validate_com03_report(prepared_report())

    def test_full_graph_mutations_fail(self):
        mutations = [
            lambda value: value.update(extra=True),
            lambda value: value["candidate"]["build"]["binary_post"].update(bytes=True),
            lambda value: value["toolchain"]["post"]["uv"].update(extra=True),
            lambda value: value["harness"]["shared_com01_helper"].update(sha256="0" * 64),
            lambda value: value["harness"]["source"]["files"][0].update(sha256="0" * 64),
            lambda value: value["scenarios"][0].update(mode="error"),
            lambda value: value["scenarios"][7].update(outcome="matched"),
            lambda value: value["scenarios"][0]["payloads"]["golden"].update(bytes=True),
            lambda value: value["scenarios"][0]["candidate"].update(extra=True),
            lambda value: (value["scenarios"][0]["candidate"].update(exit_code=3), value["scenarios"][0]["oracle"].update(exit_code=3)),
            lambda value: (value["scenarios"][0]["candidate"].update(stdout_sha256="0" * 64), value["scenarios"][0]["oracle"].update(stdout_sha256="0" * 64)),
            lambda value: (value["scenarios"][0]["candidate"].update(stderr_category="json_error"), value["scenarios"][0]["oracle"].update(stderr_category="json_error")),
            lambda value: value["scenarios"][0].update(atol=1),
            lambda value: value["scenarios"][0].update(atol=True),
        ]
        for mutate in mutations:
            value = prepared_report()
            mutate(value)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                _validate_com03_report(value)

    def test_receipt_mutations_hit_target_invariants(self):
        mutations = [
            (lambda build: (build["binary_pre"].update(nlink=True), build["binary_post"].update(nlink=True)), "COM-03 binary receipt drift"),
            (lambda build: (build["cargo_source_pre"].update(nlink=True), build["cargo_source_post"].update(nlink=True)), "COM-03 Cargo source receipt drift"),
            (lambda build: tuple(build[key].update(bytes=-1) for key in ("binary_pre", "binary_post", "cargo_source_pre", "cargo_source_post")), "COM-03 binary receipt drift"),
            (lambda build: (build["cargo_source_pre"].update(basename="forged.exe"), build["cargo_source_post"].update(basename="forged.exe")), "COM-03 Cargo source receipt drift"),
            (lambda build: tuple(build[key].update(basename="forged.exe") for key in ("binary_pre", "binary_post", "cargo_source_pre", "cargo_source_post")), "COM-03 binary receipt drift"),
            (lambda build: tuple(build[key].update(sha256="z" * 64) for key in ("binary_pre", "binary_post", "cargo_source_pre", "cargo_source_post")), "COM-03 binary receipt drift"),
        ]
        for mutate, error in mutations:
            value = prepared_report()
            mutate(value["candidate"]["build"])
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                _validate_com03_report(value)

    def test_build_environment_receipt_and_mutations(self):
        _validate_com03_report(prepared_report())
        mutations = [
            lambda environment: environment.pop("linker_forced"),
            lambda environment: environment.update(linker_forced=False),
            lambda environment: environment.update(cargo_cache_bound_pre_post=1),
        ]
        for mutate in mutations:
            value = prepared_report()
            mutate(value["candidate"]["build"]["environment"])
            with self.subTest(mutation=mutate), self.assertRaisesRegex(
                ValueError,
                "candidate.build.environment|COM-03 build environment policy drift",
            ):
                _validate_com03_report(value)

    def test_aggregate_rejects_cross_run_graph_drift(self):
        first = prepared_report()
        second = copy.deepcopy(first)
        second["run_id"] = "1" * 64
        second["nonce"] = "2" * 64
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            one, two = root / "one.json", root / "two.json"
            _atomic_json_create(one, first, output_root=root)
            _atomic_json_create(two, second, output_root=root)
            result = aggregate(one, two, root / "aggregate.json")
            self.assertEqual(result["fresh_replays"], 2)
            bad = copy.deepcopy(second)
            bad["scenarios"][0]["payloads"]["golden"]["sha256"] = "0" * 64
            bad_path = root / "bad.json"
            _atomic_json_create(bad_path, bad, output_root=root)
            with self.assertRaises(AggregateError):
                aggregate(one, bad_path, root / "blocked.json")


if __name__ == "__main__":
    unittest.main()
