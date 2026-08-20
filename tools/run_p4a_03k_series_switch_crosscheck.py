# -*- coding: utf-8 -*-
"""P4A-03k typed IBIS series switch groups cross-check (product vs independent ref).

Drives the product series switch group runner (p4a_03k_series_switch_runner) over valid
and invalid series switch group inputs. An independent Python reference recomputes
the lifting rules. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03k-series-switch-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03k.series-switch-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03k.series-switch-groups-v1.typed-switch-groups"


def ref_lift_switch_group(group_name: str, on_models: list[str], off_models: list[str]) -> dict[str, Any]:
    if not group_name or not group_name.strip():
        return {"valid": False, "lift_error": "EmptyGroupName"}
    trimmed = group_name.strip()
    if not trimmed.isascii():
        return {"valid": False, "lift_error": "NonAsciiGroupName"}
    if not all(c.isalnum() or c in "_-." for c in trimmed):
        return {"valid": False, "lift_error": "InvalidGroupName"}
    if not on_models and not off_models:
        return {"valid": False, "lift_error": "EmptyStateModels"}

    def validate_models(models: list[str]) -> tuple[list[str] | None, str | None]:
        seen = set()
        res = []
        for m in models:
            mt = m.strip()
            if not mt:
                return None, "EmptyGroupName"
            if not mt.isascii():
                return None, "NonAsciiGroupName"
            if mt in seen:
                return None, f'DuplicateModelInGroup("{mt}")'
            seen.add(mt)
            res.append(mt)
        return res, None

    on_clean, err = validate_models(on_models)
    if err:
        return {"valid": False, "lift_error": err}
    off_clean, err = validate_models(off_models)
    if err:
        return {"valid": False, "lift_error": err}

    return {
        "valid": True,
        "group_name": trimmed,
        "on_state_models": on_clean,
        "off_state_models": off_clean,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03k_series_switch_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03k_series_switch_runner-*.exe"))[-1]

    cases = [
        {
            "label": "full_switch_group",
            "group_name": "GROUP_1",
            "on_state_models": ["R_ON_50", "C_ON_1P"],
            "off_state_models": ["R_OFF_10K"],
        },
        {
            "label": "on_only_switch_group",
            "group_name": "GROUP_ON",
            "on_state_models": ["SW_ON"],
            "off_state_models": [],
        },
        {
            "label": "empty_state_models",
            "group_name": "GROUP_EMPTY",
            "on_state_models": [],
            "off_state_models": [],
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03k-") as tmp:
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
            reference = ref_lift_switch_group(case["group_name"], case["on_state_models"], case["off_state_models"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("group_name") != reference["group_name"] or
                    product.get("on_state_models") != reference["on_state_models"] or
                    product.get("off_state_models") != reference["off_state_models"]):
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
