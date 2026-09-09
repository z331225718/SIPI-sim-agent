"""Portable failure-path checks for the Windows source-build entry."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows PowerShell required")
class BuildWindowsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sipi-build-entry-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "checkout with spaces"
        self.script = self.root / "tools" / "build_windows.ps1"
        self.script.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "tools" / "build_windows.ps1", self.script)
        for relative in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "crates/sipi-cli/Cargo.toml"):
            file = self.root / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.touch()
        self.env = dict(os.environ)
        self.env.update({
            "PATH": str(Path(os.environ["SystemRoot"]) / "System32"),
            "CARGO_HOME": str(self.root / "empty-cargo"),
            "USERPROFILE": str(self.root / "user"),
            "ProgramFiles(x86)": str(self.root / "no-visual-studio"),
            "OS": "Windows_NT",
            "PROCESSOR_ARCHITECTURE": "AMD64",
        })
        self.env.pop("PROCESSOR_ARCHITEW6432", None)

    def run_check(self, *options):
        result = subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.script), "-Check", *options],
            env=self.env, cwd=self.temp.name, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertFalse((self.root / "target").exists())
        return result.stdout + result.stderr

    def fake_cargo(self, home):
        binary = home / "bin" / "cargo.exe"
        binary.parent.mkdir(parents=True)
        # -Check must inspect files without executing even the selected cargo.
        binary.write_bytes(b"not an executable")

    def test_missing_tools_report_rust_and_msvc_without_building(self):
        output = self.run_check()
        self.assertIn("Cargo/Rust not found", output)
        self.assertIn("MSVC C++ Build Tools not found", output)
        self.assertIn("https://rust-lang.org/tools/install/", output)

    def test_cargo_home_fallback_works_without_path_or_execution(self):
        self.fake_cargo(Path(self.env["CARGO_HOME"]))
        output = self.run_check()
        self.assertIn("Cargo: ", output)
        self.assertNotIn("Cargo/Rust not found", output)
        self.assertIn("MSVC C++ Build Tools not found", output)

    def test_default_userprofile_cargo_fallback(self):
        self.env.pop("CARGO_HOME")
        self.fake_cargo(Path(self.env["USERPROFILE"]) / ".cargo")
        output = self.run_check()
        self.assertIn("Cargo: ", output)
        self.assertNotIn("Cargo/Rust not found", output)

    def test_explicit_cargo_home_does_not_silently_use_other_user_home(self):
        self.fake_cargo(Path(self.env["USERPROFILE"]) / ".cargo")
        self.assertIn("Cargo/Rust not found", self.run_check())

    def test_incomplete_checkout_has_actionable_error(self):
        (self.root / "Cargo.lock").unlink()
        self.assertIn("Incomplete SIPI checkout: missing Cargo.lock", self.run_check())

    def test_unsupported_architecture_fails_before_build(self):
        self.env["PROCESSOR_ARCHITECTURE"] = "ARM64"
        self.assertIn("Windows x64 only", self.run_check())

    def test_channel_build_requires_the_in_repo_native_source_and_template(self):
        self.assertIn("missing crates/sipi-pybert-direct/Cargo.toml", self.run_check("-Channel"))
        crate = self.root / "crates/sipi-pybert-direct/Cargo.toml"
        crate.parent.mkdir(parents=True)
        crate.touch()
        self.assertIn("missing examples/channel-native/metallic-line.json", self.run_check("-Channel"))
        template = self.root / "examples/channel-native/metallic-line.json"
        template.parent.mkdir(parents=True)
        template.touch()
        self.assertIn("Cargo/Rust not found", self.run_check("-Channel"))


if __name__ == "__main__":
    unittest.main()
