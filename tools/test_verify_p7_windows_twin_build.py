"""Unit tests for the P7-01a twin-build gate without invoking Cargo."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p7_gate", ROOT / "tools" / "verify_p7_windows_twin_build.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class TwinBuildGateTests(unittest.TestCase):
    def test_compare_requires_size_and_digest_identity(self) -> None:
        same = {"binary_bytes": 4, "binary_sha256": "a" * 64}
        different_size = {"binary_bytes": 5, "binary_sha256": "a" * 64}
        different_digest = {"binary_bytes": 4, "binary_sha256": "b" * 64}
        self.assertEqual(GATE.compare_builds(same, same), {"size_match": True, "digest_match": True})
        self.assertEqual(GATE.compare_builds(same, different_size), {"size_match": False, "digest_match": True})
        self.assertEqual(GATE.compare_builds(same, different_digest), {"size_match": True, "digest_match": False})

    def test_scrubbed_environment_sets_only_external_target_policy(self) -> None:
        target = Path("external-target")
        environment = GATE.scrubbed_environment(
            {"PATH": "x", "PYTHONPATH": "bad", "CARGO_TARGET_DIR": "bad", "CARGO_INCREMENTAL": "1"},
            target,
        )
        self.assertEqual(environment["PATH"], "x")
        self.assertEqual(environment["CARGO_TARGET_DIR"], str(target))
        self.assertEqual(environment["CARGO_INCREMENTAL"], "0")
        self.assertEqual(environment["CARGO_NET_OFFLINE"], "true")
        self.assertEqual(environment["RUSTFLAGS"], GATE.REPRO_RUSTFLAGS)
        self.assertNotIn("PYTHONPATH", environment)

    def test_materialization_rejects_escape_and_link_entries(self) -> None:
        for name, kind in [("../escape", "file"), ("link", "symlink")]:
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode="w") as bundle:
                entry = tarfile.TarInfo(name)
                if kind == "symlink":
                    entry.type = tarfile.SYMTYPE
                    entry.linkname = "target"
                else:
                    entry.size = 1
                bundle.addfile(entry, None if kind == "symlink" else io.BytesIO(b"x"))
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(GATE.GateError):
                    GATE.materialize_archive(archive.getvalue(), Path(directory) / "source")

    def test_workspace_output_is_rejected(self) -> None:
        with self.assertRaises(GATE.GateError):
            GATE.require_external(ROOT, ROOT)
        GATE.require_external(Path(tempfile.gettempdir()) / "sipi-p7-test", ROOT)

    def test_report_path_must_be_external_and_new(self) -> None:
        with self.assertRaises(GATE.GateError):
            GATE.prepare_report_path(ROOT / "report.json", ROOT)

        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            report.write_text("existing", encoding="utf-8")
            with self.assertRaises(GATE.GateError):
                GATE.prepare_report_path(report, ROOT)


if __name__ == "__main__":
    unittest.main()
