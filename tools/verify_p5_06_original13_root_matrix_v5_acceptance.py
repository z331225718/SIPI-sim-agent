"""Verify the immutable public-root original-13 v5 acceptance record."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

try:
    from .verify_p5_06_original13_root_matrix_v5 import verify as verify_report
except ImportError:
    from verify_p5_06_original13_root_matrix_v5 import verify as verify_report


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "docs/baselines/p5-06-original13-root-matrix-v5-acceptance.v1.yaml"
SCHEMA = "sipi.p5-06.original13-root-matrix-v5-acceptance.v1"
HEX = re.compile(r"^[0-9a-f]{64}$")
GIT_HEX = re.compile(r"^[0-9a-f]{40}$")


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def path_is_safe(value: object) -> bool:
    return isinstance(value, str) and bool(value) and not Path(value).is_absolute() and "\\" not in value and all(
        part not in {"", ".", ".."} for part in value.split("/")
    )


def bound_file(root: Path, item: object, message: str) -> Path:
    require(isinstance(item, dict) and set(item) == {"path", "bytes", "sha256"}, message)
    require(path_is_safe(item["path"]) and isinstance(item["bytes"], int) and item["bytes"] > 0 and isinstance(item["sha256"], str) and HEX.fullmatch(item["sha256"]), message)
    path = root / item["path"]
    require(path.is_file() and path.stat().st_size == item["bytes"] and digest(path) == item["sha256"], message)
    return path


def verify(root: Path = ROOT) -> dict[str, object]:
    manifest_path = root / MANIFEST
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "schema", "status", "supersedes", "candidate", "upstream", "public_route", "matrix", "reports",
        "aggregate", "audit", "gate_tools", "performance", "gates", "claims", "non_claims",
    }
    require(isinstance(document, dict) and set(document) == expected, "manifest envelope")
    require(document["schema"] == SCHEMA and document["status"] == "accepted_stage1_public_root_scalar_and_per_workbook_performance", "manifest status")
    require(document["supersedes"] == {"path": "docs/baselines/p5-06-original13-rust-matlab-r2024b-current-acceptance.v1.yaml", "kind": "additive_public_root_replay"}, "supersedes")

    candidate = document["candidate"]
    upstream = document["upstream"]
    identity_keys = {"commit", "tree", "archive_bytes", "archive_sha256"}
    for identity, name in ((candidate, "candidate"), (upstream, "upstream")):
        require(isinstance(identity, dict) and set(identity) == identity_keys and all(isinstance(identity[key], str) and GIT_HEX.fullmatch(identity[key]) for key in ("commit", "tree")) and isinstance(identity["archive_sha256"], str) and HEX.fullmatch(identity["archive_sha256"]) and isinstance(identity["archive_bytes"], int) and identity["archive_bytes"] > 0, name)
    actual_tree = subprocess.run(["git", "-C", str(root), "show", "-s", "--format=%T", candidate["commit"]], check=True, capture_output=True, text=True).stdout.strip()
    require(actual_tree == candidate["tree"], "candidate tree")

    require(document["public_route"] == {"binary": "sipi.exe", "manifest": "crates/sipi-cli/Cargo.toml", "feature": "com-direct-integration", "argv": ["com", "run"], "receipt_schema": "sipi.com.r480-cli-receipt.v1"}, "public route")
    matrix = document["matrix"]
    require(matrix == {"workbooks": 13, "package_cases": 28, "scalar_slots": 303, "channels": ["THRU", "FEXT", "NEXT"], "matlab_release": "R2024b", "matlab_launch_mode": "python_engine_per_workbook_noFigureWindows_singleCompThread", "rust_rayon_num_threads": 16, "timing_scope": "model-subprocess-only:engine-start-run-quit-or-rust-run-write", "timing_clock": "perf_counter_ns"}, "matrix")

    reports = document["reports"]
    require(isinstance(reports, list) and [item.get("engine") if isinstance(item, dict) else None for item in reports] == ["matlab", "matlab", "rust", "rust"], "report order")
    report_hashes: list[str] = []
    report_documents: list[dict] = []
    for item in reports:
        require(isinstance(item, dict) and set(item) == {"path", "engine", "bytes", "sha256"}, "report binding")
        path = bound_file(root, {key: item[key] for key in ("path", "bytes", "sha256")}, "report content")
        report = json.loads(path.read_text(encoding="utf-8"))
        require(report["engine"] == item["engine"], "report engine")
        verify_report(report)
        require(report["source"]["candidate"] == candidate and report["source"]["upstream"] == upstream, "report source identity")
        report_hashes.append(item["sha256"])
        report_documents.append(report)

    aggregate_path = bound_file(root, document["aggregate"], "aggregate content")
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    require(aggregate["schema"] == "sipi.p5-06.original13-root-aggregate.v5" and aggregate["status"] == "accepted_stage1", "aggregate status")
    require(aggregate["matrix"] == {"workbook_count": 13, "case_count": 28, "scalar_slot_count": 303}, "aggregate matrix")
    require(aggregate["source"]["candidate"] == candidate and aggregate["source"]["upstream"] == upstream, "aggregate source")
    require([item["report_sha256"] for item in aggregate["runs"]] == report_hashes, "aggregate report hashes")
    require(aggregate["gates"] == {"matlab_repeat_1e_12": True, "rust_repeat_exact": True, "rust_vs_matlab_1e_9": True, "per_workbook_rust_not_slower": True, "total_rust_not_slower": True}, "aggregate gates")
    require(aggregate["claims"] == {"stage1_scalar_acceptance": True, "performance_acceptance": True, "array_acceptance": False, "release": False, "s_parameter_fit": False, "one_final_fd_to_td_impulse": True}, "aggregate claims")

    for item in document["gate_tools"].values():
        bound_file(root, item, "gate tool")
    bound_file(root, document["audit"], "audit content")

    performance = document["performance"]
    require(isinstance(performance, dict) and set(performance) == {"matlab_best_total_wall_ns", "rust_worst_total_wall_ns", "speedup_floor"}, "performance shape")
    require(performance["matlab_best_total_wall_ns"] == aggregate["performance"]["matlab_best_total_wall_ns"] and performance["rust_worst_total_wall_ns"] == aggregate["performance"]["rust_worst_total_wall_ns"], "performance totals")
    require(isinstance(performance["speedup_floor"], float) and math.isclose(performance["speedup_floor"], performance["matlab_best_total_wall_ns"] / performance["rust_worst_total_wall_ns"], rel_tol=1.0e-12), "speedup")
    require(document["gates"] == {"matlab_repeat_1e_12": True, "rust_repeat_exact": True, "rust_vs_matlab_1e_9": True, "per_workbook_rust_not_slower": True, "total_rust_not_slower": True, "s_parameter_fit": False, "one_final_fd_to_td_impulse": True}, "gates")
    require(document["claims"] == {"stage1_scalar_acceptance": True, "public_root_route_exercised": True, "performance_acceptance": True, "array_acceptance": False, "release": False, "p5_06_main_closed": False}, "claims")
    require(document["non_claims"] == ["no_single_thread_algorithm_comparison", "no_array_or_checkpoint_acceptance", "no_warning_or_full_surface_acceptance_beyond_303_scalar_slots", "no_ieee_certification", "no_release"], "non-claims")
    return {"valid": True, "status": document["status"], "aggregate_sha256": document["aggregate"]["sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root.resolve()), sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError, VerificationError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
