"""Tests for the external-only P5-06i result custody observer."""

from __future__ import annotations

import copy
from pathlib import Path
import re
import sys
import tempfile
import unittest

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import observe_p5_06i_external_result_custody as observer  # noqa: E402


EXTERNAL_AVAILABLE = observer.DEFAULT_COM_ROOT.is_dir()


class CanonicalizationTests(unittest.TestCase):
    def test_digest_preserves_array_shape_dtype_and_order(self) -> None:
        first = np.array([[1, 2], [3, 4]], dtype=np.int16)
        same_values_different_shape = np.array([1, 2, 3, 4], dtype=np.int16)
        different_dtype = np.array([[1, 2], [3, 4]], dtype=np.int32)
        self.assertNotEqual(observer.digest(first), observer.digest(same_values_different_shape))
        self.assertNotEqual(observer.digest(first), observer.digest(different_dtype))

    def test_digest_is_stable_for_complex_and_nonfinite_values(self) -> None:
        value = np.array([complex(1, 2), np.inf, -np.inf, np.nan], dtype=np.complex128)
        self.assertEqual(observer.digest(value), observer.digest(value.copy()))


@unittest.skipUnless(EXTERNAL_AVAILABLE, "authorized external COM checkout is unavailable")
class ExternalCustodyTests(unittest.TestCase):
    def test_observed_payload_contract(self) -> None:
        evidence = observer.observe()
        self.assertEqual(evidence["status"], "external_result_payload_observed_not_authoritative")
        self.assertEqual(evidence["external_source"]["identity"]["commit"], "5272ffe74702cd585054d975559b06f8afae7b6e")
        self.assertFalse(evidence["external_source"]["matlab_invoked"])
        self.assertFalse(evidence["external_source"]["result_generator_commit_verified"])
        self.assertFalse(evidence["external_source"]["ignored_outputs_git_object_bound"])
        self.assertEqual(evidence["payload_count"], 4)
        self.assertEqual(
            [payload["case_identity"]["id"] for payload in evidence["payloads"]],
            ["fixtures_case1", "fixtures_case2", "synthetic_case1", "synthetic_case2"],
        )
        self.assertTrue(all(payload["csv"]["header_matches_output_fields"] for payload in evidence["payloads"]))
        self.assertTrue(all(payload["field_counts"] == {"output_args": 98, "OP": 95, "param": 177} for payload in evidence["payloads"]))
        self.assertTrue(all(payload["default_resolution"]["needs_oracle_occurrence_count"] == 20 for payload in evidence["payloads"]))
        self.assertTrue(all(payload["checkpoints"]["tolerance_status"] == "missing" for payload in evidence["payloads"]))
        self.assertEqual(evidence["warning_contract"]["exact_run_warning_report_status"], "missing")

    def test_bound_artifacts_redact_machine_paths_and_noncanonical_urls(self) -> None:
        evidence_path = observer.EVIDENCE
        audit_path = ROOT / "docs" / "baselines" / "audits" / "2026-08-21-p5-06i-external-result-custody.md"
        texts = [evidence_path.read_text(encoding="utf-8"), audit_path.read_text(encoding="utf-8")]
        forbidden = ("C:" + "/", "C:" + "\\", "file" + "://")
        for text in texts:
            for marker in forbidden:
                self.assertNotIn(marker.lower(), text.lower())
            for url in re.findall(r"https?://[^\s`]+", text):
                self.assertEqual(url.rstrip(".,)"), observer.CANONICAL_ORIGIN)
        evidence = yaml.safe_load(texts[0])
        self.assertEqual(evidence["external_source"]["logical_root"], "external_com_checkout")

        def assert_url_fields(value: object, key_path: tuple[str, ...] = ()) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    assert_url_fields(child, (*key_path, str(key)))
            elif isinstance(value, list):
                for child in value:
                    assert_url_fields(child, key_path)
            elif isinstance(value, str) and re.search(r"https?://", value):
                self.assertEqual(key_path[-1], "canonical_origin")

        assert_url_fields(evidence)
        for material in evidence["registered_materials"]:
            self.assertEqual(material["logical_root"], "external_com_checkout")
            self.assertNotIn("path", material)
            self.assertNotIn(":/", material["relative_to_root"])
        for payload in evidence["payloads"]:
            self.assertEqual(payload["mat"]["logical_root"], "external_com_checkout")
            self.assertEqual(payload["csv"]["logical_root"], "external_com_checkout")
            self.assertEqual(payload["observed_identity"]["config_file"]["kind"], "redacted_absolute_path")
            self.assertNotIn("value", payload["observed_identity"]["config_file"])

    def test_committed_evidence_verifies(self) -> None:
        report = observer.verify()
        self.assertEqual(report["status"], "external_result_custody_verified")
        self.assertEqual(report["payload_count"], 4)

    def test_mutated_evidence_fails_closed(self) -> None:
        evidence = observer.observe()
        mutated = copy.deepcopy(evidence)
        mutated["payloads"][0]["mat"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory(prefix="p5-06i-test-") as temporary:
            path = Path(temporary) / "evidence.yaml"
            path.write_text(yaml.safe_dump(mutated, sort_keys=False), encoding="utf-8")
            with self.assertRaises(observer.ObservationError):
                observer.verify(observer.DEFAULT_COM_ROOT, path)


if __name__ == "__main__":
    unittest.main()
