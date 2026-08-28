"""Replay the implemented PB-01/PB-02 branches from an immutable candidate.

This additive runner deliberately leaves the historical preparation runner and
formal gate untouched.  It reuses their bounded process, archive, patch, and
comparison primitives while binding the production candidate to an explicit
commit.  The result is scoped evidence: the six portable PB-02 cases and the
PB-01 Duo-binary leaf are recorded individually, while the known CTLE fixture
and invalid jitter span remain blocked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

import run_pb_01_02_portable_matrix as matrix
import run_pb_02_direct_replay as custody


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UPSTREAM = Path(r"C:\Users\z3312\code\Py-bert-agent")
EXPECTED_CANDIDATE_COMMIT = "0d57b36f965588bed3393d2a0a529e4d573a493c"
EXPECTED_UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
EXPECTED_UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
CORPUS_RELATIVE = Path("docs/baselines/pb-01-02-portable-matrix-inputs.v1.json")
PB01_FIXTURE = Path("crates/sipi-pybert-direct/fixtures/pb-01-legacy-nrz.yaml")
PB02_FIXTURE = Path("crates/sipi-pybert-direct/fixtures/pb-02-nrz.json")
PB01_CASE_IDS = ("pb01_duo_binary_analytic_line",)
PB02_CASE_IDS = (
    "pb02_nrz_impulse",
    "pb02_pam4_impulse",
    "pb02_duo_binary_impulse",
    "pb02_impulse_tx_rx_equalization",
    "pb02_impulse_analytic_ctle",
    "pb02_impulse_jitter_bathtub_analysis",
)
EXPECTED_CASE_IDS = PB01_CASE_IDS + PB02_CASE_IDS
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
FUTURE_RUN_IDS = (
    "pb-01-02-candidate-run-01",
    "pb-01-02-candidate-run-02",
)
CHALLENGE_ID = "pb-01-02-candidate-matrix-v1"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _git(root: Path, *args: str, raw: bool = False) -> bytes | str:
    result = matrix.subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(root), *args],
        stdout=matrix.subprocess.PIPE,
        stderr=matrix.subprocess.PIPE,
        check=True,
    )
    return result.stdout if raw else result.stdout.decode("ascii").strip()


def _commit_tree(repo: Path, commit: str) -> tuple[str, str]:
    resolved = str(_git(repo, "rev-parse", f"{commit}^{{commit}}"))
    return resolved, str(_git(repo, "rev-parse", f"{resolved}^{{tree}}"))


def _safe_case_id(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value) is None:
        raise RuntimeError("case id is not a safe token")
    return value


def _challenge_for_run_id(run_id: str) -> dict[str, Any]:
    try:
        run_index = FUTURE_RUN_IDS.index(run_id) + 1
    except ValueError as error:
        raise RuntimeError("run_id is not one of the two fixed future replay IDs") from error
    return {
        "id": CHALLENGE_ID,
        "run_index": run_index,
        "run_count": len(FUTURE_RUN_IDS),
        "fresh_archive_replay": True,
        "nonce_required": True,
        "report_sha256_required": True,
    }


def _toolchain_post(candidates: dict[str, Path], identities: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = deepcopy(identities)
    for role, executable in candidates.items():
        payload, fact = matrix.secure_read(executable.parent, executable.name, matrix.MAX_FILE_BYTES * 16, require_nlink_one=False)
        identity = result[role]
        if _sha256(payload) != identity["file_sha256"] or fact != identity["file_custody_pre"]:
            raise matrix.CustodyError(f"{role} executable changed during replay")
        identity["file_custody_post"] = fact
        identity["file_custody_equal"] = True
    return result


def _resolve_tool(value: str, role: str, version_args: tuple[str, ...]) -> tuple[Path, dict[str, Any]]:
    """Resolve a runtime tool without imposing a hard-link policy on Rustup."""

    executable = custody._resolve_executable(value, role)
    payload, file_fact = matrix.secure_read(
        executable.parent, executable.name, matrix.MAX_FILE_BYTES * 16, require_nlink_one=False
    )
    actual_args = ("/dump", "/headers", str(executable)) if role == "link" else version_args
    process = matrix.subprocess.run(
        [str(executable), *actual_args],
        stdout=matrix.subprocess.PIPE,
        stderr=matrix.subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(f"{role} version command failed")
    if len(process.stdout) > matrix.MAX_PROCESS_CAPTURE_BYTES or len(process.stderr) > matrix.MAX_PROCESS_CAPTURE_BYTES:
        raise RuntimeError(f"{role} version output exceeds budget")
    return executable, {
        "role": role,
        "executable": executable.name,
        "file_sha256": _sha256(payload),
        "version_sha256": _sha256(process.stdout + b"\0" + process.stderr),
        "version_exit": process.returncode,
        "path_redacted": True,
        "file_custody_pre": file_fact,
    }


def _source_identity(root: Path, info: dict[str, Any], prefixes: tuple[str, ...]) -> dict[str, Any]:
    inventory = matrix._inventory(root)
    scoped = custody._inventory(root, prefixes)
    return {
        "commit": info["commit"],
        "tree": info["tree"],
        "archive_sha256": info["archive_sha256"],
        "inventory_sha256": inventory["sha256"],
        "scoped_inventory_sha256": scoped["sha256"],
    }


def _fixture_binding(path: Path, payload: bytes) -> dict[str, Any]:
    return {"path": path.as_posix(), "bytes": len(payload), "sha256": _sha256(payload), "archive_present": True}


def _case_patch(corpus: dict[str, Any], case_id: str) -> tuple[str, dict[str, Any]]:
    for lane, key in (("PB-01", "pb01_cases"), ("PB-02", "pb02_cases")):
        for case in corpus[key]:
            if case["id"] == case_id:
                return lane, deepcopy(case["patch"])
    raise RuntimeError(f"matrix case is not present in the archived corpus: {case_id}")


def _derive_input(base: bytes, patch: dict[str, Any], lane: str) -> bytes:
    return matrix._patch_pb01(base, patch) if lane == "PB-01" else matrix._patch_pb02(base, patch)


def _provenance_blockers(case_id: str, payload: bytes) -> list[str]:
    if case_id == "pb02_impulse_analytic_ctle":
        value = matrix._json_loads(payload)
        extension = value.get("rx", {}).get("ctle", {}).get("impulseResponseVPerV")
        if extension == [1.0, 0.25, -0.05]:
            return ["local_ctle_impulse_extension_not_in_pinned_native_schema"]
    if case_id == "pb02_impulse_jitter_bathtub_analysis":
        value = matrix._json_loads(payload)
        timebase = value.get("timebase", {})
        pattern = value.get("pattern", {})
        analysis = value.get("analysis", {})
        if (
            timebase.get("nbits") == 16
            and pattern.get("kind") == "prbs"
            and pattern.get("order") == 7
            and analysis.get("jitterEyeUis") == 8
        ):
            return ["jitter_span_invalid_for_16_bit_prbs7_fixture"]
    return []


def _case_record(
    result: dict[str, Any],
    inputs: list[dict[str, Any]],
    *,
    lane: str,
    base_binding: dict[str, Any],
    patch: dict[str, Any],
    derived: bytes,
) -> dict[str, Any]:
    case_id = _safe_case_id(result["id"])
    expected_suffix = "yaml" if lane == "PB-01" else "json"
    provenance = _provenance_blockers(case_id, derived)
    if case_id == "pb02_impulse_tx_rx_equalization" and any(
        item in result["blockers"] for item in ("candidate_artifact_invalid", "oracle_artifact_invalid")
    ):
        provenance.append("strict_native_npz_member_set_drift")
    blockers = sorted(set(result["blockers"]) | set(provenance))
    return {
        "id": case_id,
        "lane": lane,
        "status": "passed" if result["status"] == "passed" and not provenance else "blocked",
        "blockers": blockers,
        "input": {
            "path": f"{case_id}/input.{expected_suffix}",
            "base_fixture": base_binding,
            "patch": patch,
            "patch_sha256": _sha256(_canonical(patch)),
            "derived_bytes": len(derived),
            "derived_sha256": _sha256(derived),
            "archive_derived_input": True,
            "custody": inputs[0],
        },
        "comparison": result["comparison"],
        "artifacts": [],
    }


def _strip_process_facts(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_process_facts(item)
            for key, item in value.items()
            if key not in {"candidate_process", "oracle_process"}
        }
    if isinstance(value, list):
        return [_strip_process_facts(item) for item in value]
    return value


def _run(args: argparse.Namespace) -> dict[str, Any]:
    challenge = _challenge_for_run_id(args.run_id)
    candidate_repo = args.candidate_repo.resolve(strict=True)
    upstream_repo = args.upstream_repo.resolve(strict=True)
    candidate_commit, candidate_tree = _commit_tree(candidate_repo, args.candidate_commit)
    upstream_commit, upstream_tree = _commit_tree(upstream_repo, args.upstream_commit)
    if (upstream_commit, upstream_tree) != (EXPECTED_UPSTREAM_COMMIT, EXPECTED_UPSTREAM_TREE):
        raise RuntimeError("upstream source is not the pinned PyBERT archive")
    if candidate_commit != EXPECTED_CANDIDATE_COMMIT:
        raise RuntimeError("candidate ref did not resolve to the requested immutable commit")
    work_parent = Path(os.path.abspath(os.fspath(args.work_root))) if args.work_root else Path(tempfile.mkdtemp(prefix="sipi-pb-current-matrix-"))
    custody_facts = custody._validate_external_fresh_work_root(work_parent, candidate_repo, upstream_repo)
    run_root = work_parent / args.run_id
    if run_root.exists():
        raise RuntimeError(f"run root already exists: {run_root}")
    run_root.mkdir()
    custody_facts.update({"run_root_created_new": True, "run_root_path_redacted": True})

    candidate_root, candidate_source = matrix.materialize_archive(candidate_repo, candidate_commit, run_root, "candidate", args.timeout_seconds)
    upstream_root, upstream_source = matrix.materialize_archive(upstream_repo, upstream_commit, run_root, "upstream", args.timeout_seconds)
    oracle_root, oracle_source = matrix.materialize_archive(upstream_repo, upstream_commit, run_root, "oracle", args.timeout_seconds)
    custody_facts["materialized_archives_created_new"] = True
    candidate_pre = matrix._inventory(candidate_root)
    upstream_pre = matrix._inventory(upstream_root)
    oracle_pre = custody._inventory(oracle_root, custody.UPSTREAM_FACT_PATHS)

    corpus_path, corpus_payload = custody._read_archived_fixture(candidate_root, CORPUS_RELATIVE)
    corpus = matrix.load_corpus(corpus_payload)
    base01_path, base01_payload = custody._read_archived_fixture(candidate_root, Path(corpus["base_fixtures"]["PB-01"]))
    base02_path, base02_payload = custody._read_archived_fixture(candidate_root, Path(corpus["base_fixtures"]["PB-02"]))
    base_bindings = {
        "PB-01": _fixture_binding(Path(corpus["base_fixtures"]["PB-01"]), base01_payload),
        "PB-02": _fixture_binding(Path(corpus["base_fixtures"]["PB-02"]), base02_payload),
    }
    if base01_path.relative_to(candidate_root).as_posix() != base_bindings["PB-01"]["path"] or base02_path.relative_to(candidate_root).as_posix() != base_bindings["PB-02"]["path"]:
        raise RuntimeError("archived fixture path binding drift")

    tool_root = matrix._fresh_child(run_root, "tool-capture")
    cargo, cargo_identity = _resolve_tool(args.cargo, "cargo", ("--version",))
    rustc, rustc_identity = _resolve_tool(args.rustc, "rustc", ("-Vv",))
    uv, uv_identity = _resolve_tool(args.uv, "uv", ("--version",))
    linker, linker_identity = _resolve_tool(args.linker, "link", ("/?",))
    tool_identities = {"cargo": cargo_identity, "rustc": rustc_identity, "uv": uv_identity, "link": linker_identity}
    upstream_venv = run_root / "upstream-venv"
    oracle_runtime = matrix._probe_oracle_runtime(oracle_root, upstream_venv, run_root, uv, cargo, rustc, linker, args.timeout_seconds)
    oracle_runtime["oracle_work_archive_sha256"] = oracle_source["archive_sha256"]
    oracle_runtime["oracle_work_started_clean"] = True
    binary, build = matrix._build_candidate(candidate_root, run_root, cargo, rustc, linker, args.timeout_seconds)

    cases: list[dict[str, Any]] = []
    all_inputs: list[dict[str, Any]] = []
    all_artifacts: list[dict[str, Any]] = []
    for case_id in EXPECTED_CASE_IDS:
        lane, patch = _case_patch(corpus, case_id)
        base = base01_payload if lane == "PB-01" else base02_payload
        result, inputs, artifacts = matrix._run_matrix_case(
            case=next(item for item in corpus["pb01_cases" if lane == "PB-01" else "pb02_cases"] if item["id"] == case_id),
            lane=lane,
            base=base,
            run_root=run_root,
            candidate_root=candidate_root,
            upstream_root=oracle_root,
            binary=binary,
            cargo=cargo,
            rustc=rustc,
            uv=uv,
            linker=linker,
            timeout=args.timeout_seconds,
        )
        derived = _derive_input(base, patch, lane)
        case = _case_record(result, inputs, lane=lane, base_binding=base_bindings[lane], patch=patch, derived=derived)
        case["artifacts"] = [dict(item) for item in artifacts]
        cases.append(case)
        all_inputs.extend(inputs)
        all_artifacts.extend(artifacts)

    candidate_post = matrix._inventory(candidate_root)
    upstream_post = matrix._inventory(upstream_root)
    oracle_post = custody._inventory(oracle_root, custody.UPSTREAM_FACT_PATHS)
    if candidate_pre != candidate_post or upstream_pre != upstream_post or oracle_pre != oracle_post:
        raise matrix.CustodyError("materialized archive inventory changed during replay")
    tool_identities = _toolchain_post({"cargo": cargo, "rustc": rustc, "uv": uv, "link": linker}, tool_identities)
    custody_facts["archive_materialization"] = [
        {"role": "candidate", "archive_sha256": candidate_source["archive_sha256"], "fact": candidate_source["archive"]},
        {"role": "upstream_pristine", "archive_sha256": upstream_source["archive_sha256"], "fact": upstream_source["archive"]},
        {"role": "upstream_oracle", "archive_sha256": oracle_source["archive_sha256"], "fact": oracle_source["archive"]},
    ]
    custody_facts["inputs"] = all_inputs
    custody_facts["artifacts"] = all_artifacts
    custody_facts["output"] = {"fresh_root": True, "exclusive_report": True}

    candidate_identity = _source_identity(candidate_root, candidate_source, ("crates/sipi-pybert-direct",))
    upstream_identity = _source_identity(upstream_root, upstream_source, ("native/pybert-core", "native/pybert-python", "src/pybert"))
    report = {
        "schema": "sipi.pb-01-02-candidate-matrix-replay.v1",
        "version": 1,
        "status": "passed_scoped" if all(item["status"] == "passed" for item in cases) else "scoped_matrix_blocked",
        "run_id": args.run_id,
        "challenge": challenge,
        "fresh_run_nonce": secrets.token_hex(32),
        "source_mode": "git_archive_at_immutable_commit",
        "candidate": candidate_identity,
        "upstream": upstream_identity,
        "corpus": _fixture_binding(CORPUS_RELATIVE, corpus_payload),
        "fixtures": base_bindings,
        "toolchain": {"timeout_seconds": args.timeout_seconds, **tool_identities},
        "build": build,
        "oracle_runtime": oracle_runtime,
        "custody": custody_facts,
        "codec_boundary": {
            "candidate": "python_pickle_dict_sipi.pybert_data.v1",
            "oracle": "PyBertData_class_pickle",
            "comparison": "selected_numeric_arrays_only",
            "class_codec_byte_parity": False,
        },
        "cases": cases,
        "claims": {
            "pb01_duo_selected_array_parity": cases[0]["status"] == "passed",
            "pb02_nrz_pam4_duo_eq_logical_npz_parity": all(item["status"] == "passed" for item in cases[1:5]),
            "global_branch_parity": False,
            "whole_payload_parity": False,
            "release_acceptance": False,
            "product_capability_admission": False,
        },
        "non_claims": [
            "This is an additive candidate replay from the immutable production commit, not the historical preparation gate.",
            "PB-01 compares selected numeric arrays across the dictionary and PyBertData class codec boundary; byte/class compatibility is not claimed.",
            "PB-02 strict comparison includes normalized metadata and logical NPZ member payloads; wrapper metadata is not silently discarded.",
            "The CTLE case is blocked because the local impulseResponseVPerV extension is not in the pinned native fixture schema; the jitter case is blocked because the 16-bit PRBS-7 span cannot satisfy jitterEyeUis=8.",
            "These reports are not a license decision, product capability admission, release approval, or global branch parity claim.",
        ],
        "harness": {
            "source_mode": "working_tree_content_hash_at_replay",
            "runner": {"path": "tools/run_pb_01_02_candidate_matrix.py", "sha256": _sha256(Path(__file__).read_bytes())},
            "legacy_matrix_primitives": {"path": "tools/run_pb_01_02_portable_matrix.py", "sha256": _sha256((ROOT / "tools/run_pb_01_02_portable_matrix.py").read_bytes())},
            "native_custody_primitives": {"path": "tools/run_pb_02_direct_replay.py", "sha256": _sha256((ROOT / "tools/run_pb_02_direct_replay.py").read_bytes())},
            "immutable_harness_commit": None,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    if args.work_root is None and not args.keep_work:
        import shutil

        shutil.rmtree(work_parent, ignore_errors=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--candidate-commit", default=EXPECTED_CANDIDATE_COMMIT)
    parser.add_argument("--upstream-repo", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--upstream-commit", default=EXPECTED_UPSTREAM_COMMIT)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--cargo", default=os.environ.get("CARGO", r"C:\Users\z3312\.cargo\bin\cargo.exe"))
    parser.add_argument("--rustc", default=os.environ.get("RUSTC", r"C:\Users\z3312\.cargo\bin\rustc.exe"))
    parser.add_argument("--uv", default=os.environ.get("UV", "uv"))
    parser.add_argument("--linker", default=os.environ.get("LINK", r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\link.exe"))
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--keep-work", action="store_true")
    args = parser.parse_args()
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", args.run_id) is None:
        parser.error("--run-id must be a single safe token")
    try:
        report = _run(args)
    except (OSError, RuntimeError, matrix.CustodyError, matrix.subprocess.SubprocessError, ValueError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "report": str(args.report)}, sort_keys=True))
    return 0 if report["status"] == "passed_scoped" else 1


if __name__ == "__main__":
    raise SystemExit(main())
