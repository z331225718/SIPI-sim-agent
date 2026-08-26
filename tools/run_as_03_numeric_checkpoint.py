"""Run an immutable, physical AS-03 S-to-Y checkpoint without claiming parity."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UPSTREAM = ROOT.parent / "agent-spice"
GIT_EXE = "git"
UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
RUNNER_RELATIVE = "tools/run_as_03_numeric_checkpoint.py"
FIXTURE = b"# Hz S RI R 50\n1e6 0.01 0 0.8 0 0.8 0 0.01 0\n1e7 0.01 0 0.79 0 0.79 0 0.01 0\n1e8 0.01 0 0.7 0 0.7 0 0.01 0\n1e9 0.01 0 0.4 0 0.4 0 0.01 0\n"
FIXTURE_SHA = "4da06c257a0f0108e4391d65f894b6bb0d62a24a8f00f82f0f0734e061f5de70"
CANDIDATE_FILES = (
    "crates/sipi-agent-spice-direct/src/as03_fit_yparam.rs",
    "crates/sipi-agent-spice-direct/src/fit_sparam.rs",
)
UPSTREAM_FILES = (
    "src/agent_spice/sparam/yparam.py",
    "src/agent_spice/sparam/native_vf.py",
    "src/agent_spice/sparam/pole_relocation.py",
)
EXPECTED_UPSTREAM = {
    "src/agent_spice/sparam/yparam.py": ("473746afe5efb3e5117c58b446e2a7ccb3ca8872", 30937, "ca6ec999b93f78094c7ea58997676bd886130baf0bdaec04957c3c480ba5b713"),
    "src/agent_spice/sparam/native_vf.py": ("971a98924d52b9fb57738a6a729501dfda934968", 61818, "90db63aadeeb0be5c0a29b750d617079d598f0afe7c441a0398a8648daad31a6"),
    "src/agent_spice/sparam/pole_relocation.py": ("befdbbfbd3dd98a9d45ea5133e17aa3a252d50f3", 18535, "515bdc4ebaa6f1c1642ff9ebd5ebe773fae8723c59f779f496f389d38545a0a5"),
}
MARKER = "AS03_PHYSICAL_CHECKPOINT_V1="
PROBE_SUFFIX = r'''

    #[test]
    fn as03_physical_checkpoint_probe_v1() {
        use sha2::{Digest, Sha256};
        let fixture = std::env::var("AS03_CHECKPOINT_FIXTURE").unwrap();
        let fixture_path = Path::new(&fixture);
        let fixture_bytes = fs::read(fixture_path).unwrap();
        let fixture_sha256 = format!("{:x}", Sha256::digest(&fixture_bytes));
        let network = read_multiport_touchstone(fixture_path).unwrap();
        let sample = network.samples()[0].clone();
        let sample_cells = sample.iter().map(|value| json!({
            "re_bits": format!("{:016x}", value.re.to_bits()),
            "im_bits": format!("{:016x}", value.im.to_bits()),
        })).collect::<Vec<_>>();
        let (matrix, condition) = convert_s_to_y(
            &sample,
            network.ports(),
            network.reference_impedance(),
            1.0e12,
        ).unwrap();
        let cells = matrix.iter().map(|value| json!({
            "re": format!("{:.17}", value.re),
            "im": format!("{:.17}", value.im),
            "re_bits": format!("{:016x}", value.re.to_bits()),
            "im_bits": format!("{:016x}", value.im.to_bits()),
        })).collect::<Vec<_>>();
        println!("AS03_PHYSICAL_CHECKPOINT_V1={}", json!({
            "schema": "sipi.as-03-s-to-y-checkpoint.v1",
            "frequency_hz": 1_000_000u64,
            "sample_index": 0u64,
            "ports": 2u64,
            "condition": format!("{:.17}", condition),
            "matrix": cells,
            "parser_receipt": {
                "fixture_sha256": fixture_sha256,
                "fixture_bytes": fixture_bytes.len(),
                "frequency_points": network.sample_count(),
                "frequency_hz": network.frequencies_hz()[0] as u64,
                "ports": network.ports(),
                "reference_impedance_bits": format!("{:016x}", network.reference_impedance().to_bits()),
                "sample_matrix": sample_cells,
            },
        }));
    }
'''.encode("ascii")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _safe_relative(value: str | Path) -> Path:
    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw or "\0" in raw:
        raise RuntimeError("path must be non-empty and relative")
    host, posix, windows = Path(raw), PurePosixPath(raw), PureWindowsPath(raw)
    if host.is_absolute() or host.anchor or posix.is_absolute() or posix.anchor or windows.is_absolute() or windows.anchor or windows.drive or raw.startswith(("/", "\\")):
        raise RuntimeError("path must be repository-relative")
    parts = [part for part in re.split(r"[\\/]", raw) if part not in ("", ".")]
    if not parts or ".." in parts:
        raise RuntimeError("path traversal is forbidden")
    return Path(*parts)


def _has_reparse_component(path: Path) -> bool:
    current = path.absolute()
    while True:
        try:
            info = current.lstat()
        except FileNotFoundError:
            info = None
        if info is not None and (stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)):
            return True
        if current.parent == current:
            return False
        current = current.parent


def _regular_single_link(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    info = resolved.stat()
    if _has_reparse_component(path) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise RuntimeError(f"{label} must be a regular single-link file")
    return resolved


def _regular(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    info = resolved.stat()
    if _has_reparse_component(path) or not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"{label} must be a regular file")
    return resolved


def _repo(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    git_admin = resolved / ".git"
    if _has_reparse_component(path) or _has_reparse_component(git_admin) or not resolved.is_dir() or not git_admin.exists():
        raise RuntimeError(f"{label} repository custody failed")
    return resolved


def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    env = dict(os.environ)
    for key in tuple(env):
        if key in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"} or key.startswith("GIT_CONFIG_"):
            env.pop(key, None)
    result = _bounded_process(
        [GIT_EXE, "-c", "core.autocrlf=false", "-C", str(repo), *args],
        cwd=repo,
        env=env,
        timeout=300,
        stdout_limit=160 * 1024 * 1024 if binary else 1024 * 1024,
        stderr_limit=4 * 1024 * 1024,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} failed")
    return result.stdout if binary else result.stdout.decode("ascii").strip()


def _source(repo: Path, commit: str, relative: str) -> dict[str, Any]:
    relative = _safe_relative(relative).as_posix()
    blob = str(_git(repo, "rev-parse", f"{commit}:{relative}"))
    content = _git(repo, "cat-file", "blob", blob, binary=True)
    assert isinstance(content, bytes)
    return {"path": relative, "git_blob": blob, "bytes": len(content), "sha256": _sha(content)}


def _archive(repo: Path, commit: str, destination: Path) -> dict[str, Any]:
    payload = _git(repo, "archive", "--format=tar", commit, binary=True)
    assert isinstance(payload, bytes)
    destination.mkdir(exist_ok=False)
    root = destination.resolve(strict=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        members = archive.getmembers()
        seen: set[str] = set()
        for member in members:
            pure = PurePosixPath(member.name)
            if not member.name or "\\" in member.name or pure.is_absolute() or ".." in pure.parts or ":" in pure.parts[0]:
                raise RuntimeError("unsafe archive member")
            folded = member.name.casefold()
            if folded in seen or not (member.isfile() or member.isdir()) or member.issym() or member.islnk():
                raise RuntimeError("unsupported or duplicate archive member")
            seen.add(folded)
            target = (destination / Path(*pure.parts)).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError("archive member escaped")
        archive.extractall(destination, members=members)
    for child in destination.rglob("*"):
        resolved = child.resolve(strict=True)
        info = resolved.stat()
        if _has_reparse_component(child) or (resolved != root and root not in resolved.parents):
            raise RuntimeError("materialized archive escaped")
        if child.is_file() and info.st_nlink != 1:
            raise RuntimeError("materialized archive contains linked file")
    return {"sha256": _sha(payload), "bytes": len(payload)}


def _resolve_tool(raw: str, label: str) -> Path:
    literal = Path(raw)
    found = literal if literal.is_file() else Path(shutil.which(raw) or "")
    if not found:
        raise RuntimeError(f"{label} executable not found")
    return _regular(found, label)


def _bounded_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int,
    stdout_limit: int,
    stderr_limit: int,
) -> subprocess.CompletedProcess[bytes]:
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    buffers = [bytearray(), bytearray()]
    overflow: list[str] = []

    def drain(stream: Any, index: int, limit: int, label: str) -> None:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                return
            if len(buffers[index]) + len(chunk) > limit:
                overflow.append(label)
                try:
                    process.kill()
                except OSError:
                    pass
                return
            buffers[index].extend(chunk)

    threads = [
        threading.Thread(target=drain, args=(process.stdout, 0, stdout_limit, "stdout"), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, 1, stderr_limit, "stderr"), daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.wait()
        for thread in threads:
            thread.join()
        process.stdout.close()
        process.stderr.close()
        raise RuntimeError("bounded subprocess timed out") from error
    for thread in threads:
        thread.join()
    process.stdout.close()
    process.stderr.close()
    if overflow:
        raise RuntimeError(f"bounded subprocess exceeded {overflow[0]} byte limit")
    return subprocess.CompletedProcess(command, process.returncode, bytes(buffers[0]), bytes(buffers[1]))


def _tool_snapshot(path: Path, role: str, args: tuple[str, ...]) -> dict[str, Any]:
    result = _bounded_process(
        [str(path), *args], cwd=ROOT, env=dict(os.environ), timeout=60,
        stdout_limit=1024 * 1024, stderr_limit=1024 * 1024,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{role} identity failed")
    return {"role": role, "executable": path.name, "path_redacted": True, "file_sha256": _sha(path.read_bytes()), "version_sha256": _sha(result.stdout + b"\0" + result.stderr), "version_exit": 0}


def _tool_identity(pre: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
    if not _exact_equal(pre, post):
        raise RuntimeError(f"{pre.get('role', 'tool')} identity drift")
    return {"role": pre["role"], "pre": pre, "post": post, "pre_post_equal": True}


def _exact_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(_exact_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_exact_equal(a, b) for a, b in zip(left, right, strict=True))
    return bool(left == right)


def _module_snapshot(python: Path, env: dict[str, str]) -> dict[str, Any]:
    script = r'''import hashlib,json,pathlib
import numpy,skrf
def fact(module):
 p=pathlib.Path(module.__file__).resolve(strict=True)
 return {"version":module.__version__,"basename":p.name,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
print(json.dumps({"numpy":fact(numpy),"skrf":fact(skrf)},sort_keys=True,separators=(",",":")))'''
    result = _bounded_process(
        [str(python), "-I", "-c", script], cwd=ROOT, env=env, timeout=60,
        stdout_limit=1024 * 1024, stderr_limit=1024 * 1024,
    )
    if result.returncode != 0:
        raise RuntimeError("Python module identity failed")
    value = json.loads(result.stdout.decode("utf-8"))
    if type(value) is not dict or set(value) != {"numpy", "skrf"}:
        raise RuntimeError("Python module identity malformed")
    return value


def _env(cargo: Path, rustc: Path, target: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in tuple(env):
        if key in {"RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS"} or key.startswith("CARGO_BUILD_"):
            env.pop(key, None)
    env.update({"CARGO": str(cargo), "RUSTC": str(rustc), "CARGO_TARGET_DIR": str(target), "CARGO_NET_OFFLINE": "true", "CARGO_INCREMENTAL": "0"})
    return env


def _run(command: list[str], cwd: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[bytes]:
    result = _bounded_process(
        command, cwd=cwd, env=env, timeout=timeout,
        stdout_limit=8 * 1024 * 1024, stderr_limit=8 * 1024 * 1024,
    )
    if result.returncode != 0:
        raise RuntimeError(f"execution failed: {Path(command[0]).name}")
    return result


def _summary(result: subprocess.CompletedProcess[bytes]) -> dict[str, Any]:
    return {
        "exit_code": result.returncode,
        "stdout_sha256": _sha(result.stdout),
        "stdout_bytes": len(result.stdout),
        "stdout_limit_bytes": 8 * 1024 * 1024,
        "stdout_within_limit": len(result.stdout) <= 8 * 1024 * 1024,
        "stderr_sha256": _sha(result.stderr),
        "stderr_bytes": len(result.stderr),
        "stderr_limit_bytes": 8 * 1024 * 1024,
        "stderr_within_limit": len(result.stderr) <= 8 * 1024 * 1024,
    }


def _parse_marker(stdout: bytes) -> dict[str, Any]:
    lines = [line for line in stdout.decode("utf-8", errors="strict").splitlines() if MARKER in line]
    if len(lines) != 1:
        raise RuntimeError("checkpoint marker missing or ambiguous")
    value = json.loads(lines[0].split(MARKER, 1)[1])
    if type(value) is not dict:
        raise RuntimeError("checkpoint payload malformed")
    return value


def _checkpoint(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"schema", "frequency_hz", "sample_index", "ports", "condition", "matrix", "parser_receipt"}
    if set(value) != expected or value["schema"] != "sipi.as-03-s-to-y-checkpoint.v1" or type(value["frequency_hz"]) is not int or type(value["sample_index"]) is not int or type(value["ports"]) is not int or type(value["matrix"]) is not list or len(value["matrix"]) != 4:
        raise RuntimeError("checkpoint exact structure failed")
    raw = bytearray()
    for cell in value["matrix"]:
        if type(cell) is not dict or set(cell) != {"re", "im", "re_bits", "im_bits"}:
            raise RuntimeError("checkpoint cell malformed")
        for name in ("re_bits", "im_bits"):
            bits = cell[name]
            if type(bits) is not str or re.fullmatch(r"[0-9a-f]{16}", bits) is None:
                raise RuntimeError("checkpoint bits malformed")
            raw.extend(int(bits, 16).to_bytes(8, "little"))
    receipt = value["parser_receipt"]
    if type(receipt) is not dict or set(receipt) != {"fixture_sha256", "fixture_bytes", "frequency_points", "frequency_hz", "ports", "reference_impedance_bits", "sample_matrix"}:
        raise RuntimeError("parser receipt malformed")
    if any(type(receipt[key]) is not int for key in ("fixture_bytes", "frequency_points", "frequency_hz", "ports")) or type(receipt["sample_matrix"]) is not list:
        raise RuntimeError("parser receipt exact types failed")
    normalized = {"frequency_hz": value["frequency_hz"], "sample_index": value["sample_index"], "ports": value["ports"], "matrix": value["matrix"], "parser_receipt": receipt}
    return {**value, "physical_f64_le_sha256": _sha(bytes(raw)), "normalized_sha256": _sha(_canonical(normalized)), "parser_receipt_sha256": _sha(_canonical(receipt))}


def _python_probe_script() -> str:
    return r'''import hashlib,json,struct,sys
sys.path.insert(0,sys.argv[1])
import numpy as np
import skrf
n=skrf.Network(sys.argv[2])
fixture=open(sys.argv[2],"rb").read()
m=n.y[0]
cells=[]
for value in m.reshape(-1):
    cells.append({"re":format(float(value.real),".17f"),"im":format(float(value.imag),".17f"),"re_bits":struct.pack(">d",float(value.real)).hex(),"im_bits":struct.pack(">d",float(value.imag)).hex()})
sample=[]
for value in n.s[0].reshape(-1):
    sample.append({"re_bits":struct.pack(">d",float(value.real)).hex(),"im_bits":struct.pack(">d",float(value.imag)).hex()})
receipt={"fixture_sha256":hashlib.sha256(fixture).hexdigest(),"fixture_bytes":len(fixture),"frequency_points":len(n.f),"frequency_hz":int(n.f[0]),"ports":int(n.nports),"reference_impedance_bits":struct.pack(">d",float(n.z0[0,0].real)).hex(),"sample_matrix":sample}
print("AS03_PHYSICAL_CHECKPOINT_V1="+json.dumps({"schema":"sipi.as-03-s-to-y-checkpoint.v1","frequency_hz":int(n.f[0]),"sample_index":0,"ports":int(n.nports),"condition":"not_exposed","matrix":cells,"parser_receipt":receipt},sort_keys=True,separators=(",",":")))
print("AS03_MODULES_V1="+json.dumps({"numpy":{"version":np.__version__,"basename":__import__('pathlib').Path(np.__file__).name,"sha256":hashlib.sha256(open(np.__file__,'rb').read()).hexdigest()},"skrf":{"version":skrf.__version__,"basename":__import__('pathlib').Path(skrf.__file__).name,"sha256":hashlib.sha256(open(skrf.__file__,'rb').read()).hexdigest()}},sort_keys=True,separators=(",",":")))'''


def _module_marker(stdout: bytes) -> dict[str, Any]:
    prefix = "AS03_MODULES_V1="
    lines = [line for line in stdout.decode("utf-8").splitlines() if line.startswith(prefix)]
    if len(lines) != 1:
        raise RuntimeError("module identity marker missing")
    return json.loads(lines[0][len(prefix):])


def _fixture_receipt(payload: bytes) -> dict[str, Any]:
    text = payload.decode("ascii")
    lines = [line.split("!", 1)[0].strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines or [token.casefold() for token in lines[0].split()] != ["#", "hz", "s", "ri", "r", "50"]:
        raise RuntimeError("fixed fixture header drift")
    rows = [[float(token) for token in line.split()] for line in lines[1:]]
    if len(rows) != 4 or any(len(row) != 9 for row in rows):
        raise RuntimeError("fixed fixture row shape drift")
    sample_tokens = rows[0][1:]
    column_major = [complex(sample_tokens[index], sample_tokens[index + 1]) for index in range(0, 8, 2)]
    row_major = [column_major[column * 2 + row] for row in range(2) for column in range(2)]
    return {
        "fixture_sha256": _sha(payload),
        "fixture_bytes": len(payload),
        "frequency_points": len(rows),
        "frequency_hz": int(rows[0][0]),
        "ports": 2,
        "reference_impedance_bits": struct.pack(">d", 50.0).hex(),
        "sample_matrix": [
            {"re_bits": struct.pack(">d", value.real).hex(), "im_bits": struct.pack(">d", value.imag).hex()}
            for value in row_major
        ],
    }


def _comparison(candidate: dict[str, Any], upstream: dict[str, Any]) -> dict[str, Any]:
    differences: list[dict[str, Any]] = []
    for index, (left, right) in enumerate(zip(candidate["matrix"], upstream["matrix"], strict=True)):
        for part in ("re", "im"):
            if left[f"{part}_bits"] != right[f"{part}_bits"]:
                a = struct.unpack(">d", bytes.fromhex(left[f"{part}_bits"]))[0]
                b = struct.unpack(">d", bytes.fromhex(right[f"{part}_bits"]))[0]
                delta = a - b
                differences.append({"row": index // 2, "column": index % 2, "component": part, "candidate": left[part], "upstream": right[part], "delta": repr(delta), "delta_bits": struct.pack(">d", delta).hex()})
    if not differences:
        raise RuntimeError("physical checkpoints unexpectedly match")
    maximum = max(differences, key=lambda item: abs(struct.unpack(">d", bytes.fromhex(item["delta_bits"]))[0]))
    return {"first_lexicographic_difference": differences[0], "max_abs_difference": maximum, "differing_components": len(differences)}


def _assert_no_absolute(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_no_absolute(key); _assert_no_absolute(item)
    elif isinstance(value, list):
        for item in value: _assert_no_absolute(item)
    elif isinstance(value, str) and re.search(r"(?:^[A-Za-z]:[\\/]|^//|^/)", value):
        raise RuntimeError("report contains an absolute path")


def run(args: argparse.Namespace) -> dict[str, Any]:
    global GIT_EXE
    git = _resolve_tool(args.git, "git")
    GIT_EXE = str(git)
    cargo = _resolve_tool(args.cargo, "cargo")
    rustc = _resolve_tool(args.rustc or str(cargo.with_name("rustc.exe" if os.name == "nt" else "rustc")), "rustc")
    python = _resolve_tool(args.python, "python")
    tool_pre = {
        "git": _tool_snapshot(git, "git", ("--version",)),
        "cargo": _tool_snapshot(cargo, "cargo", ("--version",)),
        "rustc": _tool_snapshot(rustc, "rustc", ("-Vv",)),
        "python": _tool_snapshot(python, "python", ("--version",)),
    }
    module_pre = _module_snapshot(python, dict(os.environ))
    candidate_repo = _repo(args.candidate_repo, "candidate")
    upstream_repo = _repo(args.upstream_repo, "upstream")
    candidate_commit = str(_git(candidate_repo, "rev-parse", f"{args.candidate_commit}^{{commit}}"))
    candidate_tree = str(_git(candidate_repo, "rev-parse", f"{candidate_commit}^{{tree}}"))
    upstream_commit = str(_git(upstream_repo, "rev-parse", f"{args.upstream_commit}^{{commit}}"))
    upstream_tree = str(_git(upstream_repo, "rev-parse", f"{upstream_commit}^{{tree}}"))
    if upstream_commit != UPSTREAM_COMMIT or upstream_tree != UPSTREAM_TREE:
        raise RuntimeError("upstream pin mismatch")
    candidate_sources = [_source(candidate_repo, candidate_commit, item) for item in CANDIDATE_FILES]
    upstream_sources = [_source(upstream_repo, upstream_commit, item) for item in UPSTREAM_FILES]
    if any((item["git_blob"], item["bytes"], item["sha256"]) != EXPECTED_UPSTREAM[item["path"]] for item in upstream_sources):
        raise RuntimeError("upstream Git-object source mismatch")
    report_relative = _safe_relative(args.report)
    if report_relative.parts[:2] != ("docs", "baselines"):
        raise RuntimeError("report must be under docs/baselines")
    report_path = ROOT / report_relative
    if report_path.exists() or _has_reparse_component(report_path.parent):
        raise RuntimeError("report must be create-new under regular parent")
    work_parent = Path(args.work_root).absolute() if args.work_root else Path(tempfile.mkdtemp(prefix="sipi-as03-checkpoint-parent-"))
    made_parent = args.work_root is None
    if args.work_root:
        if work_parent.exists() or not work_parent.is_absolute() or _has_reparse_component(work_parent.parent):
            raise RuntimeError("work root must be fresh, absolute, and regular")
        work_parent.mkdir()
    work_root = work_parent.resolve(strict=True)
    for repo in (candidate_repo, upstream_repo):
        if work_root == repo or repo in work_root.parents or work_root in repo.parents:
            raise RuntimeError("work root must be external to repositories")
    try:
        candidate_root, upstream_root = work_root / "candidate", work_root / "upstream"
        candidate_archive = _archive(candidate_repo, candidate_commit, candidate_root)
        upstream_archive = _archive(upstream_repo, upstream_commit, upstream_root)
        target = work_root / "target"
        env = _env(cargo, rustc, target)
        manifest = candidate_root / "crates/sipi-agent-spice-direct/Cargo.toml"
        fixture = work_root / "line.s2p"; fixture.write_bytes(FIXTURE)
        _regular_single_link(fixture, "fixture")
        if _sha(FIXTURE) != FIXTURE_SHA: raise RuntimeError("fixture constant drift")
        parsed_fixture = _fixture_receipt(FIXTURE)
        env["AS03_CHECKPOINT_FIXTURE"] = str(fixture)
        original = candidate_root / CANDIDATE_FILES[0]
        original_bytes = original.read_bytes()
        if _sha(original_bytes) != candidate_sources[0]["sha256"] or not original_bytes.endswith(b"}\n"):
            raise RuntimeError("candidate archived probe source mismatch")
        instrumented = original_bytes[:-2] + PROBE_SUFFIX + b"}\n"
        original.write_bytes(instrumented)
        probe = _run([str(cargo), "test", "--offline", "--locked", "--manifest-path", str(manifest), "--lib", "as03_physical_checkpoint_probe_v1", "--", "--nocapture"], candidate_root, env, args.timeout_seconds)
        candidate_checkpoint = _checkpoint(_parse_marker(probe.stdout))
        upstream_probe = _run([str(python), "-I", "-c", _python_probe_script(), str(upstream_root / "src"), str(fixture)], upstream_root, env, args.timeout_seconds)
        upstream_checkpoint = _checkpoint(_parse_marker(upstream_probe.stdout))
        probe_modules = _module_marker(upstream_probe.stdout)
        if not _exact_equal(candidate_checkpoint["parser_receipt"], parsed_fixture) or not _exact_equal(upstream_checkpoint["parser_receipt"], parsed_fixture):
            raise RuntimeError("candidate/upstream parser receipt does not match runner fixture parse")
        tool_post = {
            "git": _tool_snapshot(git, "git", ("--version",)),
            "cargo": _tool_snapshot(cargo, "cargo", ("--version",)),
            "rustc": _tool_snapshot(rustc, "rustc", ("-Vv",)),
            "python": _tool_snapshot(python, "python", ("--version",)),
        }
        module_post = _module_snapshot(python, dict(os.environ))
        if not _exact_equal(probe_modules, module_post) or not _exact_equal(module_pre, module_post):
            raise RuntimeError("NumPy/scikit-rf identity drift")
        comparison = _comparison(candidate_checkpoint, upstream_checkpoint)
        anchor_payload = {"fixture_receipt": parsed_fixture, "candidate_commit": candidate_commit, "candidate_tree": candidate_tree, "upstream_commit": upstream_commit, "upstream_tree": upstream_tree, "candidate_physical": candidate_checkpoint["physical_f64_le_sha256"], "candidate_normalized": candidate_checkpoint["normalized_sha256"], "upstream_physical": upstream_checkpoint["physical_f64_le_sha256"], "upstream_normalized": upstream_checkpoint["normalized_sha256"], "comparison": comparison}
        report = {
            "schema": "sipi.as-03-numeric-physical-checkpoint.v1", "status": "blocked_numeric_semantics", "parity_claim": False, "numeric_parity": False,
            "integrity_gate": "passed", "run_id": args.run_id, "fresh_run_nonce": secrets.token_hex(32),
            "trust": {"scope": "integrity_only", "external_trust_root": False, "reciprocal_execution_anchor": True},
            "scope": {"workflow": "fit-yparam", "y_parameter_fit": True, "si_s_parameter_fit": False, "as05_xyce_xdm": False},
            "runner": {"path": RUNNER_RELATIVE, "sha256": _sha((ROOT / RUNNER_RELATIVE).read_bytes())},
            "fixture": {"kind": "fixed_touchstone_line_s2p_v1", "sha256": FIXTURE_SHA, "bytes": len(FIXTURE), "frequency_points": 4, "parsed_receipt": parsed_fixture},
            "candidate": {"commit": candidate_commit, "tree": candidate_tree, "archive": candidate_archive, "sources": candidate_sources, "instrumentation": {"kind": "append_private_module_test_only", "suffix_sha256": _sha(PROBE_SUFFIX), "instrumented_source_sha256": _sha(instrumented), "production_source_unchanged": True}},
            "upstream": {"commit": upstream_commit, "tree": upstream_tree, "archive": upstream_archive, "sources": upstream_sources},
            "toolchain": {
                "git": _tool_identity(tool_pre["git"], tool_post["git"]),
                "cargo": _tool_identity(tool_pre["cargo"], tool_post["cargo"]),
                "rustc": _tool_identity(tool_pre["rustc"], tool_post["rustc"]),
                "python": _tool_identity(tool_pre["python"], tool_post["python"]),
                "modules": {"pre": module_pre, "post": module_post, "pre_post_equal": True},
                "timeout_seconds": args.timeout_seconds,
                "stdout_limit_bytes": 8 * 1024 * 1024,
                "stderr_limit_bytes": 8 * 1024 * 1024,
            },
            "execution": {"candidate_probe": _summary(probe), "upstream_probe": _summary(upstream_probe)},
            "checkpoint": {"candidate": candidate_checkpoint, "upstream": upstream_checkpoint, "comparison": comparison, "reciprocal_anchor_sha256": _sha(_canonical(anchor_payload))},
            "blockers": ["s_to_y_operation_order_divergence_before_fit", "residue_least_squares_solver_is_faer_qr_not_numpy_lstsq", "exact_cross_runtime_float_parity_requires_numpy_lapack_or_a_new_solver"],
            "non_claims": ["no_external_trust_root", "no_global_numeric_parity", "no_acceptance_tolerance", "no_si_channel_s_parameter_fit", "no_as05_xyce_xdm", "no_product_or_release_promotion"],
            "custody": {"git_object_sources": True, "immutable_archives": True, "archive_links_rejected": True, "single_link_files": True, "work_root_external": True, "paths_redacted": True},
        }
        _assert_no_absolute(report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
        _regular_single_link(report_path, "report")
        return report
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
        if made_parent and work_parent.exists(): shutil.rmtree(work_parent, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--upstream-repo", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--upstream-commit", default=UPSTREAM_COMMIT)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--cargo", default=os.environ.get("CARGO", "cargo"))
    parser.add_argument("--git", default=os.environ.get("GIT", "git"))
    parser.add_argument("--rustc")
    parser.add_argument("--python", default=str(DEFAULT_UPSTREAM / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")))
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(json.dumps({"valid": False, "error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "run_id": result["run_id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
