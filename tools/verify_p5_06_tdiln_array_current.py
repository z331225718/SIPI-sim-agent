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
        "6459743d8957d895d80a5ac62baa3c5f83d457ef9ca4f16ba1eae3335e84c2c4",
    ),
    "replay_02": (
        "docs/baselines/p5-06-tdiln-array-current-replay-02.v1.json",
        "68b56f3ac8899fbbc8d52d86abd480398c9e805d9470501b8486ba4e78685094",
    ),
    "aggregate": (
        "docs/baselines/p5-06-tdiln-array-current-replay-aggregate.v1.json",
        "5306c74a4872a1d86d377b2a0d4f2700ff1c2ef14a3fdafffcba481e3ff00018",
    ),
}

EXPECTED_SCOPE = {
    "candidate": {
        "commit": "b456e9d57b2449787e22cdefdad6c0edc70d69dc",
        "tree": "9cd25bd57387e571917cf5274952d8c4fffe44f5",
        "archive_sha256": "dfbf605916dccb0912a7dbc565eb49e58055efb869113ee0fc3704c598c0f0a8",
        "archive_bytes": 58337280,
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
    "matlab_best_total_core_seconds": 1753.3723475,
    "rust_worst_total_wall_seconds": 195.89563529996667,
    "speedup_floor": 8.950543205391662,
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
