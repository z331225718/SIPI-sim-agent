from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ..errors import ContractViolation


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
