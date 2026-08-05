from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from sipi_contracts import (
    RunRecordV1,
    SipiArtifactRefV1,
    SuccessManifestV1,
    parse_artifact_ref,
    parse_run_record,
    parse_success_manifest,
    resolve_artifact_path,
    validate_success_manifest_relation,
)
from sipi_contracts.validation.paths import portable_artifact_path_key

from .checksums import canonical_json_bytes, checksums_document, sha256_file
from .errors import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    AttemptAlreadyExists,
    SuccessMarkerAlreadyExists,
    SuccessMarkerRejected,
)


_RUN_RECORD_NAME = "run-record.json"
_CHECKSUMS_NAME = "checksums.json"
_SUCCESS_MARKER_NAME = "success-manifest.json"


@dataclass(frozen=True, slots=True)
class PreparedAttempt:
    staging_dir: Path
    run_record: RunRecordV1
    artifacts: tuple[SipiArtifactRefV1, ...]


@dataclass(frozen=True, slots=True)
class MaterializedAttempt:
    attempt_dir: Path
    run_record: RunRecordV1
    manifest: SuccessManifestV1 | None
    marker_bytes: bytes | None


@dataclass(frozen=True, slots=True)
class InstalledMarker:
    attempt_dir: Path
    manifest: SuccessManifestV1


class AttemptStore:
    """Prepare immutable attempt evidence and expose success through one final marker."""

    def __init__(self, staging_root: str | Path, publish_root: str | Path) -> None:
        self._staging_root = _existing_root(staging_root, "staging")
        self._publish_root = _existing_root(publish_root, "publish")

    def prepare_attempt(self, staging_relative_path: str, run_record: RunRecordV1) -> PreparedAttempt:
        if not isinstance(run_record, RunRecordV1):
            raise TypeError("run_record must be a RunRecordV1")
        record = parse_run_record(run_record.to_wire())
        staging_dir = _existing_directory(self._staging_root, staging_relative_path, "staging")
        artifacts = tuple(parse_artifact_ref(artifact) for artifact in record.to_wire()["artifacts"])
        for artifact in artifacts:
            _verify_artifact(staging_dir, artifact)
        return PreparedAttempt(staging_dir=staging_dir, run_record=record, artifacts=artifacts)

    def materialize(self, prepared: PreparedAttempt, destination_relative_path: str) -> MaterializedAttempt:
        if not isinstance(prepared, PreparedAttempt):
            raise TypeError("prepared must be a PreparedAttempt")
        staging_dir = _existing_directory_under_root(self._staging_root, prepared.staging_dir, "staging")
        run_record = parse_run_record(prepared.run_record.to_wire())
        artifacts = tuple(parse_artifact_ref(artifact) for artifact in run_record.to_wire()["artifacts"])
        attempt_dir = _create_attempt_directory(self._publish_root, destination_relative_path)
        try:
            copied_entries = []
            for artifact in artifacts:
                source = _verify_artifact(staging_dir, artifact)
                target = _artifact_target(attempt_dir, artifact)
                _copy_new_file(source, target)
                copied_entries.append(_checksum_entry(artifact.to_wire()))
                _verify_artifact(attempt_dir, artifact)

            record_bytes = canonical_json_bytes(run_record.to_wire())
            record_path = attempt_dir / _RUN_RECORD_NAME
            _write_new_file_atomically(record_path, record_bytes)
            record_sha256, record_length = sha256_file(record_path)

            if run_record["status"] != "succeeded":
                return MaterializedAttempt(attempt_dir=attempt_dir, run_record=run_record, manifest=None, marker_bytes=None)

            checksum_entries = copied_entries + [{"byte_length": record_length, "relative_path": _RUN_RECORD_NAME, "sha256": record_sha256}]
            checksum_path = attempt_dir / _CHECKSUMS_NAME
            _write_new_file_atomically(checksum_path, checksums_document(checksum_entries))
            checksums_sha256, _ = sha256_file(checksum_path)
            manifest = parse_success_manifest({
                "schema": "sipi.success-manifest.v1",
                "run_id": run_record["run_id"],
                "analysis_id": run_record["analysis_id"],
                "attempt_id": run_record["attempt_id"],
                "run_record_sha256": record_sha256,
                "checksums_sha256": checksums_sha256,
                "artifacts": [artifact.to_wire() for artifact in artifacts],
                "extensions": {},
            })
            validate_success_manifest_relation(run_record, manifest)
            return MaterializedAttempt(attempt_dir=attempt_dir, run_record=run_record, manifest=manifest, marker_bytes=canonical_json_bytes(manifest.to_wire()))
        except Exception:
            # The incomplete destination remains diagnostic evidence but has no success marker.
            raise

    def install_success_marker(self, materialized: MaterializedAttempt) -> InstalledMarker:
        if not isinstance(materialized, MaterializedAttempt):
            raise TypeError("materialized must be a MaterializedAttempt")
        attempt_dir = _existing_directory_under_root(self._publish_root, materialized.attempt_dir, "publish")
        run_record = parse_run_record(materialized.run_record.to_wire())
        if run_record["status"] != "succeeded":
            raise SuccessMarkerRejected("only a succeeded materialized attempt can install a success marker")
        manifest = _verified_success_manifest(attempt_dir, run_record)
        marker = attempt_dir / _SUCCESS_MARKER_NAME
        if marker.exists() or marker.is_symlink():
            raise SuccessMarkerAlreadyExists("success marker already exists")
        try:
            _write_new_file_atomically(marker, canonical_json_bytes(manifest.to_wire()))
        except FileExistsError as error:
            raise SuccessMarkerAlreadyExists("success marker already exists") from error
        return InstalledMarker(attempt_dir=attempt_dir, manifest=manifest)


def _existing_root(value: str | Path, name: str) -> Path:
    path = Path(value).resolve(strict=True)
    if not path.is_dir():
        raise ArtifactStoreError(f"{name} root must be an existing directory")
    return path


def _relative_parts(relative_path: str) -> tuple[str, ...]:
    if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path or ":" in relative_path or relative_path.startswith("/"):
        raise ArtifactStoreError("attempt path must be a portable relative directory")
    parts = tuple(relative_path.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ArtifactStoreError("attempt path escapes its root")
    portable_artifact_path_key(relative_path)
    return parts


def _is_within(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _existing_directory(root: Path, relative_path: str, label: str) -> Path:
    candidate = root.joinpath(*_relative_parts(relative_path))
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as error:
        raise ArtifactStoreError(f"{label} attempt directory does not exist") from error
    if not resolved.is_dir() or not _is_within(root, resolved):
        raise ArtifactStoreError(f"{label} attempt directory escapes its root")
    return resolved


def _existing_directory_under_root(root: Path, value: str | Path, label: str) -> Path:
    try:
        resolved = Path(value).resolve(strict=True)
    except FileNotFoundError as error:
        raise ArtifactStoreError(f"{label} attempt directory does not exist") from error
    if not resolved.is_dir() or not _is_within(root, resolved):
        raise ArtifactStoreError(f"{label} attempt directory escapes its root")
    return resolved


def _create_attempt_directory(root: Path, relative_path: str) -> Path:
    parts = _relative_parts(relative_path)
    cursor = root
    for index, part in enumerate(parts):
        candidate = cursor / part
        if index == len(parts) - 1:
            try:
                candidate.mkdir()
            except FileExistsError as error:
                raise AttemptAlreadyExists("publish attempt directory already exists") from error
        elif candidate.exists() or candidate.is_symlink():
            if candidate.is_symlink() or not candidate.is_dir():
                raise ArtifactStoreError("publish path has a non-directory or symlink parent")
        else:
            candidate.mkdir()
        resolved = candidate.resolve(strict=True)
        if not _is_within(root, resolved):
            raise ArtifactStoreError("publish attempt directory escapes its root")
        cursor = resolved
    return cursor


def _artifact_target(attempt_dir: Path, artifact: SipiArtifactRefV1) -> Path:
    target = attempt_dir.joinpath(*str(artifact["relative_path"]).split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _verify_artifact(root: Path, artifact: SipiArtifactRefV1) -> Path:
    lexical_path = root.joinpath(*str(artifact["relative_path"]).split("/"))
    if lexical_path.is_symlink():
        raise ArtifactIntegrityError(f"artifact is a symlink: {artifact['relative_path']}")
    path = resolve_artifact_path(root, artifact.to_wire(), must_exist=True)
    if path.is_symlink() or not path.is_file():
        raise ArtifactIntegrityError(f"artifact is not a regular file: {artifact['relative_path']}")
    actual_sha256, actual_length = sha256_file(path)
    if actual_sha256 != artifact["sha256"] or actual_length != artifact["byte_length"]:
        raise ArtifactIntegrityError(f"artifact integrity mismatch: {artifact['relative_path']}")
    return path


def _checksum_entry(artifact: dict[str, object]) -> dict[str, object]:
    return {"byte_length": artifact["byte_length"], "relative_path": artifact["relative_path"], "sha256": artifact["sha256"]}


def _copy_new_file(source: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        raise AttemptAlreadyExists(f"artifact target already exists: {target}")
    with source.open("rb") as reader, target.open("xb") as writer:
        shutil.copyfileobj(reader, writer)
        writer.flush()
        os.fsync(writer.fileno())


def _write_new_file(path: Path, contents: bytes) -> None:
    with path.open("xb") as output:
        output.write(contents)
        output.flush()
        os.fsync(output.fileno())


def _write_new_file_atomically(path: Path, contents: bytes) -> None:
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    installed = False
    try:
        _write_new_file(temporary, contents)
        if os.name == "nt":
            os.rename(temporary, path)
        else:
            os.link(temporary, path)
        installed = True
    finally:
        if temporary.exists() or temporary.is_symlink():
            try:
                temporary.unlink()
            except OSError:
                if not installed:
                    raise


def _verified_success_manifest(attempt_dir: Path, run_record: RunRecordV1) -> SuccessManifestV1:
    record_path = attempt_dir / _RUN_RECORD_NAME
    expected_record = canonical_json_bytes(run_record.to_wire())
    if record_path.is_symlink() or not record_path.is_file() or record_path.read_bytes() != expected_record:
        raise ArtifactIntegrityError("materialized run record mismatch")
    record_sha256, record_length = sha256_file(record_path)
    artifacts = tuple(parse_artifact_ref(artifact) for artifact in run_record.to_wire()["artifacts"])
    entries = []
    for artifact in artifacts:
        _verify_artifact(attempt_dir, artifact)
        entries.append(_checksum_entry(artifact.to_wire()))
    entries.append({"byte_length": record_length, "relative_path": _RUN_RECORD_NAME, "sha256": record_sha256})
    checksum_path = attempt_dir / _CHECKSUMS_NAME
    expected_checksums = checksums_document(entries)
    if checksum_path.is_symlink() or not checksum_path.is_file() or checksum_path.read_bytes() != expected_checksums:
        raise ArtifactIntegrityError("materialized checksums mismatch")
    checksums_sha256, _ = sha256_file(checksum_path)
    manifest = parse_success_manifest({
        "schema": "sipi.success-manifest.v1",
        "run_id": run_record["run_id"],
        "analysis_id": run_record["analysis_id"],
        "attempt_id": run_record["attempt_id"],
        "run_record_sha256": record_sha256,
        "checksums_sha256": checksums_sha256,
        "artifacts": [artifact.to_wire() for artifact in artifacts],
        "extensions": {},
    })
    validate_success_manifest_relation(run_record, manifest)
    return manifest
