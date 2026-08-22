import copy
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import aggregate_as_01_fit_sparam_bound as aggregate
import run_as_01_fit_sparam_bound as runner


HEX = "a" * 64


def toolchain():
    identity = lambda role: {
        "role": role,
        "executable": f"{role}.exe",
        "path_redacted": True,
        "file_sha256": HEX,
        "version_exit_code": 0,
        "version_output_sha256": HEX,
    }
    return {
        "cargo": identity("cargo"),
        "rustc": identity("rustc"),
        "python": identity("python"),
        "uv": identity("uv"),
        "timeout_seconds": 10,
    }


def report(run_id: str, nonce: str):
    comparison = {
        "numeric_parity": False,
        "complete_contract_parity_claim": False,
        "numeric_mismatch_open": True,
        "acceptance_tolerance": None,
        "scenario_count": 1,
        "numeric_cases": ["fit"],
        "scenarios": [],
        "sha256": HEX,
    }
    return {
        "schema": runner.SCHEMA,
        "status": "completed_numeric_mismatch",
        "custody_valid": True,
        "parity_claim": False,
        "numeric_mismatch_open": True,
        "run_id": run_id,
        "fresh_run_nonce": nonce,
        "source_mode": "candidate_and_upstream_git_archive_at_immutable_commit",
        "harness_source_mode": "content_addressed_worktree_file_pending_owner_commit",
        "bound_runner": {"path": "tools/run.py", "sha256": HEX},
        "bound_oracle_lock": {"path": "lock.txt", "sha256": HEX},
        "candidate": {"commit": runner.EXPECTED_CANDIDATE_COMMIT, "tree": runner.EXPECTED_CANDIDATE_TREE},
        "upstream": {"commit": runner.EXPECTED_UPSTREAM_COMMIT, "tree": runner.EXPECTED_UPSTREAM_TREE},
        "archived_preparation_runner": {"path": "tools/run.py", "sha256": HEX},
        "scenario_set_sha256": HEX,
        "fixture_sha256": HEX,
        "toolchain": toolchain(),
        "oracle_environment": {
            "lock": {"path": "lock.txt", "bytes": 10, "sha256": HEX, "require_hashes": True},
            "venv": {"exit_code": 0},
            "sync": {"exit_code": 0},
            "runtime_python": {
                **toolchain()["python"],
                "role": "oracle_python",
            },
            "installed": {"distributions": [], "distribution_sha256": HEX, "numeric_config_sha256": HEX},
            "isolation": {
                "isolated_flag": "-I",
                "python_no_user_site": True,
                "python_path_cleared": True,
                "python_home_cleared": True,
                "virtual_env_cleared": True,
                "numeric_threads": 1,
            },
        },
        "build": {"exit_code": 0, "binary_present": True, "binary_sha256": HEX},
        "comparison": comparison,
    }


class As01BoundTests(unittest.TestCase):
    def test_run_id_is_path_free_and_bounded(self):
        self.assertIsNotNone(runner.RUN_ID.fullmatch("as01-bound-01"))
        self.assertIsNone(runner.RUN_ID.fullmatch("../escape"))
        self.assertIsNone(runner.RUN_ID.fullmatch(r"C:\\escape"))

    def test_archive_link_is_rejected(self):
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w:") as archive:
            member = tarfile.TarInfo("escape")
            member.type = tarfile.SYMTYPE
            member.linkname = "../outside"
            archive.addfile(member)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(RuntimeError):
                runner._extract_archive(payload.getvalue(), Path(temporary) / "archive")

    def test_aggregate_accepts_two_distinct_mismatch_reports(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.json"
            second = root / "second.json"
            output = root / "aggregate.json"
            first.write_text(json.dumps(report("run-1", "1" * 64)), encoding="utf-8")
            second.write_text(json.dumps(report("run-2", "2" * 64)), encoding="utf-8")
            document = aggregate.aggregate(first, second, output)
            self.assertEqual(document["status"], "completed_numeric_mismatch")
            self.assertEqual(document["blockers"], [])
            self.assertNotIn(str(root), output.read_text(encoding="utf-8"))

    def test_aggregate_rejects_source_drift_and_parity_overclaim(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_document = report("run-1", "1" * 64)
            second_document = report("run-2", "2" * 64)
            second_document["candidate"] = {"commit": "drift"}
            second_document["comparison"] = copy.deepcopy(second_document["comparison"])
            second_document["comparison"]["numeric_parity"] = True
            first = root / "first.json"
            second = root / "second.json"
            first.write_text(json.dumps(first_document), encoding="utf-8")
            second.write_text(json.dumps(second_document), encoding="utf-8")
            document = aggregate.aggregate(first, second, root / "aggregate.json")
            self.assertEqual(document["status"], "blocked")
            self.assertTrue(any("candidate drift" in item for item in document["blockers"]))
            self.assertTrue(any("overclaims parity" in item for item in document["blockers"]))

    def test_toolchain_rejects_paths_and_extra_keys(self):
        value = toolchain()
        value["python"]["executable"] = r"C:\Python\python.exe"
        self.assertFalse(aggregate._valid_toolchain(value))
        value = toolchain()
        value["cargo"]["path"] = r"C:\cargo.exe"
        self.assertFalse(aggregate._valid_toolchain(value))


if __name__ == "__main__":
    unittest.main()
