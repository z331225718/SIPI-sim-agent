"""Git-object fixture tests for the P2-01 provenance preflight."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("tran_provenance", ROOT / "tools" / "verify_tran_provenance_preflight.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class TranProvenancePreflightTests(unittest.TestCase):
    def make_repo(self, root: Path, *, include_native: bool) -> str:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "test"], check=True)
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "https://example.invalid/agent-spice.git"], check=True)
        (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
        if include_native:
            native = root / "native" / "crates" / "sipi-circuit"
            (native / "src").mkdir(parents=True)
            (native / "Cargo.toml").write_text("[package]\nname='fixture'\nversion='0.1.0'\n", encoding="utf-8")
            (native / "Cargo.lock").write_text("version = 4\n[[package]]\nname='fixture'\nversion='0.1.0'\n", encoding="utf-8")
            (native / "src" / "lib.rs").write_text("pub fn fixture() {}\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
        return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()

    def test_exact_git_object_mapping_is_replayable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            source_commit = self.make_repo(source, include_native=True)
            self.make_repo(target, include_native=True)
            manifest = GATE.materialize_manifest(target, source, source_commit)
            report = GATE.verify_manifest(target, source, manifest)
            self.assertEqual(report["status"], "preflight_passed")
            self.assertEqual(report["direct_mit_exact_count"], 3)

    def test_changed_target_blob_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            source_commit = self.make_repo(source, include_native=True)
            self.make_repo(target, include_native=True)
            manifest = GATE.materialize_manifest(target, source, source_commit)
            manifest = json.loads(json.dumps(manifest))
            manifest["entries"][0]["target"]["content_sha256"] = "0" * 64
            with self.assertRaises(GATE.PreflightError):
                GATE.verify_manifest(target, source, manifest)

    def test_absent_source_tree_keeps_target_entries_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            source_commit = self.make_repo(source, include_native=False)
            self.make_repo(target, include_native=True)
            manifest = GATE.materialize_manifest(target, source, source_commit)
            self.assertTrue(all(entry["assessment"] == "unknown" for entry in manifest["entries"]))
            self.assertEqual(GATE.verify_manifest(target, source, manifest)["unknown_count"], 3)
