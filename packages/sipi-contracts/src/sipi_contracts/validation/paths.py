from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ..errors import ContractViolation


_WINDOWS_DEVICE_NAMES = {"con", "prn", "aux", "nul", *(f"com{index}" for index in range(1, 10)), *(f"lpt{index}" for index in range(1, 10))}


def portable_artifact_path_key(relative_path: str) -> str:
    """Return the Windows-safe identity key for a portable artifact path."""
    parts = relative_path.split("/")
    for part in parts:
        if part.endswith((".", " ")):
            raise ContractViolation("sipi.artifact-ref.v1", "path", "/relative_path", "artifact path segment has a trailing dot or space")
        if part.split(".", 1)[0].casefold() in _WINDOWS_DEVICE_NAMES:
            raise ContractViolation("sipi.artifact-ref.v1", "path", "/relative_path", "artifact path uses a Windows device name")
    return "/".join(part.casefold() for part in parts)


def resolve_artifact_path(run_root: str | Path, artifact: Mapping[str, object], *, must_exist: bool = False) -> Path:
    """Resolve an artifact only when its lexical and existing-parent paths stay in run_root."""
    schema_id = "sipi.artifact-ref.v1"
    relative_path = artifact.get("relative_path")
    if not isinstance(relative_path, str) or not relative_path or relative_path.endswith("/"):
        raise ContractViolation(schema_id, "path", "/relative_path", "artifact path must name a relative file")
    if "\\" in relative_path or ":" in relative_path or relative_path.startswith("/"):
        raise ContractViolation(schema_id, "path", "/relative_path", "artifact path is not portable")
    parts = relative_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ContractViolation(schema_id, "path", "/relative_path", "artifact path escapes its run root")
    portable_artifact_path_key(relative_path)
    root = Path(run_root).resolve(strict=True)
    candidate = root.joinpath(*parts)
    existing_parent = candidate.parent
    while not existing_parent.exists() and existing_parent != root:
        existing_parent = existing_parent.parent
    resolved_parent = existing_parent.resolve(strict=True)
    if root != resolved_parent and root not in resolved_parent.parents:
        raise ContractViolation(schema_id, "path", "/relative_path", "artifact path traverses a symlink outside the run root")
    resolved = resolved_parent.joinpath(*candidate.relative_to(existing_parent).parts)
    if resolved.exists() or resolved.is_symlink():
        if must_exist and not resolved.is_file():
            raise ContractViolation(schema_id, "missing_artifact", "/relative_path", "artifact file does not exist")
        resolved = resolved.resolve(strict=True)
        if root != resolved and root not in resolved.parents:
            raise ContractViolation(schema_id, "path", "/relative_path", "artifact file resolves outside the run root")
    elif must_exist:
        raise ContractViolation(schema_id, "missing_artifact", "/relative_path", "artifact file does not exist")
    return resolved
