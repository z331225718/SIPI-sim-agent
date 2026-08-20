"""P4B-07 RX AMI_Init probe-surface exploration.

The RX fixture crashed on the identity-like matrix (07a). This exploration
observes AMI_Init across four documented matrix variants in two fresh
custodies, hash-pinned. Outcome per variant is recorded (success or
reproducible crash); no claim about DLL internals is made.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-07-rx-init-surface-exploration-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-07.rx-init-surface-exploration-evidence.v1"

CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
RX_DLL = "ads-pcie-gen5-rx-dll"
RX_AMI = "ads-pcie-gen5-rx-ami"
VARIANTS = ["identity_like", "decay", "uniform", "decay_coupled"]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def registry_entry(registry: dict, material_id: str) -> dict:
    for material in registry["materials"]:
        if material["id"] == material_id:
            return material
    raise RuntimeError(f"material not registered: {material_id}")


def build_runner() -> Path:
    completed = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-ami-host", "--test", "p4b_authorized_fixture_abi_runner"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=ROOT,
    )
    if completed.returncode != 0:
        raise RuntimeError("runner build failed")
    candidates = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_authorized_fixture_abi_runner-*.exe"))
    if not candidates:
        raise RuntimeError("runner executable not found")
    return candidates[-1]


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    dll_entry = registry_entry(registry, RX_DLL)
    ami_entry = registry_entry(registry, RX_AMI)
    dll_source = Path(str(dll_entry["path"]).replace("/", "\\"))
    ami_source = Path(str(ami_entry["path"]).replace("/", "\\"))
    expected_dll = dll_entry["sha256"].lower()
    runner = build_runner()
    outcomes = {variant: [] for variant in VARIANTS}
    with tempfile.TemporaryDirectory(prefix="p4b07-rx-explore-") as tmp:
        work_root = Path(tmp)
        for variant in VARIANTS:
            for index in (0, 1):
                custody = work_root / f"{variant}-{index}"
                custody.mkdir()
                dll_copy = custody / dll_source.name
                ami_copy = custody / ami_source.name
                shutil.copy2(dll_source, dll_copy)
                shutil.copy2(ami_source, ami_copy)
                if sha256_file(dll_copy) != expected_dll:
                    raise RuntimeError(f"hash drift: {variant} {index}")
                report_path = custody / "report.json"
                completed = subprocess.run(
                    [str(runner), "--dll", str(dll_copy), "--ami", str(ami_copy),
                     "--expected-sha256", expected_dll, "--mode", "init",
                     "--matrix-variant", variant, "--rows", "4", "--aggressors", "3",
                     "--report", str(report_path)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
                if completed.returncode == 0 and report_path.is_file():
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    outcomes[variant].append({"status": report.get("probe", {}).get("phase"), "rc": 0})
                elif completed.returncode == 0:
                    outcomes[variant].append({"status": "no_report", "rc": 0})
                else:
                    outcomes[variant].append({"status": "probe_crash", "rc": completed.returncode})
    variant_results = {}
    for variant in VARIANTS:
        first, second = outcomes[variant]
        reproducible = first == second
        succeeded = first["status"] == "init_only"
        variant_results[variant] = {
            "custody_0": first,
            "custody_1": second,
            "reproducible": reproducible,
            "init_succeeded": succeeded and reproducible,
        }
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "rx_init_probe_surface_explored_documented_variants",
        "authorization_ref": "docs/baselines/authorized-material-registry.v1.yaml",
        "dll_sha256": expected_dll,
        "probe": {"mode": "init", "rows": 4, "aggressors": 3, "timebase": "1ps_31.25ps"},
        "variants": variant_results,
        "non_claims": [
            "not_dll_internal_cause",
            "not_ibis_ami_compatibility",
            "not_numerical_parity",
            "not_worker_admission",
            "not_release_evidence",
        ],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print(json.dumps(variant_results, indent=1))
    print("exploration evidence written: " + str(EVIDENCE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
