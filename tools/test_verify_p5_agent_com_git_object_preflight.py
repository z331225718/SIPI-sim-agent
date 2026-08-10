"""Tests for the P5 agent-com Git-object provenance preflight."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p5_agent_com_preflight", ROOT / "tools" / "verify_p5_agent_com_git_object_preflight.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class AgentComGitObjectPreflightTests(unittest.TestCase):
    def _run(self, root: Path, *arguments: str) -> None:
        subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)

    def _source(self) -> tempfile.TemporaryDirectory[str]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        self._run(root, "init")
        self._run(root, "config", "user.email", "test@example.invalid")
        self._run(root, "config", "user.name", "Test")
        self._run(root, "remote", "add", "origin", GATE.CANONICAL_ORIGIN)
        for path, content in {
            "LICENSE": "MIT License\n",
            "src/core.py": "pass\n",
            "matlab_src/model.m": "% external oracle\n",
            "fixtures/channel.s4p": "external data\n",
            "benchmarks/figure.png": "not an image fixture\n",
            "docs/readme.md": "documentation\n",
        }.items():
            destination = root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        self._run(root, "add", ".")
        self._run(root, "commit", "-m", "fixture")
        return temporary

    def test_materializes_complete_external_only_inventory(self) -> None:
        with self._source() as path:
            manifest = GATE.materialize_manifest(Path(path))
            report = GATE.verify_manifest(Path(path), manifest)
        self.assertEqual(report["status"], "git_object_preflight_passed")
        classes = {entry["path"]: entry["path_class"] for entry in manifest["entries"]}
        self.assertEqual(classes["src/core.py"], "source_code")
        self.assertEqual(classes["matlab_src/model.m"], "matlab_source")
        self.assertEqual(classes["fixtures/channel.s4p"], "data_fixture")
        self.assertFalse(manifest["promotion_eligible"])

    def test_rejects_dirty_source_or_promotion_tampering(self) -> None:
        with self._source() as path:
            root = Path(path)
            manifest = GATE.materialize_manifest(root)
            altered = copy.deepcopy(manifest)
            altered["entries"][1]["action"] = "release_input"
            with self.assertRaises(GATE.PreflightError):
                GATE.verify_manifest(root, altered)
            (root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            with self.assertRaises(GATE.PreflightError):
                GATE.verify_manifest(root, manifest)

    def test_rejects_missing_or_non_mit_root_license(self) -> None:
        with self._source() as path:
            root = Path(path)
            (root / "LICENSE").write_text("unknown\n", encoding="utf-8")
            self._run(root, "add", "LICENSE")
            self._run(root, "commit", "-m", "non-mit")
            with self.assertRaises(GATE.PreflightError):
                GATE.materialize_manifest(root)

        with self._source() as path:
            root = Path(path)
            (root / "LICENSE").unlink()
            self._run(root, "add", "-u")
            self._run(root, "commit", "-m", "remove-license")
            with self.assertRaises(GATE.PreflightError):
                GATE.materialize_manifest(root)


if __name__ == "__main__":
    unittest.main()
