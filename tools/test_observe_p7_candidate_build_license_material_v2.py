"""Unit tests for the P7 Cargo license-material observer."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p7_license_material_v2", ROOT / "tools" / "observe_p7_candidate_build_license_material_v2.py"
)
assert SPEC and SPEC.loader
OBSERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OBSERVER)


class CandidateBuildLicenseMaterialTests(unittest.TestCase):
    def test_compiler_artifact_requires_and_binds_manifest_path(self) -> None:
        message = {
            "reason": "compiler-artifact", "package_id": "registry+https://example.invalid#demo@1.2.3",
            "manifest_path": "C:/registry/src/index/demo-1.2.3/Cargo.toml",
        }
        completed = mock.Mock(stdout=json.dumps(message).encode("utf-8") + b"\n", stderr=b"")
        with mock.patch.object(OBSERVER, "_run", return_value=completed):
            artifacts, _ = OBSERVER._cargo_build_artifacts("cargo", Path("C:/source"), Path("C:/target"))
        self.assertEqual(artifacts[message["package_id"]], Path(message["manifest_path"]))
        del message["manifest_path"]
        completed = mock.Mock(stdout=json.dumps(message).encode("utf-8") + b"\n", stderr=b"")
        with mock.patch.object(OBSERVER, "_run", return_value=completed):
            with self.assertRaisesRegex(OBSERVER.ObservationError, "cargo_message_invalid"):
                OBSERVER._cargo_build_artifacts("cargo", Path("C:/source"), Path("C:/target"))

    def test_workspace_inherited_license_is_not_a_license_conclusion(self) -> None:
        manifest = b"[package]\nname = 'demo'\nversion = '1.2.3'\nlicense.workspace = true\n"
        self.assertEqual(OBSERVER._literal_license(manifest), (None, None))

    def test_workspace_inherited_version_uses_candidate_workspace_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Cargo.toml").write_text("[workspace.package]\nversion = '1.2.3'\n", encoding="utf-8")
            manifest_path = root / "crates" / "demo" / "Cargo.toml"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                "[package]\nname = 'demo'\nversion.workspace = true\nlicense.workspace = true\n",
                encoding="utf-8",
            )
            boundary = {
                "crates/demo/Cargo.toml": {
                    "rule": "test",
                    "class": "quarantine",
                    "license": "LicenseRef-Provenance-Pending",
                    "provenance": "project_authored",
                    "distribution": "non-distributed",
                }
            }
            material = OBSERVER._workspace_material(root, manifest_path, boundary)
            self.assertEqual(material["version"], "1.2.3")
            self.assertEqual(material["version_source"], "workspace_package")
            self.assertIsNone(material["literal_license"])

    def test_rejected_report_is_explicit_and_keeps_all_promotion_gates_blocked(self) -> None:
        report = OBSERVER._rejected_report(
            commit="a" * 40,
            tree="b" * 40,
            lock_sha256="c" * 64,
            toolchain_sha256="d" * 64,
            cargo_version_sha256="e" * 64,
            reason="cargo_metadata_failed",
        )
        self.assertEqual(report["status"], "selected_windows_build_license_material_rejected")
        self.assertEqual(report["build"]["rejection_stage"], "build_closure")
        self.assertEqual(report["build"]["rejection_reason"], "cargo_metadata_failed")
        self.assertNotIn("package_set", report)
        self.assertFalse(report["gates"]["selected_windows_build_package_set_observed"])
        self.assertFalse(report["gates"]["license_declared_metadata_observed"])
        self.assertFalse(report["gates"]["release_ready"])
        self.assertEqual(report["gates"]["promotion_status"], "blocked")
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn(str(ROOT), serialized)
        self.assertNotIn("NOASSERTION", serialized)

    def test_registry_material_requires_the_locked_archive_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "cache" / "index"
            cache.mkdir(parents=True)
            package = {"name": "demo", "version": "1.2.3", "source": "registry+https://example.invalid/index"}
            archive = cache / "demo-1.2.3.crate"
            payload = io.BytesIO()
            with tarfile.open(fileobj=payload, mode="w:gz") as tar:
                manifest = b"[package]\nname = 'demo'\nversion = '1.2.3'\nlicense = 'MIT'\n"
                info = tarfile.TarInfo("demo-1.2.3/Cargo.toml")
                info.size = len(manifest)
                tar.addfile(info, io.BytesIO(manifest))
                license_text = b"example license\n"
                info = tarfile.TarInfo("demo-1.2.3/LICENSE")
                info.size = len(license_text)
                tar.addfile(info, io.BytesIO(license_text))
            archive.write_bytes(payload.getvalue())
            lock = {("demo", "1.2.3", package["source"]): {"checksum": "0" * 64}}
            with self.assertRaisesRegex(OBSERVER.ObservationError, "registry_archive_checksum_mismatch"):
                OBSERVER._registry_material(cache.parent, package, lock)
            lock[("demo", "1.2.3", package["source"])]["checksum"] = OBSERVER.sha256(archive.read_bytes())
            material = OBSERVER._registry_material(cache.parent, package, lock)
            self.assertEqual(material["literal_license"], "MIT")
            self.assertEqual(material["license_concluded"], "NOASSERTION")
            self.assertEqual(material["notice_requirement"], "not_evaluated")
            self.assertEqual(material["license_materials"][0]["path"], "LICENSE")

    def test_license_candidate_paths_reject_traversal_and_links(self) -> None:
        unsafe = tarfile.TarInfo("../LICENSE")
        unsafe.size = 0
        with self.assertRaisesRegex(OBSERVER.ObservationError, "crate_archive_unsafe"):
            OBSERVER._license_candidates([unsafe])
        linked = tarfile.TarInfo("crate/LICENSE")
        linked.type = tarfile.SYMTYPE
        linked.linkname = "elsewhere"
        with self.assertRaisesRegex(OBSERVER.ObservationError, "crate_archive_unsafe"):
            OBSERVER._license_candidates([linked])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
