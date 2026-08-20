# -*- coding: utf-8 -*-
"""P4A-03g typed IBIS component declaration cross-check (product vs independent ref).

Drives the product component declaration runner (p4a_03g_component_declaration_runner)
over valid and invalid component declaration inputs. An independent Python reference
recomputes the lifting rules. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03g-component-declaration-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03g.component-declaration-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03g.component-declaration-v1.typed-component"


def ref_lift_component(name: str, manufacturer: str | None, package_name: str | None) -> dict[str, Any]:
    if not name or not name.strip():
        return {"valid": False, "lift_error": "EmptyName"}
    trimmed = name.strip()
    if not trimmed.isascii():
        return {"valid": False, "lift_error": "NonAsciiName"}
    if not all(c.isalnum() or c in "_-." for c in trimmed):
        return {"valid": False, "lift_error": "InvalidName"}
    m = manufacturer.strip() if manufacturer and manufacturer.strip() else None
    p = package_name.strip() if package_name and package_name.strip() else None
    return {
        "valid": True,
        "name": trimmed,
        "manufacturer": m,
        "package_name": p,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03g_component_declaration_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03g_component_declaration_runner-*.exe"))[-1]

    cases = [
        {
            "label": "full_component",
            "name": "AS4C512M8S1",
            "manufacturer": "Alliance Memory",
            "package_name": "FBGA84",
        },
        {
            "label": "minimal_component",
            "name": "CHIP_V1.0",
            "manufacturer": None,
            "package_name": None,
        },
        {
            "label": "invalid_name",
            "name": "CHIP @1",
            "manufacturer": "Vendor",
            "package_name": "PKG",
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03g-") as tmp:
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
            reference = ref_lift_component(case["name"], case["manufacturer"], case["package_name"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            if product.get("valid"):
                if (product.get("name") != reference["name"] or
                    product.get("manufacturer") != reference["manufacturer"] or
                    product.get("package_name") != reference["package_name"]):
                    matched = False
            else:
                if product.get("lift_error") != reference["lift_error"]:
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
