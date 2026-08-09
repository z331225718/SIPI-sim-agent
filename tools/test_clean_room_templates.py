from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from verify_clean_room_templates import TEMPLATES, verify


class CleanRoomTemplateTests(unittest.TestCase):
    def test_current_templates_are_valid(self) -> None:
        report = verify()
        self.assertTrue(report["valid"], report["blockers"])

    def test_missing_heading_and_prohibited_marker_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative, headings in TEMPLATES.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("\n".join(["# Template", *headings]), encoding="utf-8")
            target = root / "docs/clean-room/templates/observation-spec.v1.md"
            target.write_text(target.read_text(encoding="utf-8").replace("## Seal", ""), encoding="utf-8")
            report = verify(root)
            self.assertFalse(report["valid"])
            self.assertTrue(any("headings" in item for item in report["blockers"]))
            target.write_text(target.read_text(encoding="utf-8") + "\nPyBERT source", encoding="utf-8")
            report = verify(root)
            self.assertFalse(report["valid"])
            self.assertTrue(any("prohibited" in item for item in report["blockers"]))
