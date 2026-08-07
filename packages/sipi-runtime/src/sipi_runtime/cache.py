"""Content-addressed success cache (M3-09b).

The cache stores one immutable success manifest plus its artifacts per final
cache identity (see ``cache_identity``): canonical payload, input/upstream
artifact hashes, complete resolved selection, actual bundle hashes, schema/
profile, resources and randomness.  Execution-layer IDs and lineage never
participate.  A cache hit reuses the original success manifest instead of
faking an engine run.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class CacheMiss(LookupError):
    pass


@dataclass(frozen=True)
class CacheRecord:
    key: str
    manifest_sha256: str
    manifest: Mapping[str, Any]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CacheStore:
    """Directory-per-key cache under ``root/<key>/``."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _dir(self, key: str) -> Path:
        return self.root / hashlib.sha256(key.encode("utf-8")).hexdigest()

    def lookup(self, key: str) -> CacheRecord:
        directory = self._dir(key)
        manifest_path = directory / "success-manifest.json"
        if not manifest_path.is_file():
            raise CacheMiss(key)
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        return CacheRecord(key=key, manifest_sha256=_sha256_bytes(manifest_bytes), manifest=manifest)

    def store(self, key: str, manifest: Mapping[str, Any], artifacts: Mapping[str, Path]) -> str:
        directory = self._dir(key)
        manifest_bytes = json.dumps(dict(manifest), sort_keys=True, separators=(",", ":")).encode("utf-8")
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "success-manifest.json").write_bytes(manifest_bytes)
        for relative_path, source in artifacts.items():
            target = directory / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return _sha256_bytes(manifest_bytes)

    def materialize(self, key: str, run_root: Path) -> None:
        """Copy cached artifacts into the run root (downstream bound inputs rely on them)."""
        record = self.lookup(key)
        for artifact in record.manifest.get("artifacts", []):
            relative_path = artifact["relative_path"]
            source = self._dir(key) / relative_path
            target = run_root / relative_path
            if not source.is_file():
                raise CacheMiss(f"cached artifact missing: {relative_path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
