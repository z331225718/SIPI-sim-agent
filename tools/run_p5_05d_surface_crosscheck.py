"""P5-05d parameter surface cross-check: product runner vs oracle surface.

Extracts every (key, value) pair from the authorized COM_Settings xlsx
(hash-pinned) with the r4.80 lookup scan semantics and classifies the
unique keys against the canonical consumption key set observed from the
authorized MATLAB r4.80 source (214 keys). The oracle extraction runs in
fresh external custody on ComSettings.from_xlsx; the product runner
consumes the same workbook. CSV/MAT fixture surfaces are exercised for
the same extraction semantics. Hash-only evidence; no release claim.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
COM_SRC = Path(r"C:\Users\z3312\code\COM\src")
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
REFERENCE = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-reference.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-05d-surface-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-05d.surface-crosscheck-evidence.v1"
MATERIAL_ID = "com-r480-config-120g-c2m"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def oracle_kind_name(value: object) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "Bool"
    if isinstance(value, int):
        return "Integer"
    if isinstance(value, float):
        return "Number"
    if isinstance(value, str):
        return "String"
    return "Array"


def extract_pairs(settings) -> list[dict[str, object]]:
    pairs = []
    for row in settings.rows:
        for index, cell in enumerate(row):
            if not (isinstance(cell.value, str) and cell.value.strip()):
                continue
            if index + 1 >= len(row) or row[index + 1].value is None:
                continue
            right = row[index + 1]
            pairs.append({
                "key": cell.value,
                "left": cell.coordinate,
                "right": right.coordinate,
                "value_kind": oracle_kind_name(right.value),
            })
    return pairs


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    from agent_com.config.excel import ComSettings

    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    materials = {m["id"]: m for m in registry["materials"]}
    material = materials.get(MATERIAL_ID)
    if material is None:
        raise SystemExit("missing material: " + MATERIAL_ID)
    source = Path(str(material["path"]).replace("/", "\\"))
    if sha256_bytes(source.read_bytes()) != material["sha256"].lower():
        raise SystemExit("hash drift: " + MATERIAL_ID)

    reference = yaml.safe_load(REFERENCE.read_text(encoding="utf-8"))
    canonical_keys = sorted(reference["keys"].keys())
    canonical_bytes = json.dumps(canonical_keys, separators=(",", ":")).encode("utf-8")

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_05d_surface_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_05d_surface_runner-*.exe"))[-1]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-05d-crosscheck-") as tmp:
        work = Path(tmp)
        canonical_path = work / "canonical.json"
        canonical_path.write_bytes(canonical_bytes)
        # --- xlsx surface (authorized config) ---
        work_xlsx = work / "config.xlsx"
        import shutil
        shutil.copy2(source, work_xlsx)
        oracle = ComSettings.from_xlsx(source)
        oracle_pairs = extract_pairs(oracle)
        oracle_keys = sorted({entry["key"] for entry in oracle_pairs})
        oracle_consumed = sorted(set(oracle_keys) & set(canonical_keys))
        oracle_unconsumed = sorted(set(oracle_keys) - set(canonical_keys))
        report_path = work / "xlsx-product.json"
        run = subprocess.run(
            [str(runner), "--settings", str(work_xlsx), "--kind", "xlsx",
             "--canonical", str(canonical_path), "--report", str(report_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if run.returncode != 0:
            raise SystemExit("xlsx runner failed: " + run.stdout + run.stderr)
        product = json.loads(report_path.read_text(encoding="utf-8"))
        surface = product["surface"]
        diffs = []
        if len(surface["pairs"]) != len(oracle_pairs):
            diffs.append("pairs " + str(len(surface["pairs"])) + " vs " + str(len(oracle_pairs)))
        else:
            for expected, actual in zip(oracle_pairs, surface["pairs"]):
                if expected != actual:
                    diffs.append("pair " + json.dumps(expected) + " vs " + json.dumps(actual))
                    break
        if surface["consumed"] != oracle_consumed:
            diffs.append("consumed drift")
        if surface["unconsumed"] != oracle_unconsumed:
            diffs.append("unconsumed drift")
        entries.append({
            "id": "xlsx_authorized_config",
            "kind": "xlsx",
            "settings_sha256": product["settings_sha256"],
            "pairs": len(surface["pairs"]),
            "unique_keys": len(oracle_keys),
            "consumed": len(oracle_consumed),
            "unconsumed": len(oracle_unconsumed),
            "matched": not diffs,
            "diffs": diffs[:10],
        })
        # --- csv fixture surface ---
        csv_fixture = (
            "f_b,53.125\r\n"
            "unused_csv_key,value\r\n"
            "A_ft,0.6\r\n"
        )
        csv_path = work / "config.csv"
        csv_path.write_bytes(b"\xef\xbb\xbf" + csv_fixture.encode("utf-8"))
        oracle_csv = ComSettings.from_csv(csv_path)
        oracle_csv_pairs = extract_pairs(oracle_csv)
        oracle_csv_keys = sorted({entry["key"] for entry in oracle_csv_pairs})
        oracle_csv_consumed = sorted(set(oracle_csv_keys) & set(canonical_keys))
        oracle_csv_unconsumed = sorted(set(oracle_csv_keys) - set(canonical_keys))
        csv_report = work / "csv-product.json"
        run = subprocess.run(
            [str(runner), "--settings", str(csv_path), "--kind", "csv",
             "--canonical", str(canonical_path), "--report", str(csv_report)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if run.returncode != 0:
            raise SystemExit("csv runner failed: " + run.stdout + run.stderr)
        csv_product = json.loads(csv_report.read_text(encoding="utf-8"))
        csv_surface = csv_product["surface"]
        csv_diffs = []
        if len(csv_surface["pairs"]) != len(oracle_csv_pairs):
            csv_diffs.append("pairs")
        else:
            for expected, actual in zip(oracle_csv_pairs, csv_surface["pairs"]):
                if expected != actual:
                    csv_diffs.append("pair " + json.dumps(expected) + " vs " + json.dumps(actual))
                    break
        if csv_surface["consumed"] != oracle_csv_consumed or csv_surface["unconsumed"] != oracle_csv_unconsumed:
            csv_diffs.append("classification drift")
        entries.append({
            "id": "csv_fixture",
            "kind": "csv",
            "settings_sha256": csv_product["settings_sha256"],
            "pairs": len(csv_surface["pairs"]),
            "consumed": len(oracle_csv_consumed),
            "unconsumed": len(oracle_csv_unconsumed),
            "matched": not csv_diffs,
            "diffs": csv_diffs[:10],
        })
        # --- mat fixture surface ---
        import numpy as np
        from scipy.io import savemat
        parameter = np.empty((1, 3), dtype=object)
        parameter[0, 0] = "f_b"
        parameter[0, 1] = np.array([53.125])
        parameter[0, 2] = "unused_mat_key"
        mat_path = work / "config.mat"
        savemat(mat_path, {"parameter": parameter})
        oracle_mat = ComSettings.from_mat(mat_path)
        oracle_mat_pairs = extract_pairs(oracle_mat)
        oracle_mat_keys = sorted({entry["key"] for entry in oracle_mat_pairs})
        oracle_mat_consumed = sorted(set(oracle_mat_keys) & set(canonical_keys))
        oracle_mat_unconsumed = sorted(set(oracle_mat_keys) - set(canonical_keys))
        mat_report = work / "mat-product.json"
        run = subprocess.run(
            [str(runner), "--settings", str(mat_path), "--kind", "mat",
             "--canonical", str(canonical_path), "--report", str(mat_report)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if run.returncode != 0:
            raise SystemExit("mat runner failed: " + run.stdout + run.stderr)
        mat_product = json.loads(mat_report.read_text(encoding="utf-8"))
        mat_surface = mat_product["surface"]
        mat_diffs = []
        if len(mat_surface["pairs"]) != len(oracle_mat_pairs):
            mat_diffs.append("pairs")
        else:
            for expected, actual in zip(oracle_mat_pairs, mat_surface["pairs"]):
                if expected != actual:
                    mat_diffs.append("pair " + json.dumps(expected) + " vs " + json.dumps(actual))
                    break
        if mat_surface["consumed"] != oracle_mat_consumed or mat_surface["unconsumed"] != oracle_mat_unconsumed:
            mat_diffs.append("classification drift")
        entries.append({
            "id": "mat_fixture",
            "kind": "mat",
            "settings_sha256": mat_product["settings_sha256"],
            "pairs": len(mat_surface["pairs"]),
            "consumed": len(oracle_mat_consumed),
            "unconsumed": len(oracle_mat_unconsumed),
            "matched": not mat_diffs,
            "diffs": mat_diffs[:10],
        })
    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "surface_crosscheck_matched" if matched else "surface_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "path": "src/agent_com/config/excel.py",
            "surface": "ComSettings grid scan (lookup semantics)",
        },
        "canonical": {
            "ref": "docs/baselines/p5-r480-canonical-parameter-reference.v1.yaml",
            "key_count": len(canonical_keys),
            "sha256": sha256_bytes(canonical_bytes),
        },
        "entries": entries,
        "non_claims": ["not_value_consumption", "not_behavior_profile", "not_release_evidence"],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    for entry in entries:
        print(entry["id"], "matched=" + str(entry["matched"]), "pairs=" + str(entry["pairs"]),
              "consumed=" + str(entry["consumed"]), "unconsumed=" + str(entry["unconsumed"]))
        for diff in entry.get("diffs", []):
            print("  diff:", diff)
    print("all_matched=" + str(matched))
    print("evidence written: " + str(EVIDENCE))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())