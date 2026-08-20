# -*- coding: utf-8 -*-
"""P5-02n warning-report aggregator cross-check: product vs independent ref.

Aggregates per-array deterministic warning flags (P5-02m: anti-causal,
high-frequency non-decay) into a single stable report: the lexicographically
sorted active warning codes, the per-code flagging-slice lists (in input
order), and the total flagged-slice count. Product path is
aggregate_warning_report_v1 via the runner binary; the reference recomputes
the same stable aggregation from scratch. Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-02n-warning-report-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-02n.warning-report-crosscheck-evidence.v1"


def reference_aggregate(rows: list[list[Any]]) -> dict[str, Any]:
    """Independent reference: sorted active codes + per-code flagging slices."""
    if not rows:
        return {"ok": False, "error": "empty_reports", "active_codes": [], "flagged_total": 0, "per_code": []}
    for name, anti, high in rows:
        if name == "":
            return {"ok": False, "error": "empty_slice_name", "active_codes": [], "flagged_total": 0, "per_code": []}
    active = []
    per_code = []
    for token, field in (("anti_causal", 1), ("high_freq_non_decay", 2)):
        # flagging slices: rows where column [field] (1=anti, 2=high) is True

        flagging = [r[0] for r in rows if bool(r[field])]
        if flagging:
            active.append(token)
            per_code.append({"code": token, "slices": flagging})
    flagged_total = sum(1 for r in rows if bool(r[1]) or bool(r[2]))
    return {"ok": True, "error": None, "active_codes": active, "flagged_total": flagged_total, "per_code": per_code}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-com", "--test", "p5_02n_warning_report_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_02n_warning_report_runner-*.exe"))[-1]

    cases = [
        {"label": "union_sorted", "rows": [["pad", True, False], ["die", False, True], ["pk", True, True]]},
        {"label": "none_active", "rows": [["pad", False, False], ["die", False, False]]},
        {"label": "single_code_high_freq", "rows": [["a", False, True], ["b", False, True]]},
        {"label": "single_code_anti_causal", "rows": [["x", True, False], ["y", True, False], ["z", True, False]]},
        {"label": "empty_reports_fails", "rows": []},
        {"label": "empty_slice_name_fails", "rows": [["", True, False]]},
        {"label": "mixed_active_and_clean_slices", "rows": [["good", False, False], ["bad_anti", True, False], ["bad_high", False, True]]},
        {"label": "all_flags_all_slices", "rows": [["a", True, True], ["b", True, True]]},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-02n-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_path = work / "input.json"
            input_path.write_text(json.dumps(case["rows"], separators=(",", ":")), encoding="utf-8")
            report_path = work / "product.json"
            r = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0: raise SystemExit("runner failed :: " + r.stdout + r.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = reference_aggregate(case["rows"])
            mismatched = (
                bool(product.get("ok")) != bool(reference["ok"])
                or (product.get("active_codes") or []) != reference["active_codes"]
                or (product.get("flagged_total") or 0) != reference["flagged_total"]
                or (product.get("per_code") or []) != reference["per_code"]
            )
            if mismatched: ok_all = False
            entries.append({
                "label": case["label"],
                "matched": not mismatched,
                "product_ok": bool(product.get("ok")),
                "reference_ok": bool(reference["ok"]),
                "product_active": product.get("active_codes") or [],
                "reference_active": reference["active_codes"],
                "product_flagged_total": product.get("flagged_total") or 0,
                "reference_flagged_total": reference["flagged_total"],
            })

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if ok_all else "mis_match",
        "policy": "sipi.p5-02n.warning-report.v1.aggregate",
        "matched_count": sum(1 for e in entries if e["matched"]),
        "case_count": len(entries),
        "entries": entries,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"],
                      "matched_count": evidence["matched_count"], "case_count": evidence["case_count"]}, indent=2))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())