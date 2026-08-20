# -*- coding: utf-8 -*-
"""P4A-03ad typed IBIS model selector keywords cross-check (product vs independent ref).

Drives the product model selector keywords runner (p4a_03ad_model_selector_keywords_runner) over valid
and invalid model selector inputs. An independent Python reference recomputes the lifting rules.
Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03ad-model-selector-keywords-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03ad.model-selector-keywords-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03ad.model-selector-keywords-v1.typed-selector-keywords"


def ref_lift_model_selector(sname: str, options: list[dict[str, Any]]) -> dict[str, Any]:
    if not sname or not sname.strip():
        return {"valid": False, "lift_error": "EmptySelectorName"}
    s_trimmed = sname.strip()
    if not s_trimmed.isascii():
        return {"valid": False, "lift_error": "NonAsciiName"}
    if not all(c.isalnum() or c in "_-." for c in s_trimmed):
        return {"valid": False, "lift_error": "InvalidName"}
    if not options:
        return {"valid": False, "lift_error": "EmptyModelOptions"}

    seen = set()
    clean_opts = []
    for opt in options:
        mn = opt.get("model_name", "").strip()
        desc = opt.get("description")
        if not mn:
            return {"valid": False, "lift_error": "EmptySelectorName"}
        if not mn.isascii():
            return {"valid": False, "lift_error": "NonAsciiName"}
        if not all(c.isalnum() or c in "_-." for c in mn):
            return {"valid": False, "lift_error": "InvalidName"}
        desc_clean = None
        if desc and desc.strip():
            desc_clean = desc.strip()
            if not desc_clean.isascii():
                return {"valid": False, "lift_error": "NonAsciiName"}
        if mn in seen:
            return {"valid": False, "lift_error": f'DuplicateModelOption("{mn}")'}
        seen.add(mn)
        clean_opts.append({"model_name": mn, "description": desc_clean})

    return {
        "valid": True,
        "selector_name": s_trimmed,
        "option_count": len(clean_opts),
        "model_options": clean_opts,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03ad_model_selector_keywords_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03ad_model_selector_keywords_runner-*.exe"))[-1]

    cases = [
        {
            "label": "valid_model_selector",
            "selector_name": "SEL_DRV_IMP",
            "model_options": [
                {"model_name": "MODE_50OHM", "description": "50 Ohm Driver"},
                {"model_name": "MODE_40OHM", "description": "40 Ohm Driver"},
            ],
        },
        {
            "label": "empty_model_options",
            "selector_name": "SEL_1",
            "model_options": [],
        },
        {
            "label": "duplicate_model_option",
            "selector_name": "SEL_1",
            "model_options": [
                {"model_name": "MODE_50OHM", "description": None},
                {"model_name": "MODE_50OHM", "description": None},
            ],
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03ad-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_path = work / f"{case['label']}_in.json"
            input_path.write_text(json.dumps(case), encoding="utf-8")
            report_path = work / f"{case['label']}_rep.json"
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0:
                raise SystemExit(f"runner failed for {case['label']}: " + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = ref_lift_model_selector(case["selector_name"], case["model_options"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("selector_name") != reference["selector_name"] or
                    product.get("option_count") != reference["option_count"] or
                    product.get("model_options") != reference["model_options"]):
                    matched = False
            else:
                if str(product.get("lift_error")) != str(reference.get("lift_error")):
                    matched = False

            if not matched:
                ok_all = False

            entries.append({
                "label": case["label"],
                "matched": matched,
                "product": product,
                "reference": reference,
            })

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if ok_all else "mis_match",
        "policy": POLICY,
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
