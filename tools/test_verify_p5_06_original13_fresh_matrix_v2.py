from __future__ import annotations

import copy
import unittest

from tools.matlab_oracle_failure_v2 import DOMAIN_CATALOG
from tools.test_verify_p5_06_original13_fresh_matrix import sample
from tools.verify_p5_06_original13_fresh_matrix import Error
from tools.verify_p5_06_original13_fresh_matrix_v2 import verify


def v2() -> dict:
    report = sample()
    report["schema"] = "sipi.p5-06.original13-fresh-run.v2"
    report["engine"] = "matlab"
    report["records"][0]["status"] = "oracle_domain_rejected"
    report["records"][0]["config_materialization"] = {"comparison": "worker_failed"}
    report["records"][0]["matlab_failure_classification"] = {
        "kind": "oracle_domain_rejected",
        "failure_identifier_sha256": "a" * 64,
        "failure_message_sha256": "b" * 64,
        "failure_report_sha256": "c" * 64,
        "domain_catalog": DOMAIN_CATALOG,
    }
    return report


class Original13V2Tests(unittest.TestCase):
    def test_domain_rejection_is_valid_but_not_a_success(self) -> None:
        self.assertTrue(verify(v2()))

    def test_missing_or_inconsistent_classification_is_rejected(self) -> None:
        for mutate in (
            lambda value: value["records"][0].pop("matlab_failure_classification"),
            lambda value: value["records"][0]["matlab_failure_classification"].__setitem__("kind", "runtime_transport_failed"),
            lambda value: value["records"][0]["matlab_failure_classification"].__setitem__("domain_catalog", "unbound"),
            lambda value: value["records"][0].__setitem__("case_count", 1),
        ):
            report = v2()
            mutate(report)
            with self.assertRaises(Error):
                verify(report)

    def test_non_failure_records_require_not_applicable_marker(self) -> None:
        report = v2()
        report["records"][0]["status"] = "candidate_timeout"
        report["records"][0]["matlab_failure_classification"] = {"kind": "runtime_transport_failed"}
        with self.assertRaises(Error):
            verify(report)
        report = copy.deepcopy(v2())
        report["records"][0]["status"] = "candidate_timeout"
        report["records"][0]["matlab_failure_classification"] = {"kind": "not_applicable"}
        self.assertTrue(verify(report))


if __name__ == "__main__":
    unittest.main()
