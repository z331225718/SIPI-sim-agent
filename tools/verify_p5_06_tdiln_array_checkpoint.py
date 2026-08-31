"""Verify the immutable P5-06 named TDILN array checkpoint record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from tools.aggregate_p5_06_tdiln_array_replay import aggregate
except ImportError:
    from aggregate_p5_06_tdiln_array_replay import aggregate


ARTIFACTS = {
    "replay_01": (
        "docs/baselines/p5-06-tdiln-array-replay-01.v1.json",
        "81e39e0297ae5a2990c38b6540e68faed7d6a23d3469bca9f67c7b893605045c",
    ),
    "replay_02": (
        "docs/baselines/p5-06-tdiln-array-replay-02.v1.json",
        "7487a2547cbfd698a52a29ea8a73fa6352948fd61d63b0654577f2b23aad3c4e",
    ),
    "aggregate": (
        "docs/baselines/p5-06-tdiln-array-replay-aggregate.v1.json",
        "4cb31424ce65901fae09ec4f856b6f90b1fec6b3bdf809e1d0d26657ed02bf01",
    ),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_document(document: Any) -> None:
    require(isinstance(document, dict), "manifest mapping")
    expected = {"schema", "status", "scope", "artifacts", "gates", "performance", "claims", "non_claims"}
    require(set(document) == expected, "manifest keys")
    require(
        document["schema"] == "sipi.p5-06.tdiln-array-checkpoint-acceptance.v1"
        and document["status"] == "accepted_named_tdiln_array_checkpoint",
        "manifest status",
    )
    scope = document["scope"]
    require(isinstance(scope, dict) and set(scope) == {"candidate", "upstream", "matlab_release", "original_workbook_count", "channel_roles", "named_sidecar_vectors"}, "scope keys")
    require(scope["candidate"] == {"commit": "f26cb1748c63b08db8e60dd558bc9ae18515a198", "tree": "8ed0cee4aab31ec58caf17ad6f71bbedfe38c998", "archive_sha256": "6861b73d21de3fd21a4a6796b4e9fa1885f37bc940b4ec84aa60eff5d896b11b", "archive_bytes": 58101760}, "candidate")
    require(scope["upstream"] == {"commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea"}, "upstream")
    require(scope["matlab_release"] == "R2024b" and scope["original_workbook_count"] == 13 and scope["channel_roles"] == ["THRU", "FEXT", "NEXT"], "matrix scope")
    require(scope["named_sidecar_vectors"] == {"time_s": "exact_f64_little_endian", "iln_pulse": {"atol": 5e-12, "rtol": 1e-9}, "reference_pulse": {"atol": 5e-12, "rtol": 1e-9}, "fitted_pulse": {"atol": 5e-12, "rtol": 1e-9}, "pdf_axis": {"atol": 5e-12, "rtol": 1e-9}, "pdf_probability": {"atol": 5e-12, "rtol": 1e-9}}, "array scope")
    require(document["artifacts"] == {key: {"path": path, "sha256": digest} for key, (path, digest) in ARTIFACTS.items()}, "artifact receipts")
    require(document["gates"] == {"two_fresh_replays": True, "rust_semantic_repeat_exact": True, "per_workbook_rust_not_slower": True, "total_rust_not_slower": True}, "gates")
    require(document["performance"] == {"matlab_best_total_core_seconds": 1748.0102438, "rust_worst_total_wall_seconds": 463.4996931000496, "speedup_floor": 3.7713298839718536}, "performance")
    require(document["claims"] == {"tdiln_named_intermediate_checkpoint_parity": True, "performance_acceptance_checkpoint": True, "full_result_graph": False, "complete_warning_catalog": False, "release": False, "p5_06_main_closed": False}, "claims")
    require(document["non_claims"] == ["current_candidate_rebinding", "public_tdiln_sidecar_wire", "complete_warning_catalog", "full_result_graph", "release"], "non-claims")


def verify(root: Path) -> dict[str, str]:
    manifest = root / "docs/baselines/p5-06-tdiln-array-checkpoint-acceptance.v1.yaml"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    validate_document(document)
    paths = {key: root / path for key, (path, _) in ARTIFACTS.items()}
    for key, (_, digest) in ARTIFACTS.items():
        require(sha256(paths[key]) == digest, f"artifact receipt drift: {key}")
    first = json.loads(paths["replay_01"].read_text(encoding="utf-8"))
    second = json.loads(paths["replay_02"].read_text(encoding="utf-8"))
    aggregate_document = json.loads(paths["aggregate"].read_text(encoding="utf-8"))
    replayed = aggregate(first, second, sha256(paths["replay_01"]), sha256(paths["replay_02"]))
    require(replayed == aggregate_document, "aggregate replay drift")
    require(aggregate_document["status"] == "accepted_diagnostic_checkpoint", "aggregate status")
    require(aggregate_document["gates"] == document["gates"], "aggregate gates")
    require(aggregate_document["performance"] == {"per_workbook": aggregate_document["performance"]["per_workbook"], **document["performance"]}, "aggregate performance")
    require(aggregate_document["claims"] == {"tdiln_named_intermediate_checkpoint_parity": True, "performance_acceptance_checkpoint": True, "full_result_graph": False, "complete_warning_catalog": False, "channel_s_parameter_fit": False, "release": False}, "aggregate claims")
    return {"valid": "true", "manifest_sha256": sha256(manifest), "aggregate_sha256": sha256(paths["aggregate"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(verify(args.root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
