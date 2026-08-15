"""Run the fixed ADS pulse bench and export only the reduced CMP1_OR payload."""

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


class OriginalProductRawError(RuntimeError):
    pass


def identity(path: Path) -> tuple[int, str]:
    return path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()


def export_or_hdiff(destination: Path) -> dict[str, Any]:
    if identity(COMMON.ADS_PYTHON) != COMMON.PYTHON_ID or identity(COMMON.API_DOC) != COMMON.DOC_ID:
        raise OriginalProductRawError("ads_dataset_api_identity_mismatch")
    payload = destination / "or-hdiff.bin"
    result = subprocess.run([str(COMMON.ADS_PYTHON), "-B", str(COMMON.EXTRACTOR), "--dataset", str(destination / "p3c_prbs9.ds"), "--or-hdiff-payload", str(payload)], check=False, capture_output=True, text=True, encoding="utf-8", errors="strict")
    if result.returncode:
        raise OriginalProductRawError("ads_or_hdiff_export_rejected")
    try:
        summary = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise OriginalProductRawError("ads_or_hdiff_export_invalid") from error
    payload_identity = summary.get("or_hdiff_payload") if isinstance(summary, dict) else None
    if not isinstance(summary, dict) or not isinstance(summary.get("or_node_count"), int) or summary["or_node_count"] < 2 or not isinstance(payload_identity, dict) or set(payload_identity) != {"byte_length", "sha256"} or identity(payload) != (payload_identity["byte_length"], payload_identity["sha256"]):
        raise OriginalProductRawError("ads_or_hdiff_payload_identity_invalid")
    return {"payload": payload_identity, "or_node_count": summary["or_node_count"], "axis_sha256": summary["axis_sha256"], "selected_hdiff_sha256": summary["selected_hdiff_sha256"]}


def materialize(source: Path, destination: Path, invoke_ads: bool) -> dict[str, Any]:
    value = COMMON.SURFACE.materialize_probe(source, destination, invoke_ads=invoke_ads)
    if invoke_ads:
        value["original_spectrum_or_hdiff"] = export_or_hdiff(destination)
        value["ads_dataset_api"] = {"python": {"byte_length": COMMON.PYTHON_ID[0], "sha256": COMMON.PYTHON_ID[1]}, "api_doc": {"byte_length": COMMON.DOC_ID[0], "sha256": COMMON.DOC_ID[1]}}
    (destination / "manifest.json").write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="ascii", newline="\n")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s4p", type=Path, required=True); parser.add_argument("--output-root", type=Path, required=True); parser.add_argument("--run-id", required=True); parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not COMMON.SURFACE.PULSE.ads.valid_run_id(args.run_id):
            raise OriginalProductRawError("run_id_invalid")
        output_root = COMMON.SURFACE.PULSE.require_external(args.output_root, "output_root")
        value = materialize(COMMON.SURFACE.PULSE.require_external(args.s4p, "s4p"), output_root / args.run_id, args.run)
    except (OSError, ValueError, OriginalProductRawError, COMMON.SURFACE.PassivitySurfaceError, COMMON.SURFACE.PULSE.FixedPulseError, COMMON.SURFACE.PULSE.ads.ExternalReferenceError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, sort_keys=True)); return 2
    print(json.dumps({"status": "ads_run_completed" if args.run else "generated", "original_spectrum_or_hdiff": value.get("original_spectrum_or_hdiff")}, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
