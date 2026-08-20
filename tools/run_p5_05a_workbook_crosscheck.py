"""P5-05a workbook importer cross-check: product runner vs agent-com oracle.

Runs the product workbook importer on the authorized COM_Settings xlsx
(hash-pinned) and compares the full raw-cell grid, strict flag, and
keyword lookups against the MIT agent-com ComSettings implementation
imported in fresh external custody. Negative container fixtures must
fail closed on both sides. Hash-only evidence; no release claim.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
COM_SRC = Path(r"C:\Users\z3312\code\COM\src")
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-05a-workbook-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-05a.workbook-crosscheck-evidence.v1"
MATERIAL_ID = "com-r480-config-120g-c2m"
LOOKUPS = ["f_b", "A_ft", "Port Order", "COM_Settings", "FOM"]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def oracle_value_kind(value: object) -> dict[str, object]:
    if value is None:
        return {"kind": "None"}
    if isinstance(value, bool):
        return {"kind": "Bool", "value": value}
    if isinstance(value, int):
        return {"kind": "Integer", "value": value}
    if isinstance(value, float):
        return {"kind": "Number", "value": value}
    if isinstance(value, str):
        return {"kind": "String", "value": value}
    return {"kind": "Unsupported", "value": repr(value)}


def oracle_surface(settings, path: Path) -> dict[str, object]:
    rows = []
    max_column = 0
    for row in settings.rows:
        cells = []
        for cell in row:
            cells.append({
                "coordinate": cell.coordinate,
                "value": oracle_value_kind(cell.value),
                "formula": cell.formula,
            })
        max_column = max(max_column, len(cells))
        rows.append(cells)
    lookups = []
    for keyword in LOOKUPS:
        try:
            cell = settings.lookup_optional(keyword)
        except Exception as error:  # DuplicateParameterError / MissingParameterError
            lookups.append({"keyword": keyword, "found": False, "error": type(error).__name__})
            continue
        if cell is None:
            lookups.append({"keyword": keyword, "found": False})
        else:
            lookups.append({
                "keyword": keyword,
                "found": True,
                "cell": {
                    "coordinate": cell.coordinate,
                    "value": oracle_value_kind(cell.value),
                    "formula": cell.formula,
                },
            })
    return {"rows": len(rows), "columns": max_column, "grid": rows, "lookups": lookups}


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    import openpyxl
    from agent_com.config.excel import ComSettings

    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    materials = {m["id"]: m for m in registry["materials"]}
    material = materials.get(MATERIAL_ID)
    if material is None:
        raise SystemExit("missing material: " + MATERIAL_ID)
    source = Path(str(material["path"]).replace("/", "\\"))
    if sha256_bytes(source.read_bytes()) != material["sha256"].lower():
        raise SystemExit("hash drift: " + MATERIAL_ID)

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_05a_workbook_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_05a_workbook_runner-*.exe"))[-1]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-05a-crosscheck-") as tmp:
        work = Path(tmp)
        work_xlsx = work / "config.xlsx"
        shutil.copy2(source, work_xlsx)
        oracle_settings = ComSettings.from_xlsx(source)
        oracle = oracle_surface(oracle_settings, source)
        report_path = work / "product.json"
        command = [str(runner), "--xlsx", str(work_xlsx), "--report", str(report_path)]
        for keyword in LOOKUPS:
            command += ["--lookup", keyword]
        run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if run.returncode != 0:
            raise SystemExit("runner failed: " + run.stdout + run.stderr)
        product = json.loads(report_path.read_text(encoding="utf-8"))
        diffs = []
        if bool(product["strict"]) is not False:
            diffs.append("strict_mismatch")
        if product["rows"] != oracle["rows"]:
            diffs.append("rows " + str(product["rows"]) + " vs " + str(oracle["rows"]))
        if product["columns"] != oracle["columns"]:
            diffs.append("columns " + str(product["columns"]) + " vs " + str(oracle["columns"]))
        oracle_grid = oracle["grid"]
        product_grid = product["grid"]
        cell_count = 0
        for row_index in range(oracle["rows"]):
            oracle_row = oracle_grid[row_index]
            product_row = product_grid[row_index]["cells"]
            for column_index in range(oracle["columns"]):
                cell_count += 1
                expected = oracle_row[column_index]
                actual = product_row[column_index]
                if expected != actual:
                    diffs.append("cell " + str(row_index + 1) + "," + str(column_index + 1) + " " + json.dumps(expected) + " vs " + json.dumps(actual))
                    if len(diffs) > 12:
                        break
            if len(diffs) > 12:
                break
        oracle_lookup_by_key = {entry["keyword"]: entry for entry in oracle["lookups"]}
        for entry in product["lookups"]:
            expected = oracle_lookup_by_key.get(entry["keyword"])
            if expected != entry:
                diffs.append("lookup " + entry["keyword"] + " " + json.dumps(expected) + " vs " + json.dumps(entry))
        entries.append({
            "id": "com-r480-config-120g-c2m",
            "xlsx_sha256": product["xlsx_sha256"],
            "rows": product["rows"],
            "columns": product["columns"],
            "cell_count": cell_count,
            "matched": not diffs,
            "diffs": diffs[:12],
        })
        # Negative container fixtures: macro content and external links.
        negative = []
        for injection, expected_error in (
            ("xl/vbaproject.bin", "macro"),
            ("xl/externallinks/externalLink1.xml", "externallinks"),
        ):
            neg_path = work / (expected_error + ".xlsx")
            with zipfile.ZipFile(source) as archive:
                with zipfile.ZipFile(neg_path, "w", zipfile.ZIP_DEFLATED) as out:
                    for item in archive.infolist():
                        out.writestr(item, archive.read(item.filename))
                    out.writestr(injection, b"injected")
            oracle_rejected = False
            try:
                ComSettings.from_xlsx(neg_path)
            except Exception:
                oracle_rejected = True
            product_rejected = False
            neg_report = work / (expected_error + "-product.json")
            neg_run = subprocess.run(
                [str(runner), "--xlsx", str(neg_path), "--report", str(neg_report)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            product_rejected = neg_run.returncode != 0
            negative.append({
                "id": "negative_" + expected_error,
                "oracle_rejected": oracle_rejected,
                "product_rejected": product_rejected,
                "matched": oracle_rejected and product_rejected,
            })
    matched = all(entry["matched"] for entry in entries) and all(entry["matched"] for entry in negative)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "workbook_crosscheck_matched" if matched else "workbook_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "path": "src/agent_com/config/excel.py",
            "function": "ComSettings.from_xlsx",
            "numpy_version": np.__version__,
            "openpyxl_version": openpyxl.__version__,
        },
        "material_id": MATERIAL_ID,
        "entries": entries,
        "negative": negative,
        "lookups": LOOKUPS,
        "non_claims": ["not_csv_mat_reader", "not_parameter_dto_consumption", "not_release_evidence"],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    for entry in entries:
        print(entry["id"], "matched=" + str(entry["matched"]), "cells=" + str(entry["cell_count"]))
    for entry in negative:
        print(entry["id"], "matched=" + str(entry["matched"]), "oracle=" + str(entry["oracle_rejected"]), "product=" + str(entry["product_rejected"]))
    print("all_matched=" + str(matched))
    print("evidence written: " + str(EVIDENCE))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
