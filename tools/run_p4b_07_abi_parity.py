"""P4B-07b raw ABI output parity orchestrator.

For the owner-authorized TX fixture, runs the clean-room Rust host and
the independent ctypes observer on the same fixed probe matrix in two
fresh custodies, and requires: host_0 == host_1 (reproducibility),
observer_0 == observer_1 (reproducibility), and host_i == observer_i
(parity) per probe. Evidence is hash-only; RX remains the 07a crash
observation and is not part of the parity claim. Any mismatch fails
closed with no evidence written.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-07-raw-abi-parity-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-07.raw-abi-parity-evidence.v1"

CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
TX_DLL = "ads-pcie-gen5-tx-dll"
TX_AMI = "ads-pcie-gen5-tx-ami"
OBSERVER = ROOT / "tools" / "p4b_07_ctypes_observer.py"

PROBE_MATRIX = [
    {"mode": "init", "wave_length": None, "clock_capacity": None, "rows": 4, "aggressors": 3},
    {"mode": "single", "wave_length": 1024, "clock_capacity": 1024, "rows": 4, "aggressors": 3},
    {"mode": "single", "wave_length": 4096, "clock_capacity": 4096, "rows": 4, "aggressors": 3},
    {"mode": "multi", "wave_length": 1024, "clock_capacity": 1024, "rows": 4, "aggressors": 3},
]


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
        raise RuntimeError("runner build failed: " + completed.stderr[-400:])
    candidates = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_authorized_fixture_abi_runner-*.exe"))
    if not candidates:
        raise RuntimeError("runner executable not found")
    return candidates[-1]


def probe_key(probe: dict) -> str:
    return probe["mode"] + ("-" + str(probe["wave_length"]) if probe["wave_length"] else "")


def run_probes(runner: Path, dll_copy: Path, ami_copy: Path, expected_dll: str, work: Path) -> dict:
    reports = {}
    for probe in PROBE_MATRIX:
        key = probe_key(probe)
        host_report = work / f"host-{key}.json"
        observer_report = work / f"observer-{key}.json"
        command = [str(runner), "--dll", str(dll_copy), "--ami", str(ami_copy),
                   "--expected-sha256", expected_dll, "--mode", probe["mode"],
                   "--rows", str(probe["rows"]), "--aggressors", str(probe["aggressors"]),
                   "--report", str(host_report)]
        if probe["wave_length"] is not None:
            command += ["--wave-length", str(probe["wave_length"]), "--clock-capacity", str(probe["clock_capacity"])]
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode == 0 and host_report.is_file():
            host = json.loads(host_report.read_text(encoding="utf-8"))
        elif completed.returncode == 0:
            host = {"status": "no_report", "rc": 0}
        else:
            host = {"status": "probe_crash", "rc": completed.returncode}
        observer_command = [sys.executable, str(OBSERVER), "--dll", str(dll_copy), "--ami", str(ami_copy),
                           "--mode", probe["mode"], "--rows", str(probe["rows"]),
                           "--aggressors", str(probe["aggressors"]), "--report", str(observer_report)]
        if probe["wave_length"] is not None:
            observer_command += ["--wave-length", str(probe["wave_length"]), "--clock-capacity", str(probe["clock_capacity"])]
        obs_completed = subprocess.run(observer_command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if obs_completed.returncode == 0 and observer_report.is_file():
            observer = json.loads(observer_report.read_text(encoding="utf-8"))
        elif obs_completed.returncode == 0:
            observer = {"status": "no_report", "rc": 0}
        else:
            observer = {"status": "probe_crash", "rc": obs_completed.returncode}
        reports[key] = {"host": host, "observer": observer}
    return reports


def parity_for(host: dict, observer: dict) -> bool:
    probe = host.get("probe", {})
    # init-only: both must succeed with status 1.
    if probe.get("phase") == "init_only":
        return probe.get("init") == "ok" and observer.get("init_status") == 1
    # getwave probes: compare hashes and lengths per probe.
    host_probes = probe.get("probes")
    observer_probes = observer.get("probes")
    if not isinstance(host_probes, list) or not isinstance(observer_probes, list):
        return False
    if len(host_probes) != len(observer_probes):
        return False
    for left, right in zip(host_probes, observer_probes):
        if left.get("error") is not None or right.get("error"):
            return False
        if left.get("output_waveform_hash") != right.get("output_waveform_hash"):
            return False
        if left.get("output_waveform_len") != right.get("output_waveform_len"):
            return False
        if left.get("clocks_hash") != right.get("clocks_hash"):
            return False
        if left.get("clocks_len") != right.get("clocks_len"):
            return False
    return True


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    dll_entry = registry_entry(registry, TX_DLL)
    ami_entry = registry_entry(registry, TX_AMI)
    dll_source = Path(str(dll_entry["path"]).replace("/", "\\"))
    ami_source = Path(str(ami_entry["path"]).replace("/", "\\"))
    expected_dll = dll_entry["sha256"].lower()
    runner = build_runner()
    custody_reports = []
    with tempfile.TemporaryDirectory(prefix="p4b07-parity-") as tmp:
        work_root = Path(tmp)
        for index in (0, 1):
            custody = work_root / f"custody-{index}"
            custody.mkdir()
            dll_copy = custody / dll_source.name
            ami_copy = custody / ami_source.name
            shutil.copy2(dll_source, dll_copy)
            shutil.copy2(ami_source, ami_copy)
            if sha256_file(dll_copy) != expected_dll:
                raise RuntimeError(f"custody {index} dll hash drift")
            reports = run_probes(runner, dll_copy, ami_copy, expected_dll, custody)
            parity = {key: parity_for(value["host"], value["observer"]) for key, value in reports.items()}
            if not all(parity.values()):
                raise RuntimeError(f"custody {index} parity mismatch: {parity}")
            custody_reports.append({"index": index, "probe_parity": parity, "reports": reports})
        if custody_reports[0]["reports"] != custody_reports[1]["reports"]:
            raise RuntimeError("custody reports differ between fresh materializations")
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "tx_raw_abi_parity_reproduced_hash_only",
        "authorization_ref": "docs/baselines/authorized-material-registry.v1.yaml",
        "observation_ref": "docs/baselines/p4b-07-authorized-fixture-abi-observation-evidence.v1.yaml",
        "dll_sha256": expected_dll,
        "probe_matrix": PROBE_MATRIX,
        "custody_0_parity": custody_reports[0]["probe_parity"],
        "custody_1_parity": custody_reports[1]["probe_parity"],
        "probe_parity": "all_probes_host_equals_observer",
        "rx_surface": "not_in_this_parity_claim",
        "non_claims": [
            "not_rx_parity",
            "not_numerical_reference_parity",
            "not_ibis_ami_compatibility",
            "not_tx_rx_composition",
            "not_worker_admission",
            "not_product_runtime",
            "not_release_evidence",
        ],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print("parity evidence written: " + str(EVIDENCE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
