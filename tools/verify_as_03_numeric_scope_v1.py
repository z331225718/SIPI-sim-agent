"""Verify the narrow AS-03 fixture-scoped numeric parity observation."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import verify_as_02_03_numeric_bound_v3 as bound_verifier

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/as-03-fit-yparam-numeric-scope-v1.yaml"
UPSTREAM_SOURCE = {"commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5", "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402", "archive_sha256": "a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144"}
CANDIDATE_SOURCE = {"commit": "aeb09982f360e73159d1335c6e0dd77d1176e65a", "tree": "4d0411d9439bed2ff5410b56f799ac47583bf43a", "archive_sha256": "272beba9cff45b449cf84c19dfcd026f5d42a3d470cdd18bf38a731b3780f4e0"}
HARNESS_SHA = {"tools/run_as_02_03_numeric_bound_v3.py": "1acc6d619b37f0ea1139ce4a21117024b723a5bf934b42b927fa6af3670e9c61", "tools/aggregate_as_02_03_numeric_bound_v3.py": "d951474d93d2c0cb110ab15ad2a961905d4c067db5b9cff6ddf91b3f96fbbae4"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _has_absolute(value: object) -> bool:
    if isinstance(value, dict):
        return any(_has_absolute(k) or _has_absolute(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_has_absolute(v) for v in value)
    return isinstance(value, str) and bool(re.search(r"(?:^[A-Za-z]:[\\/]|^//|^/(?!sipi-(?:candidate|target)(?:/|$)))", value))


def _repo_file(value: object, prefix: str) -> Path | None:
    if not isinstance(value, str) or not value.startswith(prefix) or ".." in Path(value).parts:
        return None
    path = ROOT / value
    return path if path.is_file() else None


def verify(path: Path = MANIFEST, document: dict[str, object] | None = None) -> dict[str, object]:
    doc = document if document is not None else yaml.safe_load(path.read_text(encoding="utf-8"))
    result = bound_verifier.verify(path, document=doc)
    blockers = list(result["blockers"])
    if doc.get("global_row_closed") is not False or doc.get("scope", {}).get("tolerance") != 1.0e-12:
        blockers.append("scope contract")
    if doc.get("status") != "scoped_numeric_parity_observation" or doc.get("parity_claim") is not False or doc.get("scoped_observation_passed") is not True:
        blockers.append("scoped status")
    return {
        "valid": not blockers,
        "blockers": blockers,
        "harness_binding": result.get("harness_binding", "unbound"),
    }


if __name__ == "__main__":
    result = verify(Path(sys.argv[1]) if len(sys.argv) > 1 else MANIFEST)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["valid"] else 1)
