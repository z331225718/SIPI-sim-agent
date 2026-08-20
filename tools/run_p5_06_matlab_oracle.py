"""P5-06a external-only MATLAB oracle first-run orchestrator.

Materializes the authorized MATLAB r4.80 source, config sheet and
synthetic fixtures into a fresh custody root (hash-verified), then
invokes MATLAB R2024b directly with the agent-com run_com_oracle
entry (external tool, COM_ORACLE_SOURCE_DIR pointed at the custody
copy). Manifest/hash-only evidence; full outputs stay in external
custody. No product code is involved.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06-matlab-oracle-first-run-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-06.matlab-oracle-first-run-evidence.v1"
COM_REPO = Path("C:/Users/z3312/code/COM")
ORACLE_MATLAB_DIR = COM_REPO / "tools" / "matlab_oracle"

MATERIALS = {
    "com-r480-matlab-source": "com_ieee8023_480.m",
    "com-r480-config-120g-c2m": "config.xlsx",
    "com-synthetic-thru": "thru.s4p",
    "com-synthetic-fext": "fext.s4p",
    "com-synthetic-next": "next.s4p",
    "com-synthetic-manifest": "manifest.json",
    "matlab-r2024b": "matlab.exe",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    materials = {m["id"]: m for m in registry["materials"]}
    with tempfile.TemporaryDirectory(prefix="p5-06-oracle-") as tmp:
        custody = Path(tmp) / "custody"
        custody.mkdir()
        source_dir = custody / "src"
        fixture_dir = custody / "fixtures"
        source_dir.mkdir()
        fixture_dir.mkdir()
        for material_id, local_name in MATERIALS.items():
            material = materials.get(material_id)
            if material is None:
                raise SystemExit("missing material: " + material_id)
            source = Path(str(material["path"]).replace("/", "\\"))
            if sha256_file(source) != material["sha256"].lower():
                raise SystemExit("hash drift: " + material_id)
            if material_id == "com-r480-matlab-source":
                target = source_dir / local_name
            elif material_id in ("com-synthetic-thru", "com-synthetic-fext", "com-synthetic-next", "com-synthetic-manifest"):
                target = fixture_dir / local_name
            elif material_id == "com-r480-config-120g-c2m":
                continue  # xlsread basic cannot read Temp custody copies; original path used with hash verified above
            else:
                continue  # matlab launcher runs from its install path
            shutil.copy2(source, target)
        output_dir = custody / "out"
        output_dir.mkdir()
        def matlab_string(path: Path) -> str:
            return str(path).replace("\\", "/")
        expression = (
            "global COM_ORACLE_SOURCE_DIR; "
            "COM_ORACLE_SOURCE_DIR='" + matlab_string(source_dir) + "'; "
            "addpath('" + matlab_string(ORACLE_MATLAB_DIR) + "'); "
            "run_com_oracle('" + matlab_string(COM_REPO) + "', "
            "'" + matlab_string(Path(str(materials["com-r480-config-120g-c2m"]["path"]).replace("/", "\\"))) + "', "
            "'" + matlab_string(output_dir) + "', 2.656e10, 1, 1, "
            "'" + matlab_string(fixture_dir / "thru.s4p") + "', "
            "'" + matlab_string(fixture_dir / "fext.s4p") + "', "
            "'" + matlab_string(fixture_dir / "next.s4p") + "');"
        )
        command = [str(Path(str(materials["matlab-r2024b"]["path"]).replace("/", "\\"))), "-batch", expression]
        completed = subprocess.run(command, cwd=str(COM_REPO), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2400)
        if completed.returncode != 0:
            raise SystemExit("matlab failed rc=" + str(completed.returncode) + " tail=" + (completed.stdout + completed.stderr)[-1500:])
        output_hashes = {
            path.name: sha256_file(path)
            for path in sorted(output_dir.iterdir())
            if path.is_file()
        }
        summary_content = None
        summary_path = output_dir / "summary.json"
        if summary_path.is_file():
            summary_content = summary_path.read_text(encoding="utf-8", errors="replace")
        log_text = (completed.stdout + completed.stderr)[-4000:]
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matlab_oracle_first_run_succeeded_hash_bound",
        "authorization_ref": "docs/baselines/authorized-material-registry.v1.yaml",
        "target_frequency_ghz": 26.56,
        "output_file_hashes": output_hashes,
        "summary_content": summary_content,
        "stdout_tail_hash": hashlib.sha256(log_text.encode("utf-8")).hexdigest(),
        "custody": "fresh_materialization_cleaned",
        "non_claims": [
            "not_a_product_runtime",
            "not_compute_parity",
            "not_release_evidence",
        ],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print("oracle first run succeeded; files=" + str(len(output_hashes)))
    print("evidence written: " + str(EVIDENCE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
