import hashlib
import struct
import unittest

try:
    from .project_p5_06_stage2a_txle import (
        compare_projected_txle_cases,
        compare_txle_checkpoint_surface,
        project_matlab_summary,
        project_rust_result,
        validate_projected_txle_cases,
    )
except ImportError:
    from project_p5_06_stage2a_txle import (
        compare_projected_txle_cases,
        compare_txle_checkpoint_surface,
        project_matlab_summary,
        project_rust_result,
        validate_projected_txle_cases,
    )


def digest(values):
    return hashlib.sha256(b"".join(struct.pack("<d", item) for item in values)).hexdigest()


def source_scalar(value):
    return {"kind": "finite", "value": value}


def source_case(values=(1.0,)):
    return {
        "case_index": 1,
        "applicable": True,
        "final_scalar_metrics": {"COM_dB": source_scalar(-12.0), "FOM": source_scalar(-4.0)},
        "txle_taps": {
            "class": "double",
            "shape": [1, len(values)],
            "value_count": len(values),
            "storage_order": "matlab_column_major",
            "semantic_axis": "tap_order_pre_to_cursor_to_post",
            "unit": "ratio",
            "encoding": "ieee754_f64_little_endian_column_major",
            "raw_f64_sha256": digest(values),
            "column_major_values": list(values),
        },
    }


def source_summary(values=(1.0,)):
    return {"schema_version": 1, "diagnostic_only": True, "case_count": 1, "case_checkpoints": [source_case(values)]}


def rust_result(values=(1.0,)):
    return {
        "cases": [{
            "case_index": 0,
            "metrics": {"COM_dB": -12.0, "FOM": -4.0, "extra_product_metric": 3.0},
            "diagnostics": {"portable_branches": {"search": {"selected_tx_taps": list(values)}}},
        }]
    }


class TxleProjectionTests(unittest.TestCase):
    def test_projects_exact_source_and_rust_shapes(self):
        source = project_matlab_summary(source_summary((0.25, 0.75, 0.0)))
        candidate = project_rust_result(rust_result((0.25, 0.75, 0.0)))
        self.assertEqual(source[0]["txle_taps"], candidate[0]["txle_taps"])
        self.assertEqual(source[0]["txle_taps"]["shape"], [1, 3])

    def test_singleton_txle_is_still_a_vector(self):
        projected = project_matlab_summary(source_summary((1.0,)))
        self.assertEqual(projected[0]["txle_taps"]["values"], [1.0])
        self.assertEqual(projected[0]["txle_taps"]["shape"], [1, 1])

    def test_compare_accepts_exact_taps_and_scalar_tolerance(self):
        candidate = rust_result((1.0,))
        candidate["cases"][0]["metrics"]["COM_dB"] += 5e-10
        self.assertEqual(compare_txle_checkpoint_surface(source_summary((1.0,)), candidate), [])

    def test_compare_rejects_old_zero_placeholder_shape(self):
        mismatches = compare_txle_checkpoint_surface(source_summary((1.0,)), rust_result((0.0, 0.0, 0.0, 1.0, 0.0)))
        self.assertEqual(mismatches, ["case 0: TXLE checkpoint differs"])

    def test_source_digest_drift_is_rejected(self):
        document = source_summary()
        document["case_checkpoints"][0]["txle_taps"]["raw_f64_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "raw digest"):
            project_matlab_summary(document)

    def test_source_column_vector_is_rejected(self):
        document = source_summary()
        document["case_checkpoints"][0]["txle_taps"]["shape"] = [1, 1]
        document["case_checkpoints"][0]["txle_taps"]["shape"][0] = 2
        with self.assertRaisesRegex(ValueError, "row vector"):
            project_matlab_summary(document)

    def test_rust_missing_search_checkpoint_is_rejected(self):
        document = rust_result()
        del document["cases"][0]["diagnostics"]["portable_branches"]["search"]
        with self.assertRaisesRegex(ValueError, "search checkpoint"):
            project_rust_result(document)

    def test_special_scalar_tokens_must_match(self):
        document = source_summary()
        document["case_checkpoints"][0]["final_scalar_metrics"] = {"ERL": {"kind": "inf"}}
        candidate = rust_result()
        candidate["cases"][0]["metrics"] = {"ERL": "+Inf"}
        self.assertEqual(compare_txle_checkpoint_surface(document, candidate), [])
        candidate["cases"][0]["metrics"] = {"ERL": "-Inf"}
        self.assertEqual(compare_txle_checkpoint_surface(document, candidate), ["case 0: ERL special scalar differs"])

    def test_unknown_source_scalar_is_rejected(self):
        document = source_summary()
        document["case_checkpoints"][0]["final_scalar_metrics"]["not_a_metric"] = source_scalar(1.0)
        with self.assertRaisesRegex(ValueError, "scalar surface"):
            project_matlab_summary(document)

    def test_projected_report_digest_is_revalidated(self):
        projected = project_matlab_summary(source_summary())
        projected[0]["txle_taps"]["raw_f64_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "digest"):
            validate_projected_txle_cases(projected, "report")

    def test_projected_comparison_honors_explicit_tolerance(self):
        source = project_matlab_summary(source_summary())
        candidate = project_rust_result(rust_result())
        candidate[0]["final_scalar_metrics"]["COM_dB"] += 2e-12
        self.assertEqual(
            compare_projected_txle_cases(source, candidate, finite_tolerance=1e-12),
            ["case 0: COM_dB differs"],
        )


if __name__ == "__main__":
    unittest.main()
