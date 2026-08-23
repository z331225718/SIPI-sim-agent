"""Archive-only PB-04/PB-05 replay against the pinned Python backend.

PB-04 deliberately invokes the candidate ``sim-auto`` without silently
substituting a Rust result.  PB-05 supplies the result-adapter JSON produced by
the independent pinned Python process to ``sim-compare``.  A missing, failed,
or over-budget reference remains a blocked/not-evaluated outcome; this runner
never creates a same-crate reference.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

from pb_03_replay_common import (
    DEFAULT_UPSTREAM,
    ROOT,
    UPSTREAM_COMMIT,
    UPSTREAM_TREE,
    _binary,
    archive_repo,
    artifact_summary,
    build_summary,
    resolve_toolchain,
    run_command,
    sha256,
)


FIXTURE = "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml"
EXTERNAL_HELPER = ROOT / "tools/pb_python_external_reference.py"


def digest_file(path: Path) -> str:
    return sha256(path.read_bytes())


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def materialize_harness_snapshot(payload: bytes, root: Path, name: str) -> Path:
    snapshot = root / "harness" / name
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(payload)
    if sha256(snapshot.read_bytes()) != sha256(payload):
        raise RuntimeError("external helper snapshot digest changed during materialization")
    return snapshot


def run_replay(
    *,
    row: str,
    candidate_repo: Path,
    upstream_repo: Path,
    output: Path,
    run_id: str,
    candidate_commit: str,
    candidate_tree: str,
    candidate_archive_sha256: str,
    timeout: int,
) -> dict[str, Any]:
    if row not in {"PB-04", "PB-05"}:
        raise ValueError("row must be PB-04 or PB-05")
    helper_payload = EXTERNAL_HELPER.read_bytes()
    helper_sha256 = sha256(helper_payload)
    toolchain_report, tool_paths = resolve_toolchain(timeout)

    with tempfile.TemporaryDirectory(prefix=f"sipi-{row.lower()}-python-external-") as temporary:
        work = Path(temporary)
        candidate_root = work / "candidate"
        upstream_root = work / "upstream"
        candidate_identity = archive_repo(candidate_repo, candidate_commit, candidate_root)
        if candidate_identity.get("tree") != candidate_tree or candidate_identity.get("archive_sha256") != candidate_archive_sha256:
            raise RuntimeError("candidate archive identity does not match the requested prep commit")
        upstream_identity = archive_repo(upstream_repo, UPSTREAM_COMMIT, upstream_root)
        helper_snapshot = materialize_harness_snapshot(helper_payload, work, EXTERNAL_HELPER.name)
        candidate_fixture = candidate_root / FIXTURE
        upstream_fixture = upstream_root / FIXTURE
        if not candidate_fixture.is_file():
            raise RuntimeError("candidate archive fixture is absent")
        # The fixture is evidence input, so it must come from the same immutable
        # candidate archive as the binary.  Never read a working-tree copy before
        # materializing the archive and never let one replace the archived bytes.
        fixture_bytes = candidate_fixture.read_bytes()
        upstream_fixture.parent.mkdir(parents=True, exist_ok=True)
        upstream_fixture.write_bytes(fixture_bytes)
        config = candidate_fixture
        oracle_config = upstream_fixture

        build_result = run_command(
            [
                "cargo",
                "build",
                "--manifest-path",
                str(candidate_root / "crates/sipi-pybert-direct/Cargo.toml"),
                "--release",
                "--locked",
            ],
            candidate_root,
            timeout,
            tool_paths,
        )
        binary = _binary(candidate_root / "crates" / "sipi-pybert-direct" / "target")
        build = build_summary(build_result, binary)

        external_reference = work / "external-reference.json"
        oracle_process = run_command(
            [
                "uv",
                "run",
                "--project",
                str(upstream_root),
                "--frozen",
                "python",
                str(helper_snapshot),
                str(oracle_config),
                "--output",
                str(external_reference),
            ],
            oracle_config.parent,
            timeout,
            tool_paths,
        )
        reference_summary: dict[str, Any] = {
            "present": external_reference.is_file(),
            "schema": None,
            "sha256": sha256(external_reference.read_bytes()) if external_reference.is_file() else None,
            "bytes": external_reference.stat().st_size if external_reference.is_file() else None,
            "array_count": None,
            "two_dimensional_arrays": [],
            "result_adapter_schema": None,
        }
        if external_reference.is_file():
            try:
                reference = json.loads(external_reference.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                reference = None
            if isinstance(reference, dict):
                adapter = reference.get("result_adapter")
                reference_summary.update(
                    {
                        "schema": reference.get("schema"),
                        "array_count": adapter.get("array_count") if isinstance(adapter, dict) else None,
                        "two_dimensional_arrays": adapter.get("two_dimensional_arrays", []) if isinstance(adapter, dict) else [],
                        "result_adapter_schema": adapter.get("schema") if isinstance(adapter, dict) else None,
                        "metrics_keys": sorted(reference.get("metrics", {}).keys()) if isinstance(reference.get("metrics"), dict) else [],
                    }
                )

        candidate_output = work / "candidate-output"
        if binary.is_file():
            command = "sim-auto" if row == "PB-04" else "sim-compare"
            candidate_command = [str(binary), command, str(config), "--output-dir", str(candidate_output)]
            if row == "PB-05":
                candidate_command.extend(["--reference-json", str(external_reference)])
            candidate_process = run_command(candidate_command, candidate_root, timeout, tool_paths)
        else:
            candidate_process = {"exit_code": None, "skipped": True}

        candidate_artifact = artifact_summary(candidate_output)
        selection = None
        comparison = None
        stderr_json = candidate_process.get("stderr_json") if isinstance(candidate_process, dict) else None
        if isinstance(stderr_json, dict):
            diagnostics = stderr_json.get("diagnostics")
            if isinstance(diagnostics, dict):
                selection = diagnostics.get("engine_selection")
                comparison = diagnostics.get("comparison")
        if isinstance(candidate_artifact, dict):
            meta_path = candidate_output / "meta.json"
            if meta_path.is_file():
                try:
                    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    metadata = None
                if isinstance(metadata, dict):
                    diagnostics = metadata.get("diagnostics")
                    if isinstance(diagnostics, dict):
                        selection = selection or diagnostics.get("engine_selection")
                        comparison = comparison or diagnostics.get("comparison")

        blockers: list[str] = []
        if oracle_process.get("exit_code") != 0:
            blockers.append("independent pinned Python BackendRunResult oracle failed")
        if not reference_summary["present"]:
            blockers.append("external Python reference artifact is absent")
        elif reference_summary.get("schema") != "pybert.backend-run-result.v1":
            blockers.append("external Python reference schema mismatch")
        if row == "PB-04":
            if not isinstance(selection, dict):
                blockers.append("sim-auto selection diagnostics are absent")
            else:
                if selection.get("selected") != "python":
                    blockers.append("sim-auto did not preserve pinned Python selection")
                if selection.get("implementation") != "external_python_reference_required":
                    blockers.append("sim-auto fallback was not fail-closed")
                if selection.get("rust_only") is not False:
                    blockers.append("sim-auto claimed Rust-only fallback")
            if candidate_process.get("exit_code") == 0:
                blockers.append("sim-auto unexpectedly promoted a Rust result")
            else:
                blockers.append("sim-auto parity gate remains blocked pending Python Web result ownership")
        else:
            if candidate_process.get("exit_code") not in {0, 1}:
                blockers.append("sim-compare process did not produce a bounded result")
            if isinstance(comparison, dict):
                if comparison.get("status_only_comparison") is not False:
                    blockers.append("sim-compare comparison is not payload-based")
                if comparison.get("passed") is True:
                    # A passing result is still not promotion by this evidence
                    # row; it must be reviewed against the complete external
                    # result-adapter payload first.
                    blockers.append("external payload unexpectedly passed without promotion review")
            elif candidate_process.get("exit_code") != 0:
                blockers.append("sim-compare did not emit comparison diagnostics")
            if reference_summary.get("bytes", 0) and reference_summary["bytes"] > 16 * 1024 * 1024:
                blockers.append("full result-adapter reference exceeds the current 16 MiB JSON admission budget")

        result = {
            "schema": "sipi.pb-04-05-python-external-replay.v1",
            "version": 1,
            "row": row,
            "status": "passed" if not blockers else "blocked",
            "source_mode": "git_archive_at_candidate_prep_commit_plus_candidate_archive_fixture_copy_and_harness_snapshot",
            "run_id": run_id,
            "fresh_run_nonce": uuid.uuid4().hex,
            "candidate": candidate_identity,
            "upstream": upstream_identity,
            "fixture": {
                "path": FIXTURE,
                "archive_present": True,
                "sha256": sha256(candidate_fixture.read_bytes()),
                "source": "candidate_archive",
                "archive_source_sha256": sha256(candidate_fixture.read_bytes()),
                "oracle_copy": "content_addressed_copy_from_candidate_archive",
            },
            "harness": {
                "runner": {"path": relative(Path(__file__)), "sha256": digest_file(Path(__file__))},
                "python_external_reference": {"path": relative(EXTERNAL_HELPER), "sha256": helper_sha256, "snapshot": "candidate_prep_archive_harness_snapshot"},
            },
            "build": build,
            "toolchain": toolchain_report,
            "oracle": {
                "process": oracle_process,
                "backend": "python",
                "source_command": "PythonSimulationBackend",
                "independent": True,
                "reference": reference_summary,
            },
            "candidate_process": candidate_process,
            "candidate_artifact": candidate_artifact,
            "selection": selection,
            "comparison": comparison,
            "claims": {
                "independent_python_reference": True,
                "same_crate_self_compare": False,
                "payload_compare": row == "PB-05"
                and isinstance(comparison, dict)
                and comparison.get("reason") != "not_evaluated",
                "global_row_closed": False,
                "promotion": False,
                "release_approval": False,
            },
            "blockers": blockers,
            "non_claims": [
                "The external JSON is produced by the pinned Python BackendRunResult adapter, not a Rust shadow.",
                "AMI/IBIS/DLL/service branches and exact PyBertData class pickle restoration remain outside this portable result.",
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--row", choices=("PB-04", "PB-05"), required=True)
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--upstream-repo", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--candidate-archive-sha256", required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    result = run_replay(
        row=args.row,
        candidate_repo=args.candidate_repo.resolve(),
        upstream_repo=args.upstream_repo.resolve(),
        output=args.output.resolve(),
        run_id=args.run_id,
        candidate_commit=args.candidate_commit,
        candidate_tree=args.candidate_tree,
        candidate_archive_sha256=args.candidate_archive_sha256,
        timeout=args.timeout,
    )
    print(json.dumps({"row": args.row, "run_id": args.run_id, "status": result["status"]}, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
