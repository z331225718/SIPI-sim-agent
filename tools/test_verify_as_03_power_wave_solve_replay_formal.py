"""Git-gate and mutation tests for the AS-03 formal verifier."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_as_03_power_wave_solve_replay_formal as formal
import test_verify_as_03_power_wave_solve_replay as stage1_test


ROOT = Path(__file__).resolve().parents[1]


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode("utf-8", "strict").strip()


def manifest_template() -> dict:
    digest = "a" * 64
    value = {
        "schema": "sipi.as-03-power-wave-solve-replay-formal.v1",
        "version": 1,
        "status": "blocked_numeric_semantics",
        "stage1_preparation": {"commit": formal.STAGE1_PREP_COMMIT, "tree": formal.STAGE1_PREP_TREE, "parent": formal.STAGE1_PREP_PARENT},
        "formal_gate": {
            "commit": "1" * 40,
            "tree": "2" * 40,
            "parent": formal.FORMAL_GATE_PARENT,
            "files": [{"path": path, "blob": "3" * 40, "sha256": digest, "bytes": 1} for path in formal.FORMAL_GATE_PATHS],
        },
        "evidence": {
            "reports": [{"path": path, "sha256": digest if index == 0 else "b" * 64, "bytes": 1} for index, path in enumerate(formal.REPORT_PATHS)],
            "aggregate": {"path": formal.AGGREGATE_PATH, "sha256": "c" * 64, "bytes": 1},
        },
        "audit_binding": {"path": formal.AUDIT_PATH, "sha256": "d" * 64, "bytes": 1, "normalized_manifest_sha256": "0" * 64},
        "claims": {key: False for key in formal.CLAIM_KEYS},
    }
    value["audit_binding"]["normalized_manifest_sha256"] = formal.normalized_manifest_sha256(value)
    return value


class FormalGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="as03-formal-gate-")
        self.repo = Path(self.temp.name) / "repo"
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", "-c", "core.autocrlf=false", str(ROOT), str(self.repo)], check=True)
        git(self.repo, "checkout", "--detach", "--quiet", formal.FORMAL_GATE_PARENT)
        git(self.repo, "config", "user.name", "AS03 Formal Test")
        git(self.repo, "config", "user.email", "as03-formal@example.invalid")
        for relative in formal.FORMAL_GATE_PATHS:
            destination = self.repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        git(self.repo, "add", "--", *formal.FORMAL_GATE_PATHS)
        git(self.repo, "commit", "--quiet", "-m", "test: AS03 formal gate")
        self.commit = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_exact_two_file_gate_binds_parent_tree_blob_raw_and_current(self) -> None:
        result = formal.verify_formal_gate(self.repo, self.commit)
        self.assertEqual(result["parent"], formal.FORMAL_GATE_PARENT)
        self.assertEqual(tuple(result["changed_paths"]), formal.FORMAL_GATE_PATHS)
        self.assertFalse(result["first_introduction"])
        self.assertTrue(result["original_gate_first_introduction"])
        self.assertTrue(result["formal_artifacts_absent"])
        self.assertTrue(all("current" in item for item in result["files"].values()))

    def test_extra_path_and_wrong_parent_are_rejected(self) -> None:
        (self.repo / "extra.txt").write_text("extra\n", encoding="ascii")
        git(self.repo, "add", "extra.txt")
        git(self.repo, "commit", "--amend", "--quiet", "--no-edit")
        with self.assertRaises(formal.FormalError):
            formal.verify_formal_gate(self.repo, "HEAD")
        with self.assertRaises(formal.FormalError):
            formal.verify_formal_gate(self.repo, formal.STAGE1_PREP_COMMIT)

    def test_formal_artifact_in_gate_is_rejected(self) -> None:
        artifact = self.repo / formal.REPORT_PATHS[0]
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("{}\n", encoding="ascii")
        git(self.repo, "add", "--", formal.REPORT_PATHS[0])
        git(self.repo, "commit", "--amend", "--quiet", "--no-edit")
        with self.assertRaises(formal.FormalError):
            formal.verify_formal_gate(self.repo, "HEAD")

    def test_live_file_drift_is_rejected(self) -> None:
        target = self.repo / formal.FORMAL_GATE_PATHS[0]
        target.write_bytes(target.read_bytes() + b"# drift\n")
        with self.assertRaises(formal.FormalError):
            formal.verify_formal_gate(self.repo, self.commit)

    def test_intervening_as_locked_path_drift_is_rejected(self) -> None:
        git(self.repo, "reset", "--hard", "--quiet", formal.STAGE1_PREP_COMMIT)
        locked = self.repo / formal.AS_LOCKED_PATHS[-1]
        locked.write_bytes(locked.read_bytes() + b"# drift\n")
        git(self.repo, "add", "--", formal.AS_LOCKED_PATHS[-1])
        git(self.repo, "commit", "--quiet", "-m", "drift locked AS source")
        drift_parent = git(self.repo, "rev-parse", "HEAD")
        for relative in formal.FORMAL_GATE_PATHS:
            destination = self.repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        git(self.repo, "add", "--", *formal.FORMAL_GATE_PATHS)
        git(self.repo, "commit", "--quiet", "-m", "formal after drift")
        with mock.patch.object(formal, "FORMAL_GATE_PARENT", drift_parent), self.assertRaises(formal.FormalError):
            formal.verify_formal_gate(self.repo, "HEAD")

    def test_wrong_fixed_parent_is_rejected(self) -> None:
        with mock.patch.object(formal, "FORMAL_GATE_PARENT", formal.STAGE1_PREP_PARENT), self.assertRaises(formal.FormalError):
            formal.verify_formal_gate(self.repo, self.commit)

    def test_read_rejects_mocked_reparse_root_and_parent(self) -> None:
        target = ROOT / formal.FORMAL_GATE_PATHS[0]
        for rejected in (ROOT.absolute(), target.parent.absolute()):
            original = formal.replay._is_reparse
            with self.subTest(rejected=rejected), mock.patch.object(
                formal.replay,
                "_is_reparse",
                side_effect=lambda path, rejected=rejected: path.absolute() == rejected or original(path),
            ), self.assertRaises(formal.FormalError):
                formal._read(ROOT, formal.FORMAL_GATE_PATHS[0])

    @unittest.skipUnless(sys.platform == "win32", "Windows junction custody")
    def test_read_rejects_real_root_and_parent_junctions(self) -> None:
        root = Path(self.temp.name) / "junction-source"
        nested = root / "nested"
        nested.mkdir(parents=True)
        (nested / "evidence.json").write_text("{}\n", encoding="ascii")

        for link, target, relative in (
            (Path(self.temp.name) / "root-junction", root, "nested/evidence.json"),
            (Path(self.temp.name) / "safe-root" / "nested", nested, "nested/evidence.json"),
        ):
            link.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode != 0:
                self.skipTest("junction creation is unavailable")
            try:
                with self.subTest(link=link), self.assertRaises(formal.FormalError):
                    formal._read(link if link.name == "root-junction" else link.parent, relative)
            finally:
                os.rmdir(link)


class FormalManifestTests(unittest.TestCase):
    def test_normalized_manifest_and_fixed_paths_are_accepted(self) -> None:
        value = manifest_template()
        self.assertIs(formal.validate_manifest_shape(value), value)

    def test_manifest_mutations_are_rejected(self) -> None:
        mutations = []
        value = manifest_template(); value["extra"] = True; mutations.append(value)
        value = manifest_template(); value["version"] = True; mutations.append(value)
        value = manifest_template(); value["status"] = "passed"; mutations.append(value)
        value = manifest_template(); value["formal_gate"]["parent"] = "0" * 40; mutations.append(value)
        value = manifest_template(); value["evidence"]["aggregate"]["path"] = "wrong.json"; mutations.append(value)
        value = manifest_template(); value["audit_binding"]["path"] = formal.FORMAL_GATE_PATHS[0]; mutations.append(value)
        value = manifest_template(); value["audit_binding"]["normalized_manifest_sha256"] = "f" * 64; mutations.append(value)
        value = manifest_template(); value["claims"]["numeric_parity"] = True; mutations.append(value)
        for value in mutations:
            with self.subTest(value=json.dumps(value, sort_keys=True)), self.assertRaises(formal.FormalError):
                formal.validate_manifest_shape(value)

    def test_nan_and_bool_lengths_are_rejected(self) -> None:
        value = manifest_template()
        value["audit_binding"]["bytes"] = float("nan")
        with self.assertRaises(formal.FormalError):
            formal.validate_manifest_shape(value)

    def test_strict_yaml_rejects_duplicate_keys_and_nonfinite_values(self) -> None:
        duplicate = b"schema: first\nschema: second\n"
        with self.assertRaises(formal.FormalError):
            formal._strict_yaml_load(duplicate)
        for value in (b"value: .nan\n", b"value: .inf\n", b"value: -.inf\n"):
            with self.subTest(value=value):
                loaded = formal._strict_yaml_load(value)
                with self.assertRaises(formal.FormalError):
                    formal._finite_tree(loaded)


class FormalBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="as03-formal-bundle-")
        root = Path(self.temp.name)
        self.repo = root / "repo"
        self.agent_repo = root / "agent-spice"
        self.skrf_repo = root / "scikit-rf"
        self.verify_temp = root / "verify-temp"
        for path in (self.agent_repo, self.skrf_repo, self.verify_temp):
            path.mkdir()
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", "-c", "core.autocrlf=false", str(ROOT), str(self.repo)], check=True)
        git(self.repo, "checkout", "--detach", "--quiet", formal.FORMAL_GATE_PARENT)
        git(self.repo, "config", "user.name", "AS03 Bundle Test")
        git(self.repo, "config", "user.email", "as03-bundle@example.invalid")
        for relative in formal.FORMAL_GATE_PATHS:
            destination = self.repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        git(self.repo, "add", "--", *formal.FORMAL_GATE_PATHS)
        git(self.repo, "commit", "--quiet", "-m", "test: AS03 formal gate")
        self.gate_commit = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_bundle(self, *, attack: bool = False, audit_extra: bool = False, extra_path: bool = False, old_gate: bool = False) -> None:
        first = stage1_test.report("formal-01", "a")
        second = stage1_test.report("formal-02", "b")
        for report in (first, second):
            report["prep"]["commit"] = formal.STAGE1_PREP_COMMIT
            report["prep"]["tree"] = formal.STAGE1_PREP_TREE
            if attack:
                report["claims"]["numeric_parity"] = True
                report["numeric_change"]["numeric_parity"] = True
        first_payload = stage1_test.payload(first)
        second_payload = stage1_test.payload(second)
        aggregate = stage1_test.aggregate(first, second, first_payload, second_payload)
        for index, path in enumerate(formal.REPORT_PATHS):
            aggregate["reports"][index]["basename"] = Path(path).name
        if attack:
            aggregate["claims"]["numeric_parity"] = True
            aggregate["numeric_change"]["numeric_parity"] = True
        aggregate_payload = stage1_test.payload(aggregate)
        payloads = (first_payload, second_payload)
        for relative, payload in zip(formal.REPORT_PATHS, payloads, strict=True):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        aggregate_target = self.repo / formal.AGGREGATE_PATH
        aggregate_target.parent.mkdir(parents=True, exist_ok=True)
        aggregate_target.write_bytes(aggregate_payload)
        gate = formal.verify_formal_gate(self.repo, self.gate_commit)
        manifest = manifest_template()
        manifest["formal_gate"].update({"commit": gate["commit"], "tree": gate["tree"], "parent": gate["parent"]})
        manifest["formal_gate"]["files"] = [{key: item[key] for key in ("path", "blob", "sha256", "bytes")} for item in gate["files"].values()]
        manifest["evidence"] = {
            "reports": [{"path": path, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)} for path, payload in zip(formal.REPORT_PATHS, payloads, strict=True)],
            "aggregate": {"path": formal.AGGREGATE_PATH, "sha256": hashlib.sha256(aggregate_payload).hexdigest(), "bytes": len(aggregate_payload)},
        }
        manifest["audit_binding"] = {"path": formal.AUDIT_PATH, "sha256": "0" * 64, "bytes": 1, "normalized_manifest_sha256": "0" * 64}
        if old_gate:
            manifest["formal_gate"].update({"commit": formal.ORIGINAL_GATE_COMMIT, "tree": formal.ORIGINAL_GATE_TREE, "parent": formal.FORMAL_GATE_PARENT})
        manifest["audit_binding"]["normalized_manifest_sha256"] = formal.normalized_manifest_sha256(manifest)
        binding = {
            "normalized_manifest_sha256": manifest["audit_binding"]["normalized_manifest_sha256"],
            "reports": [item["sha256"] for item in manifest["evidence"]["reports"]],
            "aggregate": manifest["evidence"]["aggregate"]["sha256"],
            "stage1_prep_commit": formal.STAGE1_PREP_COMMIT,
            "formal_gate_commit": manifest["formal_gate"]["commit"],
        }
        audit_payload = formal._audit_payload(binding) + (b"release_acceptance: true\n" if audit_extra else b"")
        manifest["audit_binding"].update({"sha256": hashlib.sha256(audit_payload).hexdigest(), "bytes": len(audit_payload)})
        manifest_target = self.repo / formal.MANIFEST_PATH
        manifest_target.parent.mkdir(parents=True, exist_ok=True)
        manifest_target.write_text(yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8", newline="\n")
        audit_target = self.repo / formal.AUDIT_PATH
        audit_target.parent.mkdir(parents=True, exist_ok=True)
        audit_target.write_bytes(audit_payload)
        paths = list(formal.FORMAL_ARTIFACT_PATHS)
        if extra_path:
            (self.repo / "extra.txt").write_text("extra\n", encoding="ascii")
            paths.append("extra.txt")
        git(self.repo, "add", "--", *paths)
        git(self.repo, "commit", "--quiet", "-m", "test: AS03 formal record")

    def _verify(self) -> dict:
        def verify_disjoint(repo: Path, agent: Path, skrf: Path, prep: str, evidence: Path, first: Path, second: Path, aggregate: Path, git_value: str, temp: Path) -> dict:
            formal.replay._require_disjoint_roots({"repository": repo, "agent": agent, "skrf": skrf, "evidence": evidence, "temp": temp})
            self.assertEqual(prep, formal.STAGE1_PREP_COMMIT)
            self.assertEqual(git_value, "git")
            self.assertEqual(evidence.parent, temp.parent)
            self.assertEqual({item.name for item in evidence.iterdir()}, {first.name, second.name, aggregate.name})
            for path in (first, second, aggregate):
                formal.replay._read_regular(path, formal.replay.MAX_REPORT_BYTES)
            return {"status": "valid"}

        with mock.patch.object(formal.stage1_verify, "verify_files", side_effect=verify_disjoint):
            return formal.verify_formal_bundle(self.repo, formal.MANIFEST_PATH, self.agent_repo, self.skrf_repo, self.verify_temp)

    def test_complete_future_bundle_valid_baseline(self) -> None:
        self._write_bundle()
        self.assertTrue(self._verify()["valid"])
        self.assertEqual(list(self.verify_temp.iterdir()), [])

    def test_exact_audit_rejects_extra_promotion_claim(self) -> None:
        self._write_bundle(audit_extra=True)
        with self.assertRaises(formal.FormalError):
            self._verify()

    def test_coordinated_report_aggregate_and_audit_promotion_is_rejected(self) -> None:
        self._write_bundle(attack=True)
        with self.assertRaises((ValueError, formal.FormalError)):
            self._verify()

    def test_record_custody_rejects_gate_head_untracked_extra_and_raw_live_drift(self) -> None:
        with self.assertRaises(formal.FormalError):
            formal.verify_record_commit(self.repo, self.gate_commit)
        self._write_bundle()
        untracked = self.repo / "untracked.txt"
        untracked.write_text("untracked\n", encoding="ascii")
        with self.assertRaises(formal.FormalError):
            formal.verify_record_commit(self.repo, self.gate_commit)
        untracked.unlink()
        report = self.repo / formal.REPORT_PATHS[0]
        report.write_bytes(report.read_bytes() + b" ")
        with self.assertRaises(formal.FormalError):
            formal.verify_record_commit(self.repo, self.gate_commit)

    def test_record_custody_rejects_extra_path_and_non_gate_parent(self) -> None:
        self._write_bundle(extra_path=True)
        with self.assertRaises(formal.FormalError):
            formal.verify_record_commit(self.repo, self.gate_commit)
        with self.assertRaises(formal.FormalError):
            formal.verify_record_commit(self.repo, formal.STAGE1_PREP_COMMIT)

    def test_record_pointing_to_original_gate_is_rejected(self) -> None:
        self._write_bundle(old_gate=True)
        with self.assertRaises(formal.FormalError):
            self._verify()

    def test_bridge_rejects_overlapping_root_and_cleans_after_stage1_failure(self) -> None:
        self._write_bundle()
        with mock.patch.object(formal.stage1_verify, "verify_files", side_effect=RuntimeError("forced Stage1 failure")):
            with self.assertRaises(RuntimeError):
                formal.verify_formal_bundle(self.repo, formal.MANIFEST_PATH, self.agent_repo, self.skrf_repo, self.verify_temp)
        self.assertEqual(list(self.verify_temp.iterdir()), [])
        with self.assertRaises(RuntimeError):
            formal._verify_stage1_through_external_bridge(self.repo, self.agent_repo, self.skrf_repo, self.repo, [], b"")

    def test_bridge_cleans_after_exclusive_write_failure(self) -> None:
        self._write_bundle()
        original = formal.replay._create_file
        calls = 0

        def fail_second(path: Path, payload: bytes, maximum: int) -> dict:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("forced exclusive write failure")
            return original(path, payload, maximum)

        with mock.patch.object(formal.replay, "_create_file", side_effect=fail_second), self.assertRaises(RuntimeError):
            formal.verify_formal_bundle(self.repo, formal.MANIFEST_PATH, self.agent_repo, self.skrf_repo, self.verify_temp)
        self.assertEqual(list(self.verify_temp.iterdir()), [])

    def test_bridge_exact_files_reject_extra_and_hardlink(self) -> None:
        bridge = self.verify_temp / "bridge"
        bridge.mkdir()
        (bridge / "expected").write_bytes(b"data")
        (bridge / "extra").write_bytes(b"extra")
        with self.assertRaises(formal.FormalError):
            formal._bridge_receipts(bridge, ("expected",))
        (bridge / "extra").unlink()
        hardlink = bridge / "hardlink"
        os.link(bridge / "expected", hardlink)
        with self.assertRaises(RuntimeError):
            formal._bridge_receipts(bridge, ("expected", "hardlink"))
        hardlink.unlink()

    def test_bridge_rejects_symlink_when_available(self) -> None:
        bridge = self.verify_temp / "bridge-symlink"
        bridge.mkdir()
        (bridge / "expected").write_bytes(b"data")
        symlink = bridge / "symlink"
        try:
            symlink.symlink_to(bridge / "expected")
        except OSError:
            return
        with self.assertRaises(formal.FormalError):
            formal._bridge_receipts(bridge, ("expected", "symlink"))

    def test_manifest_rejects_bool_byte_count(self) -> None:
        value = manifest_template()
        value["evidence"]["reports"][0]["bytes"] = True
        with self.assertRaises(formal.FormalError):
            formal.validate_manifest_shape(value)


if __name__ == "__main__":
    unittest.main()
