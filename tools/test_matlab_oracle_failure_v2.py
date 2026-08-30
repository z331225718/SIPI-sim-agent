from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.matlab_oracle_failure_v2 import ANTI_CAUSAL_MESSAGE, DOMAIN_CATALOG, classify_matlab_failure


class MatlabOracleFailureTests(unittest.TestCase):
    def failure(self, root: Path, identifier: str = "", message: str = ANTI_CAUSAL_MESSAGE, report: str = "Error using com_ieee8023_480 (line 6339)\n") -> None:
        (root / "failure.json").write_text(json.dumps({"identifier": identifier, "message": message, "report": report}), encoding="utf-8")

    def test_known_anti_causal_error_is_a_domain_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.failure(root)
            result = classify_matlab_failure(1, False, root)
        self.assertEqual(result["kind"], "oracle_domain_rejected")
        self.assertEqual(result["domain_catalog"], DOMAIN_CATALOG)
        self.assertEqual(result["failure_message_sha256"], hashlib.sha256(ANTI_CAUSAL_MESSAGE.encode()).hexdigest())

    def test_stderr_text_alone_never_becomes_a_domain_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(classify_matlab_failure(1, False, Path(raw)), {"kind": "runtime_transport_failed"})

    def test_other_oracle_exception_is_hash_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.failure(root, "COM:BadExtraParameter", "C:\\Users\\secret\\input.xlsx", "Error using com_ieee8023_480 (line 190)")
            result = classify_matlab_failure(1, False, root)
        self.assertEqual(result["kind"], "oracle_source_exception")
        self.assertNotIn("C:\\Users", json.dumps(result))
        self.assertNotIn("input.xlsx", json.dumps(result))

    def test_malformed_or_oversized_artifact_is_transport_failure(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "failure.json").write_text("[]", encoding="utf-8")
            self.assertEqual(classify_matlab_failure(1, False, root), {"kind": "runtime_transport_failed"})
            (root / "failure.json").write_bytes(b"x" * (128 * 1024 + 1))
            self.assertEqual(classify_matlab_failure(1, False, root), {"kind": "runtime_transport_failed"})

    def test_timeout_wins_over_any_oracle_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.failure(root)
            self.assertEqual(classify_matlab_failure(124, True, root), {"kind": "worker_timeout"})


if __name__ == "__main__":
    unittest.main()
