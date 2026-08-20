# -*- coding: utf-8 -*-
"""P4A-03ab typed IBIS model declaration keywords cross-check (product vs independent ref).

Drives the product model keywords runner (p4a_03ab_model_keywords_runner) over valid
and invalid model sub-keyword configurations. An independent Python reference recomputes the validation rules.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03ab-model-keywords-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03ab.model-keywords-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03ab.model-keywords-v1.typed-model-keywords"


def ref_validate_model_keywords(model_type: str, has_pullup: bool, has_pulldown: bool,
                                has_gnd_clamp: bool, has_power_clamp: bool) -> dict[str, Any]:
    mtype = model_type.strip().lower()
    if mtype in ("output", "io", "i/o", "3state", "3-state"):
        if not has_pullup:
            return {"valid": False, "validation_error": f'MissingRequiredSubKeyword {{ model_type: "{model_type}", missing_keyword: "[Pullup]" }}'}
        if not has_pulldown:
            return {"valid": False, "validation_error": f'MissingRequiredSubKeyword {{ model_type: "{model_type}", missing_keyword: "[Pulldown]" }}'}

    return {
        "valid": True,
        "model_type": model_type,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03ab_model_keywords_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03ab_model_keywords_runner-*.exe"))[-1]

    cases = [
        {
            "label": "valid_output_keywords",
            "model_type": "Output",
            "has_pullup": True,
            "has_pulldown": True,
            "has_gnd_clamp": True,
            "has_power_clamp": True,
        },
        {
            "label": "missing_pullup_output",
            "model_type": "Output",
            "has_pullup": False,
            "has_pulldown": True,
            "has_gnd_clamp": True,
            "has_power_clamp": True,
        },
        {
            "label": "missing_pulldown_output",
            "model_type": "Output",
            "has_pullup": True,
            "has_pulldown": False,
            "has_gnd_clamp": True,
            "has_power_clamp": True,
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03ab-") as tmp:
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
            reference = ref_validate_model_keywords(
                case["model_type"], case["has_pullup"], case["has_pulldown"],
                case["has_gnd_clamp"], case["has_power_clamp"]
            )

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if product.get("model_type") != reference["model_type"]:
                    matched = False
            else:
                if str(product.get("validation_error")) != str(reference.get("validation_error")):
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
