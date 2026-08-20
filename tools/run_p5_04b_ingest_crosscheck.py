"""P5-04b ingest cross-check: product ingest vs MATLAB oracle.

Runs the product ingest runner on the three authorized synthetic S4P
fixtures (thru/fext/next) in fresh custody and compares the sdd21
magnitude at 26.56 GHz against the oracle network_metrics (-10 / -40 /
-40 dB). Hash-only evidence; no release claim.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
SURFACE = ROOT / "docs" / "baselines" / "p5-06-oracle-metric-surface.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04b-ingest-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04b.ingest-crosscheck-evidence.v1"
TARGET_HZ = 2.656e10

CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
FIXTURES = [("com-synthetic-thru", "thru.s4p", -10.0), ("com-synthetic-fext", "fext.s4p", -40.0), ("com-synthetic-next", "next.s4p", -40.0)]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    materials = {m["id"]: m for m in registry["materials"]}
    surface = yaml.safe_load(SURFACE.read_text(encoding="utf-8"))
    completed = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04b_ingest_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if completed.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04b_ingest_runner-*.exe"))[-1]
    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-04b-ingest-") as tmp:
        work = Path(tmp)
        for material_id, local_name, oracle_db in FIXTURES:
            material = materials.get(material_id)
            if material is None:
                raise SystemExit("missing: " + material_id)
            source = Path(str(material["path"]).replace("/", "\\"))
            if sha256_file(source) != material["sha256"].lower():
                raise SystemExit("hash drift: " + material_id)
            copy = work / local_name
            shutil.copy2(source, copy)
            report_path = work / (material_id + ".json")
            run = subprocess.run(
                [str(runner), "--s4p", str(copy), "--target-hz", str(TARGET_HZ), "--report", str(report_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if run.returncode != 0:
                raise SystemExit("runner failed: " + material_id)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            target = report.get("target")
            if target is None:
                raise SystemExit("target frequency missing: " + material_id)
            product_db = target["magnitude_db"]
            delta_db = product_db - oracle_db
            entries.append({
                "material_id": material_id,
                "oracle_sdd21_db": oracle_db,
                "product_sdd21_db": product_db,
                "delta_db": delta_db,
                "series_sha256": report["series_sha256"],
                "rows": report["rows"],
            })
    max_delta = max(abs(entry["delta_db"]) for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "ingest_sdd21_crosscheck_matched" if max_delta < 1.0 else "ingest_sdd21_crosscheck_mismatch",
        "target_frequency_hz": TARGET_HZ,
        "oracle_surface_ref": "docs/baselines/p5-06-oracle-metric-surface.v1.yaml",
        "entries": entries,
        "max_abs_delta_db": max_delta,
        "tolerance_db": 1.0,
        "non_claims": [
            "not_full_bandwidth_parity",
            "not_stage_chain_parity",
            "not_release_evidence",
        ],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    for entry in entries:
        print(entry["material_id"], "product=" + str(round(entry["product_sdd21_db"], 4)), "oracle=" + str(entry["oracle_sdd21_db"]), "delta=" + str(round(entry["delta_db"], 4)))
    print("max_delta_db=" + str(round(max_delta, 6)))
    print("evidence written: " + str(EVIDENCE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
