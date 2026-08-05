from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from sipi_contracts.validation.paths import portable_artifact_path_key


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_length = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            byte_length += len(chunk)
    return digest.hexdigest(), byte_length


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def checksums_document(entries: Iterable[Mapping[str, Any]]) -> bytes:
    files = [dict(entry) for entry in entries]
    files.sort(key=lambda entry: portable_artifact_path_key(str(entry["relative_path"])))
    return canonical_json_bytes({"algorithm": "sha256", "files": files, "version": 1})
