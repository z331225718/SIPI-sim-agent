"""Audit the session slice bookkeeping: PLAN markers, charters, verifiers,
tests and audits must all exist and be referenced consistently.

Each slice delivered in the 2026-08-16 session is registered with its PLAN
marker and its artifact paths (charter optional for decision-only slices).
The audit fails closed if any registered file disappears or if the PLAN
marker is missing, so dangling references cannot silently accumulate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.session-slices.reference-audit.v1"
PLAN = ROOT / "PLAN.md"

SLICES = [
    {
        "id": "P4A-04f",
        "plan_marker": "**P4A-04f",
        "charter": "docs/baselines/p4a-04f-vt-table-core.v1.yaml",
        "verifier": "tools/verify_p4a_04f_vt_table_core.py",
        "test": "tools/test_verify_p4a_04f_vt_table_core.py",
        "audit": "docs/baselines/audits/2026-08-16-p4a-04f-vt-table-core.md",
    },
    {
        "id": "P4A-04g",
        "plan_marker": "**P4A-04g",
        "charter": "docs/baselines/p4a-04g-ramp-package-spec-core.v1.yaml",
        "verifier": "tools/verify_p4a_04g_ramp_package_spec_core.py",
        "test": "tools/test_verify_p4a_04g_ramp_package_spec_core.py",
        "audit": "docs/baselines/audits/2026-08-16-p4a-04g-ramp-package-spec-core.md",
    },
    {
        "id": "P4B-02b1",
        "plan_marker": "**P4B-02b1",
        "charter": "docs/baselines/p4b-02b1-parameter-value-core.v1.yaml",
        "verifier": "tools/verify_p4b_02b1_parameter_value_core.py",
        "test": "tools/test_verify_p4b_02b1_parameter_value_core.py",
        "audit": "docs/baselines/audits/2026-08-16-p4b-02b1-parameter-value-core.md",
    },
    {
        "id": "P4B-02b2",
        "plan_marker": "**P4B-02b2",
        "charter": "docs/baselines/p4b-02b2-parameter-form-binding.v1.yaml",
        "verifier": "tools/verify_p4b_02b2_parameter_form_binding.py",
        "test": "tools/test_verify_p4b_02b2_parameter_form_binding.py",
        "audit": "docs/baselines/audits/2026-08-16-p4b-02b2-parameter-form-binding.md",
    },
    {
        "id": "P3C-02d",
        "plan_marker": "**P3C-02d",
        "charter": "docs/baselines/p3c-02-bathtub-decision-preflight.v1.yaml",
        "verifier": "tools/verify_p3c_02_bathtub_decision_preflight.py",
        "test": "tools/test_verify_p3c_02_bathtub_decision_preflight.py",
        "audit": "docs/baselines/audits/2026-08-16-p3c-02-bathtub-decision-preflight.md",
    },
    {
        "id": "P3C-03b",
        "plan_marker": "**P3C-03b",
        "charter": "docs/baselines/p3c-03-profile-compare-decision-preflight.v1.yaml",
        "verifier": "tools/verify_p3c_03_profile_compare_decision_preflight.py",
        "test": "tools/test_verify_p3c_03_profile_compare_decision_preflight.py",
        "audit": "docs/baselines/audits/2026-08-16-p3c-03-profile-compare-decision-preflight.md",
    },
    {
        "id": "P3B-05b",
        "plan_marker": "**P3B-05b",
        "charter": "docs/baselines/p3b-05-seed-noise-jitter-decision-preflight.v1.yaml",
        "verifier": "tools/verify_p3b_05b_seed_noise_jitter_decision_preflight.py",
        "test": "tools/test_verify_p3b_05b_seed_noise_jitter_decision_preflight.py",
        "audit": "docs/baselines/audits/2026-08-16-p3b-05b-seed-noise-jitter-decision-preflight.md",
    },
    {
        "id": "P7-08c",
        "plan_marker": "**P7-08c",
        "charter": "docs/baselines/p7-08-retirement-approval-record.v1.yaml",
        "verifier": "tools/verify_p7_08_retirement_approval_record.py",
        "test": "tools/test_verify_p7_08_retirement_approval_record.py",
        "audit": "docs/baselines/audits/2026-08-16-p7-08-retirement-approval-signed.md",
    },
    {
        "id": "P4B-04c",
        "plan_marker": "**P4B-04c",
        "charter": None,
        "verifier": "tools/verify_p4b_04_worker_partial_state.py",
        "test": "tools/test_verify_p4b_04_worker_partial_state.py",
        "audit": "docs/baselines/audits/2026-08-16-p4b-04-owner-decision-closure.md",
    },
]


class SliceAuditError(RuntimeError):
    pass


def validate(root: Path = ROOT) -> dict:
    plan_text = PLAN.read_text(encoding="utf-8")
    checked = []
    for slice_ in SLICES:
        identifier = slice_["id"]
        if slice_["plan_marker"] not in plan_text:
            raise SliceAuditError(f"plan_marker_missing:{identifier}")
        for kind in ("charter", "verifier", "test", "audit"):
            relative = slice_.get(kind)
            if relative is None:
                continue
            if not (root / relative).is_file():
                raise SliceAuditError(f"slice_file_missing:{identifier}:{kind}:{relative}")
            checked.append(relative)
    return {"valid": True, "slices": len(SLICES), "files_checked": len(checked)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except SliceAuditError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
