"""Run a bounded, clean-archive Agent-COM workbook replay.

The v5 runner is diagnostic evidence only.  It keeps the pinned source and
fixture identities visible, but deliberately never turns a successful run
into a product or upstream-parity claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

CANDIDATE_COMMIT = "bc882d2e5a19c2a844bacc485ede5b874e8f9c37"
CANDIDATE_TREE = "d87cfecea77ccd670073a6c069658e6b4e8c3137"
CANDIDATE_ARCHIVE_SHA256 = "1f44f6dccba7a00684a82c4c7ce6248eb5ea7f353875af5d9589d17ece6883d0"
CANDIDATE_ARCHIVE_BYTES = 51384320
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
UPSTREAM_ARCHIVE_SHA256 = "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf"
UPSTREAM_ARCHIVE_BYTES = 43694080
UV_PROJECT_VENV_IDENTITY = "materialized_upstream_project_venv"
UV_VENV_ABSENT_IDENTITY = "not_injected"
REGULAR_NONREPARSE_IDENTITY = "regular_nonreparse_file"
CANDIDATE_RESULT_PROVENANCE_SCOPE = "first_case_result"
PACKAGE_CASE_THRU_SOURCE_KIND = "workbook-s4p-source"
WORKBOOK = "matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx"
S4P = "fixtures/synthetic/kappa_asymmetric_reflective_10db_at_26p56ghz.s4p"
FIXTURE_EXPECTED = {
    "workbook": {
        "path": WORKBOOK,
        "git_blob_sha1": "22b633b6092b4b0de0ca89273515329b362eabae",
        "bytes": 67087,
        "sha256": "e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925",
    },
    "s4p": {
        "path": S4P,
        "git_blob_sha1": "a1fe8618043b31f63dfb24454ac1d296000010c0",
        "bytes": 6457063,
        "sha256": "3a563543ba664fcc04c1ac5603ad305cb0b1d110c3d9020727444b1c3fd2d0ec",
    },
}
PORT_ORDER = [1, 3, 2, 4]
CONTROL_VECTORS = ([0.0, 0.0], [0.0, 0.001])
METRIC_KEYS = (
    "FOM",
    "COM_dB",
    "VEC_dB",
    "VEO_mV",
    "sigma_N_V",
    "available_signal_v",
    "interference_noise_v",
    "threshold_der",
    "impulse_sample_count",
)
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_TOOL_OUTPUT_BYTES = 1024 * 1024
MAX_SOURCE_FILE_BYTES = 32 * 1024 * 1024
HEX64 = set("0123456789abcdef")
PATH_LEAK = re.compile(r"(?i)(?:^|[\s=(\[\{\"'])(?:[a-z]:[\\/]|\\\\|/|file://|\.\.?[\\/])")
UPSTREAM_ENV_CLEARED_KEYS = (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "PYTHONBREAKPOINT",
    "PYTHONINSPECT",
    "PYTHONWARNINGS",
    "PYTHONSAFEPATH",
    "PYTHONEXECUTABLE",
    "PYTHONUTF8",
    "PYTHONIOENCODING",
    "PYTHONHASHSEED",
    "PYTHONMALLOC",
    "PYTHONPROFILEIMPORTTIME",
    "VIRTUAL_ENV",
    "UV_PROJECT_ENVIRONMENT",
    "UV_PYTHON",
    "UV_PYTHON_DOWNLOADS",
    "UV_INDEX_URL",
    "UV_EXTRA_INDEX_URL",
    "UV_NO_INDEX",
    "UV_LINK_MODE",
    "UV_CACHE_DIR",
    "PIP_CONFIG_FILE",
    "PIP_INDEX_URL",
    "PIP_EXTRA_INDEX_URL",
    "PIP_FIND_LINKS",
    "PIP_REQUIRE_VIRTUALENV",
    "PIP_NO_INDEX",
    "CONDA_PREFIX",
    "CONDA_DEFAULT_ENV",
    "CONDA_PYTHON_EXE",
)
BUILD_ENV_CLEARED_KEYS = (
    "RUSTFLAGS",
    "CARGO_ENCODED_RUSTFLAGS",
    "RUSTC_WRAPPER",
    "RUSTC_WORKSPACE_WRAPPER",
    "CARGO_BUILD_RUSTC",
    "CARGO_BUILD_RUSTC_WRAPPER",
    "CARGO_BUILD_RUSTDOC",
    "RUSTDOCFLAGS",
    "CARGO_BUILD_TARGET",
    "RUSTUP_TOOLCHAIN",
    "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER",
    "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_RUSTFLAGS",
    "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_RUSTDOCFLAGS",
    "CARGO_BUILD_JOBS",
    "CARGO_BUILD_PIPELINING",
    "RUSTC_BOOTSTRAP",
)
BUILD_COMMAND = "cargo build --manifest-path crates/sipi-agent-com-direct/Cargo.toml --bin sipi-com-direct-run --release --locked --offline --config build.rustflags=[] --config build.rustdocflags=[] --config target.x86_64-pc-windows-msvc.rustflags=[] --config target.x86_64-pc-windows-msvc.rustdocflags=[]"
BUILD_ENV_POLICY = "offline_incremental_zero_explicit_rustc_target_flags_and_wrappers_cleared_cli_rustflags_overrides"
BUILD_CONFIG_POLICY = "cli_build_and_target_rustflags_and_rustdocflags_empty"
BUILD_CARGO_HOME_POLICY = "host_cargo_home_retained_for_offline_dependency_cache"
UPSTREAM_UV_COMMAND = "uv run --frozen --offline --project <clean-upstream> --python <pinned-python> python -c <probe>"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def output_bytes(value: bytes | str | None) -> bytes:
    """Return subprocess output without assuming the host code page."""
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8", errors="replace")


def valid_hex64(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and value == value.lower() and set(value) <= HEX64


def token(value: str) -> None:
    if not valid_hex64(value):
        raise ValueError("run_id/nonce must be lowercase 64-hex")


def is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400)
    except (OSError, ValueError):
        return True


def safe_member(name: str) -> PurePosixPath:
    if not isinstance(name, str) or "\x00" in name or "//" in name or "\\\\" in name:
        raise ValueError("unsafe archive separator")
    path = PurePosixPath(name.replace("\\", "/"))
    if (
        path.is_absolute()
        or not path.parts
        or any(part in ("", ".", "..") for part in path.parts)
        or ":" in path.parts[0]
    ):
        raise ValueError("unsafe archive member")
    return path


def bounded_file_digest(path: Path, maximum: int) -> tuple[int, str]:
    if is_reparse_point(path) or not path.is_file():
        raise ValueError("path is not a regular file")
    before = path.stat()
    if before.st_size < 0 or before.st_size > maximum:
        raise ValueError("file exceeds bounded size")
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(min(1024 * 1024, maximum - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > maximum:
                raise ValueError("file exceeds bounded size")
            hasher.update(chunk)
    after = path.stat()
    if size != before.st_size or after.st_size != before.st_size:
        raise ValueError("file changed while hashing")
    return size, hasher.hexdigest()


def bounded_file_bytes(path: Path, maximum: int) -> bytes:
    size, _ = bounded_file_digest(path, maximum)
    with path.open("rb") as stream:
        payload = stream.read(maximum + 1)
    if len(payload) != size:
        raise ValueError("file changed while reading")
    return payload


def uv_virtual_env_receipt(root: Path, environment: dict[str, str]) -> dict[str, Any]:
    """Accept only uv's project venv and publish no host path."""
    raw = environment.get("VIRTUAL_ENV")
    if raw is None:
        return {
            "present": False,
            "relative_path": None,
            "basename": None,
            "root_contained": False,
            "path_redacted": True,
            "identity": UV_VENV_ABSENT_IDENTITY,
        }
    if not isinstance(raw, str) or not raw:
        raise ValueError("VIRTUAL_ENV is not a non-empty path")
    try:
        raw_path = Path(raw)
        root_path = root.resolve()
        expected = (root_path / ".venv").resolve()
        if is_reparse_point(raw_path):
            raise ValueError("uv VIRTUAL_ENV is a reparse point")
        resolved = raw_path.resolve()
        if resolved != expected or is_reparse_point(resolved) or not resolved.is_dir():
            raise ValueError("uv VIRTUAL_ENV escaped the materialized project")
        relative = resolved.relative_to(root_path).as_posix()
    except (OSError, RuntimeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error) == "uv VIRTUAL_ENV escaped the materialized project":
            raise
        raise ValueError("uv VIRTUAL_ENV is not the materialized project venv") from error
    if relative != ".venv":
        raise ValueError("uv VIRTUAL_ENV relative identity drift")
    return {
        "present": True,
        "relative_path": relative,
        "basename": ".venv",
        "root_contained": True,
        "path_redacted": True,
        "identity": UV_PROJECT_VENV_IDENTITY,
    }


def project_venv_relative(value: Any) -> bool:
    """Recognize only a normalized package path below the project venv."""
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    parts = value.split("/")
    return len(parts) >= 2 and parts[0] == ".venv" and all(part not in ("", ".", "..") for part in parts)


def archive(repo: Path, revision: str, destination: Path, expected: dict[str, Any] | None = None) -> tuple[int, str]:
    if destination.exists():
        raise FileExistsError("archive destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        completed = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-C", str(repo), "archive", "--format=tar", revision],
            stdout=stream,
            stderr=subprocess.PIPE,
            timeout=120,
            check=False,
        )
    size, sha = bounded_file_digest(destination, MAX_MEMBER_BYTES * 8)
    if completed.returncode:
        raise RuntimeError("git archive failed")
    if expected is not None and (size != expected["bytes"] or sha != expected["sha256"]):
        raise RuntimeError("pinned archive identity mismatch")
    return size, sha


def extract(archive_path: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError("extract destination already exists")
    destination.mkdir(parents=True)
    seen: set[str] = set()
    with tarfile.open(archive_path, "r:") as stream:
        for member in stream.getmembers():
            relative = safe_member(member.name)
            name = relative.as_posix()
            if name in seen:
                raise ValueError("duplicate archive member")
            seen.add(name)
            if member.issym() or member.islnk() or not (member.isdir() or member.isreg()):
                raise ValueError("unsafe archive member type")
            if member.isreg() and (member.size < 0 or member.size > MAX_MEMBER_BYTES):
                raise ValueError("archive member exceeds bounded size")
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = stream.extractfile(member)
            if source is None:
                raise ValueError("archive member has no payload")
            payload = source.read(member.size + 1)
            if len(payload) != member.size:
                raise ValueError("archive member size changed while reading")
            with target.open("xb") as output:
                output.write(payload)


def bounded(command: list[str], cwd: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=False,
        timeout=timeout,
        check=False,
    )


def resolve_executable(value: Path | str) -> Path:
    literal = Path(value)
    if literal.is_file() and not is_reparse_point(literal):
        return literal.resolve()
    found = shutil.which(str(value))
    if found is None:
        raise RuntimeError(f"executable cannot be resolved: {value}")
    resolved = Path(found)
    if is_reparse_point(resolved) or not resolved.is_file():
        raise RuntimeError("resolved executable is not a regular file")
    return resolved.resolve()


def tool_identity(role: str, executable: Path | str, version_args: list[str]) -> dict[str, Any]:
    resolved = resolve_executable(executable)
    file_bytes, file_sha = bounded_file_digest(resolved, MAX_MEMBER_BYTES * 8)
    completed = subprocess.run(
        [str(resolved), *version_args],
        capture_output=True,
        text=False,
        timeout=30,
        check=False,
    )
    stdout = output_bytes(completed.stdout)
    stderr = output_bytes(completed.stderr)
    if len(stdout) + len(stderr) > MAX_TOOL_OUTPUT_BYTES:
        raise RuntimeError(f"{role} version output exceeds bound")
    if completed.returncode != 0:
        raise RuntimeError(f"{role} version command failed")
    return {
        "role": role,
        "basename": resolved.name,
        "file_bytes": file_bytes,
        "file_sha256": file_sha,
        "version_args": list(version_args),
        "version_exit": completed.returncode,
        "version_stdout_sha256": digest(stdout),
        "version_stderr_sha256": digest(stderr),
        "path_redacted": True,
    }


def build_environment_keys(environment: dict[str, str]) -> tuple[str, ...]:
    dynamic = sorted(
        key
        for key in environment
        if key.startswith("CARGO_TARGET_") and key.endswith(("_RUSTFLAGS", "_RUSTDOCFLAGS", "_LINKER"))
    )
    return tuple(dict.fromkeys((*BUILD_ENV_CLEARED_KEYS, *dynamic)))


def runtime_environment(rustc: Path, target: Path) -> dict[str, str]:
    environment = dict(os.environ)
    for key in build_environment_keys(environment):
        environment.pop(key, None)
    environment.update(
        {
            "CARGO_INCREMENTAL": "0",
            "CARGO_NET_OFFLINE": "true",
            "CARGO_TERM_COLOR": "never",
            "RUSTC": str(rustc),
            "CARGO_TARGET_DIR": str(target),
        }
    )
    if any(key in environment for key in build_environment_keys(environment)):
        raise RuntimeError("build environment override survived sanitization")
    return environment


def build_environment_receipt(target: Path, cleared_keys: tuple[str, ...]) -> dict[str, Any]:
    """Describe the build isolation policy without publishing host paths."""
    return {
        "cleared_keys": list(cleared_keys),
        "forced_keys": [
            "CARGO_INCREMENTAL",
            "CARGO_NET_OFFLINE",
            "CARGO_TERM_COLOR",
            "RUSTC",
            "CARGO_TARGET_DIR",
        ],
        "flags_cleared": True,
        "target_flags_cleared": True,
        "wrappers_cleared": True,
            "config_policy": BUILD_CONFIG_POLICY,
            "cargo_home_policy": BUILD_CARGO_HOME_POLICY,
        "target_basename": target.name,
        "path_redacted": True,
    }


def _existing_ancestors(path: Path) -> list[Path]:
    ancestors: list[Path] = []
    current = path
    while True:
        if current.exists():
            ancestors.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return ancestors


def fresh_scratch_root(scratch_root: Path, run_id: str, nonce: str) -> dict[str, Any]:
    if scratch_root.exists() or not scratch_root.is_absolute():
        raise FileExistsError("scratch root must be a fresh absolute caller-supplied path")
    if nonce not in scratch_root.name:
        raise ValueError("scratch root basename must bind the caller nonce")
    parent = scratch_root.parent
    if not parent.exists() or not parent.is_dir():
        raise FileNotFoundError("scratch root parent is unavailable")
    for ancestor in _existing_ancestors(parent):
        if is_reparse_point(ancestor):
            raise ValueError("scratch root has a reparse-point ancestor")
    resolved = scratch_root.resolve()
    scratch_root.mkdir(parents=False)
    if is_reparse_point(scratch_root) or not scratch_root.is_dir() or scratch_root.resolve() != resolved:
        raise ValueError("fresh scratch root did not materialize as the requested regular directory")
    marker_name = ".sipi-com-workbook-accm-v5-root-marker"
    marker = scratch_root / marker_name
    marker_payload = f"sipi-com-workbook-accm-v5\nrun_id={run_id}\nnonce={nonce}\n".encode("ascii")
    with marker.open("xb") as stream:
        stream.write(marker_payload)
    marker_bytes, marker_sha = bounded_file_digest(marker, 4096)
    return {
        "basename": scratch_root.name,
        "nonce": nonce,
        "nonce_bound": True,
        "fresh_at_start": True,
        "reparse_ancestors_checked": True,
        "path_redacted": True,
        "marker": {"basename": marker_name, "bytes": marker_bytes, "sha256": marker_sha, "path_redacted": True},
    }


def scratch_post_receipt(scratch_root: Path, initial: dict[str, Any]) -> dict[str, Any]:
    """Recheck the caller root and marker after all child processes finish."""
    if is_reparse_point(scratch_root) or not scratch_root.is_dir():
        raise ValueError("scratch root was removed or replaced")
    marker = scratch_root / initial["marker"]["basename"]
    marker_bytes, marker_sha = bounded_file_digest(marker, 4096)
    if marker_bytes != initial["marker"]["bytes"] or marker_sha != initial["marker"]["sha256"]:
        raise ValueError("scratch root marker changed during replay")
    return {
        "basename": scratch_root.name,
        "nonce": initial["nonce"],
        "post_verified": True,
        "path_redacted": True,
        "marker": {"basename": marker.name, "bytes": marker_bytes, "sha256": marker_sha, "path_redacted": True},
    }


def capture_receipt(completed: subprocess.CompletedProcess[bytes]) -> dict[str, Any]:
    stdout = output_bytes(completed.stdout)
    stderr = output_bytes(completed.stderr)
    if len(stdout) > MAX_CAPTURE_BYTES or len(stderr) > MAX_CAPTURE_BYTES:
        raise RuntimeError("subprocess capture exceeds bound")
    return {
        "exit": completed.returncode,
        "stdout_sha256": digest(stdout),
        "stderr_sha256": digest(stderr),
    }


def numeric_metrics(metrics: Any) -> dict[str, float | None]:
    if not isinstance(metrics, dict):
        raise ValueError("metrics must be an object")
    result: dict[str, float | None] = {}
    for key in METRIC_KEYS:
        value = metrics.get(key)
        if value is None:
            result[key] = None
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"metric is not a finite scalar: {key}")
        else:
            result[key] = float(value)
    return result


def candidate_array_receipt(value: Any, name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"candidate array receipt is not an object: {name}")
    sample_count = value.get("sample_count")
    sha = value.get("sha256")
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count < 0 or not valid_hex64(sha):
        raise ValueError(f"invalid candidate array receipt: {name}")
    return {"sample_count": sample_count, "sha256": sha}


def candidate_projection(case: Any) -> dict[str, Any]:
    if not isinstance(case, dict):
        raise ValueError("candidate case is not an object")
    case_index = case.get("case_index")
    if type(case_index) is not int or case_index < 0:
        raise ValueError("candidate case index is not an integer")
    diagnostics = case.get("diagnostics")
    if not isinstance(diagnostics, dict):
        raise ValueError("candidate case diagnostics are missing")
    portable = diagnostics.get("portable_branches")
    if not isinstance(portable, dict):
        raise ValueError("candidate portable branch diagnostics are missing")
    search = portable.get("search")
    if not isinstance(search, dict):
        raise ValueError("candidate search diagnostics are missing")
    metric_projection = numeric_metrics(case.get("metrics"))
    winner = {
        "cursor_index": search.get("cursor_index"),
        "ctle_index": search.get("ctle_index"),
        "high_pass_index": search.get("high_pass_index"),
        "tx_grid_index": search.get("tx_grid_index"),
        "sigma_n_v": search.get("sigma_n_v") if search.get("sigma_n_v") is not None else metric_projection.get("sigma_N_V"),
        "fom_db": search.get("fom_db") if search.get("fom_db") is not None else metric_projection.get("FOM"),
        "selected_tx_taps": search.get("selected_tx_taps"),
        "dfe_taps": search.get("dfe_taps", search.get("selected_dfe_taps")),
        "dfe_published": "dfe_taps" in search or "selected_dfe_taps" in search,
        "selected_pulse": {
            "sample_count": search.get("selected_pulse_sample_count"),
            "sha256": search.get("selected_pulse_sha256"),
        },
    }
    for key in ("cursor_index", "ctle_index", "high_pass_index", "tx_grid_index"):
        if isinstance(winner[key], bool) or not isinstance(winner[key], int) or winner[key] < 0:
            raise ValueError(f"invalid candidate winner field: {key}")
    for key in ("sigma_n_v", "fom_db"):
        if not isinstance(winner[key], (int, float)) or isinstance(winner[key], bool) or not math.isfinite(float(winner[key])):
            raise ValueError(f"invalid candidate winner field: {key}")
        winner[key] = float(winner[key])
    taps = winner["selected_tx_taps"]
    if not isinstance(taps, list) or any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) for value in taps):
        raise ValueError("invalid candidate TX taps")
    winner["selected_tx_taps"] = [float(value) for value in taps]
    winner["selected_pulse"] = candidate_array_receipt(winner["selected_pulse"], "selected_pulse")
    dfe = winner["dfe_taps"]
    if dfe is not None:
        if not isinstance(dfe, list) or any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) for value in dfe):
            raise ValueError("invalid candidate DFE taps")
        winner["dfe_taps"] = [float(value) for value in dfe]
    arrays = {
        "channel_impulse": candidate_array_receipt(diagnostics.get("channel_impulse"), "channel_impulse"),
        "channel_pulse": candidate_array_receipt(diagnostics.get("channel_pulse"), "channel_pulse"),
    }
    observed_port_order = None
    for source in (case, diagnostics, portable, search):
        if not isinstance(source, dict):
            continue
        for key in ("port_order", "snpPortsOrder", "applied_port_order"):
            if key in source:
                observed_port_order = source[key]
                break
        if observed_port_order is not None:
            break
    if observed_port_order is not None:
        if (
            not isinstance(observed_port_order, list)
            or len(observed_port_order) != len(PORT_ORDER)
            or any(isinstance(value, bool) or not isinstance(value, int) for value in observed_port_order)
            or sorted(observed_port_order) != sorted(PORT_ORDER)
        ):
            raise ValueError("invalid candidate applied port order")
    return {
        "case_index": case_index,
        "metrics": metric_projection,
        "winner": winner,
        "arrays": arrays,
        "port_order": observed_port_order,
        "port_order_observed": observed_port_order is not None,
    }


def first_case_result_provenance(value: Any, cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Project document provenance once, with an explicit first-case scope."""
    required = {"config_sha256", "channel_source_sha256", "impulse_sha256"}
    if not isinstance(value, dict) or not required.issubset(value):
        raise ValueError("candidate result provenance schema drift")
    projected = {key: value[key] for key in required}
    for key, item in projected.items():
        if not valid_hex64(item):
            raise ValueError(f"candidate result provenance.{key} is not a SHA-256")
    if not cases or not isinstance(cases[0], dict):
        raise ValueError("candidate result has no first case")
    first_impulse = cases[0].get("arrays", {}).get("channel_impulse")
    if not isinstance(first_impulse, dict) or projected["impulse_sha256"] != first_impulse.get("sha256"):
        raise ValueError("candidate first-case impulse provenance is not the reported array")
    if projected["channel_source_sha256"] != FIXTURE_EXPECTED["s4p"]["sha256"]:
        raise ValueError("candidate result channel source is not the pinned S4P fixture")
    return {
        "scope": CANDIDATE_RESULT_PROVENANCE_SCOPE,
        "case_index": 0,
        "config_sha256": projected["config_sha256"],
        "channel_source_sha256": projected["channel_source_sha256"],
        "impulse_sha256": projected["impulse_sha256"],
    }


def package_case_manifests(value: Any, raw_cases: list[Any], projected_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retain only ordered, path-free per-case THRU source identity."""
    if not isinstance(value, dict):
        raise ValueError("candidate package provenance is missing")
    manifests = value.get("manifests")
    if not isinstance(manifests, list) or len(manifests) != len(projected_cases) or len(raw_cases) != len(projected_cases):
        raise ValueError("candidate package case manifest count drift")
    result: list[dict[str, Any]] = []
    for index, (raw_case, projected_case, manifest) in enumerate(zip(raw_cases, projected_cases, manifests)):
        raw_case_index = raw_case.get("package_case_index") if isinstance(raw_case, dict) else None
        projected_case_index = projected_case.get("case_index") if isinstance(projected_case, dict) else None
        if type(raw_case_index) is not int or raw_case_index != index or type(projected_case_index) is not int or projected_case_index != index:
            raise ValueError("candidate package case order drift")
        if not isinstance(manifest, dict):
            raise ValueError("candidate package case manifest shape drift")
        case_id = manifest.get("case_id")
        raw_case_id = raw_case.get("case_id")
        thru = manifest.get("thru")
        if not isinstance(case_id, str) or case_id != f"workbook-case-{index}" or raw_case_id != case_id or not isinstance(thru, dict):
            raise ValueError("candidate package case identity drift")
        source_sha = thru.get("sha256")
        identity = thru.get("identity")
        source_kind = thru.get("source_kind")
        if not valid_hex64(source_sha) or source_sha != FIXTURE_EXPECTED["s4p"]["sha256"] or identity != f"{case_id}:thru" or source_kind != PACKAGE_CASE_THRU_SOURCE_KIND:
            raise ValueError("candidate package THRU source identity drift")
        result.append({
            "case_id": case_id,
            "order": index,
            "thru": {"source_sha256": source_sha, "identity": identity, "source_kind": source_kind},
        })
    return result


def artifact_inventory(root: Path) -> list[dict[str, Any]]:
    if is_reparse_point(root) or not root.is_dir():
        raise ValueError("artifact root is not a regular directory")
    allowed = {"result.json", "report.html", "diagnostics.json", "legacy.csv"}
    result = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if child.name not in allowed or is_reparse_point(child) or not child.is_file():
            raise ValueError("unexpected candidate artifact entry")
        size, sha = bounded_file_digest(child, MAX_ARTIFACT_BYTES)
        result.append({"basename": child.name, "bytes": size, "sha256": sha, "path_redacted": True})
    if {item["basename"] for item in result} != {"result.json", "report.html", "diagnostics.json"}:
        raise ValueError("candidate artifact set is incomplete")
    return result


def run_candidate_build(root: Path, cargo: Path, rustc: Path, target: Path, timeout: int = 900) -> tuple[dict[str, Any], Path, dict[str, str]]:
    target.parent.mkdir(parents=True, exist_ok=True)
    cleared_keys = build_environment_keys(dict(os.environ))
    environment = runtime_environment(rustc, target)
    command = [
        str(cargo),
        "build",
        "--manifest-path",
        "crates/sipi-agent-com-direct/Cargo.toml",
        "--bin",
        "sipi-com-direct-run",
        "--release",
        "--locked",
        "--offline",
        "--config",
        "build.rustflags=[]",
        "--config",
        "build.rustdocflags=[]",
        "--config",
        "target.x86_64-pc-windows-msvc.rustflags=[]",
        "--config",
        "target.x86_64-pc-windows-msvc.rustdocflags=[]",
    ]
    completed = bounded(command, root, environment, timeout)
    receipt = capture_receipt(completed)
    receipt.update(
        {
            "command": BUILD_COMMAND,
            "timeout_s": timeout,
            "env_policy": BUILD_ENV_POLICY,
            "env_receipt": build_environment_receipt(target, cleared_keys),
        }
    )
    binary = target / "release" / "sipi-com-direct-run.exe"
    if completed.returncode != 0:
        receipt["blocker"] = "candidate release build failed"
        return receipt, binary, environment
    if is_reparse_point(binary) or not binary.is_file():
        receipt["blocker"] = "candidate binary missing after successful build"
        return receipt, binary, environment
    size, sha = bounded_file_digest(binary, MAX_MEMBER_BYTES * 8)
    receipt["binary_pre"] = {"basename": binary.name, "bytes": size, "sha256": sha, "path_redacted": True}
    return receipt, binary, environment


def run_candidate_probe(root: Path, binary: Path, environment: dict[str, str], vector: list[float], control_index: int, timeout: int = 180) -> dict[str, Any]:
    if not binary.is_file():
        return {"runtime_exit": None, "consumer_proof": False, "blocker": "candidate binary unavailable"}
    output = root / "outputs" / f"candidate-{control_index}"
    if output.exists():
        raise FileExistsError("candidate output root is not fresh")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(binary),
        "run",
        "--config",
        str(root / "inputs" / "pinned-workbook.xlsx"),
        "--thru",
        str(root / "inputs" / "pinned-channel.s4p"),
        "--output-dir",
        str(output),
        "--override",
        f"AC_CM_RMS={json.dumps(vector, separators=(',', ':'))}",
        "--overwrite",
    ]
    completed = bounded(command, root, environment, timeout)
    receipt = capture_receipt(completed)
    receipt["runtime_timeout_s"] = timeout
    receipt["command"] = "sipi-com-direct-run run --config <pinned-workbook> --thru <pinned-s4p> --output-dir <fresh-output> --override AC_CM_RMS=<vector> --overwrite"
    receipt["vector"] = list(vector)
    if completed.returncode != 0:
        receipt.update({"runtime_exit": completed.returncode, "consumer_proof": False, "blocker": "candidate runtime failed"})
        return receipt
    result_path = output / "result.json"
    try:
        raw = bounded_file_bytes(result_path, MAX_ARTIFACT_BYTES)
        document = json.loads(raw)
        cases = document.get("cases")
        if not isinstance(cases, list) or not cases:
            raise ValueError("candidate result has no cases")
        projection = [candidate_projection(case) for case in cases]
        provenance = document.get("provenance") if isinstance(document.get("provenance"), dict) else {}
        result_provenance = first_case_result_provenance(provenance, projection)
        case_manifests = package_case_manifests(provenance.get("package_cases"), cases, projection)
        receipt.update(
            {
                "runtime_exit": completed.returncode,
                "consumer_proof": True,
                "artifact_sha256": digest(raw),
                "artifacts": artifact_inventory(output),
                "first_case_result_provenance": result_provenance,
                "package_case_manifests": case_manifests,
                "cases": projection,
                "blocker": None,
            }
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        receipt.update({"runtime_exit": completed.returncode, "consumer_proof": False, "blocker": f"candidate result artifact invalid: {type(error).__name__}"})
    return receipt


def upstream_probe_script(vector: list[float], source_identity: dict[str, Any] | None = None) -> str:
    return f'''from pathlib import Path
import hashlib, json, math, os, re
import numpy as np
import scipy
import agent_com
from agent_com import BehaviorProfile, ChannelSet, RunOptions, load_config, run_com

MAX_SOURCE_FILE_BYTES = {MAX_SOURCE_FILE_BYTES}
UPSTREAM_ENV_CLEARED_KEYS = {UPSTREAM_ENV_CLEARED_KEYS!r}
EXPECTED_SOURCE_IDENTITY = {source_identity!r}
UV_PROJECT_VENV_IDENTITY = {UV_PROJECT_VENV_IDENTITY!r}
UV_VENV_ABSENT_IDENTITY = {UV_VENV_ABSENT_IDENTITY!r}
REGULAR_NONREPARSE_IDENTITY = {REGULAR_NONREPARSE_IDENTITY!r}

def is_reparse(path):
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400)
    except OSError:
        return True

def has_reparse_ancestor(path):
    current = Path(path)
    while True:
        if is_reparse(current):
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent

def bytes_receipt(path, root, require_contained=False, package=False):
    raw_path = Path(path)
    if has_reparse_ancestor(raw_path):
        raise RuntimeError("runtime module path has a symlink or reparse ancestor")
    path = raw_path.resolve()
    root = Path(root).resolve()
    if has_reparse_ancestor(path):
        raise RuntimeError("resolved runtime module path has a symlink or reparse ancestor")
    try:
        relative = path.relative_to(root).as_posix()
        contained = True
    except ValueError:
        if require_contained:
            raise RuntimeError("agent_com import escaped materialized archive")
        relative = None
        contained = False
    if not path.is_file():
        raise RuntimeError("runtime module is not a regular file")
    payload = path.read_bytes()
    if len(payload) > MAX_SOURCE_FILE_BYTES:
        raise RuntimeError("runtime module exceeds source bound")
    receipt = {{"relative_path": relative, "basename": path.name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "root_contained": contained, "path_redacted": True}}
    if package:
        receipt.update({{"regular_file": True, "reparse_checked": True, "identity": REGULAR_NONREPARSE_IDENTITY}})
    return receipt

def source_inventory(root):
    raw_package = Path(root) / "src" / "agent_com"
    if raw_package.is_symlink():
        raise RuntimeError("materialized agent_com source package is a symlink")
    package = raw_package.resolve()
    if not package.is_dir():
        raise RuntimeError("materialized agent_com source package is unavailable")
    entries = []
    for path in sorted(package.rglob("*.py"), key=lambda item: item.as_posix()):
        if has_reparse_ancestor(path) or not path.is_file():
            raise RuntimeError("agent_com source inventory contains a non-regular file")
        payload = path.read_bytes()
        if len(payload) > MAX_SOURCE_FILE_BYTES:
            raise RuntimeError("agent_com source file exceeds bound")
        entries.append({{"path": path.relative_to(Path(root).resolve()).as_posix(), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}})
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return {{"count": len(entries), "total_bytes": sum(item["bytes"] for item in entries), "sha256": hashlib.sha256(canonical).hexdigest()}}

def module_receipt(module, root, name):
    filename = getattr(module, "__file__", None)
    if not filename:
        raise RuntimeError(f"{{name}} has no module file")
    receipt = bytes_receipt(filename, root, package=True)
    receipt.update({{"module": name, "version": str(getattr(module, "__version__", "unknown"))}})
    return receipt

def project_venv_relative(value):
    if not isinstance(value, str) or not value or "\\\\" in value or ":" in value:
        return False
    parts = value.split("/")
    return len(parts) >= 2 and parts[0] == ".venv" and all(part not in ("", ".", "..") for part in parts)

def validate_package_location(receipt, name, uv_virtual_env):
    if receipt["regular_file"] is not True or receipt["reparse_checked"] is not True or receipt["identity"] != REGULAR_NONREPARSE_IDENTITY:
        raise RuntimeError(f"{{name}} runtime file identity is not regular and non-reparse")
    if uv_virtual_env["present"]:
        relative = receipt["relative_path"]
        if not receipt["root_contained"] or not project_venv_relative(relative):
            raise RuntimeError(f"{{name}} runtime module escaped the uv project venv")
    elif receipt["root_contained"] is not False or receipt["relative_path"] is not None:
        raise RuntimeError(f"{{name}} external runtime identity is not explicit")

def runtime_proof(root):
    missing = [key for key in UPSTREAM_ENV_CLEARED_KEYS if key not in ("PYTHONPATH", "VIRTUAL_ENV") and key in os.environ]
    unexpected_python = [key for key in os.environ if key.startswith("PYTHON") and key not in ("PYTHONNOUSERSITE", "PYTHONPATH")]
    if missing or unexpected_python:
        raise RuntimeError("host Python environment override survived sanitization")
    if os.environ.get("PYTHONNOUSERSITE") != "1" or os.environ.get("UV_NO_CONFIG") != "1":
        raise RuntimeError("required isolated Python environment flags are missing")
    pythonpath = os.environ.get("PYTHONPATH")
    if pythonpath is None:
        pythonpath_mode = "unset"
    elif pythonpath == str((Path(root) / "src").resolve()):
        pythonpath_mode = "materialized_archive_src"
    else:
        raise RuntimeError("PYTHONPATH is not the materialized archive source")
    package_file = bytes_receipt(agent_com.__file__, root, require_contained=True)
    if package_file["relative_path"] != "src/agent_com/__init__.py":
        raise RuntimeError("agent_com import did not resolve to the archive package")
    raw_virtual_env = os.environ.get("VIRTUAL_ENV")
    if raw_virtual_env is None:
        uv_virtual_env = {{"present": False, "relative_path": None, "basename": None, "root_contained": False, "path_redacted": True, "identity": UV_VENV_ABSENT_IDENTITY}}
    else:
        virtual_env = Path(raw_virtual_env)
        archive_root = Path(root).resolve()
        expected_virtual_env = (archive_root / ".venv").resolve()
        if virtual_env.is_symlink():
            raise RuntimeError("uv VIRTUAL_ENV is a symlink")
        try:
            if bool(getattr(virtual_env.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400):
                raise RuntimeError("uv VIRTUAL_ENV is a reparse point")
        except OSError as error:
            raise RuntimeError("uv VIRTUAL_ENV cannot be inspected") from error
        resolved_virtual_env = virtual_env.resolve()
        if resolved_virtual_env != expected_virtual_env or not resolved_virtual_env.is_dir():
            raise RuntimeError("uv VIRTUAL_ENV escaped the materialized project")
        try:
            relative_virtual_env = resolved_virtual_env.relative_to(archive_root).as_posix()
        except ValueError as error:
            raise RuntimeError("uv VIRTUAL_ENV is outside the materialized archive") from error
        if relative_virtual_env != ".venv":
            raise RuntimeError("uv VIRTUAL_ENV relative identity drift")
        uv_virtual_env = {{"present": True, "relative_path": relative_virtual_env, "basename": ".venv", "root_contained": True, "path_redacted": True, "identity": UV_PROJECT_VENV_IDENTITY}}
    proof = {{
        "environment": {{"cleared": list(UPSTREAM_ENV_CLEARED_KEYS), "pythonpath_mode": pythonpath_mode, "pythonno_user_site": True, "uv_no_config": True, "uv_virtual_env": uv_virtual_env}},
        "agent_com": {{"module": "agent_com", "contained_in_materialized_archive": True, "module_file": package_file, "package_source_inventory": source_inventory(root)}},
        "numpy": module_receipt(np, root, "numpy"),
        "scipy": module_receipt(scipy, root, "scipy"),
    }}
    validate_package_location(proof["numpy"], "numpy", uv_virtual_env)
    validate_package_location(proof["scipy"], "scipy", uv_virtual_env)
    if EXPECTED_SOURCE_IDENTITY is not None:
        if proof["agent_com"]["module_file"] != EXPECTED_SOURCE_IDENTITY["module_file"] or proof["agent_com"]["package_source_inventory"] != EXPECTED_SOURCE_IDENTITY["package_source_inventory"]:
            raise RuntimeError("agent_com source identity changed from archive preflight")
    return proof

def scalar(value):
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, np.ndarray):
        if value.size != 1:
            return None
        value = value.reshape(-1)[0].item()
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    return None

def metrics(value, diagnostics):
    result = {{key: scalar(value.get(key)) for key in {METRIC_KEYS!r}}}
    if result["sigma_N_V"] is None:
        result["sigma_N_V"] = scalar(diagnostics.get("sigma_n_v"))
    return result

def array_receipt(value):
    if value is None:
        return None
    try:
        array = np.asarray(value, dtype="<f8")
        payload = np.ascontiguousarray(array, dtype="<f8").tobytes(order="C")
        return {{"shape": list(array.shape), "sample_count": int(array.size), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}}
    except (TypeError, ValueError):
        return None

def q(case):
    diagnostics = case.diagnostics
    plots = diagnostics.get("matlab_r480_plots", {{}})
    fd = plots.get("fd", {{}})
    return {{"metrics": metrics(dict(case.metrics), diagnostics), "winner": {{
        "cursor_index": diagnostics.get("cursor_index"),
        "ctle_index": diagnostics.get("ctle_index"),
        "high_pass_index": diagnostics.get("high_pass_index"),
        "tx_grid_index": diagnostics.get("tx_grid_index"),
        "sigma_n_v": scalar(diagnostics.get("sigma_n_v")),
        "fom_db": scalar(diagnostics.get("fom_db")) if scalar(diagnostics.get("fom_db")) is not None else scalar(case.metrics.get("FOM")),
        "selected_tx_taps": None,
        "dfe_taps": None if diagnostics.get("dfe_taps") is None else np.asarray(diagnostics.get("dfe_taps"), dtype=float).reshape(-1).tolist(),
        "dfe_published": "dfe_taps" in diagnostics,
    }}, "port_order": order, "arrays": {{
        "unequalized_impulse": array_receipt(diagnostics.get("unequalized_impulse")),
        "equalized_pulse": array_receipt(diagnostics.get("equalized_pulse")),
        "frequency_hz": array_receipt(fd.get("frequency_hz")),
        "ptdr": array_receipt(diagnostics.get("ptdr")),
        "ptdr_gated": array_receipt(diagnostics.get("ptdr_gated")),
        "tdr_time_s": array_receipt(diagnostics.get("tdr_time_s")),
     }}}}

root = Path.cwd()
profile = BehaviorProfile.r480()
config = load_config(root / {WORKBOOK!r}, profile=profile, overrides={{"AC_CM_RMS": {vector!r}}})
result = run_com(config=config, channels=ChannelSet(root / {S4P!r}), options=RunOptions(profile=profile, diagnostics=True))
raw_order = str(config.settings.lookup("Port Order").value)
order = [int(item) for item in re.findall(r"[0-9]+", raw_order)]
print(json.dumps({{"config_sha256": config.source_sha256, "port_order": order, "runtime_proof": runtime_proof(root), "cases": [q(case) for case in result.cases]}}, allow_nan=False, separators=(",", ":")))
'''


def parse_upstream_probe(completed: subprocess.CompletedProcess[bytes], runtime: str, attempts: list[dict[str, Any]], source_identity: dict[str, Any] | None = None) -> dict[str, Any]:
    receipt = capture_receipt(completed)
    stdout = output_bytes(completed.stdout)
    stderr = output_bytes(completed.stderr)
    payload: dict[str, Any] = {**receipt, "stdout_bytes": len(stdout), "stderr_bytes": len(stderr), "runtime": runtime, "attempts": attempts}
    if completed.returncode != 0:
        payload["blocker"] = "upstream runtime failed"
        return payload
    try:
        value = json.loads(stdout.decode("utf-8").strip().splitlines()[-1])
        cases = value["cases"]
        config_sha = value["config_sha256"]
        order = value["port_order"]
        runtime_proof = value["runtime_proof"]
        validate_runtime_proof(runtime_proof, source_identity)
        if not valid_hex64(config_sha) or order != PORT_ORDER or not isinstance(cases, list) or not cases:
            raise ValueError("upstream probe projection invalid")
        for case in cases:
            if not isinstance(case, dict) or not isinstance(case.get("metrics"), dict) or not isinstance(case.get("winner"), dict):
                raise ValueError("upstream case projection invalid")
        payload.update({"config_sha256": config_sha, "port_order": order, "runtime_proof": runtime_proof, "artifact": {"basename": "upstream-projection.json", "bytes": len(stdout), "sha256": digest(stdout), "path_redacted": True}, "cases": cases, "blocker": None})
    except (IndexError, KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        payload["blocker"] = f"upstream artifact invalid: {type(error).__name__}"
    return payload


def validate_uv_virtual_env_receipt(value: Any) -> None:
    required = {"present", "relative_path", "basename", "root_contained", "path_redacted", "identity"}
    if not isinstance(value, dict) or set(value) != required or not isinstance(value["present"], bool) or value["path_redacted"] is not True:
        raise ValueError("uv VIRTUAL_ENV receipt shape invalid")
    if value["present"]:
        if value["relative_path"] != ".venv" or value["basename"] != ".venv" or value["root_contained"] is not True or value["identity"] != UV_PROJECT_VENV_IDENTITY:
            raise ValueError("uv VIRTUAL_ENV containment or identity invalid")
    elif value["relative_path"] is not None or value["basename"] is not None or value["root_contained"] is not False or value["identity"] != UV_VENV_ABSENT_IDENTITY:
        raise ValueError("absent uv VIRTUAL_ENV receipt drift")


def validate_runtime_package_receipt(value: Any, name: str, uv_virtual_env: dict[str, Any]) -> None:
    required = {
        "relative_path",
        "basename",
        "bytes",
        "sha256",
        "root_contained",
        "path_redacted",
        "regular_file",
        "reparse_checked",
        "identity",
        "module",
        "version",
    }
    if not isinstance(value, dict) or set(value) != required or value["module"] != name or value["path_redacted"] is not True or value["regular_file"] is not True or value["reparse_checked"] is not True or value["identity"] != REGULAR_NONREPARSE_IDENTITY:
        raise ValueError(f"{name} runtime identity invalid")
    if isinstance(value["bytes"], bool) or not isinstance(value["bytes"], int) or value["bytes"] <= 0 or not valid_hex64(value["sha256"]):
        raise ValueError(f"{name} runtime receipt invalid")
    if not isinstance(value["version"], str) or not value["version"] or not isinstance(value["basename"], str) or not value["basename"] or "/" in value["basename"] or "\\" in value["basename"]:
        raise ValueError(f"{name} runtime basename/version invalid")
    if uv_virtual_env["present"]:
        relative = value["relative_path"]
        if value["root_contained"] is not True or not project_venv_relative(relative):
            raise ValueError(f"{name} runtime module is outside the uv project venv")
    elif value["root_contained"] is not False or value["relative_path"] is not None:
        raise ValueError(f"{name} external runtime identity is not explicit")


def validate_runtime_proof(value: Any, source_identity: dict[str, Any] | None = None) -> None:
    if not isinstance(value, dict) or set(value) != {"environment", "agent_com", "numpy", "scipy"}:
        raise ValueError("upstream runtime proof shape invalid")
    environment = value["environment"]
    if not isinstance(environment, dict) or set(environment) != {"cleared", "pythonpath_mode", "pythonno_user_site", "uv_no_config", "uv_virtual_env"}:
        raise ValueError("upstream environment proof shape invalid")
    if environment["cleared"] != list(UPSTREAM_ENV_CLEARED_KEYS) or environment["pythonpath_mode"] not in {"unset", "materialized_archive_src"} or environment["pythonno_user_site"] is not True or environment["uv_no_config"] is not True:
        raise ValueError("upstream environment proof invalid")
    validate_uv_virtual_env_receipt(environment["uv_virtual_env"])
    agent = value["agent_com"]
    if not isinstance(agent, dict) or set(agent) != {"module", "contained_in_materialized_archive", "module_file", "package_source_inventory"} or agent["module"] != "agent_com" or agent["contained_in_materialized_archive"] is not True:
        raise ValueError("agent_com containment proof invalid")
    module_file = agent["module_file"]
    if not isinstance(module_file, dict) or set(module_file) != {"relative_path", "basename", "bytes", "sha256", "root_contained", "path_redacted"} or module_file["relative_path"] != "src/agent_com/__init__.py" or module_file["basename"] != "__init__.py" or module_file["root_contained"] is not True or module_file["path_redacted"] is not True:
        raise ValueError("agent_com source identity invalid")
    if not isinstance(module_file["bytes"], int) or module_file["bytes"] <= 0 or not valid_hex64(module_file["sha256"]):
        raise ValueError("agent_com source receipt invalid")
    inventory = agent["package_source_inventory"]
    if not isinstance(inventory, dict) or set(inventory) != {"count", "total_bytes", "sha256"} or not isinstance(inventory["count"], int) or inventory["count"] <= 0 or not isinstance(inventory["total_bytes"], int) or inventory["total_bytes"] <= 0 or not valid_hex64(inventory["sha256"]):
        raise ValueError("agent_com source inventory invalid")
    if source_identity is not None:
        if not isinstance(source_identity, dict) or set(source_identity) != {"module_file", "package_source_inventory"} or module_file != source_identity["module_file"] or inventory != source_identity["package_source_inventory"]:
            raise ValueError("agent_com source identity changed from archive preflight")
    for name in ("numpy", "scipy"):
        validate_runtime_package_receipt(value[name], name, environment["uv_virtual_env"])


def classify_upstream_blocker(stderr: bytes) -> str:
    lowered = stderr.lower()
    if b"not found in the cache" in lowered or b"network connectivity is disabled" in lowered:
        return "offline_dependency_cache_missing"
    if b"matlab" in lowered:
        return "upstream_matlab_runtime_unavailable"
    return "upstream_runtime_failed"


def upstream_environment(root: Path, direct: bool) -> dict[str, str]:
    environment = dict(os.environ)
    for key in tuple(environment):
        if key == "VIRTUAL_ENV" or key.startswith("PYTHON"):
            environment.pop(key, None)
    for key in UPSTREAM_ENV_CLEARED_KEYS:
        environment.pop(key, None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["UV_NO_CONFIG"] = "1"
    if direct:
        environment["PYTHONPATH"] = str((root / "src").resolve())
    return environment


def run_upstream_probe(root: Path, python: Path, vector: list[float], timeout: int = 180, uv: Path | None = None, source_identity: dict[str, Any] | None = None) -> dict[str, Any]:
    script = upstream_probe_script(vector, source_identity)
    attempts: list[dict[str, Any]] = []
    if uv is not None:
        uv_command = [str(uv), "run", "--frozen", "--offline", "--project", str(root), "--python", str(python), "python", "-c", script]
        uv_environment = upstream_environment(root, direct=False)
        completed = bounded(uv_command, root, uv_environment, timeout)
        attempt = capture_receipt(completed)
        attempt.update({"stdout_bytes": len(output_bytes(completed.stdout)), "stderr_bytes": len(output_bytes(completed.stderr)), "method": "uv_offline", "command": UPSTREAM_UV_COMMAND, "blocker": None if completed.returncode == 0 else classify_upstream_blocker(output_bytes(completed.stderr))})
        attempts.append(attempt)
        if completed.returncode == 0:
            result = parse_upstream_probe(completed, "executed_clean_archive_uv", attempts, source_identity)
            if "cases" in result:
                return result
    direct_environment = upstream_environment(root, direct=True)
    completed = bounded([str(python), "-c", script], root, direct_environment, timeout)
    attempt = capture_receipt(completed)
    attempt.update({"stdout_bytes": len(output_bytes(completed.stdout)), "stderr_bytes": len(output_bytes(completed.stderr)), "method": "direct_python_external_env", "command": "python -c <probe> with PYTHONPATH=<clean-upstream>/src", "blocker": None if completed.returncode == 0 else classify_upstream_blocker(output_bytes(completed.stderr))})
    attempts.append(attempt)
    result = parse_upstream_probe(completed, "executed_clean_archive_external_python_env", attempts, source_identity)
    if "cases" not in result:
        result["upstream_runtime_blocker"] = result.get("blocker", "upstream runtime unavailable")
    return result


def fixture_receipts(upstream_root: Path, inputs: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    inputs.mkdir(parents=True, exist_ok=True)
    for key, expected in FIXTURE_EXPECTED.items():
        source = upstream_root / expected["path"]
        payload = bounded_file_bytes(source, MAX_MEMBER_BYTES)
        if len(payload) != expected["bytes"] or digest(payload) != expected["sha256"]:
            raise RuntimeError(f"{key} fixture identity mismatch")
        target = inputs / ("pinned-workbook.xlsx" if key == "workbook" else "pinned-channel.s4p")
        target.write_bytes(payload)
        target_size, target_sha = bounded_file_digest(target, MAX_MEMBER_BYTES)
        if target_size != len(payload) or target_sha != digest(payload):
            raise RuntimeError(f"{key} fixture copy changed")
        result[key] = {**expected, "source_commit": UPSTREAM_COMMIT, "basename": Path(expected["path"]).name, "materialized_bytes": target_size, "materialized_sha256": target_sha}
    return result


def source_identity_receipt(upstream_root: Path) -> dict[str, Any]:
    """Hash the extracted upstream package independently of the child probe."""
    package = upstream_root / "src" / "agent_com"
    if is_reparse_point(package) or not package.is_dir():
        raise ValueError("upstream source package is not a regular directory")
    entries: list[dict[str, Any]] = []
    for path in sorted(package.rglob("*.py"), key=lambda item: item.as_posix()):
        if is_reparse_point(path) or not path.is_file():
            raise ValueError("upstream source inventory contains a non-regular file")
        size, sha = bounded_file_digest(path, MAX_SOURCE_FILE_BYTES)
        entries.append({"path": path.relative_to(upstream_root).as_posix(), "bytes": size, "sha256": sha})
    if not entries:
        raise ValueError("upstream source inventory is empty")
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    init_path = package / "__init__.py"
    init_bytes, init_sha = bounded_file_digest(init_path, MAX_SOURCE_FILE_BYTES)
    return {
        "package_source_inventory": {
            "count": len(entries),
            "total_bytes": sum(item["bytes"] for item in entries),
            "sha256": digest(canonical),
        },
        "module_file": {
            "relative_path": "src/agent_com/__init__.py",
            "basename": "__init__.py",
            "bytes": init_bytes,
            "sha256": init_sha,
            "root_contained": True,
            "path_redacted": True,
        },
    }


def fixture_post_receipts(upstream_root: Path, inputs: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, expected in FIXTURE_EXPECTED.items():
        source = upstream_root / expected["path"]
        target = inputs / ("pinned-workbook.xlsx" if key == "workbook" else "pinned-channel.s4p")
        source_bytes, source_sha = bounded_file_digest(source, MAX_MEMBER_BYTES)
        target_bytes, target_sha = bounded_file_digest(target, MAX_MEMBER_BYTES)
        result[key] = {
            "source_bytes": source_bytes,
            "source_sha256": source_sha,
            "materialized_bytes": target_bytes,
            "materialized_sha256": target_sha,
        }
    return result


def archive_post_receipts(candidate_tar: Path, upstream_tar: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, archive_path in (("candidate", candidate_tar), ("upstream", upstream_tar)):
        size, sha = bounded_file_digest(archive_path, MAX_MEMBER_BYTES * 8)
        result[key] = {"bytes": size, "sha256": sha, "path_redacted": True}
    return result


def compare_case(upstream: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    upstream_metrics = upstream.get("metrics", {})
    candidate_metrics = candidate.get("metrics", {})
    metric_delta: dict[str, float | None] = {}
    for key in METRIC_KEYS:
        left, right = upstream_metrics.get(key), candidate_metrics.get(key)
        metric_delta[key] = None if left is None or right is None else abs(float(left) - float(right))
    uw = upstream.get("winner", {})
    cw = candidate.get("winner", {})
    upstream_port_order = upstream.get("port_order", PORT_ORDER)
    candidate_port_order = candidate.get("port_order")
    port_order_observed = candidate_port_order is not None
    port_order_match = port_order_observed and candidate_port_order == upstream_port_order == PORT_ORDER
    return {
        "port_order_match": port_order_match,
        "port_order_observed": port_order_observed,
        "port_order_status": "observed" if port_order_observed else "not_observed",
        "cursor_index_match": uw.get("cursor_index") == cw.get("cursor_index"),
        "sigma_n_v_abs_delta": None if uw.get("sigma_n_v") is None or cw.get("sigma_n_v") is None else abs(float(uw["sigma_n_v"]) - float(cw["sigma_n_v"])),
        "fom_db_abs_delta": None if uw.get("fom_db") is None or cw.get("fom_db") is None else abs(float(uw["fom_db"]) - float(cw["fom_db"])),
        "metric_abs_delta": metric_delta,
        "dfe": {"upstream_published": bool(uw.get("dfe_published")), "candidate_published": bool(cw.get("dfe_published")), "status": "candidate_missing" if uw.get("dfe_published") and not cw.get("dfe_published") else "observed"},
        "array_receipts": {"upstream": upstream.get("arrays", {}), "candidate": candidate.get("arrays", {})},
    }


def formal_upstream_success(value: Any) -> bool:
    """Return true only for the single clean UV execution accepted by v5."""
    if not isinstance(value, dict) or value.get("runtime") != "executed_clean_archive_uv" or value.get("exit") != 0 or value.get("blocker") is not None or not isinstance(value.get("cases"), list) or len(value["cases"]) != 2:
        return False
    attempts = value.get("attempts")
    if not isinstance(attempts, list) or len(attempts) != 1:
        return False
    attempt = attempts[0]
    if not isinstance(attempt, dict) or attempt.get("method") != "uv_offline" or attempt.get("command") != UPSTREAM_UV_COMMAND or attempt.get("exit") != 0 or attempt.get("blocker") is not None:
        return False
    if value.get("stdout_sha256") != attempt.get("stdout_sha256") or value.get("stderr_sha256") != attempt.get("stderr_sha256") or value.get("stdout_bytes") != attempt.get("stdout_bytes") or value.get("stderr_bytes") != attempt.get("stderr_bytes"):
        return False
    artifact = value.get("artifact")
    return isinstance(artifact, dict) and artifact.get("bytes") == value.get("stdout_bytes") and artifact.get("sha256") == value.get("stdout_sha256")


def run_one(repo: Path, upstream_repo: Path, scratch_root: Path, cargo: Path, python: Path, run_id: str, nonce: str, uv: Path | None = None, rustc: Path | None = None) -> dict[str, Any]:
    token(run_id)
    token(nonce)
    if run_id == nonce:
        raise ValueError("run_id and nonce must be distinct")
    scratch = fresh_scratch_root(scratch_root, run_id, nonce)
    candidate_tar = scratch_root / "candidate.tar"
    upstream_tar = scratch_root / "upstream.tar"
    candidate_size, candidate_sha = archive(repo, CANDIDATE_COMMIT, candidate_tar, {"bytes": CANDIDATE_ARCHIVE_BYTES, "sha256": CANDIDATE_ARCHIVE_SHA256})
    upstream_size, upstream_sha = archive(upstream_repo, UPSTREAM_COMMIT, upstream_tar, {"bytes": UPSTREAM_ARCHIVE_BYTES, "sha256": UPSTREAM_ARCHIVE_SHA256})
    candidate_root = scratch_root / "candidate"
    upstream_root = scratch_root / "upstream"
    extract(candidate_tar, candidate_root)
    extract(upstream_tar, upstream_root)
    upstream_source_pre = source_identity_receipt(upstream_root)
    fixtures = fixture_receipts(upstream_root, candidate_root / "inputs")
    resolved_cargo = resolve_executable(cargo)
    resolved_rustc = resolve_executable(rustc if rustc is not None else resolved_cargo.with_name("rustc.exe"))
    resolved_python = resolve_executable(python)
    resolved_uv = resolve_executable(uv) if uv is not None else None
    toolchain = {
        "cargo": tool_identity("cargo", resolved_cargo, ["--version"]),
        "rustc": tool_identity("rustc", resolved_rustc, ["--version"]),
        "python": tool_identity("python", resolved_python, ["--version"]),
        "uv": tool_identity("uv", resolved_uv, ["--version"]) if resolved_uv is not None else None,
    }
    build, binary, environment = run_candidate_build(candidate_root, resolved_cargo, resolved_rustc, scratch_root / "candidate-target")
    controls: list[dict[str, Any]] = []
    blockers: list[str] = []
    for index, vector in enumerate(CONTROL_VECTORS):
        upstream = run_upstream_probe(upstream_root, resolved_python, list(vector), timeout=600, uv=resolved_uv, source_identity=upstream_source_pre)
        candidate = run_candidate_probe(candidate_root, binary, environment, list(vector), index)
        comparison: list[dict[str, Any]] = []
        if "cases" in upstream and "cases" in candidate:
            for left, right in zip(upstream["cases"], candidate["cases"]):
                comparison.append(compare_case(left, right))
        controls.append({"vector": list(vector), "upstream": upstream, "candidate": candidate, "comparison": comparison})
    fixture_post = fixture_post_receipts(upstream_root, candidate_root / "inputs")
    expected_fixture_post = {
        key: {
            "source_bytes": expected["bytes"],
            "source_sha256": expected["sha256"],
            "materialized_bytes": expected["bytes"],
            "materialized_sha256": expected["sha256"],
        }
        for key, expected in FIXTURE_EXPECTED.items()
    }
    if fixture_post != expected_fixture_post:
        blockers.append("fixture_identity_drift")
    upstream_source_post = source_identity_receipt(upstream_root)
    if upstream_source_post != upstream_source_pre:
        blockers.append("upstream_source_identity_drift")
    scratch_post = scratch_post_receipt(scratch_root, scratch)
    archive_post = archive_post_receipts(candidate_tar, upstream_tar)
    expected_archive_post = {
        "candidate": {"bytes": candidate_size, "sha256": candidate_sha, "path_redacted": True},
        "upstream": {"bytes": upstream_size, "sha256": upstream_sha, "path_redacted": True},
    }
    if archive_post != expected_archive_post:
        blockers.append("archive_identity_drift")
    toolchain_post = {
        "cargo": tool_identity("cargo", resolved_cargo, ["--version"]),
        "rustc": tool_identity("rustc", resolved_rustc, ["--version"]),
        "python": tool_identity("python", resolved_python, ["--version"]),
        "uv": tool_identity("uv", resolved_uv, ["--version"]) if resolved_uv is not None else None,
    }
    toolchain_stable = toolchain == toolchain_post
    binary_post = None
    if binary.is_file() and not is_reparse_point(binary):
        binary_bytes, binary_sha = bounded_file_digest(binary, MAX_MEMBER_BYTES * 8)
        binary_post = {"basename": binary.name, "bytes": binary_bytes, "sha256": binary_sha, "path_redacted": True}
    build["binary_post"] = binary_post
    build["binary_stable"] = binary_post is not None and build.get("binary_pre") == binary_post
    if not build["binary_stable"]:
        blockers.append("candidate_binary_identity_drift")
    if not toolchain_stable:
        blockers.append("toolchain_identity_drift")
    upstream_ok = all(formal_upstream_success(item["upstream"]) for item in controls)
    candidate_ok = all(item["candidate"].get("consumer_proof") is True for item in controls)
    if not upstream_ok:
        for item in controls:
            upstream = item["upstream"]
            if not formal_upstream_success(upstream):
                blockers.append("upstream_formal_uv_runtime_not_proven")
                if "cases" not in upstream:
                    blockers.append(upstream.get("upstream_runtime_blocker", "upstream_runtime_unavailable"))
    if not candidate_ok:
        blockers.extend(item["candidate"].get("blocker", "candidate_runtime_unavailable") for item in controls if not item["candidate"].get("consumer_proof"))
    if upstream_ok and candidate_ok and any(compare.get("dfe", {}).get("status") == "candidate_missing" for item in controls for compare in item["comparison"]):
        blockers.append("candidate_dfe_taps_not_published")
    status = "scoped_mismatch_observed" if upstream_ok and candidate_ok else "blocked"
    return {
        "schema": "sipi.com.workbook-accm-replay.v5.diagnostic",
        "run_id": run_id,
        "nonce": nonce,
        "candidate": {"commit": CANDIDATE_COMMIT, "tree": CANDIDATE_TREE, "archive": {"bytes": candidate_size, "sha256": candidate_sha, "command": "git -c core.autocrlf=false archive --format=tar <candidate>"}},
        "upstream": {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE, "archive": {"bytes": upstream_size, "sha256": upstream_sha, "command": "git -c core.autocrlf=false archive --format=tar <upstream>"}},
        "fixtures": fixtures,
        "fixture_post": fixture_post,
        "upstream_source_pre": upstream_source_pre,
        "upstream_source_post": upstream_source_post,
        "archive_post": archive_post,
        "port_order": {"source_key": "Port Order", "source_cell": "COM_Settings!G7", "one_based": PORT_ORDER},
        "toolchain": toolchain,
        "toolchain_post": toolchain_post,
        "toolchain_stable": toolchain_stable,
        "scratch": scratch,
        "scratch_post": scratch_post,
        "build": build,
        "controls": controls,
        "status": status,
        "matched": False,
        "acceptance": False,
        "blockers": sorted(set(blockers)),
        "non_claims": ["no S-parameter fit", "channel uses one final FD-to-TD impulse", "no upstream or global numeric parity", "no release or promotion claim", "candidate DFE publication is not inferred from hidden state"],
    }


def assert_report_path_free(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert_report_path_free(key)
            assert_report_path_free(item)
    elif isinstance(value, list):
        for item in value:
            assert_report_path_free(item)
    elif isinstance(value, str):
        normalized = value.replace("\\", "/")
        if PATH_LEAK.search(normalized) or normalized.startswith(("/", "../")) or "file://" in normalized.lower():
            raise ValueError("absolute path leaked into report")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--uv", type=Path)
    parser.add_argument("--run-id", default=secrets.token_hex(32))
    parser.add_argument("--nonce", default=secrets.token_hex(32))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = run_one(args.repo, args.upstream_repo, args.scratch_root, args.cargo, args.python, args.run_id, args.nonce, uv=args.uv, rustc=args.rustc)
    assert_report_path_free(result)
    if args.report.exists():
        raise FileExistsError("report path already exists")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "run_id": result["run_id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
