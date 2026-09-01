import tempfile
import unittest
from pathlib import Path

try:
    from . import run_com_normal_erl_trace_diagnostic as subject
except ImportError:
    import run_com_normal_erl_trace_diagnostic as subject


class NormalErlTraceDiagnosticTests(unittest.TestCase):
    def test_special_normalizes_rust_wire_values(self):
        self.assertEqual(subject._special("inf"), "+Inf")
        self.assertEqual(subject._special("-INF"), "-Inf")
        self.assertEqual(subject._special("NaN"), "NaN")

    def test_warning_semantics_ignore_copy_path_and_line_only(self):
        original = {"identifier": "MATLAB:pragma", "message": "file: a.m line: 1\npragma warning"}
        copy = {"identifier": "MATLAB:pragma", "message": "file: b.m line: 4\npragma warning"}
        self.assertEqual(subject._warning_semantics(original), subject._warning_semantics(copy))

    def test_warning_semantics_rejects_changed_payload(self):
        original = {"identifier": "MATLAB:pragma", "message": "file: a.m\nfirst"}
        changed = {"identifier": "MATLAB:pragma", "message": "file: b.m\nsecond"}
        self.assertNotEqual(subject._warning_semantics(original), subject._warning_semantics(changed))

    def test_replace_once_rejects_missing_or_duplicate_context(self):
        with self.assertRaisesRegex(RuntimeError, "source context drift"):
            subject._replace_once("none", "needle", "replacement", "test")
        with self.assertRaisesRegex(RuntimeError, "source context drift"):
            subject._replace_once("needle needle", "needle", "replacement", "test")

    def test_instrumentation_requires_exact_pinned_source_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            source = root / subject.SOURCE_FILE
            source.parent.mkdir(parents=True)
            source.write_text("not pinned", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "pinned MATLAB source hash drift"):
                subject.instrument_matlab_source(root, Path(temporary) / "instrumented")

    def test_trace_digest_rejects_invalid_vector_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(
                '{"schema":"sipi.com.normal-erl-array-trace.v1","diagnostic_only":true,"ports":[]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "trace ports"):
                subject._trace_digests(root)

    def test_scalar_comparator_handles_exact_specials_and_tolerance(self):
        self.assertTrue(subject._scalar_equal("+Inf", "+Inf"))
        self.assertTrue(subject._scalar_equal(1.0, 1.0 + 5e-10))
        self.assertFalse(subject._scalar_equal(1.0, 1.0 + 2e-9))


if __name__ == "__main__":
    unittest.main()
