# -*- coding: utf-8 -*-
"""P3B-04b CDR lock semantics cross-check (product vs independent ref).

Drives the product CDR lock runner (p3b_04b_cdr_lock_runner) over a configuration and a timing
error sequence. An independent Python reference replicates the hysteresis lock state machine.
Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p3b-04b-cdr-lock-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p3b-04b-cdr-lock-crosscheck-evidence.v1"
POLICY = "sipi.p3b-04b.cdr-lock.v1.acquisition-hysteresis"


def ref_track(lock_threshold: float, unlock_threshold: float,
              lock_count: int, unlock_count: int,
              errors: list[float]) -> dict[str, Any]:
    if not lock_threshold > 0.0:
        return {"valid": False, "cdr_error": "InvalidLockThreshold"}
    if not unlock_threshold >= lock_threshold:
        return {"valid": False, "cdr_error": "InvalidUnlockThreshold"}
    if lock_count == 0 or unlock_count == 0:
        return {"valid": False, "cdr_error": "InvalidCount"}
    if not errors:
        return {"valid": False, "cdr_error": "EmptySequence"}

    state = "Unlocked"
    good_run = 0
    bad_run = 0
    lock_transitions = 0
    unlock_transitions = 0
    samples: list[dict[str, Any]] = []
    for index, error in enumerate(errors):
        if not math.isfinite(error):
            return {"valid": False, "cdr_error": "NonFiniteError"}
        magnitude = abs(error)
        if magnitude <= lock_threshold:
            classification = "Good"
        elif magnitude >= unlock_threshold:
            classification = "Bad"
        else:
            classification = "Neutral"
        if classification == "Good":
            bad_run = 0
            good_run += 1
            if state == "Unlocked" and good_run >= lock_count:
                state = "Locked"
                lock_transitions += 1
                good_run = 0
                bad_run = 0
        elif classification == "Bad":
            good_run = 0
            bad_run += 1
            if state == "Locked" and bad_run >= unlock_count:
                state = "Unlocked"
                unlock_transitions += 1
                good_run = 0
                bad_run = 0
        else:
            good_run = 0
            bad_run = 0
        samples.append({
            "sample_index": index + 1,
            "error": error,
            "classification": classification,
            "state_after": state,
        })
    return {"valid": True, "final_state": state, "lock_transitions": lock_transitions,
            "unlock_transitions": unlock_transitions, "samples": samples}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-channel", "--test", "p3b_04b_cdr_lock_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3b_04b_cdr_lock_runner-*.exe"))[-1]

    cases = [
        {
            "label": "acquire_and_hold",
            "lock_threshold": 0.02,
            "unlock_threshold": 0.10,
            "lock_count": 3,
            "unlock_count": 2,
            "errors": [0.01, 0.01, 0.01, 0.05, 0.05, 0.01],
        },
        {
            "label": "unlock_and_reacquire",
            "lock_threshold": 0.02,
            "unlock_threshold": 0.10,
            "lock_count": 3,
            "unlock_count": 2,
            "errors": [0.01, 0.01, 0.01, 0.20, 0.20, 0.01, 0.01, 0.01],
        },
        {
            "label": "invalid_config",
            "lock_threshold": 0.20,
            "unlock_threshold": 0.10,
            "lock_count": 3,
            "unlock_count": 2,
            "errors": [0.01, 0.01],
        },
        {
            "label": "empty_sequence",
            "lock_threshold": 0.02,
            "unlock_threshold": 0.10,
            "lock_count": 3,
            "unlock_count": 2,
            "errors": [],
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p3b-04b-") as tmp:
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
            reference = ref_track(case["lock_threshold"], case["unlock_threshold"],
                                  case["lock_count"], case["unlock_count"], case["errors"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("final_state") != reference.get("final_state") or
                    product.get("lock_transitions") != reference.get("lock_transitions") or
                    product.get("unlock_transitions") != reference.get("unlock_transitions") or
                    product.get("samples") != reference.get("samples")):
                    matched = False
            else:
                prod_err = product.get("cdr_error")
                ref_err = reference.get("cdr_error")
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
