"""Focused tests for the AS-04 corpus recovery audit."""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys
import unittest

try:
    from tools import audit_as04_signoff_corpus_recovery as audit
except ModuleNotFoundError:  # pragma: no cover - direct script invocation
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import audit_as04_signoff_corpus_recovery as audit


class As04RecoveryAuditTests(unittest.TestCase):
    def test_required_paths_and_basenames_are_unique(self) -> None:
        self.assertEqual(len(audit.SIGNOFF_RELATIVE_PATHS), 3)
        self.assertEqual(len(audit.SIGNOFF_BASENAMES), 3)
        self.assertTrue(all(path.startswith("runs/yparam-tran-signoff/") for path in audit.SIGNOFF_RELATIVE_PATHS))

    def test_document_and_fixture_classification_is_not_signoff_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docs = root / "docs"
            fixture = root / "tests" / "synthetic_fixture"
            docs.mkdir()
            fixture.mkdir(parents=True)
            doc = docs / "ybootstrap_blackbox.rfm"
            test_file = fixture / "ybootstrap_blackbox.sp"
            doc.write_text("documentation only\n", encoding="utf-8")
            test_file.write_text("synthetic only\n", encoding="utf-8")
            records = audit.find_exact_files([root])
            by_name = {Path(str(record["path"])).name: record for record in records}
            self.assertEqual(by_name[doc.name]["classification"], "documentation_example")
            self.assertEqual(by_name[test_file.name]["classification"], "synthetic_or_test_artifact")

    def test_marker_scan_does_not_promote_marker_to_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "report.md"
            source.write_text(
                "references vddq_port3_port10.s2p and yfit_vs_raw_rms\n",
                encoding="utf-8",
            )
            records = audit.find_marker_files([root])
            self.assertEqual(len(records), 1)
            self.assertIn("vddq_port3_port10.s2p", records[0]["markers"])
            self.assertFalse((root / "runs/yparam-tran-signoff/vddq_port3_port10.s2p").exists())

    def test_git_path_parser_keeps_only_paths_with_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "runs/yparam-tran-signoff").mkdir(parents=True)
            (root / "runs/yparam-tran-signoff/vddq_port3_port10.s2p").write_text("not used", encoding="utf-8")
            # The temporary directory is deliberately not a Git repository;
            # this test only asserts that exact-file scanning sees the path.
            records = audit.find_exact_files([root])
            self.assertEqual(records[0]["classification"], "original_signoff_layout_candidate")

    def test_synthetic_manifest_is_classified_separately(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "docs/baselines/as-04-tune-yparam-tran-direct-port.v2.yaml"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                "status: completed_external_blocker_open\n"
                "corpus:\n"
                "- valid_nelder_mead_external_stub\n"
                "- external_hspice_blocker\n"
                "external_runtime_blocked: true\n",
                encoding="utf-8",
            )
            result = audit._synthetic_corpus_record(root)
            self.assertEqual(result["classification"], "synthetic_non_signoff")
            self.assertEqual(result["status"], "completed_external_blocker_open")
            self.assertEqual(result["corpus_ids"], ["valid_nelder_mead_external_stub", "external_hspice_blocker"])
            self.assertFalse(result["numeric_parity_claimed"])


if __name__ == "__main__":
    unittest.main()
