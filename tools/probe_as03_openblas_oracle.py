"""Probe AS-03 conversion bits against the pinned NumPy/scikit-rf runtime.

This is a diagnostic-only corpus. It instruments a temporary Git archive with
one private Rust test, so the production solver, CLI, PLAN, and ledger are not
changed. It intentionally does not run the residue least-squares fitter.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
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
UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
SCIKIT_RF_COMMIT = "bd651e923cac6020de49a096e1d7e9b5f949f884"
SCIKIT_RF_TREE = "e01dc798d1ba119357cc41e96802ac9aca83b9bc"
SCIKIT_RF_SOURCE = {
    "skrf/network.py": ("be5a55e367628b888a39376b693e7a5368df45a9", 291611, "62d5bd5434eb4f2bb6fef2262dd02fac828f93b9742f7c900920fbf313c8b759"),
    "skrf/mathFunctions.py": ("ad356cd00d90799ed483d4efeff83bcffeb3674f", 32637, "7ff864b104b672ddcbd06b5fe7c6d6806040827b2d156732948d58a671010462"),
}
CANDIDATE_SOURCE = "crates/sipi-agent-spice-direct/src/as03_fit_yparam.rs"
UPSTREAM_SOURCES = (
    "src/agent_spice/sparam/yparam.py",
    "src/agent_spice/sparam/native_vf.py",
)
RUNNER_RELATIVE = "tools/probe_as03_openblas_oracle.py"
CASE_SCHEMA = "sipi.as-03-openblas-oracle-cases.v1"
REPORT_SCHEMA = "sipi.as-03-openblas-oracle-corpus.v1"
RUST_MARKER = "AS03_OPENBLAS_ORACLE_RUST_V1="
PYTHON_MARKER = "AS03_OPENBLAS_ORACLE_NUMPY_V1="
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX16 = re.compile(r"^[0-9a-f]{16}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
GIT_EXE = "git"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _bits(value: float) -> str:
    return struct.pack(">d", float(value)).hex()


def _unbits(value: str) -> float:
    if HEX16.fullmatch(value) is None:
        raise RuntimeError("invalid f64 bits")
    return struct.unpack(">d", bytes.fromhex(value))[0]


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


def _regular(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    info = resolved.stat()
    if _has_reparse_component(path) or not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"{label} must be a regular file")
    return resolved


def _regular_single_link(path: Path, label: str) -> Path:
    resolved = _regular(path, label)
    if resolved.stat().st_nlink != 1:
        raise RuntimeError(f"{label} must be a single-link file")
    return resolved


def _repo(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    if _has_reparse_component(path) or _has_reparse_component(resolved / ".git") or not resolved.is_dir() or not (resolved / ".git").exists():
        raise RuntimeError(f"{label} repository custody failed")
    return resolved


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
        raise RuntimeError("git object operation failed")
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
        if _has_reparse_component(child) or (resolved != root and root not in resolved.parents):
            raise RuntimeError("materialized archive escaped")
        if child.is_file() and resolved.stat().st_nlink != 1:
            raise RuntimeError("materialized archive contains linked file")
    return {"sha256": _sha(payload), "bytes": len(payload), "links_rejected": True}


def _resolve_tool(raw: str, label: str) -> Path:
    literal = Path(raw)
    found = literal if literal.is_file() else Path(shutil.which(raw) or "")
    if not found:
        raise RuntimeError(f"{label} executable not found")
    return _regular(found, label)


def _tool_snapshot(path: Path, role: str, args: tuple[str, ...]) -> dict[str, Any]:
    result = _bounded_process([str(path), *args], cwd=ROOT, env=dict(os.environ), timeout=60, stdout_limit=1024 * 1024, stderr_limit=1024 * 1024)
    if result.returncode != 0:
        raise RuntimeError(f"{role} identity failed")
    return {
        "role": role,
        "executable": path.name,
        "path_redacted": True,
        "file_sha256": _sha(path.read_bytes()),
        "version_sha256": _sha(result.stdout + b"\0" + result.stderr),
        "version_exit": 0,
    }


def _exact_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(_exact_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_exact_equal(a, b) for a, b in zip(left, right, strict=True))
    return bool(left == right)


def _tool_identity(pre: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
    if not _exact_equal(pre, post):
        raise RuntimeError(f"{pre.get('role', 'tool')} identity drift")
    return {"role": pre["role"], "pre": pre, "post": post, "pre_post_equal": True}


def _runtime_env(cargo: Path, rustc: Path, target: Path, cases: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in tuple(env):
        if key in {"RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS"} or key.startswith("CARGO_BUILD_"):
            env.pop(key, None)
    env.update(
        {
            "CARGO": str(cargo),
            "RUSTC": str(rustc),
            "CARGO_TARGET_DIR": str(target),
            "CARGO_NET_OFFLINE": "true",
            "CARGO_INCREMENTAL": "0",
            "AS03_OPENBLAS_CASES": str(cases),
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "PYTHONHASHSEED": "0",
        }
    )
    return env


def _module_snapshot(python: Path, env: dict[str, str]) -> dict[str, Any]:
    script = r'''import hashlib,json,platform,sys
from pathlib import Path
import numpy as np
import scipy
import skrf
import numpy.linalg._umath_linalg as umath

site=Path(np.__file__).resolve().parent.parent
def fact(module, role):
    p=Path(module.__file__).resolve()
    return {"role":role,"relative_path":p.relative_to(site).as_posix(),"basename":p.name,"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"version":module.__version__}
def file_fact(p, role):
    p=Path(p).resolve()
    return {"role":role,"relative_path":p.relative_to(site).as_posix(),"basename":p.name,"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
cfg=np.show_config(mode="dicts")
bd=cfg.get("Build Dependencies",{})
def blas_fact(name):
    value=bd.get(name,{})
    return {"name":value.get("name"),"version":value.get("version"),"openblas_configuration":value.get("openblas configuration")}
openblas=[]
for directory in (site/"numpy.libs",site/"scipy.libs"):
    if directory.is_dir():
        for p in sorted(directory.glob("*openblas*.dll")):
            openblas.append(file_fact(p,"openblas_dll"))
skrf_root=Path(skrf.__file__).resolve().parent
result={
 "python":{"version":platform.python_version(),"implementation":platform.python_implementation()},
 "modules":{"numpy":fact(np,"numpy"),"scipy":fact(scipy,"scipy"),"skrf":fact(skrf,"scikit-rf"),"numpy_linalg":file_fact(umath.__file__,"numpy_linalg")},
 "scikit_rf_sources":{"network":file_fact(skrf_root/"network.py","scikit-rf_source"),"mathFunctions":file_fact(skrf_root/"mathFunctions.py","scikit-rf_source")},
 "scikit_rf_git_checkout_present":(skrf_root.parent/".git").exists(),
 "openblas":{"blas":blas_fact("blas"),"lapack":blas_fact("lapack"),"files":openblas},
 "cpu_dispatch":cfg.get("SIMD Extensions",{}),
 "machine":{"system":platform.system(),"release":platform.release(),"machine":platform.machine()},
 "thread_environment":{name:__import__("os").environ.get(name) for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS")},
}
print("AS03_OPENBLAS_RUNTIME_V1="+json.dumps(result,sort_keys=True,separators=(",",":")))'''
    result = _bounded_process([str(python), "-I", "-c", script], cwd=ROOT, env=env, timeout=60, stdout_limit=4 * 1024 * 1024, stderr_limit=2 * 1024 * 1024)
    if result.returncode != 0:
        raise RuntimeError("Python runtime snapshot failed")
    lines = [line for line in result.stdout.decode("utf-8", errors="strict").splitlines() if line.startswith("AS03_OPENBLAS_RUNTIME_V1=")]
    if len(lines) != 1:
        raise RuntimeError("Python runtime marker missing or ambiguous")
    value = json.loads(lines[0].split("=", 1)[1])
    _assert_no_absolute(value)
    return value


def _matrix_bits(matrix: list[complex]) -> list[dict[str, str]]:
    return [{"re_bits": _bits(value.real), "im_bits": _bits(value.imag)} for value in matrix]


def _case_matrix(n: int, category: str) -> list[complex]:
    values: list[complex] = []
    for row in range(n):
        for column in range(n):
            diagonal = row == column
            real = (1.25 if diagonal else 0.004 / (1.0 + abs(row - column))) + 0.001 * math.sin((row + 1) * (column + 2))
            imag = 0.002 * math.cos((row + 2) * (column + 1))
            values.append(complex(real, imag))
    if category == "pivot" and n > 1:
        values[0] = complex(1.0e-3, 1.0e-2)
        values[n] = complex(0.65, 0.18)
        values[1] = complex(0.25, -0.11)
    elif category == "near_singular":
        values[0] = complex(1.0e-8, 2.0e-9)
        if n > 1:
            values[1] = complex(2.0e-5, -1.0e-5)
            values[n] = complex(1.0e-5, 1.0e-5)
    return [value - (1.0 if index // n == index % n else 0.0) for index, value in enumerate(values)]


def make_cases() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for n in (1, 2, 3, 4, 8, 16, 32):
        for category in ("well_conditioned", "pivot", "near_singular"):
            matrix = _case_matrix(n, category)
            cases.append(
                {
                    "id": f"n{n:02d}-{category}",
                    "n": n,
                    "category": category,
                    "z0_bits": _bits(50.0),
                    "condition_limit_bits": _bits(1.0e12),
                    "s_bits": _matrix_bits(matrix),
                }
            )
    return {"schema": CASE_SCHEMA, "dimensions": [1, 2, 3, 4, 8, 16, 32], "cases": cases}


def _python_oracle_script() -> str:
    return r'''import json,struct,sys
from pathlib import Path
import numpy as np
MARKER="AS03_OPENBLAS_ORACLE_NUMPY_V1="
def unpack(bits): return struct.unpack(">d",bytes.fromhex(bits))[0]
def pack(value): return struct.pack(">d",float(value)).hex()
def matrix_bits(value): return [{"re_bits":pack(item.real),"im_bits":pack(item.imag)} for item in value.reshape(-1)]
document=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
outputs=[]
for case in document["cases"]:
 n=int(case["n"])
 s=np.array([complex(unpack(item["re_bits"]),unpack(item["im_bits"])) for item in case["s_bits"]],dtype=np.complex128).reshape((n,n))
 z0=unpack(case["z0_bits"])
 identity=np.eye(n,dtype=np.complex128)
 g=z0*identity
 f=(1.0/(2.0*np.sqrt(z0)))*identity
 a=(s@g+np.conj(g))@f
 b=(identity-s)@f
 condition=float(np.linalg.cond(identity+s))
 try:
  solved=np.linalg.solve(a,b)
  outputs.append({"id":case["id"],"n":n,"status":"accepted","condition_bits":pack(condition),"matrix_bits":matrix_bits(solved)})
 except np.linalg.LinAlgError:
  outputs.append({"id":case["id"],"n":n,"status":"solve_error","condition_bits":pack(condition),"matrix_bits":[]})
print(MARKER+json.dumps({"schema":"sipi.as-03-openblas-oracle-python.v1","cases":outputs},sort_keys=True,separators=(",",":")))'''


RUST_PROBE_SUFFIX = r'''
 
    #[test]
    fn as03_openblas_oracle_corpus_probe_v1() {
        use serde_json::json;
        let path = std::env::var("AS03_OPENBLAS_CASES").unwrap();
        let document: Value = serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();
        let cases = document["cases"].as_array().unwrap();
        let mut outputs = Vec::with_capacity(cases.len());
        for case in cases {
            let n = case["n"].as_u64().unwrap() as usize;
            let bits = |value: &Value| u64::from_str_radix(value.as_str().unwrap(), 16).unwrap();
            let z0 = f64::from_bits(bits(&case["z0_bits"]));
            let limit = f64::from_bits(bits(&case["condition_limit_bits"]));
            let sample = case["s_bits"]
                .as_array()
                .unwrap()
                .iter()
                .map(|cell| Complex::new(
                    f64::from_bits(bits(&cell["re_bits"])),
                    f64::from_bits(bits(&cell["im_bits"])),
                ))
                .collect::<Vec<_>>();
            let result = convert_s_to_y(&sample, n, z0, limit);
            match result {
                Ok((matrix, condition)) => outputs.push(json!({
                    "id": case["id"],
                    "n": n,
                    "status": "accepted",
                    "condition_bits": format!("{:016x}", condition.to_bits()),
                    "matrix_bits": matrix.iter().map(|value| json!({
                        "re_bits": format!("{:016x}", value.re.to_bits()),
                        "im_bits": format!("{:016x}", value.im.to_bits()),
                    })).collect::<Vec<_>>(),
                })),
                Err(_) => outputs.push(json!({
                    "id": case["id"],
                    "n": n,
                    "status": "conversion_error",
                    "condition_bits": Value::Null,
                    "matrix_bits": [],
                })),
            }
        }
        println!("AS03_OPENBLAS_ORACLE_RUST_V1={}", json!({
            "schema": "sipi.as-03-openblas-oracle-rust.v1",
            "cases": outputs,
        }));
    }
'''


def _parse_marker(stdout: bytes, marker: str) -> dict[str, Any]:
    lines = [line for line in stdout.decode("utf-8", errors="strict").splitlines() if line.startswith(marker)]
    if len(lines) != 1:
        raise RuntimeError("probe marker missing or ambiguous")
    value = json.loads(lines[0][len(marker):])
    if not isinstance(value, dict):
        raise RuntimeError("probe marker payload malformed")
    return value


def _run(command: list[str], cwd: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[bytes]:
    result = _bounded_process(command, cwd=cwd, env=env, timeout=timeout, stdout_limit=16 * 1024 * 1024, stderr_limit=16 * 1024 * 1024)
    if result.returncode != 0:
        raise RuntimeError(f"execution failed: {Path(command[0]).name}")
    return result


def _summary(result: subprocess.CompletedProcess[bytes]) -> dict[str, Any]:
    return {
        "exit_code": result.returncode,
        "stdout_sha256": _sha(result.stdout),
        "stdout_bytes": len(result.stdout),
        "stderr_sha256": _sha(result.stderr),
        "stderr_bytes": len(result.stderr),
        "output_limit_bytes": 16 * 1024 * 1024,
    }


def _ordered_map(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for item in value.get("cases", []):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item["id"] in result:
            raise RuntimeError("duplicate or malformed case result")
        result[item["id"]] = item
    return result


def _ulp_distance(left_bits: str, right_bits: str) -> int:
    left, right = int(left_bits, 16), int(right_bits, 16)
    sign = 1 << 63
    mask = (1 << 64) - 1
    left_ordered = ((~left) & mask) if left & sign else left | sign
    right_ordered = ((~right) & mask) if right & sign else right | sign
    return abs(left_ordered - right_ordered)


def compare_outputs(cases: dict[str, Any], oracle: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    expected = {item["id"]: item for item in cases["cases"]}
    oracle_map, candidate_map = _ordered_map(oracle), _ordered_map(candidate)
    if set(oracle_map) != set(expected) or set(candidate_map) != set(expected):
        raise RuntimeError("probe case set drift")
    per_case: list[dict[str, Any]] = []
    first_difference: dict[str, Any] | None = None
    max_ulp = 0
    exact_cases = 0
    matrix_cells = 0
    exact_cells = 0
    for case_id in expected:
        left, right = oracle_map[case_id], candidate_map[case_id]
        if left.get("n") != right.get("n") or left.get("status") != right.get("status"):
            per_case.append({"id": case_id, "status_match": False, "matrix_bit_exact": False, "differing_components": 0, "max_ulp": None})
            if first_difference is None:
                first_difference = {"case_id": case_id, "kind": "status", "oracle": left.get("status"), "candidate": right.get("status")}
            continue
        differences = 0
        case_max = 0
        oracle_matrix, candidate_matrix = left.get("matrix_bits"), right.get("matrix_bits")
        if not isinstance(oracle_matrix, list) or not isinstance(candidate_matrix, list) or len(oracle_matrix) != len(candidate_matrix):
            differences = 1
        else:
            for index, (oracle_cell, candidate_cell) in enumerate(zip(oracle_matrix, candidate_matrix, strict=True)):
                for component in ("re_bits", "im_bits"):
                    matrix_cells += 1
                    oracle_bits, candidate_bits = oracle_cell.get(component), candidate_cell.get(component)
                    if oracle_bits == candidate_bits:
                        exact_cells += 1
                        continue
                    differences += 1
                    ulp = _ulp_distance(oracle_bits, candidate_bits)
                    case_max = max(case_max, ulp)
                    max_ulp = max(max_ulp, ulp)
                    if first_difference is None:
                        oracle_value, candidate_value = _unbits(oracle_bits), _unbits(candidate_bits)
                        first_difference = {
                            "case_id": case_id,
                            "row": index // int(expected[case_id]["n"]),
                            "column": index % int(expected[case_id]["n"]),
                            "component": component.removesuffix("_bits"),
                            "oracle_bits": oracle_bits,
                            "candidate_bits": candidate_bits,
                            "oracle": repr(oracle_value),
                            "candidate": repr(candidate_value),
                            "delta": repr(candidate_value - oracle_value),
                            "ulp": ulp,
                        }
        exact = differences == 0
        if exact:
            exact_cases += 1
        per_case.append({"id": case_id, "status_match": True, "matrix_bit_exact": exact, "differing_components": differences, "max_ulp": case_max})
    return {
        "case_count": len(expected),
        "dimensions": cases["dimensions"],
        "matrix_cells": matrix_cells,
        "exact_matrix_cells": exact_cells,
        "exact_case_count": exact_cases,
        "matrix_bit_exact": exact_cells == matrix_cells and matrix_cells > 0,
        "max_ulp": max_ulp,
        "first_difference": first_difference,
        "per_case": per_case,
    }


def _assert_no_absolute(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_no_absolute(key)
            _assert_no_absolute(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_absolute(item)
    elif isinstance(value, str) and re.search(r"(?:^[A-Za-z]:[\\/]|^//|^/)", value):
        raise RuntimeError("report contains an absolute path")


def _source_match(fact: dict[str, Any], expected: tuple[str, int, str]) -> bool:
    return (fact.get("bytes"), fact.get("sha256")) == (expected[1], expected[2])


def validate_report(report: Any) -> list[str]:
    blockers: list[str] = []
    if not isinstance(report, dict) or report.get("schema") != REPORT_SCHEMA:
        return ["report schema"]
    for key, expected in (("status", "diagnostic_only_numeric_parity_open"), ("integrity_gate", "passed")):
        if report.get(key) != expected:
            blockers.append(f"report {key}")
    if report.get("parity_claim") is not False or report.get("numeric_parity") is not False:
        blockers.append("report claims")
    corpus = report.get("corpus")
    if not isinstance(corpus, dict) or corpus.get("schema") != CASE_SCHEMA or corpus.get("dimensions") != [1, 2, 3, 4, 8, 16, 32] or not isinstance(corpus.get("cases"), list) or len(corpus["cases"]) != 21:
        blockers.append("corpus shape")
    if isinstance(corpus, dict):
        seen: set[str] = set()
        for case in corpus.get("cases", []):
            if not isinstance(case, dict) or not isinstance(case.get("id"), str) or case["id"] in seen or not isinstance(case.get("s_bits"), list):
                blockers.append("corpus case")
                break
            seen.add(case["id"])
            if any(not isinstance(cell, dict) or not isinstance(cell.get("re_bits"), str) or not isinstance(cell.get("im_bits"), str) or HEX16.fullmatch(cell["re_bits"]) is None or HEX16.fullmatch(cell["im_bits"]) is None for cell in case["s_bits"]):
                blockers.append("corpus f64 bits")
                break
    comparison = report.get("comparison")
    if not isinstance(comparison, dict) or comparison.get("case_count") != 21 or not isinstance(comparison.get("per_case"), list) or len(comparison["per_case"]) != 21:
        blockers.append("comparison shape")
    runtime = report.get("runtime")
    if not isinstance(runtime, dict) or not isinstance(runtime.get("modules"), dict) or not isinstance(runtime.get("openblas"), dict):
        blockers.append("runtime shape")
    try:
        _assert_no_absolute(report)
    except RuntimeError:
        blockers.append("absolute path leakage")
    return blockers


def _run_candidate_probe(candidate_root: Path, env: dict[str, str], cargo: Path, timeout: int) -> subprocess.CompletedProcess[bytes]:
    manifest = candidate_root / "crates/sipi-agent-spice-direct/Cargo.toml"
    return _run([str(cargo), "test", "--offline", "--locked", "--manifest-path", str(manifest), "--lib", "as03_openblas_oracle_corpus_probe_v1", "--", "--nocapture"], candidate_root, env, timeout)


def run(args: argparse.Namespace) -> dict[str, Any]:
    global GIT_EXE
    git = _resolve_tool(args.git, "git")
    GIT_EXE = str(git)
    cargo = _resolve_tool(args.cargo, "cargo")
    rustc = _resolve_tool(args.rustc or str(cargo.with_name("rustc.exe" if os.name == "nt" else "rustc")), "rustc")
    python = _resolve_tool(args.python, "python")
    tool_pre = {role: _tool_snapshot(path, role, version_args) for role, path, version_args in (("git", git, ("--version",)), ("cargo", cargo, ("--version",)), ("rustc", rustc, ("-Vv",)), ("python", python, ("--version",)))}
    candidate_repo, upstream_repo = _repo(args.candidate_repo, "candidate"), _repo(args.upstream_repo, "upstream")
    candidate_commit = str(_git(candidate_repo, "rev-parse", f"{args.candidate_commit}^{{commit}}"))
    candidate_tree = str(_git(candidate_repo, "rev-parse", f"{candidate_commit}^{{tree}}"))
    upstream_commit = str(_git(upstream_repo, "rev-parse", f"{args.upstream_commit}^{{commit}}"))
    upstream_tree = str(_git(upstream_repo, "rev-parse", f"{upstream_commit}^{{tree}}"))
    if upstream_commit != UPSTREAM_COMMIT or upstream_tree != UPSTREAM_TREE:
        raise RuntimeError("upstream pin mismatch")
    candidate_source = _source(candidate_repo, candidate_commit, CANDIDATE_SOURCE)
    upstream_sources = [_source(upstream_repo, upstream_commit, item) for item in UPSTREAM_SOURCES]
    report_relative = _safe_relative(args.report)
    if report_relative.parts[:2] != ("docs", "baselines"):
        raise RuntimeError("report must be under docs/baselines")
    report_path = ROOT / report_relative
    if report_path.exists() or _has_reparse_component(report_path.parent):
        raise RuntimeError("report must be create-new under a regular parent")
    cases = make_cases()
    case_payload = _canonical(cases)
    work_parent = Path(args.work_root).absolute() if args.work_root else Path(tempfile.mkdtemp(prefix="sipi-as03-openblas-parent-"))
    made_parent = args.work_root is None
    if args.work_root:
        if work_parent.exists() or not work_parent.is_absolute() or _has_reparse_component(work_parent.parent):
            raise RuntimeError("work root must be fresh, absolute, and regular")
        work_parent.mkdir()
    work_root = work_parent.resolve(strict=True)
    try:
        candidate_root, upstream_root = work_root / "candidate", work_root / "upstream"
        candidate_archive = _archive(candidate_repo, candidate_commit, candidate_root)
        upstream_archive = _archive(upstream_repo, upstream_commit, upstream_root)
        cases_path = work_root / "cases.json"
        cases_path.write_bytes(case_payload)
        _regular_single_link(cases_path, "case corpus")
        original = candidate_root / CANDIDATE_SOURCE
        original_bytes = original.read_bytes()
        if not original_bytes.endswith(b"}\n"):
            raise RuntimeError("candidate source ending drift")
        instrumented = original_bytes[:-2] + RUST_PROBE_SUFFIX.encode("ascii") + b"}\n"
        original.write_bytes(instrumented)
        target = work_root / "target"
        env = _runtime_env(cargo, rustc, target, cases_path)
        runtime_pre = _module_snapshot(python, env)
        candidate_probe = _run_candidate_probe(candidate_root, env, cargo, args.timeout_seconds)
        candidate_payload = _parse_marker(candidate_probe.stdout, RUST_MARKER)
        oracle_probe = _run([str(python), "-I", "-c", _python_oracle_script(), str(cases_path)], upstream_root, env, args.timeout_seconds)
        oracle_payload = _parse_marker(oracle_probe.stdout, PYTHON_MARKER)
        runtime_post = _module_snapshot(python, env)
        if not _exact_equal(runtime_pre, runtime_post):
            raise RuntimeError("Python module/runtime identity drift")
        runtime = {"pre": runtime_pre, "post": runtime_post, "pre_post_equal": True, **runtime_post}
        comparison = compare_outputs(cases, oracle_payload, candidate_payload)
        tool_post = {role: _tool_snapshot(path, role, version_args) for role, path, version_args in (("git", git, ("--version",)), ("cargo", cargo, ("--version",)), ("rustc", rustc, ("-Vv",)), ("python", python, ("--version",)))}
        tools = {role: _tool_identity(tool_pre[role], tool_post[role]) for role in tool_pre}
        installed_sources = runtime.get("scikit_rf_sources", {})
        source_matches = {name: _source_match(installed_sources.get(key, {}), expected) for name, key, expected in (("network.py", "network", SCIKIT_RF_SOURCE["skrf/network.py"]), ("mathFunctions.py", "mathFunctions", SCIKIT_RF_SOURCE["skrf/mathFunctions.py"]))}
        runtime["scikit_rf_pinned_leaf_matches"] = all(source_matches.values())
        runtime["scikit_rf_pinned_leaf_source_match"] = source_matches
        corpus = dict(cases)
        corpus["input_sha256"] = _sha(case_payload)
        oracle_map, candidate_map = _ordered_map(oracle_payload), _ordered_map(candidate_payload)
        for case in corpus["cases"]:
            case["oracle"] = oracle_map[case["id"]]
            case["candidate"] = candidate_map[case["id"]]
        blockers = ["residue_least_squares_not_exercised_by_s_to_y_corpus", "fit_yparam_global_numeric_parity_remains_open"]
        if not runtime["scikit_rf_pinned_leaf_matches"]:
            blockers.append("installed_scikit_rf_leaf_does_not_match_pinned_source")
        if not runtime.get("scikit_rf_git_checkout_present"):
            blockers.append("pinned_scikit_rf_git_checkout_not_present")
        if not comparison["matrix_bit_exact"]:
            blockers.append("s_to_y_cross_runtime_bits_differ")
        report = {
            "schema": REPORT_SCHEMA,
            "status": "diagnostic_only_numeric_parity_open",
            "integrity_gate": "passed",
            "parity_claim": False,
            "numeric_parity": False,
            "scope": {"workflow": "fit-yparam", "s_to_y_conversion": True, "residue_least_squares": False, "s_parameter_fit": False, "as05_xyce_xdm": False},
            "candidate": {"commit": candidate_commit, "tree": candidate_tree, "archive": candidate_archive, "source": candidate_source, "instrumentation": {"kind": "append_private_module_test_only", "suffix_sha256": _sha(RUST_PROBE_SUFFIX.encode("ascii")), "instrumented_source_sha256": _sha(instrumented), "production_source_unchanged": True}},
            "upstream": {"commit": upstream_commit, "tree": upstream_tree, "archive": upstream_archive, "sources": upstream_sources, "scikit_rf": {"commit": SCIKIT_RF_COMMIT, "tree": SCIKIT_RF_TREE, "source_map_expected": {path: {"git_blob": value[0], "bytes": value[1], "sha256": value[2]} for path, value in SCIKIT_RF_SOURCE.items()}}},
            "runtime": runtime,
            "toolchain": {**tools, "timeout_seconds": args.timeout_seconds, "stdout_limit_bytes": 16 * 1024 * 1024, "stderr_limit_bytes": 16 * 1024 * 1024},
            "execution": {"candidate_probe": _summary(candidate_probe), "numpy_oracle": _summary(oracle_probe)},
            "corpus": corpus,
            "comparison": comparison,
            "blockers": blockers,
            "non_claims": ["no_residue_fit_numeric_parity", "no_global_numeric_parity", "no_acceptance_tolerance", "no_s_parameter_fit", "no_as05_xyce_xdm", "no_product_or_release_promotion"],
            "evidence": {"runner": {"path": RUNNER_RELATIVE, "sha256": _sha((ROOT / RUNNER_RELATIVE).read_bytes())}, "fresh_processes": True, "private_probe_only": True, "paths_redacted": True},
        }
        _assert_no_absolute(report)
        errors = validate_report(report)
        if errors:
            raise RuntimeError("generated report invalid: " + ",".join(errors))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
        _regular_single_link(report_path, "report")
        return report
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
        if made_parent and work_parent.exists():
            shutil.rmtree(work_parent, ignore_errors=True)


def verify_report(path: Path) -> dict[str, Any]:
    path = _regular_single_link(path, "report")
    report = json.loads(path.read_text(encoding="utf-8"))
    blockers = validate_report(report)
    return {"valid": not blockers, "blockers": blockers, "schema": report.get("schema"), "status": report.get("status")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--candidate-commit")
    parser.add_argument("--upstream-repo", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--upstream-commit", default=UPSTREAM_COMMIT)
    parser.add_argument("--report", default="docs/baselines/as-03-openblas-oracle-corpus.v1.json")
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--cargo", default=os.environ.get("CARGO", "cargo"))
    parser.add_argument("--rustc")
    parser.add_argument("--git", default=os.environ.get("GIT", "git"))
    parser.add_argument("--python", default=str(DEFAULT_UPSTREAM / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")))
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    try:
        if args.verify is not None:
            result = verify_report(args.verify)
        else:
            if not args.candidate_commit:
                parser.error("--candidate-commit is required unless --verify is used")
            result = {"valid": True, "status": run(args)["status"]}
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, tarfile.TarError, json.JSONDecodeError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, ensure_ascii=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("valid", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
