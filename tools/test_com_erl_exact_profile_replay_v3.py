import json
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from com_erl_exact_profile_replay_v3_support import path_free
from com_erl_exact_profile_replay_v3_support import tool_identity
from run_com_erl_exact_profile_replay_v3 import (
    FIXTURE_BYTES,
    FIXTURE_RELATIVE,
    FIXTURE_ROWS,
    FIXTURE_SHA256,
    PROFILE,
    OUTER_CONTROLS,
    RUNTIME_TIMEOUT_S,
    candidate_probe,
    canonical_config,
    upstream_command,
)
from com_erl_exact_profile_replay_v3_support import archive_materialize
from verify_com_erl_exact_profile_replay_v3 import VerificationError, verify_aggregate, verify_manifest, verify_stage
import pb_03_replay_common as pe_common
from test_pb_replay_common import ReplayCommonTests
import verify_com_erl_exact_profile_replay_v3 as verifier_module

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/com-erl-exact-profile-replay-v3.manifest.json"

class ComErlExactProfilePrepTests(unittest.TestCase):
    def test_fixture_identity_and_shape(self):
        fixture = ROOT / FIXTURE_RELATIVE
        raw = fixture.read_bytes()
        self.assertEqual(len(raw), FIXTURE_BYTES)
        self.assertEqual(__import__("hashlib").sha256(raw).hexdigest(), FIXTURE_SHA256)
        self.assertEqual(sum(1 for line in raw.decode("ascii").splitlines() if line.strip() and not line.lstrip().startswith(("!", "#"))), FIXTURE_ROWS)

    def test_config_contains_exact_outer_and_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            canonical_config(path)
            document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(set(document["portable"]["erl_only"]), set(OUTER_CONTROLS) | {"tdr_profile"})
        self.assertEqual(document["portable"]["erl_only"]["tdr_profile"], PROFILE)

    def test_timeout_is_bounded_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("run_com_erl_exact_profile_replay_v3.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(["candidate"], RUNTIME_TIMEOUT_S)):
                result = candidate_probe(Path(directory) / "candidate.exe", Path(directory) / "config.json", Path(directory) / "fixture.s2p", Path(directory) / "out")
        self.assertEqual(result, {"status": "timeout", "timeout_s": RUNTIME_TIMEOUT_S})

    def test_tool_nonzero_is_not_admitted(self):
        class Completed:
            returncode = 7
            stdout = b""
            stderr = b"tool drift"
        with tempfile.TemporaryDirectory() as directory:
            tool = Path(directory) / "tool.exe"
            tool.write_bytes(b"tool")
            with mock.patch("subprocess.run", return_value=Completed()):
                identity = tool_identity(tool, 15)
        self.assertEqual(identity["status"], "failed")
        self.assertNotEqual(identity["version_exit"], 0)

    def test_upstream_uses_resolved_uv_and_python(self):
        command = upstream_command(Path("C:/resolved/uv.exe"), Path("C:/resolved/python.exe"), "probe")
        self.assertEqual(command[0:2], [str(Path("C:/resolved/uv.exe")), "run"])
        self.assertEqual(command[command.index("--python") + 1], str(Path("C:/resolved/python.exe")))

    def test_git_archive_timeout_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["git"], 900)):
                with self.assertRaises(RuntimeError):
                    archive_materialize(Path("git.exe"), Path(directory), "commit", Path(directory) / "archive", "0" * 64)

    def test_stage_bypass_is_rejected(self):
        with self.assertRaises(VerificationError):
            verify_stage({"count": 1, "sha256": "0" * 63 + "G"})
        with self.assertRaises(VerificationError):
            verify_stage({"count": 0, "sha256": "0" * 64})

    def test_forged_aggregate_is_rejected(self):
        with self.assertRaises(VerificationError):
            verify_aggregate({"schema": "sipi.com.erl-only.exact-profile-replay.v3.aggregate"}, json.loads(MANIFEST.read_text(encoding="utf-8")), [Path("run1.json"), Path("run2.json")])

    def test_pe_raw_drift_with_same_canonical_passes_and_canonical_drift_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "first.exe"
            second_path = Path(directory) / "second.exe"
            ReplayCommonTests._write_pe(first_path)
            ReplayCommonTests._write_pe(second_path, timestamp=0x87654321, guid=b"fedcba9876543210")
            first = pe_common.windows_pe_replay_custody(first_path)
            second = pe_common.windows_pe_replay_custody(second_path)
            self.assertNotEqual(first["raw_sha256"], second["raw_sha256"])
            self.assertEqual(pe_common.compare_windows_pe_custody(first, second), [])
            mutated = bytearray(second_path.read_bytes())
            mutated[0x450] ^= 1
            second_path.write_bytes(mutated)
            changed = pe_common.windows_pe_replay_custody(second_path)
            self.assertTrue(pe_common.compare_windows_pe_custody(first, changed))

    def test_verify_aggregate_enforces_pe_custody_cross_run(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "first.exe"
            second_path = Path(directory) / "second.exe"
            ReplayCommonTests._write_pe(first_path)
            ReplayCommonTests._write_pe(second_path, timestamp=0x87654321, guid=b"fedcba9876543210")
            first_custody = pe_common.windows_pe_replay_custody(first_path)
            second_custody = pe_common.windows_pe_replay_custody(second_path)
            reports = []
            report_paths = [Path("docs/baselines/com-erl-v3-test-run1.json"), Path("docs/baselines/com-erl-v3-test-run2.json")]
            for index, custody in enumerate((first_custody, second_custody), 1):
                reports.append({
                    "schema": "sipi.com.erl-only.exact-profile-replay.v3",
                    "run_id": f"com-erl-exact-v3-run{index}",
                    "fresh_run_nonce": f"{index:064x}",
                    "candidate": {"commit": manifest["candidate"]["commit"], "tree": manifest["candidate"]["tree"], "archive_sha256": manifest["candidate"]["archive_sha256"], "materialization": "git archive; no working-tree overlay", "runtime_executed": True, "cargo_lock_sha256": "1" * 64, "binary_sha256": custody["raw_sha256"], "binary_custody": custody},
                    "upstream": manifest["upstream"],
                    "input": {"fixture_sha256": manifest["fixture"]["sha256"], "fixture_bytes": manifest["fixture"]["bytes"], "fixture_rows": manifest["fixture"]["rows"], "controls": manifest["controls"]},
                    "parity": {"status": "numeric_mismatch_open"},
                })
                path = report_paths[index - 1]
                path.write_text(json.dumps(reports[-1], sort_keys=True), encoding="utf-8")
            scoped_manifest = json.loads(json.dumps(manifest))
            scoped_manifest["reports"]["paths"] = [path.as_posix() for path in report_paths]
            aggregate = {
                "schema": "sipi.com.erl-only.exact-profile-replay.v3.aggregate",
                "status": "bound_clean_archive_observation",
                "fresh_runs": 2,
                "reports": [{"path": path.as_posix(), "sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest(), "run_id": report["run_id"], "nonce": report["fresh_run_nonce"]} for path, report in zip(report_paths, reports, strict=True)],
                "candidate": {key: reports[0]["candidate"][key] for key in ("commit", "tree", "archive_sha256", "materialization", "runtime_executed", "cargo_lock_sha256")},
                "upstream": manifest["upstream"],
                "fixture": manifest["fixture"],
                "controls": manifest["controls"],
                "stage_mapping": manifest["stage_mapping"],
                "toolchain_exact_equal": True,
                "binary_custody": [first_custody, second_custody],
                "parity": {"status": "open_until_numeric_and_stage_match", "run_statuses": ["numeric_mismatch_open", "numeric_mismatch_open"]},
                "non_claims": ["no_release_or_promotion", "no_global_migration_row_close"],
            }
            with mock.patch.object(verifier_module, "verify_report"):
                verifier_module.verify_aggregate(aggregate, scoped_manifest, report_paths)
                mutated = json.loads(json.dumps(aggregate))
                drift_report = json.loads(json.dumps(reports[1]))
                drift_report["candidate"]["binary_custody"]["canonical_sha256"] = "0" * 64
                report_paths[1].write_text(json.dumps(drift_report, sort_keys=True), encoding="utf-8")
                mutated["reports"][1]["sha256"] = __import__("hashlib").sha256(report_paths[1].read_bytes()).hexdigest()
                mutated["binary_custody"][1] = drift_report["candidate"]["binary_custody"]
                with self.assertRaises(VerificationError):
                    verifier_module.verify_aggregate(mutated, scoped_manifest, report_paths)
            for path in report_paths:
                path.unlink(missing_ok=True)

    def test_path_policy_rejects_absolute_forms(self):
        for value in ("/tmp/report.json", "C:/report.json", "C:\\report.json", "\\\\server\\share"):
            self.assertFalse(path_free(value))
        self.assertTrue(path_free("docs/baselines/report.json"))

    def test_manifest_schema_gate_and_mutations(self):
        document = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(verify_manifest(document)["schema"], document["schema"])
        mutations = [
            ("fixture", {"sha256": "0" * 64}),
            ("runtime", {"timeout_s": 15}),
            ("stage_mapping", {"ptdr_gated": {}}),
            ("candidate", {"commit": "0" * 40}),
            ("runner", {"path": "/opt/overlay.py"}),
            ("runtime", {"rustc_workspace_wrapper": "ccache"}),
        ]
        for key, value in mutations:
            mutated = json.loads(json.dumps(document))
            if key == "stage_mapping":
                mutated[key] = value
            else:
                mutated[key].update(value)
            with self.assertRaises(VerificationError):
                verify_manifest(mutated)

if __name__ == "__main__":
    unittest.main()
