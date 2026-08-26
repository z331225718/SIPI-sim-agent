"""Mutation tests for the PB-01/02/03 current scoped replay verifier."""

from __future__ import annotations

import json
import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify_pb_01_03_current_scoped_replay as verifier


ROOT = verifier.ROOT


class CurrentScopedReplayVerifierTests(unittest.TestCase):
    def _bundle(self) -> tuple[Path, Path]:
        temp = Path(tempfile.mkdtemp(prefix="pb-current-scoped-"))
        source_manifest = verifier.MANIFEST
        manifest = yaml.safe_load(source_manifest.read_text(encoding="utf-8"))
        paths = [manifest["evidence"]["audit"], manifest["evidence"]["verifier"]["path"], manifest["evidence"]["mutation_tests"]["path"]]
        paths.extend(binding["path"] for binding in manifest["evidence"]["replay_runners"])
        for row in manifest["rows"]:
            paths.extend(binding["path"] for binding in row["reports"])
        for relative in paths:
            source = ROOT / relative
            target = temp / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        manifest_target = temp / source_manifest.relative_to(ROOT)
        manifest_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_manifest, manifest_target)
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        return temp, manifest_target

    @staticmethod
    def _write_manifest(path: Path, document: dict) -> None:
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8", newline="\n")

    @staticmethod
    def _report_path(root: Path, manifest: dict, row_index: int = 0, report_index: int = 0) -> Path:
        return root / manifest["rows"][row_index]["reports"][report_index]["path"]

    @staticmethod
    def _refresh_report_binding(root: Path, document: dict, row_index: int, report_index: int) -> None:
        report_path = CurrentScopedReplayVerifierTests._report_path(root, document, row_index, report_index)
        digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
        document["rows"][row_index]["reports"][report_index]["sha256"] = digest

    def test_baseline_is_valid(self) -> None:
        root, manifest = self._bundle()
        result = verifier.verify(manifest, root)
        self.assertTrue(result["valid"], result["errors"])

    def test_manifest_schema_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["schema"] = "sipi.invalid"
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_manifest_status_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["status"] = "release_ready"
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_manifest_extra_release_flag_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["release_ready"] = True
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_manifest_source_commit_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["scope"]["candidate_commit"] = "0" * 40
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_manifest_claim_boundary_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["claims"]["nested_output_parity"] = True
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_manifest_row_set_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["rows"][2]["id"] = "PB-99"
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_manifest_report_path_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["rows"][0]["reports"][0]["path"] = "C:/host/report.json"
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_report_digest_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["rows"][0]["reports"][0]["sha256"] = "0" * 64
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_report_run_id_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        report_path = self._report_path(root, document)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["run_id"] = "reused-run"
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8", newline="\n")
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_report_nonce_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        report_path = self._report_path(root, document, row_index=2)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["fresh_run_nonce"] = "not-a-nonce"
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8", newline="\n")
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_report_absolute_path_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        report_path = self._report_path(root, document, row_index=1)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["fixture"]["path"] = r"C:\Users\attacker\fixture.json"
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8", newline="\n")
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_pb01_dictionary_schema_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        report_path = self._report_path(root, document)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["replay"]["candidate_artifact_schema"]["item_names"] = ["wrong"]
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8", newline="\n")
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_pb01_selected_array_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        report_path = self._report_path(root, document)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["replay"]["comparison"]["arrays"][0]["passed"] = False
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8", newline="\n")
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_pb02_member_digest_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        report_path = self._report_path(root, document, row_index=1)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["replay"]["candidate"]["artifacts"]["arrays"]["logical_sha256"] = "0" * 64
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8", newline="\n")
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_pb02_member_set_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        report_path = self._report_path(root, document, row_index=1)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["replay"]["parity"]["array_member_names"] = report["replay"]["parity"]["array_member_names"][:-1]
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8", newline="\n")
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_pb03_total_count_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        report_path = self._report_path(root, document, row_index=2)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["replay"]["candidate_artifact"]["arrays"]["logical_member_count"] = 150
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8", newline="\n")
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_pb03_whole_payload_claim_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["rows"][2]["artifact"]["whole_payload_parity"] = True
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_audit_digest_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["evidence"]["audit_sha256"] = "0" * 64
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_audit_content_and_manifest_digest_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        audit_path = root / document["evidence"]["audit"]
        audit_path.write_text(audit_path.read_text(encoding="utf-8") + "\nRelease ready\n", encoding="utf-8", newline="\n")
        document["evidence"]["audit_sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_verifier_physical_append_and_manifest_digest_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        verifier_path = root / document["evidence"]["verifier"]["path"]
        verifier_path.write_text(verifier_path.read_text(encoding="utf-8") + "\n# coordinated physical verifier mutation\n", encoding="utf-8", newline="\n")
        document["evidence"]["verifier"]["sha256"] = hashlib.sha256(verifier_path.read_bytes()).hexdigest()
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_mutation_test_physical_append_and_manifest_digest_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        mutation_path = root / document["evidence"]["mutation_tests"]["path"]
        mutation_path.write_text(mutation_path.read_text(encoding="utf-8") + "\n# coordinated physical mutation-test mutation\n", encoding="utf-8", newline="\n")
        document["evidence"]["mutation_tests"]["sha256"] = hashlib.sha256(mutation_path.read_bytes()).hexdigest()
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_pb02_claim_promotion_and_report_digest_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        report_path = self._report_path(root, document, row_index=1, report_index=0)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["claims"] = {"global_row_closed": True, "release_approval": True}
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8", newline="\n")
        self._refresh_report_binding(root, document, 1, 0)
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_pb03_build_failure_and_report_digest_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        report_path = self._report_path(root, document, row_index=2, report_index=0)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["build"]["exit_code"] = 1
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8", newline="\n")
        self._refresh_report_binding(root, document, 2, 0)
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_pb03_python_identity_pair_mutation_and_report_digests_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for report_index in (0, 1):
            report_path = self._report_path(root, document, row_index=2, report_index=report_index)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["toolchain"]["python"]["file_sha256"] = "0" * 64
            report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8", newline="\n")
            self._refresh_report_binding(root, document, 2, report_index)
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_pb01_inventory_pair_mutation_and_report_digests_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for report_index in (0, 1):
            report_path = self._report_path(root, document, row_index=0, report_index=report_index)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["candidate"]["inventory"]["entries"] = []
            report["candidate"]["inventory"]["sha256"] = "0" * 64
            report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8", newline="\n")
            self._refresh_report_binding(root, document, 0, report_index)
        self._write_manifest(path, document)
        self.assertFalse(verifier.verify(path, root)["valid"])

    def test_toolchain_identity_mutation_is_rejected(self) -> None:
        root, path = self._bundle()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        report_path = self._report_path(root, document, row_index=1)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["toolchain"]["cargo"]["path_redacted"] = False
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8", newline="\n")
        self.assertFalse(verifier.verify(path, root)["valid"])


if __name__ == "__main__":
    unittest.main()
