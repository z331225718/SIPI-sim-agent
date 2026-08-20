# -*- coding: utf-8 -*-
"""P5-05f COM parameter surface resolver cross-check (product vs independent ref).

Drives the product parameter resolver runner (p5_05f_parameter_resolver_runner)
over merged COM DTO inputs. An independent Python reference recomputes the control
resolution rules. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-05f-parameter-resolver-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-05f.parameter-resolver-crosscheck-evidence.v1"
POLICY = "sipi.p5-05f.com-parameter-resolver-v1.dto-to-controls"

REQUIRED_SCALARS = {
    "samples_per_ui": ["samples_per_ui", "SAMP_PER_UI", "N_v"],
    "levels": ["LEVELS", "PAM_LEVELS", "levels"],
    "bin_size": ["bin_size", "BIN_SIZE"],
    "A_v": ["A_v", "AVAILABLE_SIGNAL"],
    "R_LM": ["R_LM", "R_LM_OHM"],
    "SNR_TX": ["SNR_TX", "TX_SNR_DB"],
    "sigma_X": ["sigma_X", "SIGMA_X"],
    "sigma_RJ": ["sigma_RJ", "SIGMA_RJ"],
    "sigma_N": ["sigma_N", "SIGMA_N"],
    "A_DD": ["A_DD", "AMPLITUDE_DD"],
    "spec_ber": ["spec_ber", "SPEC_BER"],
}

REQUIRED_VECTORS = {
    "h_J": ["h_J", "JITTER_RESPONSE"],
}


def ref_resolve_controls(consumed: dict[str, Any]) -> dict[str, Any]:
    if not consumed:
        return {"valid": False, "resolver_error": "EmptyDto"}

    for norm_name, aliases in REQUIRED_SCALARS.items():
        found = False
        for a in aliases:
            if a in consumed:
                val = consumed[a]
                if "Scalar" in val:
                    found = True
                    break
                elif "Vector" in val and len(val["Vector"]) == 1:
                    found = True
                    break
                else:
                    return {"valid": False, "resolver_error": f'InvalidType("{a}")'}
        if not found:
            return {"valid": False, "resolver_error": f'MissingKey("{aliases[0]}")'}

    for norm_name, aliases in REQUIRED_VECTORS.items():
        found = False
        for a in aliases:
            if a in consumed:
                val = consumed[a]
                if "Vector" in val or "Scalar" in val:
                    found = True
                    break
                else:
                    return {"valid": False, "resolver_error": f'InvalidType("{a}")'}
        if not found:
            return {"valid": False, "resolver_error": f'MissingKey("{aliases[0]}")'}

    return {"valid": True, "consumed_count": len(consumed)}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-com", "--test", "p5_05f_parameter_resolver_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_05f_parameter_resolver_runner-*.exe"))[-1]

    valid_consumed = {
        "samples_per_ui": {"Scalar": 8.0},
        "LEVELS": {"Scalar": 4.0},
        "bin_size": {"Scalar": 0.01},
        "A_v": {"Scalar": 0.5},
        "R_LM": {"Scalar": 50.0},
        "SNR_TX": {"Scalar": 30.0},
        "sigma_X": {"Scalar": 0.03},
        "sigma_RJ": {"Scalar": 1e-4},
        "h_J": {"Vector": [0.3, 0.5, 0.2]},
        "sigma_N": {"Scalar": 0.01},
        "A_DD": {"Scalar": 0.4},
        "spec_ber": {"Scalar": 1e-4},
    }

    missing_consumed = {k: v for k, v in valid_consumed.items() if k != "A_v"}

    invalid_type_consumed = dict(valid_consumed)
    invalid_type_consumed["samples_per_ui"] = {"String": "invalid"}

    cases = [
        {"label": "valid_dto", "consumed": valid_consumed},
        {"label": "missing_required_key", "consumed": missing_consumed},
        {"label": "invalid_type", "consumed": invalid_type_consumed},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-05f-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_path = work / f"{case['label']}_in.json"
            input_path.write_text(json.dumps({"consumed": case["consumed"]}), encoding="utf-8")
            report_path = work / f"{case['label']}_rep.json"
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0:
                raise SystemExit(f"runner failed for {case['label']}: " + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = ref_resolve_controls(case["consumed"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            if product.get("valid"):
                if product.get("consumed_count") != reference["consumed_count"]:
                    matched = False
            else:
                if str(product.get("resolver_error")) != str(reference.get("resolver_error")):
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
