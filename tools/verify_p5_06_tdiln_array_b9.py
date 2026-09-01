"""Verify the b9b195a1 original-13 TDILN array replay record."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .aggregate_p5_06_tdiln_array_replay import aggregate
except ImportError:
    from aggregate_p5_06_tdiln_array_replay import aggregate


MANIFEST = "docs/baselines/p5-06-tdiln-array-b9-acceptance.v1.yaml"
ARTIFACTS = {
    "replay_01": ("docs/baselines/p5-06-tdiln-array-b9-replay-01.v1.json", "8f37dfac1b5c1d4bd5f8f9bd3475b2c709d6d85d35e9046f87dac87cc2e4e3d7"),
    "replay_02": ("docs/baselines/p5-06-tdiln-array-b9-replay-02.v1.json", "61e8a8aa62a5e873e3682caeb0674c1b1d9723fb97c9b3359582695c82763b89"),
    "aggregate": ("docs/baselines/p5-06-tdiln-array-b9-replay-aggregate.v1.json", "727455c104dd79a231e141f6e461f1886cd800d0e7b8dd2d47e04f2b027d5349"),
}
SCOPE = {
    "candidate": {"commit": "b9b195a19d3d209a37a52ba29c730759361dba03", "tree": "becca5842b55eeb1d1a310b2c3174458936ec901", "archive_sha256": "4e40155745d439a721e0f9923a36a60c9daf2404ff24f574b12a4fd7d425a8a2", "archive_bytes": 58705920},
    "upstream": {"commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea", "archive_sha256": "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf", "archive_bytes": 43694080},
    "matlab_release": "R2024b", "workbooks": 13, "channel_roles": ["THRU", "FEXT", "NEXT"],
    "vectors": {"time_s": "exact_f64_little_endian", "iln_pulse": {"atol": 5e-12, "rtol": 1e-9}, "reference_pulse": {"atol": 5e-12, "rtol": 1e-9}, "fitted_pulse": {"atol": 5e-12, "rtol": 1e-9}, "pdf_axis": {"atol": 5e-12, "rtol": 1e-9}, "pdf_probability": {"atol": 5e-12, "rtol": 1e-9}},
}
GATES = {"two_fresh_replays": True, "rust_semantic_repeat_exact": True, "per_workbook_rust_not_slower": True, "total_rust_not_slower": True}
PERFORMANCE = {"matlab_best_total_core_seconds": 1758.8355904, "rust_worst_total_wall_seconds": 190.41138859995408, "speedup_floor": 9.237029377981356}


class VerificationError(RuntimeError):
    pass


def require(value: bool, message: str) -> None:
    if not value:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt(path: str, digest: str) -> dict[str, str]:
    return {"path": path, "sha256": digest}


def verify(root: Path) -> dict[str, str]:
    document = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    expected_keys = {"schema", "status", "scope", "artifacts", "gates", "performance", "claims", "non_claims", "audit"}
    require(isinstance(document, dict) and set(document) == expected_keys, "manifest keys")
    require(document["schema"] == "sipi.p5-06.tdiln-array-b9-acceptance.v1" and document["status"] == "accepted_current_named_tdiln_array_checkpoint", "manifest status")
    require(document["scope"] == SCOPE and document["gates"] == GATES and document["performance"] == PERFORMANCE, "manifest scope or gates")
    require(document["artifacts"] == {key: receipt(path, digest) for key, (path, digest) in ARTIFACTS.items()}, "artifact receipts")
    require(document["claims"] == {"tdiln_named_intermediate_checkpoint_parity": True, "performance_acceptance_checkpoint": True, "full_result_graph": False, "complete_warning_catalog": False, "release": False, "p5_06_main_closed": False}, "claims")
    require(document["non_claims"] == ["public_tdiln_sidecar_wire", "complete_warning_catalog", "full_result_graph", "ieee_certification", "release"], "non claims")
    audit = document["audit"]
    require(isinstance(audit, dict) and set(audit) == {"path", "bytes", "sha256"}, "audit receipt")
    audit_path = root / audit["path"]
    require(audit_path.is_file() and audit_path.stat().st_size == audit["bytes"] and sha256(audit_path) == audit["sha256"], "audit drift")

    paths = {key: root / path for key, (path, _) in ARTIFACTS.items()}
    for key, (_, digest) in ARTIFACTS.items():
        require(paths[key].is_file() and sha256(paths[key]) == digest, f"artifact drift: {key}")
    first = json.loads(paths["replay_01"].read_text(encoding="utf-8"))
    second = json.loads(paths["replay_02"].read_text(encoding="utf-8"))
    replayed = aggregate(first, second, sha256(paths["replay_01"]), sha256(paths["replay_02"]))
    stored = json.loads(paths["aggregate"].read_text(encoding="utf-8"))
    require(replayed == stored and stored["status"] == "accepted_diagnostic_checkpoint", "aggregate replay")
    require(stored["source"]["candidate"] == SCOPE["candidate"] and stored["source"]["upstream"] == SCOPE["upstream"], "archive provenance")
    require(stored["gates"] == GATES and stored["performance"] == {"per_workbook": stored["performance"]["per_workbook"], **PERFORMANCE}, "aggregate gates")
    require(stored["source"]["toolchain"]["matlab"]["release"] == "R2024b", "MATLAB release")
    return {"valid": "true", "aggregate_sha256": sha256(paths["aggregate"]), "manifest_sha256": sha256(root / MANIFEST)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(verify(args.root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
