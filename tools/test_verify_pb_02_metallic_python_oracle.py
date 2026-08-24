import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_pb_02_metallic_python_oracle as verifier  # noqa: E402
import aggregate_pb_02_metallic_python_oracle as aggregator  # noqa: E402
import pb_02_metallic_python_oracle as oracle  # noqa: E402
import run_pb_02_metallic_python_oracle as runner  # noqa: E402


FIELDS = verifier.EXPECTED_FIELDS


def _report(run_id: str, nonce: str) -> dict:
    summary = {"dtype": "float64", "shape": [2], "count": 2, "f64_sha256": "a" * 64}
    fields = [{"name": name, "candidate": summary, "oracle": summary, "max_abs": 0.0, "scale": 1.0, "tolerance": 1.0e-6, "passed": True} for name in FIELDS]
    ordinary = {
        "id": verifier.EXPECTED_CASES[0], "candidate_process": {"exit_code": 0}, "oracle_process": {"exit_code": 0},
        "candidate": {"schema": "pybert.native-cli-result.v1"}, "oracle": {"schema": "pybert.python-oracle-result.v1", "backend": "python", "source_command": "PythonSimulationBackend"},
        "status": "passed", "blockers": [], "payload": {"compared_field_count": 17, "equal": True, "fields": fields},
    }
    near = {
        "id": verifier.EXPECTED_CASES[1], "candidate_process": {"exit_code": 0}, "oracle_process": {"exit_code": 1},
        "candidate": {"schema": "pybert.native-cli-result.v1"},
        "oracle": {"schema": "pybert.python-oracle-result.v1", "backend": "python", "source_command": "PythonSimulationBackend", "diagnostics": {"failure_code": "pinned_channel_cubic_interp1d_two_point_boundary", "failure_stage": "channel"}},
        "status": "blocked", "blockers": ["pinned_channel_cubic_interp1d_two_point_boundary"], "payload": {"compared_field_count": 0, "equal": False, "fields": []},
    }
    return {
        "schema": "sipi.pb-02-metallic-python-oracle-replay.v1", "run_id": run_id, "fresh_run_nonce": nonce,
        "status": "blocked",
        "candidate": verifier.EXPECTED_CANDIDATE, "upstream": verifier.EXPECTED_UPSTREAM,
        "source_mode": verifier.EXPECTED_SOURCE_MODE,
        "claims": {"independent_python_payload_oracle": True, "ordinary_payload_parity": True, "near_integral_external_blocked": True, "near_integral_counted_as_parity": False, "global_branch_parity": False, "promotion": False},
        "corpus": {"path": aggregator.EXPECTED_CORPUS, "sha256": aggregator.EXPECTED_CORPUS_SHA256},
        "fixture": {"path": aggregator.EXPECTED_FIXTURE, "sha256": aggregator.EXPECTED_FIXTURE_SHA256, "archive_present": True, "source": "candidate_archive"},
        "harness": {role: {"path": path, "sha256": aggregator.EXPECTED_HARNESS_SHA256[role]} for role, path in aggregator.EXPECTED_HARNESS_PATHS.items()},
        "toolchain": {
            "timeout_seconds": 1800,
            "cargo": {"role": "cargo", "executable": "cargo", "path_redacted": True, "file_sha256": "a" * 64, "version_exit_code": 0, "version_output_sha256": "b" * 64},
            "rustc": {"role": "rustc", "executable": "rustc", "path_redacted": True, "file_sha256": "c" * 64, "version_exit_code": 0, "version_output_sha256": "d" * 64},
            "uv": {"role": "uv", "executable": "uv", "path_redacted": True, "file_sha256": "e" * 64, "version_exit_code": 0, "version_output_sha256": "f" * 64},
            "python": {"role": "python", "executable": "python", "path_redacted": True, "file_sha256": "1" * 64, "version_exit_code": 0, "version_output_sha256": "2" * 64},
            "child_python": {"command": "uv run --project <archive> --frozen python -c <identity>", "process": {"exit_code": 0}, "identity": {"python": {"executable": "python", "file_sha256": "3" * 64, "implementation": "CPython", "version": "3.12.0", "path_redacted": True}, "numpy": {"module": "numpy", "version": "2.0.0", "core_module": "numpy._core"}, "scipy": {"module": "scipy", "version": "1.14.0"}}},
            "host_python": {"executable": "python", "file_sha256": "4" * 64, "path_redacted": True, "source": "sys.executable"},
        },
        "build": {"exit_code": 0, "binary_sha256": "b" * 64, "stderr_sha256": "s" * 64, "environment_policy": {"rustc_wrapper_cleared": True, "rustc_workspace_wrapper_cleared": True, "cargo_build_rustc_wrapper_cleared": True}, "binary_custody": {"raw_sha256": "b" * 64, "canonical_sha256": "k" * 64, "format": "pe", "machine": "x64", "profile": "release", "normalization": {"fields": []}}},
        "cases": [ordinary, near],
    }


class VerifyPb02MetallicPythonOraclePrepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = verifier.prep_document()

    def test_prep_schema_is_valid_without_formal_manifest(self):
        result = verifier.verify_prep(copy.deepcopy(self.document))
        self.assertTrue(result["valid"], result)
        self.assertFalse(verifier.MANIFEST.exists() if hasattr(verifier, "MANIFEST") else False)

    def test_candidate_identity_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["candidate"]["commit"] = "0" * 40
        result = verifier.verify_prep(document)
        self.assertIn("candidate identity drift", result["blockers"])

    def test_near_integral_failure_policy_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["case_policy"]["metallic-ctle-near-integral-3ghz"]["oracle_failure_code"] = "python_fallback"
        result = verifier.verify_prep(document)
        self.assertIn("case policy contract drift", result["blockers"])

    def test_field_count_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["corpus"]["expected_fields"] = document["corpus"]["expected_fields"][:-1]
        result = verifier.verify_prep(document)
        self.assertIn("corpus field list drift", result["blockers"])

    def test_absolute_path_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["harness"]["tools/pb_02_metallic_python_oracle.py"]["path"] = "C:/tmp/oracle.py"
        result = verifier.verify_prep(document)
        self.assertIn("harness path drift", " ".join(result["blockers"]))

    def test_toolchain_and_build_contract_mutations_are_rejected(self):
        document = copy.deepcopy(self.document)
        document["toolchain_contract"]["path_redacted"] = False
        document["build_contract"]["archive_only"] = False
        result = verifier.verify_prep(document)
        self.assertIn("toolchain contract drift", result["blockers"])
        self.assertIn("build source mode drift", result["blockers"])

    def test_aggregator_roundtrip_and_duplicate_identity_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous_root = aggregator.ROOT
            aggregator.ROOT = root
            try:
                first = root / "run-a.json"
                second = root / "run-b.json"
                first.write_text(json.dumps(_report("run-a", "1" * 32), sort_keys=True), encoding="utf-8")
                second.write_text(json.dumps(_report("run-b", "2" * 32), sort_keys=True), encoding="utf-8")
                output = root / "aggregate.json"
                second_output = root / "aggregate-second.json"
                aggregator.aggregate([first, second], output)
                aggregator.aggregate([first, second], second_output)
                self.assertEqual(output.read_bytes(), second_output.read_bytes())
                with self.assertRaises(ValueError):
                    aggregator.aggregate([first, first], root / "duplicate.json")
                duplicate = _report("run-b", "1" * 32)
                second.write_text(json.dumps(duplicate, sort_keys=True), encoding="utf-8")
                with self.assertRaises(ValueError):
                    aggregator.aggregate([first, second], root / "duplicate-nonce.json")
            finally:
                aggregator.ROOT = previous_root

    def test_oracle_failure_artifact_is_structured_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaises(ValueError):
                oracle._failure_artifact(output, ValueError("The number of derivatives at boundaries does not match"))
            metadata = json.loads((output / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["diagnostics"]["failure_code"], "pinned_channel_cubic_interp1d_two_point_boundary")
            with self.assertRaises(ValueError):
                oracle._failure_artifact(output, ValueError("unexpected backend failure"))

    def test_aggregator_allows_raw_pe_drift_but_rejects_canonical_or_payload_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous_root = aggregator.ROOT
            aggregator.ROOT = root
            try:
                first = root / "run-a.json"
                second = root / "run-b.json"
                left = _report("run-a", "1" * 32)
                right = _report("run-b", "2" * 32)
                right["build"]["binary_sha256"] = "d" * 64
                right["build"]["binary_custody"]["raw_sha256"] = "d" * 64
                right["build"]["stderr_sha256"] = "t" * 64
                first.write_text(json.dumps(left, sort_keys=True), encoding="utf-8")
                second.write_text(json.dumps(right, sort_keys=True), encoding="utf-8")
                aggregator.aggregate([first, second], root / "raw-drift.json")
                right["build"]["binary_custody"]["canonical_sha256"] = "f" * 64
                second.write_text(json.dumps(right, sort_keys=True), encoding="utf-8")
                with self.assertRaises(ValueError):
                    aggregator.aggregate([first, second], root / "canonical-drift.json")
                right["build"]["binary_custody"]["canonical_sha256"] = "k" * 64
                right["cases"][0]["payload"]["fields"][0]["passed"] = False
                second.write_text(json.dumps(right, sort_keys=True), encoding="utf-8")
                with self.assertRaises(ValueError):
                    aggregator.aggregate([first, second], root / "payload-drift.json")
            finally:
                aggregator.ROOT = previous_root

    def test_aggregator_ignores_only_normalized_raw_hex_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous_root = aggregator.ROOT
            aggregator.ROOT = root
            first = root / "run-a.json"
            second = root / "run-b.json"
            left = _report("run-a", "1" * 32)
            right = _report("run-b", "2" * 32)
            left["build"]["binary_custody"]["normalization"] = {"ranges": [{"field": "timestamp", "raw_hex": "aa"}]}
            right["build"]["binary_custody"]["normalization"] = {"ranges": [{"field": "timestamp", "raw_hex": "bb"}]}
            first.write_text(json.dumps(left, sort_keys=True), encoding="utf-8")
            second.write_text(json.dumps(right, sort_keys=True), encoding="utf-8")
            try:
                aggregator.aggregate([first, second], root / "normalized-raw-drift.json")
            finally:
                aggregator.ROOT = previous_root

    def test_payload_summary_and_exact_near_policy_mutations_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left = _report("run-a", "1" * 32)
            right = _report("run-b", "2" * 32)
            right["cases"][0]["payload"]["fields"][0]["candidate"]["f64_sha256"] = "0" * 64
            first = root / "run-a.json"
            second = root / "run-b.json"
            first.write_text(json.dumps(left, sort_keys=True), encoding="utf-8")
            second.write_text(json.dumps(right, sort_keys=True), encoding="utf-8")
            with self.assertRaises(ValueError):
                aggregator.aggregate([first, second], root / "summary-drift.json")
            right = _report("run-b", "2" * 32)
            right["cases"][1]["payload"]["equal"] = True
            second.write_text(json.dumps(right, sort_keys=True), encoding="utf-8")
            with self.assertRaises(ValueError):
                aggregator.aggregate([first, second], root / "near-equal.json")

    def test_path_name_and_windowsapps_resolution_are_fail_closed(self):
        self.assertTrue(runner.is_oracle_command(["C:/archive/tools/pb_02_metallic_python_oracle.py"]))
        self.assertFalse(runner.is_oracle_command(["C:/archive/tools/pb_02_metallic_python_oracle.py.bak"]))
        resolved = runner.resolve_host_python("C:/Users/test/AppData/Local/Microsoft/WindowsApps/python.exe")
        self.assertTrue(resolved.is_file())
        self.assertNotIn("windowsapps", str(resolved).lower())

    def test_default_and_explicit_host_toolchain_phase_use_actual_python(self):
        default_host = runner.resolve_host_python(None)
        explicit_host = runner.resolve_host_python(str(default_host))
        for host in (default_host, explicit_host):
            report, paths = runner.resolve_toolchain_for_host(host, 30)
            self.assertIs(paths["python"], host)
            self.assertEqual(report["python"]["file_sha256"], runner.sha256(host))
            self.assertTrue(report["python"]["path_redacted"])

    def test_runner_main_default_arguments_smoke(self):
        captured = {}
        original = runner.run
        def fake_run(args):
            captured["args"] = args
            return {"status": "blocked", "run_id": args.run_id, "cases": []}
        runner.run = fake_run
        try:
            with tempfile.TemporaryDirectory() as directory:
                previous = sys.argv
                sys.argv = ["run_pb_02_metallic_python_oracle.py", "--output", str(Path(directory) / "report.json"), "--run-id", "smoke"]
                try:
                    self.assertEqual(runner.main(), 1)
                finally:
                    sys.argv = previous
        finally:
            runner.run = original
        self.assertEqual(captured["args"].candidate_commit, runner.CANDIDATE["commit"])
        self.assertIsNone(captured["args"].host_python)

    def test_aggregator_rejects_runner_failure_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous_root = aggregator.ROOT
            aggregator.ROOT = root
            try:
                left = _report("run-a", "1" * 32)
                right = _report("run-b", "2" * 32)
                right["cases"][0]["oracle_process"]["exit_code"] = 1
                first = root / "run-a.json"
                second = root / "run-b.json"
                first.write_text(json.dumps(left, sort_keys=True), encoding="utf-8")
                second.write_text(json.dumps(right, sort_keys=True), encoding="utf-8")
                with self.assertRaises(ValueError):
                    aggregator.aggregate([first, second], root / "runner-failure.json")
                right["cases"][0]["oracle_process"]["exit_code"] = 0
                right["claims"]["ordinary_payload_parity"] = False
                second.write_text(json.dumps(right, sort_keys=True), encoding="utf-8")
                with self.assertRaises(ValueError):
                    aggregator.aggregate([first, second], root / "claim-before-policy.json")
            finally:
                aggregator.ROOT = previous_root


if __name__ == "__main__":
    unittest.main()
