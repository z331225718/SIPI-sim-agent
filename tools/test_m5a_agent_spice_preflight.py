from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_m5a_agent_spice_preflight import verify


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def write(root: Path, path: str, text: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def make_source(root: Path) -> tuple[Path, dict]:
    source = root / "agent-spice"
    subprocess.run(["git", "init", "-q", "-b", "main", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.email", "test@local"], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.name", "test"], check=True)
    for path in ["LICENSE", "LICENSE-MANIFEST.md", "src/agent_spice/fit.py", "native/agent-spice-sim/Cargo.toml", "docs/readme.md", "tests/test_fit.py", "third_party/solver.bin"]:
        write(source, path, path)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-qm", "baseline"], check=True)
    subprocess.run(["git", "-C", str(source), "tag", "-a", "sipi-baseline/agent-spice/20260807.2", "-m", "baseline"], check=True)
    write(source, "README.md", "migration anchor")
    subprocess.run(["git", "-C", str(source), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-qm", "anchor"], check=True)
    commit = git(source, "rev-parse", "HEAD")
    tag = git(source, "rev-parse", "sipi-baseline/agent-spice/20260807.2^{}")
    document = {
        "schema": "sipi.history-migration-preflight.v1",
        "source": {
            "commit": commit,
            "tree": git(source, "rev-parse", "HEAD^{tree}"),
            "baseline": {"tag": "sipi-baseline/agent-spice/20260807.2", "commit": tag, "tree": git(source, "rev-parse", f"{tag}^{{tree}}")},
            "evidence": [{"path": "LICENSE", "sha256": sha256(b"LICENSE").hexdigest().upper()}],
        },
        "target": {"prefix": "engines/agent-spice"},
        "filter": {
            "include_paths": ["LICENSE", "src", "native/agent-spice-sim", "docs", "tests"],
            "drop_paths": ["third_party"],
            "required_retained_paths": ["src/agent_spice", "native/agent-spice-sim", "docs", "tests"],
        },
        "restricted_paths": [{"path": "third_party", "reason": "blocked_unknown"}],
    }
    return source, document


class M5AAgentSpicePreflightTests(unittest.TestCase):
    def test_ready_source_retains_only_allowed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, document = make_source(Path(directory))
            report = verify(document, source)
        self.assertTrue(report["ready"], report["blockers"])
        self.assertEqual(report["retained_path_count"], 5)
        self.assertEqual(report["dropped_path_count"], 3)

    def test_restricted_path_must_be_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, document = make_source(Path(directory))
            document["filter"]["drop_paths"] = []
            report = verify(document, source)
        self.assertFalse(report["ready"])
        self.assertIn("restricted path is not dropped: third_party", report["blockers"])

    def test_source_tree_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, document = make_source(Path(directory))
            document["source"]["tree"] = "0" * 40
            report = verify(document, source)
        self.assertFalse(report["ready"])
        self.assertIn("source tree mismatch", report["blockers"])


if __name__ == "__main__":
    unittest.main()
