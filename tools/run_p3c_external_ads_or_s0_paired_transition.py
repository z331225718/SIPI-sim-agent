"""Run the unchanged fixed ADS pulse bench and export exact OR/S0 paired Hdiffs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
COMMON_PATH = ROOT / "tools/run_p3c_external_ads_pre_final_common_nodes.py"
spec = importlib.util.spec_from_file_location("common_nodes", COMMON_PATH)
assert spec and spec.loader
COMMON = importlib.util.module_from_spec(spec)
spec.loader.exec_module(COMMON)


class PairedTransitionError(RuntimeError):
    pass


def identity(path: Path) -> tuple[int, str]:
    return path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()


def export_pairs(destination: Path) -> dict[str, Any]:
    if identity(COMMON.ADS_PYTHON) != COMMON.PYTHON_ID or identity(COMMON.API_DOC) != COMMON.DOC_ID:
        raise PairedTransitionError("ads_dataset_api_identity_mismatch")
    payload = destination / "or-s0-hdiff.bin"
    result = subprocess.run(
        [str(COMMON.ADS_PYTHON), "-B", str(COMMON.EXTRACTOR), "--dataset", str(destination / "p3c_prbs9.ds"), "--or-s0-hdiff-payload", str(payload)],
        check=False, capture_output=True, text=True, encoding="utf-8", errors="strict",
    )
    if result.returncode:
        raise PairedTransitionError("ads_or_s0_pair_export_rejected")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise PairedTransitionError("ads_or_s0_pair_export_invalid") from error
    payload_identity = value.get("or_s0_hdiff_payload") if isinstance(value, dict) else None
    required = {"common_node_count", "mapping", "axis_sha256", "original_hdiff_sha256", "s0_hdiff_sha256", "documented_surface_transition", "or_s0_hdiff_payload"}
    if not isinstance(value, dict) or set(value) != required or value["common_node_count"] != 1024 or value["mapping"] != "or_index_equals_4_times_s0_index" or not isinstance(payload_identity, dict) or set(payload_identity) != {"byte_length", "sha256"} or identity(payload) != (payload_identity["byte_length"], payload_identity["sha256"]):
        raise PairedTransitionError("ads_or_s0_pair_export_shape")
    return {
        "payload": payload_identity,
        "common_node_count": value["common_node_count"],
        "mapping": value["mapping"],
        "axis_sha256": value["axis_sha256"],
        "original_hdiff_sha256": value["original_hdiff_sha256"],
        "s0_hdiff_sha256": value["s0_hdiff_sha256"],
        "documented_surface_transition": value["documented_surface_transition"],
    }


def materialize(source: Path, destination: Path, invoke_ads: bool) -> dict[str, Any]:
    value = COMMON.SURFACE.materialize_probe(source, destination, invoke_ads=invoke_ads)
    if invoke_ads:
        value["or_s0_paired_hdiff"] = export_pairs(destination)
        value["ads_dataset_api"] = {
            "python": {"byte_length": COMMON.PYTHON_ID[0], "sha256": COMMON.PYTHON_ID[1]},
            "api_doc": {"byte_length": COMMON.DOC_ID[0], "sha256": COMMON.DOC_ID[1]},
        }
    (destination / "manifest.json").write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="ascii", newline="\n")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s4p", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not COMMON.SURFACE.PULSE.ads.valid_run_id(args.run_id):
            raise PairedTransitionError("run_id_invalid")
        output = COMMON.SURFACE.PULSE.require_external(args.output_root, "output_root") / args.run_id
        value = materialize(COMMON.SURFACE.PULSE.require_external(args.s4p, "s4p"), output, args.run)
    except (OSError, ValueError, PairedTransitionError, COMMON.SURFACE.PassivitySurfaceError, COMMON.SURFACE.PULSE.FixedPulseError, COMMON.SURFACE.PULSE.ads.ExternalReferenceError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, sort_keys=True)); return 2
    print(json.dumps({"status": "ads_run_completed" if args.run else "generated", "or_s0_paired_hdiff": value.get("or_s0_paired_hdiff")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
