"""Verify the additive failure-classification layer for original-13 v2."""

from __future__ import annotations

import copy

try:
    from .matlab_oracle_failure_v2 import DOMAIN_CATALOG
    from .verify_p5_06_original13_fresh_matrix import Error, verify as verify_v1
except ImportError:
    from matlab_oracle_failure_v2 import DOMAIN_CATALOG
    from verify_p5_06_original13_fresh_matrix import Error, verify as verify_v1


FAILURES = {"oracle_source_exception", "oracle_domain_rejected", "worker_timeout", "runtime_transport_failed"}


def verify(report: object) -> bool:
    if not isinstance(report, dict) or report.get("schema") != "sipi.p5-06.original13-fresh-run.v2":
        raise Error("v2 envelope")
    base = copy.deepcopy(report)
    base["schema"] = "sipi.p5-06.original13-fresh-run.v1"
    for record in base.get("records", []):
        classification = record.pop("matlab_failure_classification", None)
        if not isinstance(classification, dict) or not isinstance(classification.get("kind"), str):
            raise Error("v2 classification")
        kind = classification["kind"]
        if record.get("status") in FAILURES:
            if record.get("status") != kind:
                raise Error("v2 status")
            if record.get("case_count") != 0 or record.get("metrics") != []:
                raise Error("v2 failed metrics")
            if kind == "oracle_domain_rejected":
                if set(classification) != {"kind", "failure_identifier_sha256", "failure_message_sha256", "failure_report_sha256", "domain_catalog"} or classification["domain_catalog"] != DOMAIN_CATALOG:
                    raise Error("v2 domain")
            elif kind == "oracle_source_exception":
                if set(classification) != {"kind", "failure_identifier_sha256", "failure_message_sha256", "failure_report_sha256"}:
                    raise Error("v2 source")
            elif classification != {"kind": kind}:
                raise Error("v2 failure")
            if any(
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
                for key, value in classification.items()
                if key.endswith("sha256")
            ):
                raise Error("v2 digest")
            record["status"] = "matlab_failed"
        elif classification != {"kind": "not_applicable"}:
            raise Error("v2 nonfailure")
    return verify_v1(base)
