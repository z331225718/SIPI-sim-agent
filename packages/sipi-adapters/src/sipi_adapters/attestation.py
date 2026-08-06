"""Engine bundle attestation (M2-09).

Verifies a pinned wheel bundle against its engine.lock manifest: bundle
sha256, every declared file inside the archive (sha256 + byte length), and the
entrypoint presence.  Execution of wheel bundles (isolated venv install) is a
separate later slice; attestation is the evidence gate before any such run.
"""

from __future__ import annotations

import hashlib
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AttestationError(ValueError):
    """Raised when a wheel bundle fails attestation."""


@dataclass(frozen=True)
class WheelAttestation:
    instance_id: str
    bundle_path: str
    bundle_sha256: str
    entrypoint: str
    verified_files: tuple[str, ...]
    license_status: str
    capabilities_sha256: str

    def to_wire(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "bundle_path": self.bundle_path,
            "bundle_sha256": self.bundle_sha256,
            "entrypoint": self.entrypoint,
            "verified_files": list(self.verified_files),
            "license_status": self.license_status,
            "capabilities_sha256": self.capabilities_sha256,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_wheel_bundle(engine_entry: Mapping[str, Any], repo_root: Path) -> WheelAttestation:
    bundle = engine_entry["bundle"]
    if bundle["kind"] != "local_path":
        raise AttestationError("https_url bundles cannot be attested without an approved downloader")
    candidate = (repo_root / bundle["path"]).resolve()
    if not candidate.is_relative_to(repo_root):
        raise AttestationError("bundle path escapes the repository root")
    if not candidate.is_file():
        raise AttestationError(f"engine bundle is missing: {candidate}")
    if candidate.suffix.lower() != ".whl":
        raise AttestationError("wheel attestation requires a .whl bundle")
    if _sha256(candidate) != bundle["sha256"]:
        raise AttestationError(f"engine bundle sha256 mismatch: {candidate}")
    manifest = engine_entry["bundle_manifest"]
    entrypoints = [item for item in manifest["files"] if item["role"] == "entrypoint"]
    if len(entrypoints) != 1:
        raise AttestationError("wheel manifest requires exactly one entrypoint")
    try:
        with zipfile.ZipFile(candidate) as archive:
            names = set(archive.namelist())
            verified: list[str] = []
            for item in manifest["files"]:
                relative = item["relative_path"]
                if relative not in names:
                    raise AttestationError(f"manifest file missing inside wheel: {relative}")
                data = archive.read(relative)
                if len(data) != item["byte_length"]:
                    raise AttestationError(f"manifest byte length mismatch: {relative}")
                actual = hashlib.sha256(data).hexdigest()
                if actual != item["sha256"]:
                    raise AttestationError(f"manifest file hash mismatch: {relative}")
                verified.append(relative)
            entrypoint = entrypoints[0]["relative_path"]
            if entrypoint not in names:
                raise AttestationError(f"entrypoint missing inside wheel: {entrypoint}")
            if not any(name.endswith(".dist-info/METADATA") for name in names):
                raise AttestationError("wheel is missing .dist-info/METADATA")
    except (zipfile.BadZipFile, KeyError, OSError) as error:
        raise AttestationError(f"wheel archive verification failed: {error}") from error
    return WheelAttestation(
        instance_id=engine_entry["instance_id"],
        bundle_path=str(candidate),
        bundle_sha256=bundle["sha256"],
        entrypoint=entrypoint,
        verified_files=tuple(verified),
        license_status=engine_entry["license_provenance"]["distribution_status"],
        capabilities_sha256=engine_entry["capabilities"]["sha256"],
    )
