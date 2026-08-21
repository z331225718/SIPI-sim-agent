"""Cross-check the bounded P4A-03 selected-model consumer.

Synthetic requests exercise both target shapes and fail-closed mutations.  If
the operator has materialized the complete official object outside this
worktree, the ignored runner observes its complete inventory and proves that
omitting the selected profile is rejected; this script never chooses an
official model, branch, corner, PVT, or table family.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / ("cargo.exe" if os.name == "nt" else "cargo")
RUNNER_NAME = "p4a_03bk_selected_model_runner"
EVIDENCE = ROOT / "docs/baselines/p4a-03bk-selected-model-crosscheck-evidence.v1.json"
SCHEMA = "sipi.p4a-03bk.selected-model-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03.selected-model-consumer.v1.explicit-profile-only"
DEFAULT_EXTERNAL = Path(
    r"C:\Users\z3312\code\.sipi-p4a-official-asset-20260821\as4c512m16md4v-053bin.ibs"
)


SOURCE = b"""[IBIS Ver] 5.0
[Component] demo
[Pin] pin signal model R_pin L_pin C_pin
P1 SIG M_DIRECT
P2 SEL_SIG SEL
[Model Selector] SEL
M_BRANCH branch
M_OTHER other
[Model] M_DIRECT
Model_type Input
[GND Clamp]
0V 0A
1V 1A
[Model] M_BRANCH
Model_type Input
[Power Clamp]
0V 0A
1V 2A
[Model] M_OTHER
Model_type Output
[Pulldown]
0V 0A
1V 1A
[End]
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runner_path() -> Path:
    candidates = sorted((ROOT / "target/debug/deps").glob(f"{RUNNER_NAME}-*.exe"))
    if not candidates:
        candidates = sorted((ROOT / "target/debug/deps").glob(f"{RUNNER_NAME}-*"))
    if not candidates:
        raise RuntimeError("runner_not_built")
    return candidates[-1]


def run_product(
    runner: Path,
    input_path: Path,
    request_path: Path | None,
    *markers: str,
) -> tuple[int, dict[str, Any]]:
    command = [str(runner), "--input", str(input_path)]
    if request_path is not None:
        command.extend(("--request", str(request_path)))
    for marker in markers:
        command.extend(("--marker", marker))
    process = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.stdout.strip():
        return process.returncode, json.loads(process.stdout)
    raise RuntimeError(f"runner_empty_output:{process.stderr}")


def request(*, role: dict[str, str], target: dict[str, str], corner: str, voltage: float, temperature: float, table: str) -> dict[str, Any]:
    return {
        "role": role,
        "target": target,
        "corner_pvt": {"corner": corner, "voltage_v": voltage, "temperature_c": temperature},
        "table_family": table,
    }


def check_synthetic(runner: Path, work: Path) -> dict[str, Any]:
    source = work / "synthetic.ibs"
    source.write_bytes(SOURCE)
    cases = [
        (
            "direct_model",
            request(
                role={"kind": "signal", "name": "SIG"},
                target={"kind": "model", "model": "M_DIRECT"},
                corner="typical",
                voltage=1.2,
                temperature=25.0,
                table="GND Clamp",
            ),
            {"valid": True, "selector": None, "branch": "M_DIRECT", "table_family": "GND Clamp"},
        ),
        (
            "selector_branch",
            request(
                role={"kind": "pin", "name": "P2"},
                target={"kind": "selector_branch", "selector": "SEL", "branch": "M_BRANCH"},
                corner="slow",
                voltage=1.1,
                temperature=85.0,
                table="Power Clamp",
            ),
            {"valid": True, "selector": "SEL", "branch": "M_BRANCH", "table_family": "POWER Clamp"},
        ),
    ]
    entries: list[dict[str, Any]] = []
    for label, payload, expected in cases:
        path = work / f"{label}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        code, product = run_product(runner, source, path)
        matched = code == 0 and all(product.get(key) == value for key, value in expected.items())
        entries.append({"label": label, "matched": matched, "product": product, "expected": expected})

    missing_code, missing = run_product(runner, source, None)
    missing_ok = (
        missing_code == 2
        and missing.get("error") == "missing_required_selected_profile"
        and missing.get("complete_document") is True
    )
    entries.append({"label": "missing_profile", "matched": missing_ok, "product": missing})

    duplicate = SOURCE.replace(b"P2 SEL_SIG SEL\n", b"P2 SEL_SIG SEL\nP3 SIG M_DIRECT\n")
    duplicate_source = work / "duplicate-role.ibs"
    duplicate_source.write_bytes(duplicate)
    duplicate_request = work / "duplicate-role.json"
    duplicate_request.write_text(json.dumps(cases[0][1]), encoding="utf-8")
    duplicate_code, duplicate_product = run_product(runner, duplicate_source, duplicate_request)
    duplicate_ok = duplicate_code == 2 and "RoleAmbiguous" in duplicate_product.get("error", "")
    entries.append({"label": "ambiguous_role", "matched": duplicate_ok, "product": duplicate_product})

    union_cases = [
        (
            "model_with_selector_fields",
            {**cases[0][1], "target": {"kind": "model", "model": "M_DIRECT", "selector": "SEL", "branch": "M_BRANCH"}},
        ),
        (
            "selector_branch_with_model_field",
            {**cases[1][1], "target": {"kind": "selector_branch", "selector": "SEL", "branch": "M_BRANCH", "model": "M_BRANCH"}},
        ),
        (
            "model_with_unknown_target_field",
            {**cases[0][1], "target": {"kind": "model", "model": "M_DIRECT", "unexpected": "x"}},
        ),
        (
            "selector_branch_with_unknown_target_field",
            {**cases[1][1], "target": {"kind": "selector_branch", "selector": "SEL", "branch": "M_BRANCH", "unexpected": "x"}},
        ),
        (
            "profile_with_unknown_root_field",
            {**cases[0][1], "unexpected": "x"},
        ),
        (
            "role_with_unknown_field",
            {**cases[0][1], "role": {"kind": "signal", "name": "SIG", "unexpected": "x"}},
        ),
        (
            "pvt_with_unknown_field",
            {**cases[0][1], "corner_pvt": {"corner": "typical", "voltage_v": 1.2, "temperature_c": 25.0, "unexpected": "x"}},
        ),
    ]
    for label, payload in union_cases:
        path = work / f"{label}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        union_code, union_product = run_product(runner, source, path)
        union_ok = union_code == 2 and union_product.get("error") == "invalid_selected_profile"
        entries.append({"label": label, "matched": union_ok, "product": union_product})

    return {
        "source_sha256": hashlib.sha256(SOURCE).hexdigest(),
        "case_count": len(entries),
        "matched_count": sum(entry["matched"] for entry in entries),
        "entries": entries,
    }


def check_external(runner: Path, source: Path) -> dict[str, Any]:
    if not source.is_file():
        raise RuntimeError(f"external_source_missing:{source}")
    code, product = run_product(runner, source, None, "GND", "NC", "POWER")
    expected = {
        "complete_document": True,
        "model_count": 95,
        "selector_count": 4,
        "pin_count": 200,
        "error": "missing_required_selected_profile",
    }
    matched = code == 2 and all(product.get(key) == value for key, value in expected.items())
    return {
        "byte_length": source.stat().st_size,
        "sha256": sha256(source),
        "complete_document": product.get("complete_document"),
        "model_count": product.get("model_count"),
        "selector_count": product.get("selector_count"),
        "pin_count": product.get("pin_count"),
        "matched": matched,
        "product": product,
        "expected": expected,
        "selection_status": "missing_required_selected_profile",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-source", type=Path, default=DEFAULT_EXTERNAL)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    if not args.skip_build:
        built = subprocess.run(
            [str(CARGO), "build", "-p", "sipi-ibis", "--test", RUNNER_NAME],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if built.returncode:
            raise SystemExit("runner_build_failed\n" + built.stdout + built.stderr)
    runner = runner_path()
    with tempfile.TemporaryDirectory(prefix="p4a-03bk-") as temporary:
        work = Path(temporary)
        synthetic = check_synthetic(runner, work)
        external = check_external(runner, args.official_source)
    matched = synthetic["matched_count"] == synthetic["case_count"] and external["matched"]
    evidence = {
        "schema": SCHEMA,
        "status": "matched_synthetic_and_external_missing_profile" if matched else "mismatch",
        "policy": POLICY,
        "runner": {"path": "crates/sipi-ibis/tests/p4a_03bk_selected_model_runner.rs", "sha256": sha256(ROOT / "crates/sipi-ibis/tests/p4a_03bk_selected_model_runner.rs")},
        "implementation": {"path": "crates/sipi-ibis/src/selected_model_v1.rs", "sha256": sha256(ROOT / "crates/sipi-ibis/src/selected_model_v1.rs")},
        "synthetic": synthetic,
        "external_official": external,
        "promotion_eligible": False,
        "non_claims": [
            "not_general_ibis_grammar",
            "not_external_rights_or_redistribution",
            "not_selected_official_model_or_corner",
            "not_table_value_evaluation",
            "not_transient_or_ami_runtime",
            "not_release_evidence",
        ],
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "status": evidence["status"], "matched": matched}, indent=2))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
