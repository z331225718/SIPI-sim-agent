from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/verify_channel_rfm_receiver_reference_bits_preflight.py"
SPEC = importlib.util.spec_from_file_location("reference_bits_preflight", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def source_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source"
    git(tmp_path, "init", "source")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    (repo / "scripts").mkdir()
    (repo / "tests/golden/rust_migration/agent_spice_rfm").mkdir(parents=True)
    (repo / "scripts/verify_m5b_rfm_receiver_parity.py").write_text("\n".join(MODULE.SOURCE_MARKERS), encoding="utf-8")
    (repo / "tests/golden/rust_migration/agent_spice_rfm/block_2.rfm").write_bytes(b"rfm")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "source")
    return repo


class ReferenceBitsPreflightTests(unittest.TestCase):
    def test_canonical_bits_are_explicit_and_not_inferred(self) -> None:
        bits = MODULE._canonical_bits()
        self.assertEqual(len(bits), 128)
        self.assertEqual(set(bits), {0, 1})
        self.assertEqual(bits[:4], bytes([1, 0, 1, 0]))

    def test_verify_rejects_unapproved_source_before_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = source_repo(Path(temporary))
            with self.assertRaisesRegex(ValueError, "origin"):
                MODULE.verify(repo)


if __name__ == "__main__":
    unittest.main()
