"""Mutation tests for the COM-01 fingerprint current replay gate."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock

if str(Path(__file__).resolve().parents[1] / "tools") not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from run_com_01_fingerprint_current_replay import (  # noqa: E402
    CANDIDATE_COMMIT,
    CANDIDATE_TREE,
    CANDIDATE_ARCHIVE_BYTES,
    CANDIDATE_ARCHIVE_SHA256,
    CANDIDATE_INVENTORY,
    CANDIDATE_CARGO_LOCK_SHA256,
    CANDIDATE_SOURCE_DATE_EPOCH,
    CONSUMPTION_KEYS,
    CONSUMPTION_OPTIONAL_KEYS,
    PREP_PARENT_COMMIT,
    CRATE_RELATIVE,
    CUSTODY_COMMIT,
    CUSTODY_FILES,
    CUSTODY_TREE,
    EXPECTED_FINGERPRINT,
    EXPECTED_OPTION_COUNT,
    EXPECTED_PARAMETER_COUNT,
    EXPECTED_WARNING_COUNT,
    FIXTURE_BYTES,
    FIXTURE_RELATIVE,
    FIXTURE_SHA256,
    UPSTREAM_ARCHIVE_BYTES,
    UPSTREAM_ARCHIVE_SHA256,
    UPSTREAM_INVENTORY,
    UPSTREAM_SOURCE_INVENTORY,
    UPSTREAM_INIT_BYTES,
    UPSTREAM_INIT_SHA256,
    HARNESS_FILES,
    NON_CLAIMS,
    RAW_BINARY_POLICY,
    _atomic_json_create,
    _harness_receipt,
    _load_custody,
    _payload,
)
import run_com_01_fingerprint_current_replay as runner_module  # noqa: E402
from verify_com_01_fingerprint_current_replay import (  # noqa: E402
    AGGREGATE_SCHEMA,
    AGGREGATE_STATUS,
    EXPECTED_ARTIFACT_POLICY,
    EXPECTED_PAYLOAD_RECEIPTS,
    VerificationError,
    _verify_prep_commit,
    read_json,
    validate_aggregate,
    validate_report,
    verify_bundle,
)


SHA = "a" * 64
BLOB = "b" * 40


def receipt(basename: str = "artifact.bin", nlink: int = 1) -> dict[str, object]:
    return {"basename": basename, "bytes": 1, "sha256": SHA, "nlink": nlink, "path_redacted": True}


def raw_receipt(path: str, blob: str = BLOB) -> dict[str, object]:
    return {"path": path, "git_blob_sha1": blob, "bytes": 1, "content_sha256": SHA}


def source_receipt() -> dict[str, object]:
    return {
        "module_file": {"relative_path": "src/agent_com/__init__.py", "basename": "__init__.py", "bytes": UPSTREAM_INIT_BYTES, "sha256": UPSTREAM_INIT_SHA256, "root_contained": True, "path_redacted": True},
        "package_source_inventory": dict(UPSTREAM_SOURCE_INVENTORY),
    }


def identity(role: str) -> dict[str, object]:
    return {"role": role, "basename": f"{role}.exe", "file_bytes": 1, "file_sha256": SHA, "version_args": ["--version"], "version_exit": 0, "version_stdout_sha256": SHA, "version_stderr_sha256": SHA, "path_redacted": True}


def dependency_cache() -> dict[str, object]:
    return {"scope": "resolved_locked_dependency_sources", "path_redacted": True, "package_count": 1, "file_count": 1, "total_bytes": 1, "sha256": SHA}


def payload_receipt(role: str = "candidate") -> dict[str, object]:
    return copy.deepcopy(EXPECTED_PAYLOAD_RECEIPTS[role])


def scenario() -> dict[str, object]:
    return {
        "id": "xlsx_materialized_json_default",
        "fixture_role": "primary_xlsx",
        "profile": "r480",
        "output": "materialized_json",
        "oracle": {"exit_code": 0, "payload": payload_receipt("oracle"), "runtime": "uv_frozen_offline"},
        "candidate": {"exit_code": 0, "payload": payload_receipt("candidate"), "runtime": "archive_binary_execution_copy"},
        "exact": {"materialized_fingerprint": True, "parameters": True, "options": True, "consumption": True, "warnings": True, "all": True},
        "comparison_mode": "parsed_json_semantic_numbers_with_exact_fingerprint",
    }


def harness() -> dict[str, object]:
    return {
        "prep_commit": "c" * 40,
        "prep_parent": PREP_PARENT_COMMIT,
        "prep_tree": "d" * 40,
        "changed_paths": list(HARNESS_FILES),
        "first_introduction": True,
        "formal_artifacts_absent": True,
        "files": [raw_receipt(path) for path in HARNESS_FILES],
        "shared_custody": {"commit": CUSTODY_COMMIT, "tree": CUSTODY_TREE, "files": [raw_receipt(path, blob) for path, blob in CUSTODY_FILES.items()]},
        "source_mode": "raw_git_blob_bound_before_execution",
    }


def candidate() -> dict[str, object]:
    build = {
        "command": "cargo build --manifest-path <candidate>/crates/sipi-agent-com-direct/Cargo.toml --release --locked --offline",
        "cargo_source_pre": receipt("sipi-com-direct-config-validate.exe", 2),
        "binary_pre": receipt("sipi-com-direct-config-validate.exe"),
        "binary_post": receipt("sipi-com-direct-config-validate.exe"),
        "stdout_sha256": SHA,
        "stderr_sha256": SHA,
        "log_policy": "stable_event_categories",
        "environment": {
            "cleared": ["RUSTFLAGS"], "incremental": "0", "offline": True, "rustc_forced": True, "wrappers_cleared": True,
            "source_path_remapped": True, "target_is_independent": True, "cargo_home_policy": "host_cargo_home_retained_for_offline_dependency_cache",
            "native_linker_overrides_cleared": True, "linker_forced": True, "cargo_cache_bound_pre_post": True,
        },
        "copy_matches_source": True,
        "raw_binary_scope": "execution_copy_only",
        "dependency_cache_pre": dependency_cache(),
        "dependency_cache_post": dependency_cache(),
        "dependency_cache_equal": True,
        "tool_identities_pre": {role: identity(role) for role in ("cargo", "rustc", "python", "uv", "linker")},
        "tool_identities_post": {role: identity(role) for role in ("cargo", "rustc", "python", "uv", "linker")},
        "tool_identities_equal": True,
        "git_identity_pre": receipt("git.exe"),
        "git_identity_post": receipt("git.exe"),
        "git_identity_equal": True,
    }
    return {
        "commit": CANDIDATE_COMMIT,
        "tree": CANDIDATE_TREE,
        "archive": {"bytes": CANDIDATE_ARCHIVE_BYTES, "sha256": CANDIDATE_ARCHIVE_SHA256, "command": "git -c core.autocrlf=false archive --format=tar <revision>", "path_redacted": True},
        "source_mode": "git_archive_at_immutable_commit",
        "inventory": dict(CANDIDATE_INVENTORY),
        "cargo_lock_sha256": CANDIDATE_CARGO_LOCK_SHA256,
        "source_date_epoch": CANDIDATE_SOURCE_DATE_EPOCH,
        "build": build,
        "cargo_binary_basename": "sipi-com-direct-config-validate.exe",
    }


def upstream() -> dict[str, object]:
    modules = {name: {"relative_path": "src/agent_com/__init__.py" if name == "agent_com" else ".venv/site-packages/module.py", "basename": "__init__.py" if name == "agent_com" else "module.py", "bytes": 1, "sha256": SHA} for name in ("agent_com", "numpy", "openpyxl", "scipy", "yaml")}
    environment = {"cleared": ["PYTHONPATH"], "pythonno_user_site": True, "uv_no_config": True, "project_venv": "materialized_inside_archive", "direct_python_fallback": False, "global_uv_cache": "required_path_redacted_environment_local", "uv_frozen": True, "uv_offline": True, "dependency_modules_scope": "environment_local_recheck_not_replay_artifact"}
    modules["agent_com"] = {"relative_path": "src/agent_com/__init__.py", "basename": "__init__.py", "bytes": UPSTREAM_INIT_BYTES, "sha256": UPSTREAM_INIT_SHA256}
    runtime = {"runtime": "executed_clean_archive_uv_frozen_offline", "command": "uv run --frozen --offline --project <clean-upstream>", "exit": 0, "stdout_bytes": 1, "stdout_sha256": SHA, "stderr_bytes": 0, "stderr_sha256": SHA, "source": source_receipt(), "environment": environment, "modules": modules}
    return {"commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea", "archive": {"bytes": UPSTREAM_ARCHIVE_BYTES, "sha256": UPSTREAM_ARCHIVE_SHA256, "command": "git -c core.autocrlf=false archive --format=tar <revision>", "path_redacted": True}, "source_mode": "git_archive_at_immutable_commit", "inventory": dict(UPSTREAM_INVENTORY), "source": source_receipt(), "runtime": runtime}


def report(run_id: str = "e" * 64, nonce: str = "f" * 64) -> dict[str, object]:
    exact = {"materialized_fingerprint": True, "parameters": True, "options": True, "consumption": True, "warnings": True, "all": True}
    return {
        "schema": "sipi.com-01.fingerprint-current-replay.v1", "status": "scoped_exact_materialized_fingerprint_replay", "work_item": "COM-01", "leaf": "config-validate", "run_id": run_id, "fresh_run_nonce": nonce, "source_mode": "git_archive_at_immutable_commit", "candidate": candidate(), "upstream": upstream(), "harness": harness(), "toolchain": {role: identity(role) for role in ("cargo", "rustc", "python", "uv", "linker")} | {"timeout_seconds": 300}, "fixture": {"role": "primary_xlsx", "relative_path": FIXTURE_RELATIVE.as_posix(), "basename": FIXTURE_RELATIVE.name, "bytes": FIXTURE_BYTES, "sha256": FIXTURE_SHA256, "path_redacted": True, "custody": "upstream_git_archive_only"}, "scenario": scenario(), "expected": {"materialized_fingerprint": EXPECTED_FINGERPRINT, "parameter_count": EXPECTED_PARAMETER_COUNT, "option_count": EXPECTED_OPTION_COUNT, "warning_count": EXPECTED_WARNING_COUNT}, "exact": exact, "artifact_policy": EXPECTED_ARTIFACT_POLICY, "acceptance": False, "non_claims": list(NON_CLAIMS),
    }


def aggregate_document(first: dict[str, object], second: dict[str, object]) -> dict[str, object]:
    return {
        "schema": AGGREGATE_SCHEMA, "status": AGGREGATE_STATUS, "work_item": "COM-01", "leaf": "config-validate", "fresh_replays": 2,
        "reports": [{"path": "first.json", "sha256": SHA, "run_id": first["run_id"], "fresh_run_nonce": first["fresh_run_nonce"], "candidate_binary_sha256": SHA}, {"path": "second.json", "sha256": "b" * 64, "run_id": second["run_id"], "fresh_run_nonce": second["fresh_run_nonce"], "candidate_binary_sha256": SHA}],
        "candidate": {key: value for key, value in first["candidate"].items() if key != "build"}, "build_receipts": [first["candidate"]["build"], second["candidate"]["build"]], "upstream": first["upstream"], "harness": first["harness"], "toolchain": first["toolchain"], "fixture": first["fixture"], "scenario": first["scenario"], "expected": first["expected"], "exact": first["exact"], "binary_bit_reproducible": False, "binary_reproducibility": RAW_BINARY_POLICY, "raw_binary_sha_equal": True, "blockers": [], "acceptance": False, "artifact_policy": EXPECTED_ARTIFACT_POLICY, "non_claims": list(NON_CLAIMS),
    }


def _git(repo: Path, *arguments: str, raw: bool = False) -> bytes | str:
    completed = subprocess.run([runner_module.GIT_EXECUTABLE, "-c", "core.autocrlf=false", "-C", str(repo), *arguments], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=runner_module.GIT_TIMEOUT_SECONDS)
    return completed.stdout if raw else completed.stdout.decode("ascii").strip()


def _clone_candidate(destination: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    subprocess.run([runner_module.GIT_EXECUTABLE, "-c", "core.autocrlf=false", "clone", "--no-hardlinks", "--quiet", str(root), str(destination)], check=True, timeout=runner_module.GIT_TIMEOUT_SECONDS)
    _git(destination, "checkout", "--quiet", PREP_PARENT_COMMIT)
    _git(destination, "config", "user.name", "COM-01 fingerprint test")
    _git(destination, "config", "user.email", "com-01-fingerprint@example.invalid")
    return destination


def _install_prep(repo: Path) -> tuple[str, dict[str, object]]:
    source_root = Path(__file__).resolve().parents[1]
    for relative in HARNESS_FILES:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / relative, target)
    _git(repo, "add", *HARNESS_FILES)
    _git(repo, "commit", "--quiet", "-m", "fingerprint prep")
    commit = str(_git(repo, "rev-parse", "HEAD"))
    tree = str(_git(repo, "rev-parse", "HEAD^{tree}"))
    files = []
    for relative in HARNESS_FILES:
        payload = bytes(_git(repo, "show", f"{commit}:{relative}", raw=True))
        files.append({"path": relative, "git_blob_sha1": str(_git(repo, "rev-parse", f"{commit}:{relative}")), "bytes": len(payload), "content_sha256": hashlib.sha256(payload).hexdigest()})
    custody_files = []
    for relative in CUSTODY_FILES:
        payload = bytes(_git(repo, "show", f"{CUSTODY_COMMIT}:{relative}", raw=True))
        custody_files.append({"path": relative, "git_blob_sha1": str(_git(repo, "rev-parse", f"{CUSTODY_COMMIT}:{relative}")), "bytes": len(payload), "content_sha256": hashlib.sha256(payload).hexdigest()})
    return commit, {"prep_commit": commit, "prep_parent": PREP_PARENT_COMMIT, "prep_tree": tree, "changed_paths": list(HARNESS_FILES), "first_introduction": True, "formal_artifacts_absent": True, "files": files, "shared_custody": {"commit": CUSTODY_COMMIT, "tree": CUSTODY_TREE, "files": custody_files}, "source_mode": "raw_git_blob_bound_before_execution"}


class FingerprintReplayVerifierTests(unittest.TestCase):
    def test_valid_report(self) -> None:
        validate_report(report())

    def test_candidate_commit_drift_rejected(self) -> None:
        value = report()
        value["candidate"]["commit"] = "0" * 40
        with self.assertRaises(VerificationError):
            validate_report(value)

    def test_fingerprint_drift_rejected(self) -> None:
        value = report()
        value["scenario"]["candidate"]["payload"]["materialized_fingerprint"] = "0" * 64
        with self.assertRaises(VerificationError):
            validate_report(value)

    def test_parameter_hash_drift_rejected(self) -> None:
        value = report()
        value["scenario"]["oracle"]["payload"]["parameters"]["semantic_sha256"] = "0" * 64
        with self.assertRaises(VerificationError):
            validate_report(value)

    def test_consumption_hash_is_type_sensitive(self) -> None:
        from run_com_01_fingerprint_current_replay import _typed_field_hash
        self.assertNotEqual(_typed_field_hash({"implemented": {"parameters": {"x": 1}}}), _typed_field_hash({"implemented": {"parameters": {"x": True}}}))
        value = report()
        value["scenario"]["candidate"]["payload"]["consumption"]["common_sha256"] = "0" * 64
        with self.assertRaises(VerificationError):
            validate_report(value)

    def test_payload_all_digest_coordination_forge_rejected(self) -> None:
        value = report()
        forged = "0" * 64
        for role in ("oracle", "candidate"):
            payload = value["scenario"][role]["payload"]
            payload["projection_sha256"] = forged
            payload["parameters"]["keys_sha256"] = forged
            payload["parameters"]["semantic_sha256"] = forged
            payload["options"]["keys_sha256"] = forged
            payload["options"]["semantic_sha256"] = forged
            payload["consumption"]["semantic_sha256"] = forged
            payload["consumption"]["common_sha256"] = forged
            payload["consumption"]["oracle_only_sha256"] = forged
            payload["warnings"]["semantic_sha256"] = forged
        with self.assertRaises(VerificationError):
            validate_report(value)

    def test_exactness_false_rejected(self) -> None:
        value = report()
        value["exact"]["all"] = False
        with self.assertRaises(VerificationError):
            validate_report(value)

    def test_path_leak_rejected(self) -> None:
        value = report()
        value["fixture"]["relative_path"] = r"C:\secret\fixture.xlsx"
        with self.assertRaises(VerificationError):
            validate_report(value)

    def test_nonce_shape_rejected(self) -> None:
        value = report(nonce="not-a-nonce")
        with self.assertRaises(VerificationError):
            validate_report(value)

    def test_shared_custody_blob_rejected(self) -> None:
        value = report()
        value["harness"]["shared_custody"]["files"][0]["git_blob_sha1"] = "0" * 40
        with self.assertRaises(VerificationError):
            validate_report(value)

    def test_static_archive_and_inventory_receipts_rejected(self) -> None:
        value = report()
        value["candidate"]["archive"]["sha256"] = "0" * 64
        with self.assertRaises(VerificationError):
            validate_report(value)
        value = report()
        value["upstream"]["inventory"]["sha256"] = "0" * 64
        with self.assertRaises(VerificationError):
            validate_report(value)

    def test_bool_int_and_extra_projection_rejected(self) -> None:
        value = report()
        value["expected"]["parameter_count"] = True
        with self.assertRaises(VerificationError):
            validate_report(value)
        value = report()
        value["scenario"]["oracle"]["payload"]["consumption"]["keys"].append("extra")
        with self.assertRaises(VerificationError):
            validate_report(value)

    def test_non_claims_order_and_promotion_rejected(self) -> None:
        value = report()
        value["non_claims"] = list(reversed(NON_CLAIMS))
        with self.assertRaises(VerificationError):
            validate_report(value)
        value = report()
        value["acceptance"] = True
        with self.assertRaises(VerificationError):
            validate_report(value)

    def test_aggregate_valid_and_raw_binary_not_claimed(self) -> None:
        first = report()
        second = report(run_id="1" * 64, nonce="2" * 64)
        validate_aggregate(aggregate_document(first, second))

    def test_aggregate_report_shape_rejected(self) -> None:
        first = report()
        second = report(run_id="1" * 64, nonce="2" * 64)
        value = aggregate_document(first, second)
        value["blockers"] = ["unexpected"]
        with self.assertRaises(VerificationError):
            validate_aggregate(value)

    def test_aggregate_rejects_coordinated_toolchain_drift(self) -> None:
        first = report()
        second = report(run_id="1" * 64, nonce="2" * 64)
        aggregate = aggregate_document(first, second)
        with tempfile.TemporaryDirectory(prefix="com-01-fingerprint-aggregate-") as directory:
            root = Path(directory)
            first_path, second_path, aggregate_path = (root / name for name in ("first.json", "second.json", "aggregate.json"))
            _atomic_json_create(first_path, first, output_root=root)
            _atomic_json_create(second_path, second, output_root=root)
            aggregate["reports"][0]["sha256"] = hashlib.sha256(first_path.read_bytes()).hexdigest()
            aggregate["reports"][1]["sha256"] = hashlib.sha256(second_path.read_bytes()).hexdigest()
            _atomic_json_create(aggregate_path, aggregate, output_root=root)
            verify_bundle(first_path, second_path, aggregate_path, repo_root=None)
            aggregate["toolchain"]["cargo"]["file_sha256"] = "0" * 64
            forged_path = root / "forged.json"
            _atomic_json_create(forged_path, aggregate, output_root=root)
            with self.assertRaises(VerificationError):
                verify_bundle(first_path, second_path, forged_path, repo_root=None)

    def test_report_is_json_bounded(self) -> None:
        payload = json.dumps(report(), sort_keys=True, separators=(",", ":")).encode("ascii")
        self.assertLess(len(payload), 4 * 1024 * 1024)

    def test_real_git_prep_gate_and_live_mutations(self) -> None:
        with tempfile.TemporaryDirectory(prefix="com-01-fingerprint-git-") as directory:
            repo = _clone_candidate(Path(directory) / "repo")
            _, gate = _install_prep(repo)
            _verify_prep_commit(gate, repo)
            drift = repo / HARNESS_FILES[0]
            drift.write_bytes(drift.read_bytes() + b"\n")
            with self.assertRaises(VerificationError):
                _verify_prep_commit(gate, repo)

    def test_real_git_prep_rejects_extra_changed_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="com-01-fingerprint-extra-") as directory:
            repo = _clone_candidate(Path(directory) / "repo")
            _, gate = _install_prep(repo)
            extra = repo / "tools" / "not-a-fingerprint-tool.py"
            extra.write_text("pass\n", encoding="ascii", newline="\n")
            _git(repo, "add", str(extra.relative_to(repo)))
            _git(repo, "commit", "--quiet", "-m", "extra path")
            forged = dict(gate)
            forged["prep_commit"] = str(_git(repo, "rev-parse", "HEAD"))
            forged["prep_tree"] = str(_git(repo, "rev-parse", "HEAD^{tree}"))
            with self.assertRaises(VerificationError):
                _verify_prep_commit(forged, repo)

    def test_real_e74_staged_helper_rejects_live_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="com-01-fingerprint-custody-") as directory:
            repo = _clone_candidate(Path(directory) / "repo")
            _load_custody(repo)
            helper = repo / "tools" / "run_com_01_current_candidate.py"
            helper.write_bytes(helper.read_bytes() + b"\n")
            with self.assertRaises(RuntimeError):
                _load_custody(repo)

    def test_real_runner_harness_receipt_rejects_live_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="com-01-fingerprint-runner-") as directory:
            repo = _clone_candidate(Path(directory) / "repo")
            custody = _load_custody(repo)
            prep, _ = _install_prep(repo)
            _harness_receipt(custody, repo, prep)
            runner = repo / HARNESS_FILES[0]
            runner.write_bytes(runner.read_bytes() + b"\n")
            with self.assertRaises(RuntimeError):
                _harness_receipt(custody, repo, prep)

    def test_real_runner_minimal_git_smoke(self) -> None:
        candidate_repo = Path(__file__).resolve().parents[1]
        upstream_repo = Path(r"C:\Users\z3312\code\COM")

        class SmokeCustody:
            def _toolchain(self, cargo: str, python: str, uv: str):
                return {role: identity(role) for role in ("cargo", "rustc", "python", "uv", "linker")}, {role: Path(python) for role in ("cargo", "rustc", "python", "uv", "linker")}

            def _materialize(self, root: Path, revision: str, destination: Path):
                destination.mkdir()
                if revision == CANDIDATE_COMMIT:
                    return {"commit": CANDIDATE_COMMIT, "tree": CANDIDATE_TREE, "archive": {"bytes": CANDIDATE_ARCHIVE_BYTES, "sha256": CANDIDATE_ARCHIVE_SHA256, "command": "git -c core.autocrlf=false archive --format=tar <revision>", "path_redacted": True}}
                return {"commit": runner_module.UPSTREAM_COMMIT, "tree": runner_module.UPSTREAM_TREE, "archive": {"bytes": UPSTREAM_ARCHIVE_BYTES, "sha256": UPSTREAM_ARCHIVE_SHA256, "command": "git -c core.autocrlf=false archive --format=tar <revision>", "path_redacted": True}}

            def _inventory(self, root: Path, prefixes):
                return dict(CANDIDATE_INVENTORY if CRATE_RELATIVE in prefixes else UPSTREAM_INVENTORY)

            def _git_inventory(self, root: Path, revision: str, prefixes):
                return dict(CANDIDATE_INVENTORY if CRATE_RELATIVE in prefixes else UPSTREAM_INVENTORY)

            def _safe_file(self, root: Path, relative: Path):
                return (candidate_repo if CRATE_RELATIVE in relative.parents else upstream_repo) / relative

            def _bounded_file(self, path: Path):
                payload = path.read_bytes()
                return len(payload), hashlib.sha256(payload).hexdigest()

            def _source_receipt(self, root: Path):
                return source_receipt()

            def _probe_upstream(self, *args):
                return {"runtime": "smoke", "environment": {}}

            def _build(self, *args):
                return Path("binary"), Path("cargo"), {"cargo_source_pre": {}}

            def _cargo_dependency_cache_inventory(self, *args):
                return dependency_cache()

            def _tool_identity(self, path: Path, role: str, args: tuple[str, ...]):
                return identity(role)

            def _execution_copy_receipt(self, *args):
                return {"basename": "sipi-com-direct-config-validate.exe", "bytes": 1, "sha256": SHA, "nlink": 1, "path_redacted": True}

            def _git(self, root: Path, *args, raw: bool = False):
                return runner_module._git(root, *args, raw=raw)

        args = SimpleNamespace(candidate_repo=candidate_repo, candidate_commit=CANDIDATE_COMMIT, upstream_repo=upstream_repo, upstream_commit=runner_module.UPSTREAM_COMMIT, python=sys.executable, cargo="cargo", uv="uv", timeout_seconds=1, run_id="a" * 64, prep_commit="b" * 40)
        with mock.patch.object(runner_module, "_load_custody", return_value=SmokeCustody()), mock.patch.object(runner_module, "_harness_receipt", return_value=harness()), mock.patch.object(runner_module, "_git_source_receipt"), mock.patch.object(runner_module, "_scenario", return_value=scenario()):
            result = runner_module.run(args)
        self.assertEqual(result["candidate"]["commit"], CANDIDATE_COMMIT)

    def test_real_clean_archive_uv_cargo_cli_validator_smoke(self) -> None:
        """Exercise the release lane without replacing scenario/build/materialize."""
        python_candidates = sorted(Path.home().joinpath("AppData", "Roaming", "uv", "python").glob("cpython-3.12*/python.exe"))
        try:
            python312 = python_candidates[0] if python_candidates else Path(subprocess.check_output(["py", "-3.12", "-c", "import sys; print(sys.executable)"], text=True, timeout=30).strip())
        except (OSError, subprocess.SubprocessError, IndexError):
            self.skipTest("Python 3.12 lane is unavailable")
        cargo = shutil.which("cargo") or str(Path.home() / ".cargo" / "bin" / "cargo.exe")
        uv = shutil.which("uv")
        if uv is None or not Path(cargo).is_file():
            self.skipTest("cargo/uv lane is unavailable")
        probe = subprocess.run([uv, "run", "--project", r"C:\Users\z3312\code\COM", "--python", str(python312), "--offline", "python", "-c", "import scipy"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        if probe.returncode != 0:
            self.skipTest("Python 3.12 offline scipy environment is unavailable")
        with tempfile.TemporaryDirectory(prefix="com-01-fingerprint-real-") as directory:
            root = Path(directory)
            repo = _clone_candidate(root / "candidate")
            prep, _ = _install_prep(repo)
            report_path = root / "report.json"
            command = [str(python312), str(repo / HARNESS_FILES[0]), "--candidate-repo", str(repo), "--upstream-repo", r"C:\Users\z3312\code\COM", "--prep-commit", prep, "--candidate-commit", CANDIDATE_COMMIT, "--upstream-commit", runner_module.UPSTREAM_COMMIT, "--cargo", str(cargo), "--python", str(python312), "--uv", uv, "--timeout-seconds", "600", "--run-id", "a" * 64, "--report", str(report_path)]
            completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=900)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertTrue(report_path.is_file())
            validator = "import sys; from pathlib import Path; sys.path.insert(0, str(Path(sys.argv[1]) / 'tools')); from verify_com_01_fingerprint_current_replay import read_json, validate_report; value, _ = read_json(Path(sys.argv[2]), input_root=Path(sys.argv[2]).parent); assert set(value) == {'schema','status','work_item','leaf','run_id','fresh_run_nonce','source_mode','candidate','upstream','harness','toolchain','fixture','scenario','expected','exact','artifact_policy','acceptance','non_claims'}, sorted(value); validate_report(value)"
            checked = subprocess.run([str(python312), "-c", validator, str(repo), str(report_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_real_filesystem_output_custody(self) -> None:
        with tempfile.TemporaryDirectory(prefix="com-01-fingerprint-output-") as directory:
            root = Path(directory)
            target = root / "report.json"
            _atomic_json_create(target, {"ok": True}, output_root=root)
            with self.assertRaises(FileExistsError):
                _atomic_json_create(target, {"ok": False}, output_root=root)
            link = root / "linked.json"
            if hasattr(os, "symlink"):
                try:
                    os.symlink(target, link)
                except OSError:
                    pass
                else:
                    with self.assertRaises(FileExistsError):
                        _atomic_json_create(link, {"ok": False}, output_root=root)
            outside = root.parent / f"{root.name}-outside.json"
            with self.assertRaises(RuntimeError):
                _atomic_json_create(outside, {"ok": False}, output_root=root)

    def test_atomic_output_partial_write_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory(prefix="com-01-fingerprint-partial-") as directory:
            root = Path(directory)
            target = root / "partial.json"
            original_write = os.write
            calls = 0

            def partial_write(descriptor: int, payload: bytes) -> int:
                nonlocal calls
                calls += 1
                if calls == 1:
                    return original_write(descriptor, payload[:1])
                raise OSError("injected partial write")

            with mock.patch("run_com_01_fingerprint_current_replay.os.write", side_effect=partial_write):
                with self.assertRaises(OSError):
                    _atomic_json_create(target, {"ok": True}, output_root=root)
            self.assertFalse(target.exists())

    def test_atomic_output_zero_write_fails_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory(prefix="com-01-fingerprint-zero-write-") as directory:
            root = Path(directory)
            target = root / "zero.json"
            with mock.patch("run_com_01_fingerprint_current_replay.os.write", return_value=0):
                with self.assertRaises(RuntimeError):
                    _atomic_json_create(target, {"ok": True}, output_root=root)
            self.assertFalse(target.exists())

    def test_json_rejects_nonfinite_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="com-01-fingerprint-nonfinite-") as directory:
            with self.assertRaises(RuntimeError):
                _atomic_json_create(Path(directory) / "nan.json", {"value": float("nan")}, output_root=Path(directory))
        from run_com_01_fingerprint_current_replay import _payload
        document = {"schema_version": 1, "execution": {"performed": False, "runtime_reads": "not_run"}, "config": {"path": "fixture.xlsx", "sha256": FIXTURE_SHA256, "profile": "r480"}, "materialized_fingerprint": EXPECTED_FINGERPRINT, "materialized": {"parameters": {"bad": float("inf")}, "options": {}}, "warnings": [], "config_consumption": {key: {} for key in CONSUMPTION_KEYS}}
        with self.assertRaises(RuntimeError):
            _payload(document)

    def test_runner_projection_rejects_document_extra(self) -> None:
        from run_com_01_fingerprint_current_replay import _payload

        document = {"schema_version": 1, "execution": {"performed": False, "runtime_reads": "not_run"}, "config": {"path": "fixture.xlsx", "sha256": FIXTURE_SHA256, "profile": "r480"}, "materialized_fingerprint": EXPECTED_FINGERPRINT, "materialized": {"parameters": {}, "options": {}}, "warnings": [], "config_consumption": {key: {} for key in CONSUMPTION_KEYS}}
        document["extra"] = True
        with self.assertRaises(RuntimeError):
            _payload(document)

    def test_runner_projection_retains_pinned_consumption_metadata(self) -> None:
        from run_com_01_fingerprint_current_replay import _payload

        document = {"schema_version": 1, "execution": {"performed": False, "runtime_reads": "not_run"}, "config": {"path": "fixture.xlsx", "sha256": FIXTURE_SHA256, "profile": "r480"}, "materialized_fingerprint": EXPECTED_FINGERPRINT, "materialized": {"parameters": {}, "options": {}}, "warnings": [], "config_consumption": {key: {} for key in (*CONSUMPTION_KEYS, *CONSUMPTION_OPTIONAL_KEYS)}}
        payload = _payload(document)
        self.assertEqual(list(payload["consumption"]), [*CONSUMPTION_KEYS, *CONSUMPTION_OPTIONAL_KEYS])
        document["config_consumption"]["unknown_pinned_key"] = {}
        with self.assertRaises(RuntimeError):
            _payload(document)

    def test_real_filesystem_input_custody_rejects_hardlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="com-01-fingerprint-input-") as directory:
            root = Path(directory)
            source = root / "source.json"
            source.write_text("{}\n", encoding="ascii", newline="\n")
            hardlink = root / "hardlink.json"
            try:
                os.link(source, hardlink)
            except OSError:
                self.skipTest("hardlinks are unavailable")
            with self.assertRaises(RuntimeError):
                read_json(hardlink, input_root=root)


if __name__ == "__main__":
    unittest.main()
