"""Fail-closed preflight for the TP0V current-asset scoped replay v2."""
from __future__ import annotations
import argparse, hashlib, json, tarfile
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/com-tp0v-current-asset-scoped-acceptance.v2.yaml"
HEX = set("0123456789abcdef")

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def require(condition: bool, message: str) -> None:
    if not condition: raise ValueError(message)
def load(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "manifest must be a mapping")
    return value
def archive_members(archive: Path, manifest: dict) -> None:
    upstream = manifest["upstream"]
    raw = archive.read_bytes()
    require(len(raw) == upstream["archive_bytes"] and sha(raw) == upstream["archive_sha256"], "upstream archive identity drift")
    with tarfile.open(archive) as tf:
        names = {item.name: item for item in tf.getmembers() if item.isfile()}
        for expected in [upstream["workbook"], *upstream["assets"]]:
            item = next((x for n, x in names.items() if n == expected["path"] or n.endswith("/" + expected["path"])), None)
            require(item is not None, f"archive member absent: {expected['path']}")
            payload = tf.extractfile(item).read()
            require(len(payload) == expected["bytes"] and sha(payload) == expected["sha256"], f"archive member drift: {expected['path']}")
            if "header" in expected:
                header = next((line.decode("ascii").strip() for line in payload.splitlines() if line.strip() and not line.lstrip().startswith(b"!")), None)
                require(header == expected["header"], f"touchstone header drift: {expected['path']}")
def validate(manifest: dict, archive: Path | None = None) -> None:
    require(manifest.get("schema") == "sipi.com.tp0v-current-asset-scoped-acceptance-prep.v2", "schema")
    require(manifest.get("status") == "preparation_only_pending_clean_candidate_and_harness_commit", "not a prep record")
    require(manifest.get("formal_record_absent") is True, "formal record claim")
    candidate = manifest.get("candidate")
    require(candidate == {"commit": None, "tree": None, "archive_sha256": None, "archive_bytes": None}, "candidate must remain unbound during prep")
    comparison = manifest["comparison"]
    require(comparison["key"] == ["workbook", "case", "port", "checkpoint"], "comparison key")
    require(comparison["vectors"] == ["time_s", "impedance_ohm", "ptdr", "gated"], "vector contract")
    require(comparison["prohibited"] == ["align", "interpolate", "resample", "truncate", "delay_correction"], "comparison prohibitions")
    require(comparison["anti_causal_warning"] == {"required_capture": True, "source_warning_equivalent": False, "comparison_gate": False}, "warning contract")
    require(manifest["performance_gate"]["required"] is True, "performance gate missing")
    require(manifest["performance_gate"]["rule"] == "each_case_rust_wall_clock_s_strictly_less_than_matlab_wall_clock_s", "performance rule")
    require(manifest["replays"] == ["matlab-01", "matlab-02", "rust-01", "rust-02"], "replay matrix")
    require(len(manifest["comparison"]["scalar_surface"]) == 21, "scalar surface incomplete")
    for path in manifest["formal_paths_absent"]: require(not (ROOT / path).exists(), f"formal path unexpectedly exists: {path}")
    if archive: archive_members(archive, manifest)
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--upstream-archive", type=Path)
    args = parser.parse_args(); validate(load(MANIFEST), args.upstream_archive)
    print(json.dumps({"valid": True, "status": "preparation_only_pending_clean_candidate_and_harness_commit"}, sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
