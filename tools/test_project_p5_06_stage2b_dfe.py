import hashlib
import struct
import unittest

try:
    from .project_p5_06_stage2b_dfe import (
        INAPPLICABLE_REASON,
        compare_projected_dfe_cases,
        dfe_raw_receipts_equal,
        project_matlab_summary,
        project_rust_result,
        validate_projected_dfe_cases,
    )
except ImportError:
    from project_p5_06_stage2b_dfe import (
        INAPPLICABLE_REASON,
        compare_projected_dfe_cases,
        dfe_raw_receipts_equal,
        project_matlab_summary,
        project_rust_result,
        validate_projected_dfe_cases,
    )


def digest(values):
    return hashlib.sha256(b"".join(struct.pack("<d", value) for value in values)).hexdigest()


def source_case(values=(0.25, -0.0), shape=None):
    if shape is None:
        shape = [len(values), 1]
    return {
        "case_index": 1,
        "applicable": True,
        "final_scalar_metrics": {"COM_dB": {"kind": "finite", "value": -12.0}},
        "dfe_taps": {
            "class": "double",
            "shape": shape,
            "value_count": len(values),
            "storage_order": "matlab_column_major",
            "semantic_axis": "postcursor_ui_offsets_from_winner_cursor",
            "axis_origin_ui": 1,
            "axis_step_ui": 1,
            "unit": "ratio",
            "encoding": "ieee754_f64_little_endian_column_major",
            "raw_f64_sha256": digest(values),
            "column_major_values": list(values),
        },
    }


def source_summary(case=None):
    case = source_case() if case is None else case
    return {"schema_version": 1, "diagnostic_only": True, "case_count": 1, "case_checkpoints": [case]}


def rust_result(values=(0.25, -0.0)):
    return {"cases": [{
        "case_index": 0,
        "metrics": {"COM_dB": -12.0},
        "diagnostics": {"portable_branches": {"search": {"dfe_taps": list(values)}}},
    }]}


class DfeProjectionTests(unittest.TestCase):
    def test_source_column_shape_and_signed_zero_are_exact(self):
        source = project_matlab_summary(source_summary())
        self.assertEqual(source[0]["dfe_taps"]["shape"], [2, 1])
        self.assertEqual(source[0]["dfe_taps"]["raw_f64_sha256"], digest([0.25, -0.0]))

    def test_rust_uses_source_native_column_shape(self):
        source = project_matlab_summary(source_summary())
        rust = project_rust_result(rust_result(), source)
        self.assertEqual(rust[0]["dfe_taps"], source[0]["dfe_taps"])
        self.assertEqual(compare_projected_dfe_cases(source, rust), [])

    def test_empty_dfe_is_a_valid_checkpoint(self):
        source = project_matlab_summary(source_summary(source_case(values=(), shape=[0, 0])))
        rust = project_rust_result(rust_result(values=()), source)
        self.assertEqual(source[0]["dfe_taps"], {"shape": [0, 0], "values": [], "raw_f64_sha256": digest([])})
        self.assertEqual(compare_projected_dfe_cases(source, rust), [])

    def test_erl_only_is_explicitly_excluded(self):
        matlab = source_summary({
            "case_index": 1,
            "applicable": False,
            "final_scalar_metrics": {"ERL": {"kind": "inf"}},
            "dfe_taps": {"reason": INAPPLICABLE_REASON},
        })
        source = project_matlab_summary(matlab)
        rust = {"cases": [{"case_index": 0, "metrics": {"ERL": "+Inf"}, "diagnostics": {"normal_erl": {}}}]}
        self.assertEqual(source, [])
        self.assertEqual(project_rust_result(rust, source), [])

    def test_non_erl_missing_search_is_rejected(self):
        source = project_matlab_summary(source_summary())
        document = rust_result()
        del document["cases"][0]["diagnostics"]["portable_branches"]["search"]
        with self.assertRaisesRegex(ValueError, "DFE checkpoint missing"):
            project_rust_result(document, source)

    def test_row_shape_is_not_reshaped(self):
        source = project_matlab_summary(source_summary(source_case(shape=[1, 2])))
        rust = project_rust_result(rust_result(), source)
        self.assertEqual(rust[0]["dfe_taps"]["shape"], [1, 2])
        self.assertEqual(compare_projected_dfe_cases(source, rust), [])

    def test_source_axis_mutation_is_rejected(self):
        document = source_summary()
        document["case_checkpoints"][0]["dfe_taps"]["axis_origin_ui"] = 0
        with self.assertRaisesRegex(ValueError, "axis_origin_ui"):
            project_matlab_summary(document)

    def test_shape_or_order_mutation_is_rejected_by_compare(self):
        source = project_matlab_summary(source_summary())
        rust = project_rust_result(rust_result(), source)
        rust[0]["dfe_taps"]["values"].reverse()
        rust[0]["dfe_taps"]["raw_f64_sha256"] = digest(rust[0]["dfe_taps"]["values"])
        self.assertEqual(compare_projected_dfe_cases(source, rust), ["case 0: DFE[0] differs", "case 0: DFE[1] differs"])
        rust[0]["dfe_taps"]["shape"] = [1, 2]
        self.assertEqual(compare_projected_dfe_cases(source, rust), ["case 0: DFE shape differs"])

    def test_numeric_tolerance_is_separate_from_raw_receipt_identity(self):
        source = project_matlab_summary(source_summary())
        rust = project_rust_result(rust_result((0.25 + 2e-14, -0.0)), source)
        self.assertFalse(dfe_raw_receipts_equal(source, rust))
        self.assertEqual(compare_projected_dfe_cases(source, rust), [])

    def test_signed_zero_difference_is_not_hidden_by_numeric_tolerance(self):
        source = project_matlab_summary(source_summary())
        rust = project_rust_result(rust_result((0.25, 0.0)), source)
        self.assertEqual(compare_projected_dfe_cases(source, rust), ["case 0: DFE[1] signed zero differs"])

    def test_digest_mutation_is_rejected(self):
        source = project_matlab_summary(source_summary())
        source[0]["dfe_taps"]["raw_f64_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "digest"):
            validate_projected_dfe_cases(source, "report")


if __name__ == "__main__":
    unittest.main()
