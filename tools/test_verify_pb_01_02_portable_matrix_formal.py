"""Git-gate and mutation tests for the PB matrix formal verifier."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import yaml

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify_pb_01_02_portable_matrix_formal as formal  # noqa: E402
from aggregate_pb_01_02_portable_matrix import aggregate_documents  # noqa: E402
from test_verify_pb_01_02_portable_matrix import report as stage1_report  # noqa: E402
from verify_pb_01_02_portable_matrix import VerifyError, _physical_source, _read, verify_preparation  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode("utf-8", "strict").strip()


def manifest_template() -> dict:
    digest = "a" * 64
    value = {
        "schema": "sipi.pb-01-02-portable-matrix-formal.v1",
        "version": 1,
        "status": "scoped_matrix_blocked",
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
        self.temp = tempfile.TemporaryDirectory(prefix="pb-formal-gate-")
        self.repo = Path(self.temp.name) / "repo"
        subprocess.run(["git", "-c", "core.autocrlf=false", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(self.repo)], check=True)
        git(self.repo, "config", "core.autocrlf", "false")
        git(self.repo, "checkout", "--detach", "--quiet", formal.FORMAL_GATE_PARENT)
        git(self.repo, "config", "user.name", "PB Formal Test")
        git(self.repo, "config", "user.email", "pb-formal@example.invalid")
        for relative in formal.FORMAL_GATE_PATHS:
            destination = self.repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        git(self.repo, "add", "--", *formal.FORMAL_GATE_PATHS)
        git(self.repo, "commit", "--quiet", "-m", "test: formal gate")
        self.commit = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_exact_two_file_gate_binds_parent_tree_blob_raw_and_current(self) -> None:
        result = formal.verify_formal_gate(self.repo, self.commit)
        self.assertEqual(result["parent"], formal.FORMAL_GATE_PARENT)
        self.assertTrue(result["stage1_ancestor"])
        self.assertTrue(result["protected_paths_unchanged"])
        self.assertEqual(tuple(result["changed_paths"]), formal.FORMAL_GATE_PATHS)
        self.assertTrue(result["first_introduction"])
        self.assertTrue(result["formal_artifacts_absent"])
        self.assertTrue(all("current" in item for item in result["files"].values()))

    def test_extra_path_and_wrong_parent_are_rejected(self) -> None:
        (self.repo / "extra.txt").write_text("extra\n", encoding="utf-8")
        git(self.repo, "add", "extra.txt")
        git(self.repo, "commit", "--amend", "--quiet", "--no-edit")
        with self.assertRaises(VerifyError):
            formal.verify_formal_gate(self.repo, "HEAD")
        with self.assertRaises(VerifyError):
            formal.verify_formal_gate(self.repo, formal.STAGE1_PREP_COMMIT)

    def test_formal_artifact_in_gate_is_rejected(self) -> None:
        artifact = self.repo / formal.REPORT_PATHS[0]
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("{}\n", encoding="utf-8")
        git(self.repo, "add", "--", formal.REPORT_PATHS[0])
        git(self.repo, "commit", "--amend", "--quiet", "--no-edit")
        with self.assertRaises(VerifyError):
            formal.verify_formal_gate(self.repo, "HEAD")

    def test_stage1_ancestor_harness_and_crate_drift_are_rejected(self) -> None:
        scenarios = (
            (formal.STAGE1_PREP_PARENT, None),
            (formal.STAGE1_PREP_COMMIT, "docs/baselines/pb-01-02-portable-matrix-inputs.v1.json"),
            (formal.STAGE1_PREP_COMMIT, "crates/sipi-pybert-direct/Cargo.toml"),
        )
        for base, drift_path in scenarios:
            with self.subTest(base=base, drift_path=drift_path), tempfile.TemporaryDirectory(prefix="pb-formal-drift-") as directory:
                repo = Path(directory) / "repo"
                subprocess.run(["git", "-c", "core.autocrlf=false", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(repo)], check=True)
                git(repo, "config", "core.autocrlf", "false")
                git(repo, "checkout", "--detach", "--quiet", base)
                git(repo, "config", "user.name", "PB Drift Test")
                git(repo, "config", "user.email", "pb-drift@example.invalid")
                if drift_path is not None:
                    target = repo / drift_path
                    target.write_bytes(target.read_bytes() + b"\n")
                    git(repo, "add", "--", drift_path)
                    git(repo, "commit", "--quiet", "-m", "test: protected drift")
                parent = git(repo, "rev-parse", "HEAD")
                for relative in formal.FORMAL_GATE_PATHS:
                    destination = repo / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / relative, destination)
                git(repo, "add", "--", *formal.FORMAL_GATE_PATHS)
                git(repo, "commit", "--quiet", "-m", "test: formal gate after drift")
                with mock.patch.object(formal, "FORMAL_GATE_PARENT", parent), self.assertRaises(VerifyError):
                    formal.verify_formal_gate(repo, "HEAD")

    def _write_valid_bundle(self) -> tuple[Path, dict, dict, dict]:
        stage1 = verify_preparation(self.repo, formal.STAGE1_PREP_COMMIT, formal.STAGE1_PREP_PARENT, require_live=False)
        gate = formal.verify_formal_gate(self.repo, self.commit)
        candidate_source = _physical_source(self.repo, formal.STAGE1_PREP_COMMIT)
        upstream_repo = Path(r"C:\Users\z3312\code\Py-bert-agent")
        upstream_source = _physical_source(upstream_repo, "5bf6d7ea0ace261891aaeb611ffc1c267e160afe")

        def make_report(run_id: str, nonce: str) -> dict:
            value = stage1_report(run_id, nonce)
            value["preparation"].update({"commit": formal.STAGE1_PREP_COMMIT, "tree": formal.STAGE1_PREP_TREE, "parent": formal.STAGE1_PREP_PARENT})
            for path, actual in stage1["files"].items():
                bound = value["preparation"]["files"][path]
                bound.update({key: actual[key] for key in ("blob", "sha256", "bytes")})
                for live_key in ("live_pre", "live_post"):
                    bound[live_key]["sha256"] = actual["sha256"]
                    bound[live_key]["bytes"] = actual["bytes"]
                    bound[live_key]["pre_identity"][2] = actual["bytes"]
                    bound[live_key]["post_identity"][2] = actual["bytes"]
            corpus = stage1["files"]["docs/baselines/pb-01-02-portable-matrix-inputs.v1.json"]
            value["corpus"].update({"blob": corpus["blob"], "sha256": corpus["sha256"], "bytes": corpus["bytes"]})
            for role, physical in (("candidate", candidate_source), ("upstream", upstream_source)):
                source = value["source"][role]
                source.update({"commit": physical["commit"], "tree": physical["tree"], "archive_sha256": physical["archive_sha256"], "inventory_pre_sha256": physical["inventory_sha256"], "inventory_post_sha256": physical["inventory_sha256"]})
            value["oracle_runtime"]["oracle_work_archive_sha256"] = upstream_source["archive_sha256"]
            for item in value["custody"]["archive_materialization"]:
                digest = candidate_source["archive_sha256"] if item["role"] == "candidate" else upstream_source["archive_sha256"]
                item["archive_sha256"] = digest
                item["fact"]["sha256"] = digest
            return value

        reports = [make_report("formal-run-01", "a" * 64), make_report("formal-run-02", "b" * 64)]
        report_facts = []
        for path, value in zip(formal.REPORT_PATHS, reports):
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            _, fact = _read(self.repo, path)
            report_facts.append(fact)
        aggregate = {**aggregate_documents(*reports), "report_files": report_facts}
        aggregate_target = self.repo / formal.AGGREGATE_PATH
        aggregate_target.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _, aggregate_fact = _read(self.repo, formal.AGGREGATE_PATH)
        manifest = manifest_template()
        manifest["status"] = aggregate["status"]
        manifest["formal_gate"].update({"commit": gate["commit"], "tree": gate["tree"], "parent": gate["parent"]})
        manifest["formal_gate"]["files"] = [{key: gate["files"][path][key] for key in ("path", "blob", "sha256", "bytes")} for path in formal.FORMAL_GATE_PATHS]
        manifest["evidence"] = {"reports": [{"path": path, "sha256": fact["sha256"], "bytes": fact["bytes"]} for path, fact in zip(formal.REPORT_PATHS, report_facts)], "aggregate": {"path": formal.AGGREGATE_PATH, "sha256": aggregate_fact["sha256"], "bytes": aggregate_fact["bytes"]}}
        manifest["audit_binding"] = {"path": formal.AUDIT_PATH, "sha256": "0" * 64, "bytes": 1, "normalized_manifest_sha256": "0" * 64}
        manifest["audit_binding"]["normalized_manifest_sha256"] = formal.normalized_manifest_sha256(manifest)
        binding = {"normalized_manifest_sha256": manifest["audit_binding"]["normalized_manifest_sha256"], "reports": [item["sha256"] for item in manifest["evidence"]["reports"]], "aggregate": aggregate_fact["sha256"], "stage1_prep_commit": formal.STAGE1_PREP_COMMIT, "formal_gate_commit": gate["commit"]}
        audit = {"schema": "sipi.pb-01-02-portable-matrix-audit.v1", "marker": formal.AUDIT_MARKER, "status": manifest["status"], "binding": binding, "claims": copy.deepcopy(manifest["claims"]), "non_claims": list(formal.NON_CLAIMS)}
        audit_target = self.repo / formal.AUDIT_PATH
        audit_target.parent.mkdir(parents=True, exist_ok=True)
        audit_target.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _, audit_fact = _read(self.repo, formal.AUDIT_PATH)
        manifest["audit_binding"].update({"sha256": audit_fact["sha256"], "bytes": audit_fact["bytes"]})
        manifest_target = self.repo / formal.MANIFEST_PATH
        manifest_target.write_text(yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8")
        self._commit_record()
        return manifest_target, reports[0], aggregate, audit

    def _commit_record(self) -> None:
        git(self.repo, "add", "--", *formal.FORMAL_ARTIFACT_PATHS)
        if git(self.repo, "rev-parse", "HEAD") == self.commit:
            git(self.repo, "commit", "--quiet", "-m", "test: formal record")
        else:
            git(self.repo, "commit", "--amend", "--quiet", "--no-edit")
        status = git(self.repo, "status", "--porcelain=v1", "--untracked-files=all")
        self.assertEqual(status, "", status)

    def _rewrite_audit_and_manifest(self, manifest: dict, mutate_audit=None) -> Path:
        manifest["audit_binding"]["normalized_manifest_sha256"] = formal.normalized_manifest_sha256(manifest)
        binding = {"normalized_manifest_sha256": manifest["audit_binding"]["normalized_manifest_sha256"], "reports": [item["sha256"] for item in manifest["evidence"]["reports"]], "aggregate": manifest["evidence"]["aggregate"]["sha256"], "stage1_prep_commit": formal.STAGE1_PREP_COMMIT, "formal_gate_commit": manifest["formal_gate"]["commit"]}
        audit = {"schema": "sipi.pb-01-02-portable-matrix-audit.v1", "marker": formal.AUDIT_MARKER, "status": manifest["status"], "binding": binding, "claims": copy.deepcopy(manifest["claims"]), "non_claims": list(formal.NON_CLAIMS)}
        if mutate_audit is not None:
            mutate_audit(audit)
        audit_path = self.repo / formal.AUDIT_PATH
        audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _, audit_fact = _read(self.repo, formal.AUDIT_PATH)
        manifest["audit_binding"].update({"sha256": audit_fact["sha256"], "bytes": audit_fact["bytes"]})
        manifest_path = self.repo / formal.MANIFEST_PATH
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8")
        return manifest_path

    def _rewrite_reports_and_mechanical_aggregate(self, manifest: dict, reports: list[dict]) -> None:
        facts = []
        for path, value in zip(formal.REPORT_PATHS, reports):
            (self.repo / path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            _, fact = _read(self.repo, path)
            facts.append(fact)
        aggregate = {**aggregate_documents(*reports), "report_files": facts}
        (self.repo / formal.AGGREGATE_PATH).write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _, aggregate_fact = _read(self.repo, formal.AGGREGATE_PATH)
        manifest["evidence"] = {"reports": [{"path": path, "sha256": fact["sha256"], "bytes": fact["bytes"]} for path, fact in zip(formal.REPORT_PATHS, facts)], "aggregate": {"path": formal.AGGREGATE_PATH, "sha256": aggregate_fact["sha256"], "bytes": aggregate_fact["bytes"]}}

    def test_future_complete_bundle_valid_baseline(self) -> None:
        manifest, _, _, _ = self._write_valid_bundle()
        result = formal.verify_formal_bundle(self.repo, formal.MANIFEST_PATH, Path(r"C:\Users\z3312\code\Py-bert-agent"))
        self.assertTrue(result["valid"])
        self.assertEqual(result["fresh_replays"], 2)

    def test_record_gate_rejects_head_gate_nonparent_untracked_extra_and_raw_live_drift(self) -> None:
        with self.assertRaises(VerifyError):
            formal.verify_record_gate(self.repo, self.commit)
        self._write_valid_bundle()
        formal.verify_record_gate(self.repo, self.commit)
        with self.assertRaises(VerifyError):
            formal.verify_record_gate(self.repo, formal.STAGE1_PREP_COMMIT)
        untracked = self.repo / "untracked.txt"
        untracked.write_text("untracked\n", encoding="utf-8")
        with self.assertRaises(VerifyError):
            formal.verify_record_gate(self.repo, self.commit)
        untracked.unlink()
        report = self.repo / formal.REPORT_PATHS[0]
        original = report.read_bytes()
        report.write_bytes(original + b" ")
        with self.assertRaises(VerifyError):
            formal.verify_record_gate(self.repo, self.commit)
        report.write_bytes(original)
        extra = self.repo / "extra-record.txt"
        extra.write_text("extra\n", encoding="utf-8")
        git(self.repo, "add", "extra-record.txt")
        git(self.repo, "commit", "--amend", "--quiet", "--no-edit")
        with self.assertRaises(VerifyError):
            formal.verify_record_gate(self.repo, self.commit)

    def test_future_bundle_coordinated_forges_are_rejected(self) -> None:
        manifest, _, _, _ = self._write_valid_bundle()
        manifest_value = yaml.safe_load(manifest.read_bytes())
        report_path = self.repo / formal.REPORT_PATHS[0]
        report = json.loads(report_path.read_bytes())
        report["run_nonce"] = "c" * 64
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
        _, report_fact = _read(self.repo, formal.REPORT_PATHS[0])
        manifest_value["evidence"]["reports"][0].update({"sha256": report_fact["sha256"], "bytes": report_fact["bytes"]})
        manifest_value["audit_binding"]["normalized_manifest_sha256"] = formal.normalized_manifest_sha256(manifest_value)
        manifest.write_text(yaml.safe_dump(manifest_value, sort_keys=True), encoding="utf-8")
        self._commit_record()
        with self.assertRaises(VerifyError):
            formal.verify_formal_bundle(self.repo, formal.MANIFEST_PATH, Path(r"C:\Users\z3312\code\Py-bert-agent"))

    def test_future_source_forge_with_rebuilt_hash_aggregate_and_audit_is_rejected(self) -> None:
        manifest_path, _, _, _ = self._write_valid_bundle()
        manifest = yaml.safe_load(manifest_path.read_bytes())
        reports = [json.loads((self.repo / path).read_bytes()) for path in formal.REPORT_PATHS]
        for report in reports:
            report["source"]["candidate"]["archive_sha256"] = "f" * 64
            binding = next(item for item in report["custody"]["archive_materialization"] if item["role"] == "candidate")
            binding["archive_sha256"] = "f" * 64
            binding["fact"]["sha256"] = "f" * 64
        self._rewrite_reports_and_mechanical_aggregate(manifest, reports)
        self._rewrite_audit_and_manifest(manifest)
        self._commit_record()
        with self.assertRaises(VerifyError):
            formal.verify_formal_bundle(self.repo, formal.MANIFEST_PATH, Path(r"C:\Users\z3312\code\Py-bert-agent"))

    def test_future_mechanical_aggregate_forge_with_rebound_audit_is_rejected(self) -> None:
        manifest_path, _, _, _ = self._write_valid_bundle()
        manifest = yaml.safe_load(manifest_path.read_bytes())
        aggregate_path = self.repo / formal.AGGREGATE_PATH
        aggregate = json.loads(aggregate_path.read_bytes())
        aggregate["cases"][0]["observation_equal"] = False
        aggregate_path.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _, fact = _read(self.repo, formal.AGGREGATE_PATH)
        manifest["evidence"]["aggregate"].update({"sha256": fact["sha256"], "bytes": fact["bytes"]})
        self._rewrite_audit_and_manifest(manifest)
        self._commit_record()
        with self.assertRaises(VerifyError):
            formal.verify_formal_bundle(self.repo, formal.MANIFEST_PATH, Path(r"C:\Users\z3312\code\Py-bert-agent"))

    def test_future_audit_promotion_and_swap_are_rejected(self) -> None:
        manifest, _, _, _ = self._write_valid_bundle()
        audit_path = self.repo / formal.AUDIT_PATH
        audit = json.loads(audit_path.read_bytes())
        audit["claims"]["release_acceptance"] = True
        audit_path.write_text(json.dumps(audit, sort_keys=True), encoding="utf-8")
        manifest_value = yaml.safe_load(manifest.read_bytes())
        _, audit_fact = _read(self.repo, formal.AUDIT_PATH)
        manifest_value["audit_binding"].update({"sha256": audit_fact["sha256"], "bytes": audit_fact["bytes"]})
        manifest.write_text(yaml.safe_dump(manifest_value, sort_keys=True), encoding="utf-8")
        self._commit_record()
        with self.assertRaises(VerifyError):
            formal.verify_formal_bundle(self.repo, formal.MANIFEST_PATH, Path(r"C:\Users\z3312\code\Py-bert-agent"))

    def test_future_audit_report_swap_and_manifest_claim_promotion_are_rejected(self) -> None:
        manifest_path, _, _, _ = self._write_valid_bundle()
        manifest = yaml.safe_load(manifest_path.read_bytes())
        self._rewrite_audit_and_manifest(manifest, lambda audit: audit["binding"]["reports"].reverse())
        self._commit_record()
        with self.assertRaises(VerifyError):
            formal.verify_formal_bundle(self.repo, formal.MANIFEST_PATH, Path(r"C:\Users\z3312\code\Py-bert-agent"))
        manifest_path, _, _, _ = self._write_valid_bundle()
        manifest = yaml.safe_load(manifest_path.read_bytes())
        manifest["claims"]["release_acceptance"] = True
        self._rewrite_audit_and_manifest(manifest)
        self._commit_record()
        with self.assertRaises(VerifyError):
            formal.verify_formal_bundle(self.repo, formal.MANIFEST_PATH, Path(r"C:\Users\z3312\code\Py-bert-agent"))


class FormalManifestTests(unittest.TestCase):
    def test_normalized_manifest_and_fixed_paths_are_accepted(self) -> None:
        value = manifest_template()
        self.assertIs(formal.validate_manifest_shape(value), value)

    def test_manifest_extra_bool_claim_path_and_digest_drift_are_rejected(self) -> None:
        mutations = []
        value = manifest_template(); value["extra"] = True; mutations.append(value)
        value = manifest_template(); value["version"] = True; mutations.append(value)
        value = manifest_template(); value["claims"]["numeric_parity"] = True; mutations.append(value)
        value = manifest_template(); value["evidence"]["aggregate"]["path"] = "wrong.json"; mutations.append(value)
        value = manifest_template(); value["audit_binding"]["normalized_manifest_sha256"] = "f" * 64; mutations.append(value)
        for value in mutations:
            with self.subTest(value=json.dumps(value, sort_keys=True)), self.assertRaises(VerifyError):
                formal.validate_manifest_shape(value)

    def test_nan_manifest_value_is_rejected(self) -> None:
        value = manifest_template()
        value["audit_binding"]["bytes"] = float("nan")
        with self.assertRaises(VerifyError):
            formal.validate_manifest_shape(value)

    def test_duplicate_yaml_key_is_rejected(self) -> None:
        with self.assertRaises(VerifyError):
            yaml.load("schema: one\nschema: two\n", Loader=formal._StrictLoader)


if __name__ == "__main__":
    unittest.main()
