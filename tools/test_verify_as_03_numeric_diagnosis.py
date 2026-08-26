"""Mutation and custody coverage for the AS-03 physical checkpoint verifier."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import aggregate_as_03_numeric_checkpoint as aggregator
    import run_as_03_numeric_checkpoint as runner
    import verify_as_03_numeric_diagnosis as verifier
except ModuleNotFoundError:
    from tools import aggregate_as_03_numeric_checkpoint as aggregator
    from tools import run_as_03_numeric_checkpoint as runner
    from tools import verify_as_03_numeric_diagnosis as verifier


def _leaf_paths(value: object, prefix: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
    if isinstance(value, dict):
        return [path for key, item in value.items() for path in _leaf_paths(item, (*prefix, key))]
    if isinstance(value, list):
        return [path for index, item in enumerate(value) for path in _leaf_paths(item, (*prefix, index))]
    return [prefix]


def _mutate(value: object, path: tuple[object, ...]) -> object:
    result = copy.deepcopy(value)
    target = result
    for part in path[:-1]:
        target = target[part]
    old = target[path[-1]]
    if type(old) is bool:
        target[path[-1]] = not old
    elif type(old) is int:
        target[path[-1]] = float(old)
    elif type(old) is float:
        target[path[-1]] = repr(old)
    elif type(old) is str:
        target[path[-1]] = old + "x"
    elif old is None:
        target[path[-1]] = False
    else:
        raise AssertionError(f"unsupported leaf type: {type(old)}")
    return result


class NumericDiagnosisVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = verifier.yaml.safe_load(verifier.MANIFEST.read_text(encoding="utf-8"))
        cls.physical = {}
        evidence = cls.document["evidence"]
        for item in [*evidence["reports"], evidence["aggregate"]]:
            cls.physical[item["path"]] = json.loads((verifier.ROOT / item["path"]).read_text(encoding="utf-8"))

    def verify_fast(self, document: dict, overrides: dict[str, object] | None = None) -> dict:
        with mock.patch.object(verifier, "_validate_source", return_value=True):
            return verifier.verify(document, physical_overrides=overrides)

    @staticmethod
    def rendered_sha(value: object) -> str:
        return hashlib.sha256((json.dumps(value, indent=2, sort_keys=True) + "\n").encode()).hexdigest()

    def coordinated(self, first: dict, second: dict) -> tuple[dict, dict[str, object]]:
        document = copy.deepcopy(self.document)
        report_items = document["evidence"]["reports"]
        report_items[0]["sha256"] = self.rendered_sha(first)
        report_items[1]["sha256"] = self.rendered_sha(second)
        aggregate = aggregator.build_aggregate(first, second, report_items[0], report_items[1])
        document["evidence"]["aggregate"]["sha256"] = self.rendered_sha(aggregate)
        overrides = {report_items[0]["path"]: first, report_items[1]["path"]: second, document["evidence"]["aggregate"]["path"]: aggregate}
        return document, overrides

    @staticmethod
    def refresh_checkpoint(report: dict) -> None:
        checkpoint = report["checkpoint"]
        for side in ("candidate", "upstream"):
            raw = {key: value for key, value in checkpoint[side].items() if key not in {"physical_f64_le_sha256", "normalized_sha256", "parser_receipt_sha256"}}
            checkpoint[side] = runner._checkpoint(raw)
        checkpoint["comparison"] = runner._comparison(checkpoint["candidate"], checkpoint["upstream"])
        checkpoint["reciprocal_anchor_sha256"] = verifier._derive_anchor(report, checkpoint["comparison"])

    @staticmethod
    def project_manifest_checkpoint(document: dict, report: dict) -> None:
        checkpoint = report["checkpoint"]
        document["physical_checkpoint"] = {
            "frequency_hz": checkpoint["candidate"]["frequency_hz"], "sample_index": checkpoint["candidate"]["sample_index"], "ports": checkpoint["candidate"]["ports"],
            "candidate_physical_f64_le_sha256": checkpoint["candidate"]["physical_f64_le_sha256"], "candidate_normalized_sha256": checkpoint["candidate"]["normalized_sha256"],
            "upstream_physical_f64_le_sha256": checkpoint["upstream"]["physical_f64_le_sha256"], "upstream_normalized_sha256": checkpoint["upstream"]["normalized_sha256"],
            "parser_receipt_sha256": checkpoint["candidate"]["parser_receipt_sha256"], "reciprocal_anchor_sha256": checkpoint["reciprocal_anchor_sha256"],
            "first_lexicographic_difference": checkpoint["comparison"]["first_lexicographic_difference"], "max_abs_difference": checkpoint["comparison"]["max_abs_difference"],
        }

    def test_baseline_is_valid(self) -> None:
        self.assertEqual(verifier.verify(copy.deepcopy(self.document)), {"valid": True, "blockers": []})

    def test_recursive_exact_type_frequency_points_rejects_int_to_float(self) -> None:
        value = copy.deepcopy(self.document); value["scope"]["fixture"]["frequency_points"] = 4.0
        self.assertFalse(self.verify_fast(value)["valid"])

    def test_recursive_exact_type_sample_rejects_int_to_bool(self) -> None:
        value = copy.deepcopy(self.document); value["physical_checkpoint"]["sample_index"] = False
        self.assertFalse(self.verify_fast(value)["valid"])

    def test_recursive_exact_type_archive_bytes_rejects_int_to_float(self) -> None:
        value = copy.deepcopy(self.document); value["source"]["candidate"]["archive"]["bytes"] = 52224000.0
        self.assertFalse(self.verify_fast(value)["valid"])

    def test_recursive_exact_type_report_runs_rejects_int_to_float(self) -> None:
        value = copy.deepcopy(self.document); value["evidence"]["report_runs"] = 2.0
        self.assertFalse(self.verify_fast(value)["valid"])

    def test_manifest_anchor_mutations_are_rejected(self) -> None:
        paths = (
            ("trust", "external_trust_root"),
            ("source", "candidate", "commit"),
            ("source", "upstream", "files", 0, "git_blob"),
            ("physical_checkpoint", "candidate_physical_f64_le_sha256"),
            ("physical_checkpoint", "upstream_normalized_sha256"),
            ("physical_checkpoint", "reciprocal_anchor_sha256"),
            ("physical_checkpoint", "max_abs_difference", "delta"),
            ("evidence", "runner", "sha256"),
            ("evidence", "aggregate", "sha256"),
            ("audit", "path"),
            ("numeric_parity",),
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertFalse(self.verify_fast(_mutate(self.document, path))["valid"])

    def test_every_physical_report_leaf_is_covered_by_full_graph_hash(self) -> None:
        for evidence_path, physical in self.physical.items():
            for leaf in _leaf_paths(physical):
                with self.subTest(evidence=evidence_path, leaf=leaf):
                    overrides = {evidence_path: _mutate(physical, leaf)}
                    self.assertFalse(self.verify_fast(copy.deepcopy(self.document), overrides)["valid"])

    def test_coordinated_run2_aggregate_manifest_edit_hits_stable_field_gate(self) -> None:
        first = copy.deepcopy(self.physical[self.document["evidence"]["reports"][0]["path"]])
        second = copy.deepcopy(self.physical[self.document["evidence"]["reports"][1]["path"]])
        second["toolchain"]["timeout_seconds"] = 901
        document = copy.deepcopy(self.document)
        items = document["evidence"]["reports"]
        items[1]["sha256"] = self.rendered_sha(second)
        aggregate = copy.deepcopy(self.physical[document["evidence"]["aggregate"]["path"]])
        aggregate["toolchain"]["timeout_seconds"] = 901
        document["evidence"]["aggregate"]["sha256"] = self.rendered_sha(aggregate)
        overrides = {items[1]["path"]: second, document["evidence"]["aggregate"]["path"]: aggregate}
        result = self.verify_fast(document, overrides)
        self.assertTrue(any("aggregate regeneration:fresh replay drift: toolchain" in blocker for blocker in result["blockers"]))
        self.assertFalse(any("full graph hash" in blocker for blocker in result["blockers"]))

    def test_coordinated_matrix_graph_cannot_rewrite_physical_residual_anchor(self) -> None:
        first = copy.deepcopy(self.physical[self.document["evidence"]["reports"][0]["path"]])
        second = copy.deepcopy(self.physical[self.document["evidence"]["reports"][1]["path"]])
        for report in (first, second):
            cell = report["checkpoint"]["candidate"]["matrix"][0]
            bits = int(cell["re_bits"], 16) + 1
            cell["re_bits"] = f"{bits:016x}"
            cell["re"] = format(struct.unpack(">d", bits.to_bytes(8, "big"))[0], ".17f")
            self.refresh_checkpoint(report)
        document, overrides = self.coordinated(first, second)
        self.project_manifest_checkpoint(document, first)
        result = self.verify_fast(document, overrides)
        self.assertTrue(any("physical residual anchor" in blocker for blocker in result["blockers"]))
        self.assertFalse(any("full graph hash" in blocker or "aggregate bit-exact" in blocker for blocker in result["blockers"]))

    def test_coordinated_stored_anchor_rewrite_is_recomputed(self) -> None:
        first = copy.deepcopy(self.physical[self.document["evidence"]["reports"][0]["path"]])
        second = copy.deepcopy(self.physical[self.document["evidence"]["reports"][1]["path"]])
        for report in (first, second): report["checkpoint"]["reciprocal_anchor_sha256"] = "0" * 64
        document, overrides = self.coordinated(first, second)
        self.project_manifest_checkpoint(document, first)
        result = self.verify_fast(document, overrides)
        self.assertTrue(any("reciprocal execution anchor recomputation" in blocker for blocker in result["blockers"]))
        self.assertFalse(any("full graph hash" in blocker for blocker in result["blockers"]))

    def test_coordinated_parser_receipt_rewrite_hits_fixed_fixture_anchor(self) -> None:
        first = copy.deepcopy(self.physical[self.document["evidence"]["reports"][0]["path"]])
        second = copy.deepcopy(self.physical[self.document["evidence"]["reports"][1]["path"]])
        for report in (first, second):
            receipt = copy.deepcopy(report["fixture"]["parsed_receipt"])
            receipt["sample_matrix"][0]["re_bits"] = "3f847ae147ae147c"
            report["fixture"]["parsed_receipt"] = receipt
            report["checkpoint"]["candidate"]["parser_receipt"] = copy.deepcopy(receipt)
            report["checkpoint"]["upstream"]["parser_receipt"] = copy.deepcopy(receipt)
            self.refresh_checkpoint(report)
        document, overrides = self.coordinated(first, second)
        self.project_manifest_checkpoint(document, first)
        result = self.verify_fast(document, overrides)
        self.assertTrue(any("fixed fixture parser receipt" in blocker for blocker in result["blockers"]))
        self.assertFalse(any("full graph hash" in blocker for blocker in result["blockers"]))

    def test_coordinated_equal_matrix_component_rewrite_hits_expected_physical_digest(self) -> None:
        first = copy.deepcopy(self.physical[self.document["evidence"]["reports"][0]["path"]])
        second = copy.deepcopy(self.physical[self.document["evidence"]["reports"][1]["path"]])
        forged_bits = "3cb0000000000000"
        forged_decimal = format(struct.unpack(">d", bytes.fromhex(forged_bits))[0], ".17f")
        for report in (first, second):
            for side in ("candidate", "upstream"):
                report["checkpoint"][side]["matrix"][0]["im_bits"] = forged_bits
                report["checkpoint"][side]["matrix"][0]["im"] = forged_decimal
            self.refresh_checkpoint(report)
        document, overrides = self.coordinated(first, second)
        self.project_manifest_checkpoint(document, first)
        result = self.verify_fast(document, overrides)
        self.assertTrue(any("expected complete matrix digest/raw representation" in blocker for blocker in result["blockers"]))
        self.assertFalse(any("full graph hash" in blocker or "aggregate bit-exact" in blocker for blocker in result["blockers"]))

    def test_coordinated_decimal_only_rewrite_hits_expected_raw_matrix(self) -> None:
        first = copy.deepcopy(self.physical[self.document["evidence"]["reports"][0]["path"]])
        second = copy.deepcopy(self.physical[self.document["evidence"]["reports"][1]["path"]])
        for report in (first, second):
            report["checkpoint"]["candidate"]["matrix"][1]["im"] = "-0.00000000000000000"
            self.refresh_checkpoint(report)
        document, overrides = self.coordinated(first, second)
        self.project_manifest_checkpoint(document, first)
        result = self.verify_fast(document, overrides)
        self.assertTrue(any("expected complete matrix digest/raw representation" in blocker for blocker in result["blockers"]))
        self.assertFalse(any("full graph hash" in blocker or "aggregate bit-exact" in blocker for blocker in result["blockers"]))

    def test_exact_report_keys_and_pre_post_identity_are_enforced(self) -> None:
        report = copy.deepcopy(self.physical[self.document["evidence"]["reports"][0]["path"]])
        report["unexpected"] = True
        self.assertIn("report exact top-level keys", aggregator.validate_report(report))
        report = copy.deepcopy(self.physical[self.document["evidence"]["reports"][0]["path"]])
        report["toolchain"]["python"]["post"]["version_sha256"] = "0" * 64
        self.assertIn("report toolchain", aggregator.validate_report(report))

    def test_bounded_subprocess_rejects_overflow_and_timeout(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "stdout byte limit"):
            runner._bounded_process([sys.executable, "-c", "print('x'*4096)"], cwd=verifier.ROOT, env=dict(os.environ), timeout=5, stdout_limit=64, stderr_limit=64)
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            runner._bounded_process([sys.executable, "-c", "import time;time.sleep(2)"], cwd=verifier.ROOT, env=dict(os.environ), timeout=1, stdout_limit=64, stderr_limit=64)

    def test_path_grammar_rejects_windows_posix_unc_and_traversal(self) -> None:
        for raw in (r"C:\\repo\\x", "/repo/x", r"\\\\server\\share\\x", "../x", r"a\\..\\x"):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                runner._safe_relative(raw)
        self.assertEqual(runner._safe_relative(r"docs\\baselines\\x.json"), Path("docs", "baselines", "x.json"))

    def test_single_link_gate_rejects_hardlink(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); first = root / "first"; second = root / "second"
            first.write_bytes(b"x")
            os.link(first, second)
            with self.assertRaises(RuntimeError): runner._regular_single_link(first, "fixture")

    def test_git_source_binding_uses_commit_object_not_hash_object(self) -> None:
        source = (verifier.ROOT / "tools/verify_as_03_numeric_diagnosis.py").read_text(encoding="utf-8") + (verifier.ROOT / "tools/run_as_03_numeric_checkpoint.py").read_text(encoding="utf-8")
        self.assertIn("cat-file", source)
        self.assertIn("rev-parse", source)
        self.assertNotIn("hash-object", source)

    def test_absolute_upstream_path_is_not_embedded(self) -> None:
        for relative in ("tools/run_as_03_numeric_checkpoint.py", "tools/verify_as_03_numeric_diagnosis.py"):
            text = (verifier.ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn(r"C:\Users", text)
            self.assertIn("DEFAULT_UPSTREAM", text)


if __name__ == "__main__":
    unittest.main()
