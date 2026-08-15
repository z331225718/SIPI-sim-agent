"""Verify and materialize the provisional MIT product boundary inventory."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.product-boundary.v1"
CLASSES = {"product_candidate", "migration_only", "oracle_only", "quarantine", "generated"}
PROVENANCE = {"project_authored", "clean_room", "generated", "external"}
DISTRIBUTIONS = {"product", "evidence", "non-distributed"}


def _path_is_safe(path: str) -> bool:
    candidate = Path(path)
    return (
        bool(path)
        and "\\" not in path
        and not candidate.is_absolute()
        and all(part not in {"", ".", ".."} for part in path.split("/"))
    )


def _paths_sha256(paths: list[str]) -> str:
    return hashlib.sha256(("\n".join(paths) + "\n").encode("utf-8")).hexdigest()


def tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    paths = [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]
    return sorted(paths)


def _rule_matches(path: str, rule: dict) -> bool:
    includes = rule.get("include")
    excludes = rule.get("exclude", [])
    if not isinstance(includes, list) or not isinstance(excludes, list):
        return False
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in includes) and not any(
        fnmatch.fnmatchcase(path, pattern) for pattern in excludes
    )


def _rule_metadata(rule: dict) -> dict:
    return {
        "rule": rule["id"],
        "class": rule["class"],
        "license": rule["license"],
        "provenance": rule["provenance"],
        "distribution": rule["distribution"],
    }


def materialize_inventory(document: dict, paths: list[str]) -> tuple[dict[str, dict], list[str]]:
    blockers: list[str] = []
    inventory: dict[str, dict] = {}
    rules = document.get("rules")
    if not isinstance(rules, list):
        return {}, ["rules must be a list"]
    for path in paths:
        if not _path_is_safe(path):
            blockers.append(f"unsafe tracked path: {path!r}")
            continue
        matches = [rule for rule in rules if isinstance(rule, dict) and _rule_matches(path, rule)]
        if not matches:
            blockers.append(f"unclassified tracked path: {path}")
            continue
        if len(matches) != 1:
            blockers.append(f"ambiguous tracked path: {path} -> {[rule.get('id') for rule in matches]}")
            continue
        try:
            inventory[path] = _rule_metadata(matches[0])
        except KeyError as error:
            blockers.append(f"rule missing required field {error.args[0]!r}")
    return inventory, blockers


def _verify_rules(rules: object, blockers: list[str]) -> None:
    if not isinstance(rules, list) or not rules:
        blockers.append("rules must be a non-empty list")
        return
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            blockers.append("rule must be an object")
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            blockers.append("rule id must be non-empty")
        elif rule_id in seen:
            blockers.append(f"duplicate rule id: {rule_id}")
        else:
            seen.add(rule_id)
        includes = rule.get("include")
        if not isinstance(includes, list) or not includes or not all(isinstance(item, str) and item for item in includes):
            blockers.append(f"{rule_id}: include must be a non-empty string list")
        for field, allowed in (("class", CLASSES), ("provenance", PROVENANCE), ("distribution", DISTRIBUTIONS)):
            if rule.get(field) not in allowed:
                blockers.append(f"{rule_id}: invalid {field}")
        if not isinstance(rule.get("license"), str) or not rule["license"]:
            blockers.append(f"{rule_id}: license must be non-empty")
        if not isinstance(rule.get("owner"), str) or not rule["owner"]:
            blockers.append(f"{rule_id}: owner must be non-empty")
        if rule.get("class") == "product_candidate":
            if rule.get("license") != "MIT":
                blockers.append(f"{rule_id}: product_candidate must declare MIT")
            if rule.get("distribution") != "product":
                blockers.append(f"{rule_id}: product_candidate must use product distribution")
            if rule.get("provenance") not in {"project_authored", "clean_room"}:
                blockers.append(f"{rule_id}: product_candidate provenance is not promotable")
        if rule.get("class") != "product_candidate" and rule.get("distribution") == "product":
            blockers.append(f"{rule_id}: non-product class cannot use product distribution")
        if rule.get("class") == "generated":
            for field in ("generator", "generator_version", "inputs_sha256"):
                if not isinstance(rule.get(field), str) or not rule[field]:
                    blockers.append(f"{rule_id}: generated rule missing {field}")


def verify_document(document: object, paths: list[str], *, release: bool = False) -> dict:
    blockers: list[str] = []
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        return {"valid": False, "blockers": ["boundary manifest schema mismatch"]}
    if document.get("status") != "provisional":
        blockers.append("only provisional boundary manifests are supported by v1")
    if release:
        blockers.append("provisional boundary manifest cannot authorize a release")
    _verify_rules(document.get("rules"), blockers)
    expected, materialization_blockers = materialize_inventory(document, paths)
    blockers.extend(materialization_blockers)
    inventory = document.get("inventory")
    if not isinstance(inventory, dict):
        blockers.append("inventory must be an object")
    else:
        if inventory.get("source") != "git_ls_files":
            blockers.append("inventory source must be git_ls_files")
        if inventory.get("tracked_paths_sha256") != _paths_sha256(paths):
            blockers.append("tracked path inventory is stale")
        entries = inventory.get("entries")
        if not isinstance(entries, dict):
            blockers.append("inventory entries must be an object")
        else:
            for path in entries:
                if not _path_is_safe(path):
                    blockers.append(f"unsafe inventory path: {path!r}")
            if entries != expected:
                blockers.append("inventory entries do not match current rule materialization")
    return {
        "valid": not blockers,
        "status": document.get("status"),
        "tracked_path_count": len(paths),
        "product_candidate_count": sum(item.get("class") == "product_candidate" for item in expected.values()),
        "blockers": blockers,
    }


def _load_document(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("pyyaml is unavailable")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RuntimeError("boundary manifest must be a YAML object")
    return loaded


def write_inventory(path: Path, root: Path) -> dict:
    document = _load_document(path)
    paths = tracked_paths(root)
    entries, blockers = materialize_inventory(document, paths)
    if blockers:
        raise RuntimeError("; ".join(blockers))
    document["inventory"] = {
        "source": "git_ls_files",
        "tracked_paths_sha256": _paths_sha256(paths),
        "entries": entries,
    }
    with path.open("w", encoding="utf-8", newline="\n") as output:
        output.write(yaml.safe_dump(document, sort_keys=False, allow_unicode=False))
    return {"tracked_path_count": len(paths), "inventory_sha256": _paths_sha256(paths)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=ROOT / "product-boundary.v1.yaml")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-inventory", action="store_true")
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    try:
        if args.write_inventory:
            print(json.dumps(write_inventory(args.manifest, args.root), indent=2))
            return 0
        document = _load_document(args.manifest)
        report = verify_document(document, tracked_paths(args.root), release=args.release)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
