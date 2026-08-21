"""Tests for the hash-bound external P5-06 oracle verifier."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_06_authoritative_matlab_oracle_run as verifier  # noqa: E402


SOURCE_ROOT_VALUE = os.environ.get("SIPI_P5_06_SOURCE_ROOT")
ORACLE_ROOT_VALUE = os.environ.get("SIPI_P5_06_ORACLE_ROOT")
SOURCE_ROOT = Path(SOURCE_ROOT_VALUE) if SOURCE_ROOT_VALUE else None
ORACLE_ROOT = Path(ORACLE_ROOT_VALUE) if ORACLE_ROOT_VALUE else None
EXTERNAL_AVAILABLE = bool(
    SOURCE_ROOT is not None
    and SOURCE_ROOT.is_dir()
    and ORACLE_ROOT is not None
    and (ORACLE_ROOT / "manifest.json").is_file()
)


class PureVerifierTests(unittest.TestCase):
    def test_line_ending_normalization_does_not_change_git_material(self) -> None:
        self.assertEqual(verifier.normalize_text_bytes(b"a\r\nb\r\n"), b"a\nb\n")
        with self.assertRaisesRegex(verifier.VerificationError, "bare_carriage_return"):
            verifier.normalize_text_bytes(b"a\rb")

    def test_warning_observation_is_bounded_to_known_source_messages(self) -> None:
        with tempfile.TemporaryDirectory(prefix="p5-06-oracle-warning-") as directory:
            path = Path(directory) / "matlab.log"
            path.write_text(
                "MLSE truncation failed. Try increasing trunc\n"
                "warning from an unrelated future branch\n",
                encoding="utf-8",
            )
            self.assertEqual(
                verifier.observed_warning_messages(path),
                ["MLSE truncation failed. Try increasing trunc"],
            )

    def test_comparison_rejects_relaxed_metric_tolerance(self) -> None:
        report = {
            "all_passed": True,
            "matlab_repeatability": {
                "tolerance": verifier.METRIC_ABS_TOLERANCE,
                "checks": [{"passed": True, "max_abs_delta": 0.0}],
            },
            "network_comparison": {
                "checks": [{"passed": True, "abs_delta_db": 0.0, "matlab_sdc21_abs": 0.0}],
            },
        }
        verifier._validate_comparison(report)
        relaxed = copy.deepcopy(report)
        relaxed["matlab_repeatability"]["tolerance"] = 1e-9
        with self.assertRaisesRegex(verifier.VerificationError, "metric_tolerance_mismatch"):
            verifier._validate_comparison(relaxed)

    def test_struct_field_decoder_reads_matlab_character_arrays(self) -> None:
        class FakeGroup:
            attrs = {
                "MATLAB_class": b"struct",
                "MATLAB_fields": [b"COM", [b"D", b"E", b"R"]],
            }

        self.assertEqual(verifier.matlab_struct_fields(FakeGroup()), ["COM", "DER"])


@unittest.skipUnless(EXTERNAL_AVAILABLE, "clean external oracle run is unavailable")
class ExternalOracleRunTests(unittest.TestCase):
    def test_clean_pinned_run_is_verified(self) -> None:
        assert SOURCE_ROOT is not None and ORACLE_ROOT is not None
        report = verifier.verify(SOURCE_ROOT, ORACLE_ROOT)
        self.assertEqual(report["status"], "pinned_source_external_matlab_oracle_candidate_run_observed")
        self.assertEqual(report["source"]["commit"], verifier.COMMIT)
        self.assertEqual(report["source_material"]["git_blob_sha256"], verifier.SOURCE_SHA256)
        self.assertEqual(report["run"]["case_count"], 1)
        self.assertIn("MLSE truncation failed. Try increasing trunc", report["run"]["warnings_observed"])
        self.assertEqual(report["metric_surface"]["tolerances"]["metric_abs_tolerance"], 1e-12)
        self.assertEqual(report["matlab_v73_reader"]["format"], "MATLAB v7.3 HDF5")
        self.assertEqual(report["run"]["artifact_policy"], "exact_known_hashes_and_structure_budget_only")
        self.assertFalse(report["source"]["checkout_clean"])

    def test_report_is_json_serializable(self) -> None:
        assert SOURCE_ROOT is not None and ORACLE_ROOT is not None
        report = verifier.verify(SOURCE_ROOT, ORACLE_ROOT)
        json.dumps(report, sort_keys=True)


if __name__ == "__main__":
    unittest.main()
