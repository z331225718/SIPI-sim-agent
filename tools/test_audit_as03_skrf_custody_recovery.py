from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_as03_skrf_custody_recovery as audit


class As03ScikitRfCustodyRecoveryTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _write_sources(self, root: Path, source_bytes: dict[str, bytes]) -> None:
        for relative, payload in source_bytes.items():
            path = root / Path(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)

    def _source_constants(self, source_bytes: dict[str, bytes]) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for relative, payload in source_bytes.items():
            result[relative] = {
                "blob": audit._git_blob_sha1(payload),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        return result

    def _write_distribution(self, root: Path, source_bytes: dict[str, bytes], *, record: bool = True) -> None:
        self._write_sources(root, source_bytes)
        dist = root / audit.DIST_INFO
        dist.mkdir(parents=True, exist_ok=True)
        (dist / "METADATA").write_text("Metadata-Version: 2.4\nName: scikit-rf\nVersion: 2.0.1\n", encoding="utf-8")
        rows = []
        for relative, payload in source_bytes.items():
            encoded = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode("ascii").rstrip("=")
            rows.append(f"{relative},sha256={encoded},{len(payload)}")
        rows.append(f"{audit.DIST_INFO}/METADATA,,")
        if record:
            (dist / "RECORD").write_text("\n".join(rows) + "\n", encoding="utf-8")

    def test_extracted_source_leaves_match_but_git_custody_is_missing(self) -> None:
        source_bytes = {relative: f"source:{relative}".encode("ascii") for relative in audit.PINNED_SOURCES}
        expected = self._source_constants(source_bytes)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "site-packages"
            self._write_distribution(root, source_bytes)
            with mock.patch.object(audit, "PINNED_SOURCES", expected):
                result = audit.audit([root])
        self.assertEqual(result["status"], "partial_wheel_source_match_git_custody_missing")
        self.assertFalse(result["assessment"]["complete_git_custody"])
        self.assertTrue(result["assessment"]["scoped_source_leaf_bytes_available"])
        self.assertFalse(result["assessment"]["offline_immutable_git_oracle"])
        self.assertEqual(len(result["package_trees"]), 1)

    def test_exact_git_commit_tree_and_leaves_are_reported(self) -> None:
        source_bytes = {relative: f"source:{relative}".encode("ascii") for relative in audit.PINNED_SOURCES}
        expected = self._source_constants(source_bytes)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            self._git(root, "init", "--quiet")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "AS03 test")
            self._write_sources(root, source_bytes)
            self._git(root, "add", "--", *source_bytes)
            self._git(root, "commit", "--quiet", "-m", "pinned source")
            commit = self._git(root, "rev-parse", "HEAD")
            tree = self._git(root, "rev-parse", "HEAD^{tree}")
            with mock.patch.multiple(audit, PINNED_COMMIT=commit, PINNED_TREE=tree, PINNED_SOURCES=expected):
                result = audit.audit([root])
        self.assertEqual(result["status"], "exact_pinned_git_custody_found")
        self.assertTrue(result["assessment"]["complete_git_custody"])
        self.assertTrue(result["assessment"]["offline_immutable_git_oracle"])
        self.assertEqual(result["git_repositories"][0]["source_leaves_match"], True)

    def test_record_digest_mismatch_does_not_hide_source_match(self) -> None:
        source_bytes = {relative: f"source:{relative}".encode("ascii") for relative in audit.PINNED_SOURCES}
        expected = self._source_constants(source_bytes)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "site-packages"
            self._write_distribution(root, source_bytes)
            record = root / audit.DIST_INFO / "RECORD"
            record.write_text(record.read_text(encoding="utf-8").replace("," + str(len(source_bytes["skrf/network.py"])) + "\n", ",0\n"), encoding="utf-8")
            with mock.patch.object(audit, "PINNED_SOURCES", expected):
                package = audit.package_inventory(root)
        self.assertTrue(package["all_source_leaves_match"])
        self.assertFalse(package["record_all_source_rows_match"])

    def test_wheel_archive_and_uv_http_metadata_are_only_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scikit_rf-2.0.1-py3-none-any.whl").write_bytes(b"not unpacked")
            cache = root / "scikit-rf"
            cache.mkdir()
            (cache / "2.0.1-py3-none-any.http").write_bytes(b"Sha256 abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789")
            (root / "other" ).mkdir()
            (root / "other" / "2.0.1-py3-none-any.http").write_bytes(b"not scikit-rf")
            found = audit.find_wheel_archives([root])
        self.assertEqual(len(found), 2)
        self.assertEqual({item["kind"] for item in found}, {"wheel_archive", "uv_http_cache_metadata"})

    def test_git_object_scan_records_pinned_blob_presence(self) -> None:
        source_bytes = {relative: f"source:{relative}".encode("ascii") for relative in audit.PINNED_SOURCES}
        expected = self._source_constants(source_bytes)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            self._git(root, "init", "--quiet")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "AS03 test")
            self._write_sources(root, source_bytes)
            self._git(root, "add", "--", *source_bytes)
            self._git(root, "commit", "--quiet", "-m", "pinned source")
            commit = self._git(root, "rev-parse", "HEAD")
            tree = self._git(root, "rev-parse", "HEAD^{tree}")
            with mock.patch.multiple(audit, PINNED_COMMIT=commit, PINNED_TREE=tree, PINNED_SOURCES=expected):
                inventory = audit.git_inventory(root)
        self.assertTrue(inventory["all_objects"]["pinned_object_presence"]["commit"])
        self.assertTrue(inventory["all_objects"]["pinned_object_presence"]["tree"])
        for relative in source_bytes:
            self.assertTrue(inventory["all_objects"]["pinned_object_presence"][f"blob:{relative}"])


if __name__ == "__main__":
    unittest.main()
