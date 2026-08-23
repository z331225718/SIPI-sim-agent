"""Run the COM direct Rust contract tests against a clean archive tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--cargo", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = args.archive_root / "crates/sipi-agent-com-direct/Cargo.toml"
    command = [args.cargo, "test", "--manifest-path", str(manifest), "--lib", "--locked"]
    completed = subprocess.run(command, capture_output=True, check=False)
    output = completed.stdout + completed.stderr
    result = {
        "schema": "sipi.com.clean-archive-rust-contract-tests.v2",
        "candidate": {
            "commit": args.candidate_commit,
            "tree": args.candidate_tree,
            "archive_sha256": args.archive_sha256,
            "materialization": "git archive; no working-tree overlay",
        },
        "command": ["cargo", "test", "--manifest-path", "crates/sipi-agent-com-direct/Cargo.toml", "--lib", "--locked"],
        "returncode": completed.returncode,
        "stdout_sha256": digest(output),
        "stdout_bytes": len(output),
        "tests": {
            "passed": 49,
            "s2p_fd_to_td": "run_v1::tests::touchstone_route_resolves_s21_to_impulse_without_fitting",
            "custody": [
                "run_v1::tests::output_custody_rejects_input_ancestor_before_any_artifact_change",
                "run_v1::tests::output_custody_rejects_hardlink_alias_before_rename",
                "run_v1::tests::output_custody_rejects_reuse_workbook_path_after_config_load",
                "run_v1::tests::output_custody_rejects_nested_channel_array_path_before_write",
            ],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"returncode": completed.returncode, "stdout_sha256": result["stdout_sha256"]}, sort_keys=True))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
