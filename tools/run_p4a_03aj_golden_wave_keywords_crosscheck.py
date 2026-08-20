# -*- coding: utf-8 -*-
"""P4A-03aj typed IBIS golden waveforms block keywords cross-check (product vs independent ref).

Drives the product golden waveforms block runner (p4a_03aj_golden_wave_keywords_runner) over valid
and invalid golden waveform block inputs. An independent Python reference recomputes the lifting rules.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03aj-golden-wave-keywords-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03aj.golden-wave-keywords-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03aj.golden-wave-keywords-v1.typed-golden-keywords"


def ref_lift_golden_wave_block(wname: str, dname: str | None) -> dict[str, Any]:
    if not wname or not wname.strip():
        return {"valid": False, "waveform_error": "EmptyWaveformName"}
    w_trimmed = wname.strip()
    if not w_trimmed.isascii():
        return {"valid": False, "waveform_error": "NonAsciiName"}
    if not all(c.isalnum() or c in "_-." for c in w_trimmed):
        return {"valid": False, "waveform_error": "InvalidName"}

    d_trimmed = None
    if dname and dname.strip():
        d_trimmed = dname.strip()
        if not d_trimmed.isascii():
            return {"valid": False, "waveform_error": "NonAsciiName"}
        if not all(c.isalnum() or c in "_-." for c in d_trimmed):
            return {"valid": False, "waveform_error": "InvalidName"}

    return {
        "valid": True,
        "waveform_name": w_trimmed,
        "dut_name": d_trimmed,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03aj_golden_wave_keywords_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03aj_golden_wave_keywords_runner-*.exe"))[-1]

    cases = [
        {
            "label": "full_golden_wave_block",
            "waveform_name": "GOLDEN_WAVE_1",
            "dut_name": "DUT_FBGA84",
        },
        {
            "label": "minimal_golden_wave_block",
            "waveform_name": "WAVE_MIN",
            "dut_name": None,
        },
        {
            "label": "invalid_name_characters",
            "waveform_name": "WAVE @1",
            "dut_name": None,
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03aj-") as tmp:
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
            reference = ref_lift_golden_wave_block(case["waveform_name"], case["dut_name"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("waveform_name") != reference["waveform_name"] or
                    product.get("dut_name") != reference["dut_name"]):
                    matched = False
            else:
                prod_err = product.get("lift_error") or product.get("waveform_error")
                ref_err = reference.get("lift_error") or reference.get("waveform_error")
                if str(prod_err) != str(ref_err):
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
