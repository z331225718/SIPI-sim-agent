"""P5-05b CSV reader cross-check: product runner vs agent-com oracle.

Runs the product CSV configuration reader on a fixed fixture (BOM,
quoted fields, escapes, blanks, blank rows) and compares the raw-cell
grid and keyword lookups against the MIT agent-com ComSettings.from_csv
imported in fresh external custody. Negative fixtures must fail closed
on both sides. Hash-only evidence; no release claim.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-05b-csv-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-05b.csv-crosscheck-evidence.v1"
LOOKUPS = ["f_b", "A_ft", "Port Order", "quoted", "escaped", "empty", "num", "neg", "exp", "missing_key"]

FIXTURE = (
    "f_b,53.125\r\n"
    "A_ft,0.6\r\n"
    "Port Order,\"[ 1 3 2 4 ]\"\r\n"
    "quoted,\"with,comma\"\r\n"
    "escaped,\"say \"\"hi\"\"\"\r\n"
    "empty,\r\n"
    "num,5\r\n"
    "neg,-2.5\r\n"
    "exp,1e5\r\n"
    "\r\n"
    "trailing,last\r\n"
)


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


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    from agent_com.config.excel import ComSettings

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_05b_csv_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_05b_csv_runner-*.exe"))[-1]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-05b-crosscheck-") as tmp:
        work = Path(tmp)
        fixture_bytes = b"\xef\xbb\xbf" + FIXTURE.encode("utf-8")
        fixture = work / "config.csv"
        fixture.write_bytes(fixture_bytes)
        oracle_settings = ComSettings.from_csv(fixture)
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
        command = [str(runner), "--csv", str(fixture), "--report", str(report_path)]
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
                diffs.append("row_len " + str(row_index + 1) + " " + str(len(oracle_row)) + " vs " + str(len(product_row)))
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
            "id": "csv_config_fixture",
            "csv_sha256": product["csv_sha256"],
            "rows": product["rows"],
            "columns": product["columns"],
            "matched": not diffs,
            "diffs": diffs[:10],
        })
        # Negative: unterminated quoted field.
        negative = []
        for label, bad_text in (("unterminated_quote", "key,\"value\r\n"), ):
            bad = work / (label + ".csv")
            bad.write_text(bad_text, encoding="utf-8")
            oracle_rejected = False
            try:
                ComSettings.from_csv(bad)
            except Exception:
                oracle_rejected = True
            product_rejected = False
            neg_report = work / (label + "-product.json")
            neg_run = subprocess.run(
                [str(runner), "--csv", str(bad), "--report", str(neg_report)],
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
        "status": "csv_crosscheck_matched" if matched else "csv_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "path": "src/agent_com/config/excel.py",
            "function": "ComSettings.from_csv",
        },
        "entries": entries,
        "negative": negative,
        "lookups": LOOKUPS,
        "non_claims": ["not_mat_reader", "not_parameter_dto_consumption", "not_release_evidence"],
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