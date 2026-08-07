from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "sipi-cli" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))

from sipi_cli.__main__ import main


EXAMPLES = {
    "circuit/rfm-deck": 1,
    "channel/rfm-to-link": 2,
    "com/r480": 1,
}


class ExampleProjectTests(unittest.TestCase):
    def test_all_examples_validate(self):
        for relative, analysis_count in EXAMPLES.items():
            with self.subTest(example=relative):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    status = main(["validate", "--root", str(ROOT / "examples" / relative), "--format", "json"])
                self.assertEqual(status, 0)
                payload = json.loads(stdout.getvalue())
                self.assertEqual(len(payload["analyses"]), analysis_count)

    def test_engine_lock_hashes_match_bundles(self):
        for lock_path in (ROOT / "examples").rglob("engine.lock"):
            with self.subTest(lock=str(lock_path.relative_to(ROOT / "examples"))):
                lock = json.loads(lock_path.read_text(encoding="utf-8"))
                for entry in lock["engines"]:
                    bundle = lock_path.parent / entry["bundle"]["path"]
                    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
                    self.assertEqual(entry["bundle"]["sha256"], digest)
                    manifest_file = entry["bundle_manifest"]["files"][0]
                    self.assertEqual(manifest_file["sha256"], digest)
                    self.assertEqual(manifest_file["byte_length"], bundle.stat().st_size)

    def test_rfm_to_link_example_has_bound_input(self):
        project = json.loads((ROOT / "examples" / "channel" / "rfm-to-link" / "project.json").read_text(encoding="utf-8"))
        link = next(analysis for analysis in project["analyses"] if analysis["id"] == "link-eye")
        self.assertEqual(link["depends_on"], ["rfm-response"])
        self.assertEqual(link["inputs"]["channel"]["from_analysis"], "rfm-response")
        self.assertEqual(link["inputs"]["channel"]["artifact_role"], "rfm-response")


if __name__ == "__main__":
    unittest.main()
