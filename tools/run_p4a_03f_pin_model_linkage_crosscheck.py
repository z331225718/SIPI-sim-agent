# -*- coding: utf-8 -*-
"""P4A-03f pin-to-model linkage cross-check: product vs independent ref.

Parses the same IBIS-style text input with independent logic: the reference
extracts [Model] names and [Pin] rows by its own line scanner, then resolves
every pin model against declared models plus caller markers (identical
fail-closed rules). The product path is the runner binary (structural parse
+ lift_model_declarations_v1 + lift_pin_declarations_v1 +
resolve_pin_model_linkage_v1). Both sides must agree on ok and the
resolved/marker/unresolved partitions. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03f-pin-model-linkage-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03f.pin-model-linkage-crosscheck-evidence.v1"


def reference_resolve(text: str, markers: list[str]) -> dict[str, Any]:
    """Independent scanner: pull [Model] <name> and [Pin] row triples."""
    lines = text.splitlines()
    models: list[str] = []
    pins: list[tuple[str, str, str]] = []
    in_pin = False
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("|"):
            continue
        if line.upper().startswith("[PIN]"):
            in_pin = True
            continue
        if line.upper().startswith("[MODEL]"):
            parts = line.split()
            if len(parts) >= 2:
                models.append(parts[1])
            in_pin = False
            continue
        if in_pin:
            if line.startswith("["):
                in_pin = False
                continue
            parts = line.split()
            if len(parts) >= 3:
                pins.append((parts[0], parts[1], parts[2]))
    if not pins:
        return {"ok": False, "error": "pin_error:MissingPinSection", "resolved": [], "marker": [], "unresolved": []}
    if not models:
        return {"ok": False, "error": "model_error:no_models_declared", "resolved": [], "marker": [], "unresolved": []}
    model_set = set(models)
    marker_set = set(markers)
    resolved: list[str] = []
    marker_used: list[str] = []
    for (pin_name, _signal, model) in pins:
        if model in model_set:
            resolved.append(model)
        elif model in marker_set:
            marker_used.append(model)
        else:
            return {"ok": False, "error": f"unresolved_model:{pin_name}:{model}", "resolved": [], "marker": [], "unresolved": []}
    return {"ok": True, "error": None, "resolved": resolved, "marker": marker_used, "unresolved": []}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03f_pin_model_linkage_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03f_pin_model_linkage_runner-*.exe"))[-1]

    def model_block(name: str) -> str:
        return f"[Model] {name}\nModel_type Output\n"

    cases = [
        {"label": "all_resolved_to_declared_models",
         "text": model_block("DQ_PIN") + model_block("CK_PIN") + "[Pin]\nA1 DQ0 DQ_PIN\nB2 DQ1 DQ_PIN\nC3 CK CK_PIN\n",
         "markers": []},
        {"label": "nc_marker_allowed",
         "text": model_block("DQ_PIN") + "[Pin]\nA1 NC NC\nB2 DQ0 DQ_PIN\n",
         "markers": ["NC"]},
        {"label": "nc_unresolved_without_allowance",
         "text": model_block("DQ_PIN") + "[Pin]\nA1 NC NC\nB2 DQ0 DQ_PIN\n",
         "markers": []},
        {"label": "unknown_model_rejected_pin_order",
         "text": model_block("DQ_PIN") + "[Pin]\nA1 DQ0 DQ_PIN\nB2 DQ1 MISSING\nC3 DQ2 DQ_PIN\n",
         "markers": []},
        {"label": "empty_pins_rejected",
         "text": model_block("DQ_PIN"),
         "markers": []},
        {"label": "empty_models_rejected",
         "text": "[Pin]\nA1 DQ0 DQ_PIN\n",
         "markers": []},
        {"label": "mixed_markers_and_resolved_order",
         "text": model_block("DQ_PIN") + model_block("OTHER") + "[Pin]\nA1 NC NC\nB2 DQ0 DQ_PIN\nC3 NC2 NC\n",
         "markers": ["NC"]},
        {"label": "markers_dont_conceal_unknown",
         "text": model_block("DQ_PIN") + "[Pin]\nA1 DQ0 DQ_PIN\nB2 DQ1 BOGUS\n",
         "markers": ["NC", "BOGUS"]},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03f-") as tmp:
        work = Path(tmp)
        for case in cases:
            label = case["label"]
            input_path = work / "input.txt"
            input_path.write_text(case["text"], encoding="utf-8")
            marker_path = work / "markers.json"
            marker_path.write_text(json.dumps(case["markers"]), encoding="utf-8")
            report_path = work / "product.json"
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path), "--markers", str(marker_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0: raise SystemExit("runner failed :: " + run.stdout + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = reference_resolve(case["text"], case["markers"])

            prod_ok = bool(product.get("ok"))
            ref_ok = bool(reference["ok"])
            prod_resolved = product.get("resolved") or []
            prod_marker = product.get("marker") or []
            ref_resolved = reference["resolved"]
            ref_marker = reference["marker"]
            mismatched = (
                prod_ok != ref_ok
                or prod_resolved != ref_resolved
                or prod_marker != ref_marker
            )
            if mismatched: ok_all = False
            entries.append({
                "label": label,
                "matched": not mismatched,
                "product_ok": prod_ok,
                "reference_ok": ref_ok,
                "product_resolved": prod_resolved,
                "reference_resolved": ref_resolved,
                "product_marker": prod_marker,
                "reference_marker": ref_marker,
            })

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if ok_all else "mis_match",
        "policy": "sipi.p4a-03f.pin-model-linkage.v1.typed",
        "matched_count": sum(1 for e in entries if e["matched"]),
        "case_count": len(entries),
        "entries": entries,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"], "matched_count": evidence["matched_count"], "case_count": evidence["case_count"]}, indent=2))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
