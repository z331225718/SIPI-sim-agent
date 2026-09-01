"""Audit recovery of the original Agent-Spice AS-04 signoff corpus.

This is an evidence collector, not a fixture generator.  It deliberately keeps
documentation examples and synthetic replay inputs separate from the original
``runs/yparam-tran-signoff`` inputs.  The default scan is bounded to known
workspace/cache roots and only hashes files whose names match the requested
corpus or known source documents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Iterable, Iterator, Mapping, Sequence


SCHEMA = "sipi.as04-signoff-corpus-recovery.v1"
SIGNOFF_RELATIVE_PATHS = (
    "runs/yparam-tran-signoff/vddq_port3_port10.s2p",
    "runs/yparam-tran-signoff/ybootstrap_blackbox.rfm",
    "runs/yparam-tran-signoff/ybootstrap_blackbox.sp",
)
SIGNOFF_BASENAMES = frozenset(Path(path).name.lower() for path in SIGNOFF_RELATIVE_PATHS)
SEARCH_MARKERS = (
    "vddq_port3_port10.s2p",
    "ybootstrap_blackbox.rfm",
    "ybootstrap_blackbox.sp",
    "yparam-tran-signoff",
    "yfit_vs_raw_rms",
    "yfit_vs_raw_peak",
)
MEASURE_NAMES = ("yfit_vs_raw_rms", "yfit_vs_raw_peak")
RESIDUAL_POLES_HZ = (
    "0.0628318530718",
    "0.8115045878714",
    "10.48098478623",
    "135.3671238969",
    "1748.33363523",
    "22580.59720916",
    "291639.6276132",
    "3766670.63349",
    "48648421.94905",
    "628318530.718",
)
BAND_BOUNDARIES_HZ = ("22580.59720916", "3766670.63349")
TEXT_SUFFIXES = frozenset(
    {
        ".csv",
        ".json",
        ".md",
        ".py",
        ".rfm",
        ".rs",
        ".s2p",
        ".sp",
        ".txt",
        ".toml",
        ".yaml",
        ".yml",
    }
)
PRUNED_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "node_modules",
        "site-packages",
        "target",
        "venv",
    }
)
KNOWN_DOCUMENT_RELATIVE_PATHS = (
    "engines/agent-spice/docs/yparam-heldout-tran-signoff-report.md",
    "docs/baselines/as-04-tune-yparam-tran-direct-port.v2.yaml",
    "docs/baselines/audits/2026-08-23-as-04-tune-yparam-tran-v2.md",
)
AUDIT_OWNED_NAMES = frozenset(
    {
        "audit_as04_signoff_corpus_recovery.py",
        "test_audit_as04_signoff_corpus_recovery.py",
        "2026-09-02-as04-signoff-corpus-recovery.md",
    }
)
HSPICE_PATH = Path(r"C:\synopsys\Hspice_T-2022.06-1\WIN64\hspice.exe")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def _walk_files(root: Path) -> Iterator[Path]:
    """Walk without following links or descending into build/vendor trees."""

    if not root.exists() or not root.is_dir():
        return
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories[:] = [
            name
            for name in directories
            if name.lower() not in PRUNED_DIR_NAMES and not Path(current, name).is_symlink()
        ]
        for name in files:
            path = Path(current, name)
            if not path.is_symlink():
                yield path


def classify_match(path: Path, root: Path) -> str:
    """Classify a matching path without treating docs or fixtures as inputs."""

    relative = path.relative_to(root).as_posix().lower()
    if relative.startswith("docs/") or "/docs/" in relative:
        return "documentation_example"
    if relative.startswith("runs/yparam-tran-signoff/"):
        return "original_signoff_layout_candidate"
    if "fixture" in relative or "synthetic" in relative or "test" in relative:
        return "synthetic_or_test_artifact"
    return "untracked_or_cached_candidate"


def find_exact_files(roots: Iterable[Path]) -> list[dict[str, object]]:
    """Find exact corpus basenames and hash only the matching files."""

    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for root in roots:
        root = root.resolve()
        for path in _walk_files(root):
            if path.name.lower() not in SIGNOFF_BASENAMES:
                continue
            key = _normalise_path(path).lower()
            if key in seen:
                continue
            seen.add(key)
            record: dict[str, object] = {
                "path": _normalise_path(path),
                "relative_path": path.relative_to(root).as_posix(),
                "root": _normalise_path(root),
                "classification": classify_match(path, root),
            }
            try:
                record["bytes"] = path.stat().st_size
                record["sha256"] = sha256_file(path)
            except OSError as error:
                record["read_error"] = f"{type(error).__name__}: {error}"
            records.append(record)
    return sorted(records, key=lambda record: str(record["path"]).lower())


def find_marker_files(roots: Iterable[Path], max_bytes: int = 32 * 1024 * 1024) -> list[dict[str, object]]:
    """Search bounded text-like files for corpus markers.

    This catches renamed reports and cached source snippets while avoiding
    binary databases and generated dependency trees.  A marker hit is not
    evidence that the referenced file exists.
    """

    markers = tuple(marker.lower().encode("utf-8") for marker in SEARCH_MARKERS)
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for root in roots:
        root = root.resolve()
        for path in _walk_files(root):
            if path.name.lower() in AUDIT_OWNED_NAMES:
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            key = _normalise_path(path).lower()
            if key in seen:
                continue
            seen.add(key)
            try:
                size = path.stat().st_size
                if size > max_bytes:
                    continue
                data = path.read_bytes().lower()
            except (OSError, UnicodeError):
                continue
            hits = [SEARCH_MARKERS[index] for index, marker in enumerate(markers) if marker in data]
            if hits:
                records.append(
                    {
                        "path": _normalise_path(path),
                        "root": _normalise_path(root),
                        "bytes": size,
                        "sha256": sha256_bytes(path.read_bytes()),
                        "markers": hits,
                        "classification": classify_match(path, root),
                    }
                )
    return sorted(records, key=lambda record: str(record["path"]).lower())


def _run_git(repo: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _git_status(repo: Path) -> dict[str, object]:
    result = _run_git(repo, ["status", "--porcelain=v1", "--untracked-files=all"])
    lines = [line for line in result.stdout.splitlines() if line]
    return {
        "exit_code": result.returncode,
        "clean": result.returncode == 0 and not lines,
        "entry_count": len(lines),
    }


def _git_paths(repo: Path) -> tuple[int, list[str], dict[str, list[str]]]:
    result = _run_git(repo, ["rev-list", "--objects", "--all", "--reflog"])
    lines = [line for line in result.stdout.splitlines() if line]
    paths: list[str] = []
    object_paths: dict[str, list[str]] = {}
    for line in lines:
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        object_id, path = parts
        paths.append(path)
        object_paths.setdefault(object_id, []).append(path)
    return result.returncode, paths, object_paths


def _git_object_stats(repo: Path) -> dict[str, object]:
    result = _run_git(repo, ["cat-file", "--batch-all-objects", "--batch-check"])
    counts: dict[str, int] = {}
    total_bytes = 0
    object_count = 0
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) != 3:
                continue
            _, object_type, size = parts
            counts[object_type] = counts.get(object_type, 0) + 1
            if object_type == "blob":
                total_bytes += int(size)
            object_count += 1
    return {
        "exit_code": result.returncode,
        "object_count": object_count,
        "counts": counts,
        "blob_bytes": total_bytes,
    }


def _git_blob_marker_hits(
    repo: Path, object_paths: Mapping[str, Sequence[str]], max_hits: int = 200
) -> list[dict[str, object]]:
    """Search all Git blob objects, including unreachable packed objects."""

    inventory = _run_git(repo, ["cat-file", "--batch-all-objects", "--batch-check"])
    if inventory.returncode != 0:
        return []
    blob_ids = [
        line.split()[0]
        for line in inventory.stdout.splitlines()
        if len(line.split()) == 3 and line.split()[1] == "blob"
    ]
    if not blob_ids:
        return []
    marker_bytes = tuple(marker.lower().encode("utf-8") for marker in SEARCH_MARKERS)
    hits: list[dict[str, object]] = []
    # Keep each batch bounded.  Agent-Spice contains large generated blobs;
    # sending every object in one ``cat-file`` request would retain gigabytes
    # of payload in the Python process even though only marker hits matter.
    for start in range(0, len(blob_ids), 256):
        batch_ids = blob_ids[start : start + 256]
        try:
            batch = subprocess.run(
                ["git", "-C", str(repo), "cat-file", "--batch"],
                input=("\n".join(batch_ids) + "\n").encode("ascii"),
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if batch.returncode != 0:
            continue
        output = batch.stdout
        offset = 0
        for object_id in batch_ids:
            header_end = output.find(b"\n", offset)
            if header_end < 0:
                break
            header = output[offset:header_end]
            header_parts = header.decode("ascii", errors="replace").strip().split()
            if len(header_parts) != 3 or header_parts[1] != "blob":
                break
            try:
                size = int(header_parts[2])
            except ValueError:
                break
            data_start = header_end + 1
            data_end = data_start + size
            data = output[data_start:data_end]
            if len(data) != size or data_end >= len(output):
                break
            offset = data_end + 1
            found = [
                SEARCH_MARKERS[index]
                for index, marker in enumerate(marker_bytes)
                if marker in data.lower()
            ]
            if found:
                hits.append(
                    {
                        "object": object_id,
                        "bytes": size,
                        "markers": found,
                        "reachable_paths": list(object_paths.get(object_id, ())),
                    }
                )
                if len(hits) >= max_hits:
                    return hits
    return hits


def _git_tree_entry_hits(
    repo: Path, object_paths: Mapping[str, Sequence[str]], max_hits: int = 200
) -> list[dict[str, object]]:
    """Search every tree object, including trees unreachable from refs.

    A blob can be binary and therefore contain none of the target text.  Tree
    entries are the authoritative place to check whether an unreachable Git
    snapshot ever named one of the original signoff files.
    """

    inventory = _run_git(repo, ["cat-file", "--batch-all-objects", "--batch-check"])
    if inventory.returncode != 0:
        return []
    tree_ids = [
        line.split()[0]
        for line in inventory.stdout.splitlines()
        if len(line.split()) == 3 and line.split()[1] == "tree"
    ]
    if not tree_ids:
        return []
    target_names = set(SIGNOFF_BASENAMES) | {"yparam-tran-signoff"}
    hits: list[dict[str, object]] = []
    for start in range(0, len(tree_ids), 256):
        batch_ids = tree_ids[start : start + 256]
        try:
            batch = subprocess.run(
                ["git", "-C", str(repo), "cat-file", "--batch"],
                input=("\n".join(batch_ids) + "\n").encode("ascii"),
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if batch.returncode != 0:
            continue
        output = batch.stdout
        offset = 0
        for tree_id in batch_ids:
            header_end = output.find(b"\n", offset)
            if header_end < 0:
                break
            parts = output[offset:header_end].decode("ascii", errors="replace").split()
            if len(parts) != 3 or parts[1] != "tree":
                break
            try:
                size = int(parts[2])
            except ValueError:
                break
            data_start = header_end + 1
            data_end = data_start + size
            data = output[data_start:data_end]
            if len(data) != size or data_end >= len(output):
                break
            offset = data_end + 1
            cursor = 0
            while cursor < len(data):
                mode_end = data.find(b" ", cursor)
                name_end = data.find(b"\0", mode_end + 1)
                if mode_end < 0 or name_end < 0 or name_end + 21 > len(data):
                    break
                name = data[mode_end + 1 : name_end].decode("utf-8", errors="replace")
                entry_id = data[name_end + 1 : name_end + 21].hex()
                cursor = name_end + 21
                if name.lower() in target_names:
                    hits.append(
                        {
                            "tree": tree_id,
                            "entry": name,
                            "entry_object": entry_id,
                            "reachable_paths": list(object_paths.get(tree_id, ())),
                        }
                    )
                    if len(hits) >= max_hits:
                        return hits
    return hits


def git_inventory(repo: Path) -> dict[str, object]:
    """Return path, ref/reflog, and all-object evidence for a repository."""

    repo = repo.resolve()
    head = _run_git(repo, ["rev-parse", "HEAD"])
    tree = _run_git(repo, ["rev-parse", "HEAD^{tree}"])
    rev_list_exit_code, paths, object_paths = _git_paths(repo)
    target_path_hits = [
        path
        for path in paths
        if any(marker.lower() in path.lower() for marker in SIGNOFF_BASENAMES)
        or "yparam-tran-signoff" in path.lower()
    ]
    return {
        "repo": _normalise_path(repo),
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "tree": tree.stdout.strip() if tree.returncode == 0 else None,
        "status": _git_status(repo),
        "rev_list_exit_code": rev_list_exit_code,
        "reachable_or_reflog_path_count": len(paths),
        "target_path_hits": target_path_hits,
        "all_object_stats": _git_object_stats(repo),
        "all_object_marker_hits": _git_blob_marker_hits(repo, object_paths),
        "all_tree_entry_hits": _git_tree_entry_hits(repo, object_paths),
    }


def discover_worktree_roots(repo: Path) -> list[Path]:
    result = _run_git(repo, ["worktree", "list", "--porcelain"])
    roots: list[Path] = []
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            path = Path(line.removeprefix("worktree ").strip())
            if path.exists():
                roots.append(path)
    return roots


def default_roots(workspace: Path, include_home_caches: bool = False) -> list[Path]:
    workspace = workspace.resolve()
    roots = [
        workspace,
        workspace.parent / "agent-spice",
        workspace.parent / "SIPI-m0-scratch",
    ]
    temp_root = Path(tempfile.gettempdir())
    # Avoid recursively traversing every installer/cache directory in Temp by
    # default. AS-related snapshots and replay roots use these prefixes.
    if temp_root.exists():
        roots.extend(
            child
            for child in temp_root.iterdir()
            if child.is_dir()
            and child.name.lower().startswith(
                ("as04", "as-04", "as-rfm", "agent-spice-2cc92316")
            )
        )
    if include_home_caches:
        roots.extend([Path.home() / ".codex", Path.home() / ".agents"])
    upstream = workspace.parent / "agent-spice"
    if upstream.exists():
        roots.extend(discover_worktree_roots(upstream))
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        key = _normalise_path(root).lower()
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def _known_document_records(workspace: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for relative in KNOWN_DOCUMENT_RELATIVE_PATHS:
        path = workspace / Path(relative)
        if not path.is_file():
            records.append({"path": _normalise_path(path), "present": False})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        records.append(
            {
                "path": _normalise_path(path),
                "present": True,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "classification": "documentation_example_or_replay_record",
                "can_satisfy_required_files": False,
                "explicitly_not_original_inputs": True,
                "markers": [marker for marker in SEARCH_MARKERS if marker in text],
                "explicitly_not_original_inputs": (
                    "not tracked" in text.lower()
                    or "synthetic" in text.lower()
                    or "no numerical parity" in text.lower()
                    or "external" in text.lower()
                ),
            }
        )
    return records


def _synthetic_corpus_record(workspace: Path) -> dict[str, object]:
    path = workspace / "docs/baselines/as-04-tune-yparam-tran-direct-port.v2.yaml"
    if not path.is_file():
        return {"manifest_present": False, "classification": "not_original_signoff"}
    text = path.read_text(encoding="utf-8", errors="replace")
    corpus = re.findall(r"^[- ]+([a-z0-9_]+)\s*$", text, flags=re.MULTILINE)
    return {
        "manifest_present": True,
        "manifest_path": _normalise_path(path),
        "manifest_sha256": sha256_file(path),
        "classification": "synthetic_non_signoff",
        "status": re.search(r"^status:\s*(\S+)", text, flags=re.MULTILINE).group(1)
        if re.search(r"^status:\s*(\S+)", text, flags=re.MULTILINE)
        else None,
        "corpus_ids": [item for item in corpus if item in {"valid_nelder_mead_external_stub", "invalid_csv", "duplicate_rfm_token", "missing_hspice_measure", "external_hspice_blocker"}],
        "external_runtime_blocked": "external_runtime_blocked: true" in text,
        "numeric_parity_claimed": "parity_claim: true" in text or "numeric_parity: true" in text,
        "original_input_paths_present": any(
            (workspace / Path(relative)).is_file() for relative in SIGNOFF_RELATIVE_PATHS
        ),
    }


def _hspice_record() -> dict[str, object]:
    record: dict[str, object] = {
        "path": _normalise_path(HSPICE_PATH),
        "present": HSPICE_PATH.is_file(),
        "role": "external_runtime_only",
        "sufficient_for_original_signoff": False,
    }
    if HSPICE_PATH.is_file():
        record["bytes"] = HSPICE_PATH.stat().st_size
        record["sha256"] = sha256_file(HSPICE_PATH)
    return record


def audit(
    workspace: Path,
    extra_roots: Iterable[Path] = (),
    include_home_caches: bool = False,
) -> dict[str, object]:
    workspace = workspace.resolve()
    roots = default_roots(workspace, include_home_caches=include_home_caches)
    for root in extra_roots:
        root = root.resolve()
        if root.exists() and root not in roots:
            roots.append(root)
    exact_matches = find_exact_files(roots)
    required: list[dict[str, object]] = []
    for relative in SIGNOFF_RELATIVE_PATHS:
        candidate = workspace / Path(relative)
        upstream = workspace.parent / "agent-spice" / Path(relative)
        required.append(
            {
                "relative_path": relative,
                "candidate_present": candidate.is_file(),
                "upstream_present": upstream.is_file(),
                "matching_named_files": [
                    record for record in exact_matches if str(record.get("relative_path", "")).lower().endswith(Path(relative).name.lower())
                ],
            }
        )
    repos = [workspace, workspace.parent / "agent-spice"]
    git_reports = [git_inventory(repo) for repo in repos if (repo / ".git").exists()]
    original_present = any(item["candidate_present"] or item["upstream_present"] for item in required)
    all_original_present = all(
        item["candidate_present"] or item["upstream_present"] for item in required
    )
    marker_roots = [
        root
        for root in roots
        if root.name.lower() not in {".codex", ".agents"}
    ]
    return {
        "schema": SCHEMA,
        "status": (
            "original_signoff_corpus_present"
            if all_original_present
            else "partial_original_signoff_corpus"
            if original_present
            else "missing_original_signoff_corpus"
        ),
        "scope": {
            "required_files_are_exact_names": True,
            "synthetic_inputs_are_not_accepted_as_recovery": True,
            "no_optimization_or_external_simulator_run": True,
        },
        "required_files": required,
        "documented_contract": {
            "measure_names": list(MEASURE_NAMES),
            "residual_poles_hz": list(RESIDUAL_POLES_HZ),
            "band_boundaries_hz": list(BAND_BOUNDARIES_HZ),
            "source": "engines/agent-spice/docs/yparam-heldout-tran-signoff-report.md",
            "inputs_and_results_recovered": False,
        },
        "search_roots": [_normalise_path(root) for root in roots],
        "home_cache_roots": {
            "codex": _normalise_path(Path.home() / ".codex"),
            "agents": _normalise_path(Path.home() / ".agents"),
            "included": include_home_caches,
            "note": "Use --include-home-caches for recursive exact-name and marker scanning.",
        },
        "exact_name_matches": exact_matches,
        # Cache roots are still checked for exact corpus names above.  Marker
        # content scanning is intentionally limited to source, snapshot, and
        # Temp roots because .codex/.agents contain large binary/session stores.
        "marker_scan_roots": [_normalise_path(root) for root in marker_roots],
        "marker_matches": find_marker_files(marker_roots),
        "git": git_reports,
        "source_documents": _known_document_records(workspace),
        "synthetic_corpus": _synthetic_corpus_record(workspace),
        "hspice_runtime": _hspice_record(),
        "reusable": {
            "measure_names": list(MEASURE_NAMES),
            "residual_poles_hz": list(RESIDUAL_POLES_HZ),
            "band_boundaries_hz": list(BAND_BOUNDARIES_HZ),
            "hspice_executable": _normalise_path(HSPICE_PATH) if HSPICE_PATH.is_file() else None,
            "original_s2p": False,
            "original_rfm": False,
            "original_sp": False,
            "original_rms_peak_results": False,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--extra-root", action="append", type=Path, default=[])
    parser.add_argument(
        "--include-home-caches",
        action="store_true",
        help="also scan ~/.codex and ~/.agents; omitted by default because they contain large session stores",
    )
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)
    result = audit(args.workspace, args.extra_root, include_home_caches=args.include_home_caches)
    payload = json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["status"] == "original_signoff_corpus_present" else 1


if __name__ == "__main__":
    sys.exit(main())
