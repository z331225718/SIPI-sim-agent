# -*- coding: utf-8 -*-
"""P5-06d canonical-input-key signature cross-check: product vs independent ref.

Builds the sorted canonical 'key=value' signature lines for a set of
normalized COM input keys and a SHA-256 digest over the lines joined with a
newline. The product path is canonical_input_keys_v1 via the runner binary;
the reference recomputes the same sorted lines and digest from-scratch.

Two layers are verified:
1. Synthetic cases: the product sorted lines + digest must match the
   independent Python reference exactly across happy/fail/low-bound cases.
2. The authoritative surface: extracting the P5-06c 'in_config' keys from
   the normalized-input surface and running them through the product must
   yield the same digest as recomputing in Python over the same canonical
   value tokens. Fail closed on any mismatch.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06d-canonical-input-keys-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-06d.canonical-input-keys-crosscheck-evidence.v1"
SURFACE = ROOT / "docs" / "baselines" / "p5-06-normalized-input-surface.v1.yaml"


def reference_digest(entries: list[list[str]]) -> dict[str, Any]:
    """Independent reference: sorted 'key=value' lines + sha256(void)."""
    if not entries:
        return {"ok": False, "error": "empty_input", "lines": [], "digest": None}
    seen = set()
    for key, value in entries:
        if key == "":
            return {"ok": False, "error": "empty_key", "lines": [], "digest": None}
        if value == "":
            return {"ok": False, "error": "empty_value", "lines": [], "digest": None}
        if key in seen:
            return {"ok": False, "error": f"duplicate_key:{key}", "lines": [], "digest": None}
        seen.add(key)
    lines = sorted(f"{k}={v}" for k, v in entries)
    joined = "\n".join(lines).encode("utf-8")
    digest = hashlib.sha256(joined).hexdigest()
    return {"ok": True, "error": None, "lines": lines, "digest": digest}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-com", "--test", "p5_06d_canonical_input_keys_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_06d_canonical_input_keys_runner-*.exe"))[-1]

    def run_case(entries):
        input_path = Path(tempfile.mkdtemp(prefix="p5-06d-")) / "input.json"
        input_path.write_text(json.dumps(entries, separators=(",", ":")), encoding="utf-8")
        report_path = input_path.with_name("product.json")
        r = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0: raise SystemExit("runner failed :: " + r.stdout + r.stderr)
        return json.loads(report_path.read_text(encoding="utf-8"))

    cases = [
        {"label": "three_keys_sorted", "entries": [["zeta", "1.0"], ["alpha", "0.5"], ["beta_x", "0"]]},
        {"label": "unsorted_input_stable_digest", "entries": [["b", "2"], ["a", "1"], ["c", "3"]]},
        {"label": "empty_key_fails", "entries": [["", "1"]]},
        {"label": "empty_value_fails", "entries": [["k", ""]]},
        {"label": "duplicate_key_fails", "entries": [["k", "1"], ["k", "2"]]},
        {"label": "empty_input_fails", "entries": []},
        {"label": "value_tokens_with_spaces", "entries": [["board_tl_gamma0_a1_a2", "[0 3.82e-04  9.59e-05]"], ["a_v", "0.415"]]},
        {"label": "nested_token_list", "entries": [["weights", "[1 2 3]"], ["flag", "True"], ["name", "tx"]]},
    ]

    entries_records = []
    ok_all = True
    for case in cases:
        product = run_case(case["entries"])
        reference = reference_digest(case["entries"])
        prod_ok = bool(product.get("ok"))
        ref_ok = bool(reference["ok"])
        prod_lines = product.get("lines") or []
        ref_lines = reference["lines"]
        prod_digest = product.get("digest")
        ref_digest = reference["digest"]
        mismatched = (prod_ok != ref_ok) or (prod_lines != ref_lines) or (prod_digest != ref_digest)
        if mismatched: ok_all = False
        entries_records.append({
            "label": case["label"],
            "matched": not mismatched,
            "product_ok": prod_ok,
            "reference_ok": ref_ok,
            "product_lines": prod_lines,
            "reference_lines": ref_lines,
            "product_digest": prod_digest,
            "reference_digest": ref_digest,
        })

    # Authoritative surface check: extract in_config keys from P5-06c surface.
    surface = yaml.safe_load(SURFACE.read_text(encoding="utf-8"))
    keys = surface.get("keys", {})
    in_config_entries = []
    for k, v in keys.items():
        if v.get("in_config") is True:
            value_token = v.get("config_value")
            # canonical token: numbers -> str; strings kept verbatim
            if isinstance(value_token, bool):
                token = "True" if value_token else "False"
            elif isinstance(value_token, (int, float)):
                token = str(value_token)
            else:
                token = str(value_token)
            in_config_entries.append([k, token])
    product_surface = run_case(in_config_entries)
    reference_surface = reference_digest(in_config_entries)
    surface_matched = (
        bool(product_surface.get("ok")) == bool(reference_surface["ok"])
        and (product_surface.get("lines") or []) == reference_surface["lines"]
        and product_surface.get("digest") == reference_surface["digest"]
        and bool(product_surface.get("ok"))
    )
    if not surface_matched: ok_all = False
    entries_records.append({
        "label": "authoritative_in_config_surface",
        "matched": surface_matched,
        "product_ok": bool(product_surface.get("ok")),
        "reference_ok": bool(reference_surface["ok"]),
        "surface_in_config_count": len(in_config_entries),
        "product_digest": product_surface.get("digest"),
        "reference_digest": reference_surface["digest"],
    })

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if ok_all else "mis_match",
        "policy": "sipi.p5-06d.canonical-input-keys.v1.sorted-signature",
        "matched_count": sum(1 for e in entries_records if e["matched"]),
        "case_count": len(entries_records),
        "entries": entries_records,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"],
                      "matched_count": evidence["matched_count"], "case_count": evidence["case_count"]}, indent=2))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())