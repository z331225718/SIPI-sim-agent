"""P5-05c MATLAB v5 reader cross-check: product runner vs agent-com oracle.

Generates a fixed parameter cell-array MAT v5 fixture with scipy.io.savemat,
runs the product MAT reader and compares the raw-cell grid and keyword
lookups against the MIT agent-com ComSettings.from_mat imported in fresh
external custody. Negative fixtures must fail closed on both sides.
Hash-only evidence; no release claim.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-05c-mat-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-05c.mat-crosscheck-evidence.v1"
LOOKUPS = ["f_b", "A_ft", "vector", "matrix", "empty", "int_scalar", "text", "logical_scalar", "int_vector", "missing_key"]


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
    if isinstance(value, np.ndarray):
        if value.dtype.kind in {"U", "S"}:
            return {"kind": "String", "value": "".join(str(item) for item in value.reshape(-1))}
        return {
            "kind": "Array",
            "dims": [int(dim) for dim in value.shape],
            "data": [float(item) for item in value.reshape(-1)],
        }
    return {"kind": "Unsupported", "value": repr(value)}


def main() -> int:
    global np
    import numpy as np
    from scipy.io import savemat
    sys.path.insert(0, str(COM_SRC))
    from agent_com.config.excel import ComSettings

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_05c_mat_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_05c_mat_runner-*.exe"))[-1]

    parameter = np.empty((3, 4), dtype=object)
    parameter[0, 0] = "f_b"
    parameter[0, 1] = np.array([53.125])
    parameter[0, 2] = np.array([1.0, 2.0, 3.0])
    parameter[0, 3] = np.array([])
    parameter[1, 0] = np.array([7])
    parameter[1, 1] = "A_ft"
    parameter[1, 2] = np.array([[1.0, 2.0], [3.0, 4.0]])
    parameter[1, 3] = np.array([True])
    parameter[2, 0] = np.array("")
    parameter[2, 1] = "alpha beta gamma"
    parameter[2, 2] = np.array([10, 20], dtype=np.int32)
    parameter[2, 3] = np.array([3.14])

    entries = []
    negative = []
    with tempfile.TemporaryDirectory(prefix="p5-05c-crosscheck-") as tmp:
        work = Path(tmp)
        fixture = work / "config.mat"
        savemat(fixture, {"parameter": parameter})
        fixture_hash = sha256_bytes(fixture.read_bytes())
        oracle_settings = ComSettings.from_mat(fixture)
        oracle_rows = []
        max_column = 0
        for row in oracle_settings.rows:
            cells = []
            for cell in row:
                cells.append({
                    "coordinate": cell.coordinate,
                    "value": oracle_value_kind(cell.value),
                    "formula": cell.formula,
                })
            max_column = max(max_column, len(cells))
            oracle_rows.append(cells)
        oracle_lookups = []
        for keyword in LOOKUPS:
            try:
                cell = oracle_settings.lookup_optional(keyword)
            except Exception as error:
                oracle_lookups.append({"keyword": keyword, "found": False, "error": type(error).__name__})
                continue
            if cell is None:
                oracle_lookups.append({"keyword": keyword, "found": False})
            else:
                oracle_lookups.append({
                    "keyword": keyword,
                    "found": True,
                    "cell": {
                        "coordinate": cell.coordinate,
                        "value": oracle_value_kind(cell.value),
                        "formula": cell.formula,
                    },
                })
        report_path = work / "product.json"
        command = [str(runner), "--mat", str(fixture), "--report", str(report_path)]
        for keyword in LOOKUPS:
            command += ["--lookup", keyword]
        run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if run.returncode != 0:
            raise SystemExit("runner failed: " + run.stdout + run.stderr)
        product = json.loads(report_path.read_text(encoding="utf-8"))
        diffs = []
        if product["rows"] != len(oracle_rows):
            diffs.append("rows " + str(product["rows"]) + " vs " + str(len(oracle_rows)))
        if product["columns"] != max_column:
            diffs.append("columns " + str(product["columns"]) + " vs " + str(max_column))
        for row_index in range(len(oracle_rows)):
            oracle_row = oracle_rows[row_index]
            product_row = product["grid"][row_index]["cells"]
            if len(oracle_row) != len(product_row):
                diffs.append("row_len " + str(row_index + 1))
                break
            for column_index in range(len(oracle_row)):
                if oracle_row[column_index] != product_row[column_index]:
                    diffs.append("cell " + str(row_index + 1) + "," + str(column_index + 1) + " " + json.dumps(oracle_row[column_index]) + " vs " + json.dumps(product_row[column_index]))
                    break
            if diffs:
                break
        oracle_by_key = {entry["keyword"]: entry for entry in oracle_lookups}
        for entry in product["lookups"]:
            if oracle_by_key.get(entry["keyword"]) != entry:
                diffs.append("lookup " + entry["keyword"] + " " + json.dumps(oracle_by_key.get(entry["keyword"])) + " vs " + json.dumps(entry))
        entries.append({
            "id": "mat_parameter_cell_fixture",
            "mat_sha256": fixture_hash,
            "rows": product["rows"],
            "columns": product["columns"],
            "matched": not diffs,
            "diffs": diffs[:10],
        })
        # Negative: not a MAT file; and a MAT without a parameter variable.
        bad_text = work / "bad_text.mat"
        bad_text.write_text("not a matlab file at all", encoding="utf-8")
        bad_other = work / "bad_other.mat"
        savemat(bad_other, {"other": np.array([1.0])})
        for label, path in (("not_mat", bad_text), ("no_parameter", bad_other)):
            oracle_rejected = False
            try:
                ComSettings.from_mat(path)
            except Exception:
                oracle_rejected = True
            product_rejected = False
            neg_report = work / (label + "-product.json")
            neg_run = subprocess.run(
                [str(runner), "--mat", str(path), "--report", str(neg_report)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            product_rejected = neg_run.returncode != 0
            negative.append({
                "id": "negative_" + label,
                "oracle_rejected": oracle_rejected,
                "product_rejected": product_rejected,
                "matched": oracle_rejected == product_rejected,
            })
    matched = all(entry["matched"] for entry in entries) and all(entry["matched"] for entry in negative)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "mat_crosscheck_matched" if matched else "mat_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "path": "src/agent_com/config/excel.py",
            "function": "ComSettings.from_mat",
            "numpy_version": np.__version__,
            "scipy_version": __import__("scipy").__version__,
        },
        "entries": entries,
        "negative": negative,
        "lookups": LOOKUPS,
        "non_claims": ["not_nested_cells", "not_struct_sparse_complex", "not_parameter_dto_consumption", "not_release_evidence"],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    for entry in entries:
        print(entry["id"], "matched=" + str(entry["matched"]), "rows=" + str(entry["rows"]), "cols=" + str(entry["columns"]))
        for diff in entry.get("diffs", []):
            print("  diff:", diff)
    for entry in negative:
        print(entry["id"], "matched=" + str(entry["matched"]), "oracle=" + str(entry["oracle_rejected"]), "product=" + str(entry["product_rejected"]))
    print("all_matched=" + str(matched))
    print("evidence written: " + str(EVIDENCE))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
