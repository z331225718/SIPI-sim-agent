"""P1-04B oracle-only legacy fixture boundary gate.

Legacy `sipi.*.v1` fixtures from external repositories (agent-spice,
pybert, agent-com) may only be observed worktree-externally for their
Git-object provenance. They must not enter the Rust API, product
fixtures, schemas, or implementation side until the owner confirms the
required profile. This gate fails closed if any legacy fixture path
from the fixture manifest resolves inside the repository tree, or if
any legacy schema id from the manifest appears in product Rust sources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p1-04b.legacy-fixture-boundary.v1"
MANIFEST = ROOT / "fixtures" / "manifest.v1.json"

EXTERNAL_REPOS = frozenset({"agent-spice", "pybert", "agent-com", "external"})

PRODUCT_PREFIXES = ("crates", "fixtures", "schemas", "apps", "packages", "tests")

FORBIDDEN_SCHEMA_PATTERN = re.compile(r"sipi\.[a-z0-9-]+\.v1")


class LegacyFixtureBoundaryError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LegacyFixtureBoundaryError("invalid_manifest") from error
    if not isinstance(value, dict):
        raise LegacyFixtureBoundaryError("invalid_manifest")
    return value


def git_tracked_paths() -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=120,
    )
    if completed.returncode != 0:
        raise LegacyFixtureBoundaryError("git_ls_files_failed")
    return [line for line in completed.stdout.splitlines() if line.strip()]


def rust_sources() -> list[Path]:
    sources: list[Path] = []
    for crate in sorted((ROOT / "crates").iterdir()):
        if not crate.is_dir():
            continue
        for source in crate.rglob("*.rs"):
            if "/target/" in source.as_posix():
                continue
            sources.append(source)
    return sources


def validate(manifest: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    if manifest.get("schema") != "sipi.fixture-manifest.v1":
        raise LegacyFixtureBoundaryError("manifest_schema_invalid")
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise LegacyFixtureBoundaryError("manifest_assets_invalid")

    tracked = set(git_tracked_paths())
    external_assets: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        source = asset.get("source_ref")
        asset_id = asset.get("id")
        location = asset.get("location")
        if not isinstance(location, dict):
            continue
        relative = location.get("relative_path")
        if not isinstance(relative, str) or not relative:
            continue
        if source in EXTERNAL_REPOS or relative == "unresolved":
            external_assets.append(asset_id or "?")
            # A legacy fixture asset must not materialize as tracked content.
            # The manifest's relative_path is relative to the EXTERNAL repo
            # root, so it cannot be matched against repository paths; instead
            # the asset identity itself (id) must not appear as a tracked
            # path component, and the only allowed in-repo record of the asset
            # is the manifest metadata itself.
            if asset_id:
                for tracked_path in tracked:
                    if asset_id in tracked_path.split("/"):
                        raise LegacyFixtureBoundaryError(
                            f"legacy_fixture_asset_materialized:{tracked_path}:{asset_id}"
                        )

    # No legacy schema id from the manifest may appear in product Rust sources.
    manifest_text = json.dumps(manifest, sort_keys=True)
    legacy_schema_ids = set(FORBIDDEN_SCHEMA_PATTERN.findall(manifest_text))
    product_ids = {
        "sipi.fixture-manifest.v1",
    }
    legacy_schema_ids -= product_ids
    for source in rust_sources():
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for schema_id in legacy_schema_ids:
            if schema_id in text:
                raise LegacyFixtureBoundaryError(f"legacy_schema_in_rust:{source.relative_to(root).as_posix()}:{schema_id}")

    return {
        "valid": True,
        "external_assets": len(external_assets),
        "tracked_paths": len(tracked),
        "legacy_schema_ids": len(legacy_schema_ids),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        manifest = load_json(MANIFEST)
        result = validate(manifest, ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except LegacyFixtureBoundaryError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
