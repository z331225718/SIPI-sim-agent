"""Run the pinned PyBERT Rust simulation contract probe without invoking simulation."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "schemas" / "authority.v1.yaml"
RUSTUP = Path.home() / ".cargo" / "bin" / "rustup.exe"
TOOLCHAIN = "1.97.0-x86_64-pc-windows-msvc"
PROBE = ROOT / "tests" / "contract" / "external-probes" / "pybert-simulation" / "Cargo.toml"


def _output(command: list[str]) -> str:
    return subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True, check=True).stdout.strip()


def _repository(authority: dict) -> tuple[dict, dict]:
    source = next(
        contract["source_of_truth"]
        for contract in authority["external_contracts"]
        if contract["identifier"] == {"kind": "wire_schema_id", "value": "pybert.simulation.v1"}
    )
    snapshot = json.loads((ROOT / authority["source_snapshot_ref"]).read_text(encoding="utf-8"))
    repository = next(item for item in snapshot["repositories"] if item["id"] == source["repository"])
    return source, repository


def _assert_pinned_source(source: dict, repository: dict) -> None:
    root = Path(repository["path"])
    subtree = source["path"].split("/", 1)[0]
    if _output(["git", "-C", str(root), "rev-parse", "HEAD"]) != repository["head"]:
        raise RuntimeError("pybert_head_mismatch")
    if _output(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"]) != repository["tree"]:
        raise RuntimeError("pybert_tree_mismatch")
    if _output(["git", "-C", str(root), "status", "--porcelain", "--", subtree]):
        raise RuntimeError("pybert_subtree_dirty")
    if subprocess.run(["git", "-C", str(root), "diff", "--quiet", repository["head"], "--", subtree]).returncode:
        raise RuntimeError("pybert_subtree_differs_from_snapshot")
    if _output(["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "--", subtree]):
        raise RuntimeError("pybert_subtree_has_untracked_files")
    lock_path = root / "native" / "pybert-core" / "Cargo.lock"
    expected_lock = next(item["sha256"] for item in repository["lockfiles"] if item["path"] == "native/pybert-core/Cargo.lock")
    if hashlib.sha256(lock_path.read_bytes()).hexdigest().lower() != expected_lock.lower():
        raise RuntimeError("pybert_lock_hash_mismatch")


def _assert_probe_dependency(core_manifest: Path) -> None:
    metadata = json.loads(_output([str(RUSTUP), "run", TOOLCHAIN, "cargo", "metadata", "--locked", "--format-version", "1", "--manifest-path", str(PROBE)]))
    manifests = [Path(package["manifest_path"]).resolve() for package in metadata["packages"] if package["name"] == "pybert-core"]
    if manifests != [core_manifest.resolve()]:
        raise RuntimeError("pybert_probe_dependency_mismatch")


def main() -> int:
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    source, repository = _repository(authority)
    _assert_pinned_source(source, repository)
    core_manifest = Path(repository["path"]) / "native" / "pybert-core" / "Cargo.toml"
    _assert_probe_dependency(core_manifest)
    canary = _output([str(RUSTUP), "run", TOOLCHAIN, "cargo", "test", "--locked", "--manifest-path", str(core_manifest), "--test", "contract_v1", "simulation_input_round_trips_as_versioned_json", "--", "--exact"])
    if "simulation_input_round_trips_as_versioned_json ... ok" not in canary or "1 passed" not in canary:
        raise RuntimeError("pybert_canary_not_executed")
    output = _output([str(RUSTUP), "run", TOOLCHAIN, "cargo", "run", "--locked", "--quiet", "--manifest-path", str(PROBE)])
    result = json.loads(output.splitlines()[-1])
    result["observed_source_snapshot"] = {"repository": repository["id"], "revision": repository["head"], "tree": repository["tree"]}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
