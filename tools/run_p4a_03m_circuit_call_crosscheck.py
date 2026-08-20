# -*- coding: utf-8 -*-
"""P4A-03m typed IBIS circuit call & port mapping cross-check (product vs independent ref).

Drives the product circuit call runner (p4a_03m_circuit_call_runner) over valid
and invalid circuit call inputs. An independent Python reference recomputes the lifting rules.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03m-circuit-call-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03m.circuit-call-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03m.circuit-call-declaration-v1.typed-circuit-call"


def ref_lift_circuit_call(circuit_name: str, port_mappings: list[dict[str, str]]) -> dict[str, Any]:
    if not circuit_name or not circuit_name.strip():
        return {"valid": False, "lift_error": "EmptyCircuitName"}
    trimmed = circuit_name.strip()
    if not trimmed.isascii():
        return {"valid": False, "lift_error": "NonAsciiName"}
    if not all(c.isalnum() or c in "_-." for c in trimmed):
        return {"valid": False, "lift_error": "InvalidName"}
    if not port_mappings:
        return {"valid": False, "lift_error": "EmptyPortMappings"}

    seen = set()
    cleaned = []
    for pm in port_mappings:
        p = pm.get("port_name", "").strip()
        n = pm.get("node_name", "").strip()
        if not p or not n:
            return {"valid": False, "lift_error": "EmptyCircuitName"}
        if not p.isascii() or not n.isascii():
            return {"valid": False, "lift_error": "NonAsciiName"}
        if p in seen:
            return {"valid": False, "lift_error": "DuplicatePortName(\"" + p + "\")"}
        seen.add(p)
        cleaned.append({"port_name": p, "node_name": n})

    return {
        "valid": True,
        "circuit_name": trimmed,
        "port_mapping_count": len(cleaned),
        "port_mappings": cleaned,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03m_circuit_call_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03m_circuit_call_runner-*.exe"))[-1]

    cases = [
        {
            "label": "valid_circuit_call",
            "circuit_name": "SUBCKT_DIFF",
            "port_mappings": [
                {"port_name": "P1", "node_name": "N1"},
                {"port_name": "P2", "node_name": "N2"},
            ],
        },
        {
            "label": "single_port_mapping",
            "circuit_name": "SUBCKT_1",
            "port_mappings": [
                {"port_name": "P1", "node_name": "N1"},
            ],
        },
        {
            "label": "duplicate_port_name",
            "circuit_name": "SUBCKT_DUP",
            "port_mappings": [
                {"port_name": "P1", "node_name": "N1"},
                {"port_name": "P1", "node_name": "N2"},
            ],
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03m-") as tmp:
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
            reference = ref_lift_circuit_call(case["circuit_name"], case["port_mappings"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("circuit_name") != reference["circuit_name"] or
                    product.get("port_mapping_count") != reference["port_mapping_count"] or
                    product.get("port_mappings") != reference["port_mappings"]):
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
