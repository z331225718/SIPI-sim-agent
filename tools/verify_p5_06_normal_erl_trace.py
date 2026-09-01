"""Verify the immutable P5-06 named normal-ERL MATLAB trace checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from tools.aggregate_p5_06_normal_erl_trace import aggregate
except ImportError:
    from aggregate_p5_06_normal_erl_trace import aggregate


ARTIFACTS = {
    "replay_01": ("docs/baselines/p5-06-normal-erl-trace-replay-01.v1.json", "4cf71f3bf79bf6908492b3cae1233e520eaf80e9fea15663d5a0120ffe629ac6"),
    "replay_02": ("docs/baselines/p5-06-normal-erl-trace-replay-02.v1.json", "e2499752bcf306820bf7493e05fef37a6f75bc3728788620958203384109b1c9"),
    "aggregate": ("docs/baselines/p5-06-normal-erl-trace-aggregate.v1.json", "d98dd306cdbe61b152c15ee16fdd4a5fe978edd60c30a6c54ca7b9018e748978"),
    "runner": ("tools/run_com_normal_erl_trace_diagnostic.py", "889b70aa16e8c83569b159346869e065601ff14ec4fd75033e1fed14908ded2a"),
    "matlab_wrapper": ("tools/sipi_com_normal_erl_trace_run_v1.m", "5132882ecc8c90477653e80defd75933782df953893f2d5de1058c58beea6f11"),
    "matlab_sink": ("tools/sipi_com_normal_erl_trace_sink_v1.m", "a3922fad54a69f7bbb6856be9c39b9588c91690d7dc21ca29879c0eb4eb683a1"),
    "aggregate_tool": ("tools/aggregate_p5_06_normal_erl_trace.py", "cb6eaf0be31f8b817550ae72830442f6cde7508fd19ae6c1e7138488ee6dd6eb"),
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
    require(document["schema"] == "sipi.p5-06.normal-erl-trace-acceptance.v1", "manifest schema")
    require(document["status"] == "accepted_named_normal_erl_tdr_array_checkpoint", "manifest status")
    require(document["scope"] == {
        "candidate": {"commit": "b456e9d57b2449787e22cdefdad6c0edc70d69dc", "tree": "9cd25bd57387e571917cf5274952d8c4fffe44f5", "archive_sha256": "dfbf605916dccb0912a7dbc565eb49e58055efb869113ee0fc3704c598c0f0a8", "archive_bytes": 58337280},
        "upstream": {"commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea", "archive_sha256": "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf", "archive_bytes": 43694080},
        "matlab_release": "R2024b",
        "original_workbook_indices": [3, 4, 5],
        "ports": [1, 2],
        "vectors": {"time_s": "exact_f64_little_endian", "impedance_ohm": "exact_f64_little_endian", "ptdr": "exact_f64_little_endian", "gated": "exact_f64_little_endian"},
        "instrumentation": {"source_path": "matlab_src/com_ieee8023_480.m", "original_sha256": "88db14d7d82dab980d223a5be02a28013c11e0d0239e0e97e36c9d36fef55596", "instrumented_sha256": "1409a3b6923aa9e2dc8d736f0861123ea7a6602e39c65eeae729467c26928a3c"},
    }, "scope")
    require(document["artifacts"] == {key: {"path": path, "sha256": digest} for key, (path, digest) in ARTIFACTS.items()}, "artifact receipts")
    require(document["gates"] == {"two_fresh_matlab_instrumented_replays": True, "instrumentation_scalar_and_warning_semantics_unchanged": True, "matlab_rust_normal_erl_array_digest_identity": True, "matlab_rust_scalar_parity": True, "per_workbook_rust_not_slower": True, "s_parameter_fit": False}, "gates")
    require(document["performance"] == {"minimum_speedup_floor": 72.43344098541151, "performance_scope": "supplemental_direct_normal_erl_measurement"}, "performance")
    require(document["claims"] == {"named_normal_erl_tdr_array_checkpoint_parity": True, "supplemental_rust_performance_checkpoint": True, "p5_06_main_closed": False, "release": False}, "claims")
    require(document["non_claims"] == ["not_general_finite_erl_parity", "not_full_erl_result_graph", "not_public_result_wire", "not_complete_warning_catalog", "not_instrumented_matlab_performance", "not_ieee_certification", "not_release"], "non-claims")


def verify(root: Path) -> dict[str, str]:
    manifest = root / "docs/baselines/p5-06-normal-erl-trace-acceptance.v1.yaml"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    validate_document(document)
    paths = {key: root / path for key, (path, _) in ARTIFACTS.items()}
    for key, (_, digest) in ARTIFACTS.items():
        require(sha256(paths[key]) == digest, f"artifact receipt drift: {key}")
    first = json.loads(paths["replay_01"].read_text(encoding="utf-8"))
    second = json.loads(paths["replay_02"].read_text(encoding="utf-8"))
    replayed = aggregate(first, second, sha256(paths["replay_01"]), sha256(paths["replay_02"]))
    aggregate_document = json.loads(paths["aggregate"].read_text(encoding="utf-8"))
    require(replayed == aggregate_document, "aggregate replay drift")
    require(aggregate_document["gates"] == document["gates"], "aggregate gates")
    require(aggregate_document["performance"]["minimum_speedup_floor"] == document["performance"]["minimum_speedup_floor"], "aggregate performance")
    return {"valid": "true", "manifest_sha256": sha256(manifest), "aggregate_sha256": sha256(paths["aggregate"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(verify(args.root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
