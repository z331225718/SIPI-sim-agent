from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-artifacts" / "src"))

from sipi_artifacts import ArtifactIntegrityError, ArtifactStoreError, AttemptStore, DagNodeRecordStore, NodeRecordAlreadyExists, SuccessMarkerAlreadyExists, SuccessMarkerRejected
from sipi_contracts import parse_dag_node_record, parse_run_record


def artifact(relative_path: str, contents: bytes) -> dict:
    return {
        "schema": "sipi.artifact-ref.v1", "content_schema": "fixture.output.v1",
        "relative_path": relative_path, "mime_type": "application/octet-stream",
        "sha256": hashlib.sha256(contents).hexdigest(), "byte_length": len(contents),
        "producer": "fixture.adapter", "role": "domain_result", "extensions": {},
    }


def record(*, status: str = "succeeded", artifacts: list[dict]) -> object:
    error = None if status == "succeeded" else {
        "category": "Cancelled" if status == "cancelled" else "ExternalModelFailure",
        "message": "fixture failure", "resource": None, "cause": None, "details": {},
    }
    return parse_run_record({
        "schema": "sipi.run-record.v1", "run_id": "run-1", "analysis_id": "analysis-1",
        "attempt_id": "attempt-1", "status": status, "operation": "link.simulate.v1",
        "payload_schema": "fixture.input.v1", "artifacts": artifacts, "error": error, "extensions": {},
    })


def blocked_node() -> object:
    return parse_dag_node_record({
        "schema": "sipi.dag-node-record.v1", "run_id": "run-1", "analysis_id": "analysis-2",
        "status": "blocked", "blocked_by": [{"analysis_id": "analysis-1", "terminal_status": "failed"}], "extensions": {},
    })


class AttemptStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.staging = self.root / "staging"
        self.publish = self.root / "publish"
        self.staging.mkdir()
        self.publish.mkdir()
        self.attempt = self.staging / "attempt-1"
        self.attempt.mkdir()
        self.store = AttemptStore(self.staging, self.publish)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write(self, relative_path: str, contents: bytes) -> dict:
        path = self.attempt.joinpath(*relative_path.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return artifact(relative_path, contents)

    def test_success_materializes_checksums_and_installs_only_final_marker(self):
        reference = self._write("backends/one/result.bin", b"result")
        prepared = self.store.prepare_attempt("attempt-1", record(artifacts=[reference]))
        materialized = self.store.materialize(prepared, "run-1/analysis-1/attempt-1")
        self.assertFalse((materialized.attempt_dir / "success-manifest.json").exists())
        self.assertEqual((materialized.attempt_dir / reference["relative_path"]).read_bytes(), b"result")
        checksums = json.loads((materialized.attempt_dir / "checksums.json").read_text())
        self.assertEqual([entry["relative_path"] for entry in checksums["files"]], ["backends/one/result.bin", "run-record.json"])
        installed = self.store.install_success_marker(materialized)
        self.assertEqual(installed.manifest["attempt_id"], "attempt-1")
        self.assertTrue((materialized.attempt_dir / "success-manifest.json").is_file())

    def test_non_successful_attempt_writes_record_but_cannot_publish_success(self):
        reference = self._write("diagnostics/error.bin", b"diagnostic")
        for status in ("failed", "cancelled"):
            with self.subTest(status=status):
                prepared = self.store.prepare_attempt("attempt-1", record(status=status, artifacts=[reference]))
                materialized = self.store.materialize(prepared, f"run-1/analysis-1/{status}")
                self.assertTrue((materialized.attempt_dir / "run-record.json").is_file())
                self.assertFalse((materialized.attempt_dir / "checksums.json").exists())
                with self.assertRaises(SuccessMarkerRejected):
                    self.store.install_success_marker(materialized)

    def test_tampered_or_symlinked_staging_artifact_is_rejected_without_marker(self):
        reference = self._write("backends/one/result.bin", b"original")
        prepared = self.store.prepare_attempt("attempt-1", record(artifacts=[reference]))
        (self.attempt / "backends" / "one" / "result.bin").write_bytes(b"tampered")
        with self.assertRaises(ArtifactIntegrityError):
            self.store.materialize(prepared, "run-1/analysis-1/attempt-1")
        destination = self.publish / "run-1" / "analysis-1" / "attempt-1"
        self.assertFalse((destination / "success-manifest.json").exists())

        link_target = self.root / "outside.bin"
        link_target.write_bytes(b"linked")
        link = self.attempt / "backends" / "one" / "linked.bin"
        try:
            link.symlink_to(link_target)
        except OSError:
            self.skipTest("symlink creation is unavailable")
        with self.assertRaises(ArtifactIntegrityError):
            self.store.prepare_attempt("attempt-1", record(artifacts=[artifact("backends/one/linked.bin", b"linked")]))

    def test_materialized_tampering_prevents_marker_installation(self):
        reference = self._write("backends/one/result.bin", b"result")
        prepared = self.store.prepare_attempt("attempt-1", record(artifacts=[reference]))
        materialized = self.store.materialize(prepared, "run-1/analysis-1/attempt-1")
        (materialized.attempt_dir / reference["relative_path"]).write_bytes(b"changed")
        with self.assertRaises(ArtifactIntegrityError):
            self.store.install_success_marker(materialized)
        self.assertFalse((materialized.attempt_dir / "success-manifest.json").exists())

    def test_handles_are_revalidated_against_store_roots_and_canonical_marker_bytes(self):
        reference = self._write("backends/one/result.bin", b"result")
        prepared = self.store.prepare_attempt("attempt-1", record(artifacts=[reference]))
        outside = self.root / "outside"
        outside.mkdir()
        with self.assertRaises(ArtifactStoreError):
            self.store.materialize(replace(prepared, staging_dir=outside), "run-1/analysis-1/forged")

        materialized = self.store.materialize(prepared, "run-1/analysis-1/attempt-1")
        other_staging = self.root / "other-staging"
        other_publish = self.root / "other-publish"
        other_staging.mkdir()
        other_publish.mkdir()
        other_store = AttemptStore(other_staging, other_publish)
        with self.assertRaises(ArtifactStoreError):
            other_store.install_success_marker(materialized)

        forged = replace(materialized, marker_bytes=b"not-json\n")
        self.store.install_success_marker(forged)
        self.assertEqual((materialized.attempt_dir / "success-manifest.json").read_bytes(), materialized.marker_bytes)

    def test_run_record_is_absent_when_its_atomic_write_fails(self):
        reference = self._write("backends/one/result.bin", b"result")
        prepared = self.store.prepare_attempt("attempt-1", record(artifacts=[reference]))

        def fail_after_partial_write(path: Path, contents: bytes) -> None:
            path.write_bytes(contents[:4])
            raise OSError("disk full")

        with patch("sipi_artifacts.store._write_new_file", side_effect=fail_after_partial_write):
            with self.assertRaises(OSError):
                self.store.materialize(prepared, "run-1/analysis-1/attempt-1")
        attempt_dir = self.publish / "run-1" / "analysis-1" / "attempt-1"
        self.assertFalse((attempt_dir / "run-record.json").exists())

    def test_copy_failure_leaves_no_marker_and_does_not_mutate_staging(self):
        first = self._write("backends/one/a.bin", b"a")
        second = self._write("backends/one/b.bin", b"b")
        prepared = self.store.prepare_attempt("attempt-1", record(artifacts=[first, second]))
        with patch("sipi_artifacts.store.shutil.copyfileobj", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.store.materialize(prepared, "run-1/analysis-1/attempt-1")
        self.assertEqual((self.attempt / "backends" / "one" / "a.bin").read_bytes(), b"a")
        self.assertFalse((self.publish / "run-1" / "analysis-1" / "attempt-1" / "success-manifest.json").exists())

    def test_concurrent_marker_installers_do_not_overwrite(self):
        reference = self._write("backends/one/result.bin", b"result")
        prepared = self.store.prepare_attempt("attempt-1", record(artifacts=[reference]))
        materialized = self.store.materialize(prepared, "run-1/analysis-1/attempt-1")
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(self._install_result, [materialized, materialized]))
        self.assertEqual(results.count("installed"), 1)
        self.assertEqual(results.count("exists"), 1)
        self.assertEqual((materialized.attempt_dir / "success-manifest.json").read_bytes(), materialized.marker_bytes)

    def _install_result(self, materialized) -> str:
        try:
            self.store.install_success_marker(materialized)
            return "installed"
        except SuccessMarkerAlreadyExists:
            return "exists"


class DagNodeRecordStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.publish = self.root / "publish"
        self.publish.mkdir()
        self.store = DagNodeRecordStore(self.publish)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_blocked_node_record_is_atomic_and_never_overwritten(self):
        record = blocked_node()
        installed = self.store.install_blocked("run-1/nodes/analysis-2", record)
        path = installed.node_dir / "dag-node-record.json"
        self.assertTrue(path.is_file())
        original = path.read_bytes()
        with self.assertRaises(NodeRecordAlreadyExists):
            self.store.install_blocked("run-1/nodes/analysis-2", record)
        self.assertEqual(path.read_bytes(), original)

    def test_blocked_node_store_rejects_escape_and_atomic_write_failure(self):
        record = blocked_node()
        with self.assertRaises(ArtifactStoreError):
            self.store.install_blocked("../escape", record)

        def fail_after_partial_write(path: Path, contents: bytes) -> None:
            path.write_bytes(contents[:4])
            raise OSError("disk full")

        with patch("sipi_artifacts.store._write_new_file", side_effect=fail_after_partial_write):
            with self.assertRaises(OSError):
                self.store.install_blocked("run-1/nodes/analysis-2", record)
        self.assertFalse((self.publish / "run-1" / "nodes" / "analysis-2" / "dag-node-record.json").exists())


if __name__ == "__main__":
    unittest.main()
