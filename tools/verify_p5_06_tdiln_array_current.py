"""Verify the immutable current P5-06 TDILN array checkpoint record."""

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
        "docs/baselines/p5-06-tdiln-array-current-replay-01.v1.json",
        "b76c3c854c4a09e13eb7091b2a08f3dac314a2459fd8445f03feaf91573edfea",
    ),
    "replay_02": (
        "docs/baselines/p5-06-tdiln-array-current-replay-02.v1.json",
        "53e133ecd486d6bad16ffa23813c42a6588daf569e5b27059ccdf6e53cf0c2b0",
    ),
    "aggregate": (
        "docs/baselines/p5-06-tdiln-array-current-replay-aggregate.v1.json",
        "edc0329b18c236b91deab92bd461fa643ccb99bcfbe58674de2644358db2465e",
    ),
}

EXPECTED_SCOPE = {
    "candidate": {
        "commit": "25c7ac5a348f5b5346ca6becd25b4e3dfbd4595f",
        "tree": "7fb38b6b31f0b7d26eda3ca5149e8509e06f9734",
        "archive_sha256": "1e379945bdbdc973443b9d508578b15a6fd4e8c4ab6db1d6de84156891123000",
        "archive_bytes": 58234880,
    },
    "upstream": {
        "commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
        "tree": "7094ab6e84989b218730c52432c70da10261f8ea",
    },
    "matlab_release": "R2024b",
    "original_workbook_count": 13,
    "channel_roles": ["THRU", "FEXT", "NEXT"],
    "named_sidecar_vectors": {
        "time_s": "exact_f64_little_endian",
        "iln_pulse": {"atol": 5e-12, "rtol": 1e-9},
        "reference_pulse": {"atol": 5e-12, "rtol": 1e-9},
        "fitted_pulse": {"atol": 5e-12, "rtol": 1e-9},
        "pdf_axis": {"atol": 5e-12, "rtol": 1e-9},
        "pdf_probability": {"atol": 5e-12, "rtol": 1e-9},
    },
}
GATES = {
    "two_fresh_replays": True,
    "rust_semantic_repeat_exact": True,
    "per_workbook_rust_not_slower": True,
    "total_rust_not_slower": True,
}
PERFORMANCE = {
    "matlab_best_total_core_seconds": 1738.2513337999999,
    "rust_worst_total_wall_seconds": 539.4338988000527,
    "speedup_floor": 3.222362068210145,
}
CLAIMS = {
    "tdiln_named_intermediate_checkpoint_parity": True,
    "performance_acceptance_checkpoint": True,
    "full_result_graph": False,
    "complete_warning_catalog": False,
    "release": False,
    "p5_06_main_closed": False,
}
NON_CLAIMS = ["public_tdiln_sidecar_wire", "complete_warning_catalog", "full_result_graph", "release"]


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
        document["schema"] == "sipi.p5-06.tdiln-array-current-acceptance.v1"
        and document["status"] == "accepted_current_named_tdiln_array_checkpoint",
        "manifest status",
    )
    require(document["scope"] == EXPECTED_SCOPE, "scope")
    require(
        document["artifacts"] == {key: {"path": path, "sha256": digest} for key, (path, digest) in ARTIFACTS.items()},
        "artifact receipts",
    )
    require(document["gates"] == GATES, "gates")
    require(document["performance"] == PERFORMANCE, "performance")
    require(document["claims"] == CLAIMS, "claims")
    require(document["non_claims"] == NON_CLAIMS, "non-claims")


def verify(root: Path) -> dict[str, str]:
    manifest = root / "docs/baselines/p5-06-tdiln-array-current-acceptance.v1.yaml"
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
    require(aggregate_document["gates"] == GATES, "aggregate gates")
    require(
        aggregate_document["performance"] == {"per_workbook": aggregate_document["performance"]["per_workbook"], **PERFORMANCE},
        "aggregate performance",
    )
    return {"valid": "true", "manifest_sha256": sha256(manifest), "aggregate_sha256": sha256(paths["aggregate"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(verify(args.root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
