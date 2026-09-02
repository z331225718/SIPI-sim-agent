"""Archive-built source replays for the bounded PyBERT PB-01 and PB-03 leaves.

PB-02's native-core corpus has its own immutable record.  This runner records
only the legacy class-pickle and Web-shaped `sim-rust` leaves, using fresh Git
archives for both the candidate and the pinned source oracle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
from pathlib import Path
from typing import Any

try:  # pragma: no cover - direct execution uses the fallback
    from . import run_pb_01_02_portable_matrix as matrix
except ImportError:  # pragma: no cover
    import run_pb_01_02_portable_matrix as matrix


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.pb-01-03-source-corpus-replay.v1"
PINNED_UPSTREAM = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
PINNED_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
PB01_FIXTURE = "crates/sipi-pybert-direct/fixtures/pb-01-legacy-nrz.yaml"
PB03_FIXTURE = "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml"
PB01_NAMES = (
    "chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h", "chnl_s", "tx_s",
    "ctle_s", "dfe_s", "tx_out_s", "ctle_out_s", "dfe_out_s", "chnl_p",
    "tx_out_p", "ctle_out_p", "dfe_out_p", "chnl_H", "tx_H", "ctle_H",
    "dfe_H", "tx_out_H", "ctle_out_H", "dfe_out_H", "tx_out",
)
PB01_RTOL, PB01_ATOL = 1.0e-6, 1.0e-7
PB03_RTOL, PB03_ATOL = 1.0e-9, 1.0e-12
PB03_EXCLUSIONS = (
    "$.input_file", "$.backend_metadata.run_id", "$.backend_metadata.engine.build",
    "$.diagnostics.events[].runId",
)


PB01_PROBE = r'''
import hashlib, json, math, pickle, sys
import numpy as np
left_path, right_path, rtol_text, atol_text = sys.argv[1:]
names = ["chnl_h","tx_out_h","ctle_out_h","dfe_out_h","chnl_s","tx_s","ctle_s","dfe_s","tx_out_s","ctle_out_s","dfe_out_s","chnl_p","tx_out_p","ctle_out_p","dfe_out_p","chnl_H","tx_H","ctle_H","dfe_H","tx_out_H","ctle_out_H","dfe_out_H","tx_out"]
rtol, atol = float(rtol_text), float(atol_text)
def fact(path):
    data=open(path,"rb").read(); return {"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
def describe(value):
    return {"module":type(value).__module__,"name":type(value).__name__}
left, right = pickle.load(open(left_path,"rb")), pickle.load(open(right_path,"rb"))
rows=[]; blockers=[]
for side, value in (("candidate",left),("oracle",right)):
    if describe(value) != {"module":"pybert.results","name":"PyBertData"}: blockers.append(side+":root_type")
    if not hasattr(value,"the_data") or not hasattr(value.the_data,"arrays"): blockers.append(side+":plot_graph")
if not blockers:
    la, ra = left.the_data.arrays, right.the_data.arrays
    if list(la) != names or list(ra) != names: blockers.append("canonical_member_order")
    for name in names:
        a, b = la.get(name), ra.get(name)
        row={"name":name}
        if name == "tx_out":
            passed = getattr(a,"shape",None)==getattr(b,"shape",None)==() and str(getattr(a,"dtype",None))==str(getattr(b,"dtype",None))=="object" and a.item() is None and b.item() is None
            row.update({"kind":"object_none","passed":passed})
        elif a is None or b is None:
            passed=False; row.update({"kind":"missing","passed":False})
        else:
            finite=bool(np.isfinite(a).all() and np.isfinite(b).all())
            shape=list(a.shape); dtype=str(a.dtype); same_schema=dtype==str(b.dtype)=="float64" and shape==list(b.shape)
            delta=float(np.max(np.abs(a-b),initial=0.0)) if same_schema else float("inf")
            scale=max(float(np.max(np.abs(a),initial=0.0)),float(np.max(np.abs(b),initial=0.0)),1.0) if same_schema else 1.0
            passed=finite and same_schema and delta <= atol+rtol*scale
            row.update({"kind":"float64","dtype":dtype,"shape":shape,"finite":finite,"max_abs":delta,"scale":scale,"tolerance":atol+rtol*scale,"passed":passed})
        if not passed: blockers.append(name+":drift")
        rows.append(row)
print(json.dumps({"candidate_artifact":fact(left_path),"oracle_artifact":fact(right_path),"root_types":{"candidate":describe(left),"oracle":describe(right)},"rows":rows,"blockers":blockers,"passed":not blockers},sort_keys=True,separators=(",",":")))
'''


PB03_PROBE = r'''
import copy, hashlib, json, math, sys
import numpy as np
left_dir,right_dir,rtol_text,atol_text=sys.argv[1:]
rtol,atol=float(rtol_text),float(atol_text)
def fact(path):
    data=open(path,"rb").read(); return {"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
def normalize(value,path="$"):
    if path in ("$.input_file","$.backend_metadata.run_id"): return "<runtime-provenance>"
    if path == "$.backend_metadata.engine.build": return "<engine-build>"
    if path == "$.diagnostics.events[].runId": return "<runtime-provenance>"
    if isinstance(value,dict): return {key:normalize(value[key],path+"."+key) for key in sorted(value)}
    if isinstance(value,list): return [normalize(item,path+"[]") for item in value]
    return value
def compare(left,right,path="$",drifts=None):
    if drifts is None: drifts=[]
    if isinstance(left,dict) and isinstance(right,dict):
        if set(left)!=set(right): drifts.append(path+":keyset"); return drifts
        for key in sorted(left): compare(left[key],right[key],path+"."+key,drifts)
    elif isinstance(left,list) and isinstance(right,list):
        if len(left)!=len(right): drifts.append(path+":length")
        else:
            for index,(a,b) in enumerate(zip(left,right,strict=True)): compare(a,b,path+"[]",drifts)
    elif isinstance(left,(int,float)) and not isinstance(left,bool) and isinstance(right,(int,float)) and not isinstance(right,bool):
        if not math.isfinite(float(left)) or not math.isfinite(float(right)) or not math.isclose(float(left),float(right),rel_tol=rtol,abs_tol=atol): drifts.append(path+":numeric")
    elif left != right: drifts.append(path+":value")
    return drifts
with open(left_dir+"/meta.json",encoding="utf-8") as stream: left_meta=json.load(stream)
with open(right_dir+"/meta.json",encoding="utf-8") as stream: right_meta=json.load(stream)
meta_drifts=compare(normalize(left_meta),normalize(right_meta))
rows=[]; array_drifts=[]
with np.load(left_dir+"/arrays.npz",allow_pickle=False) as left, np.load(right_dir+"/arrays.npz",allow_pickle=False) as right:
    if set(left.files)!=set(right.files): array_drifts.append("member_set")
    for name in sorted(set(left.files)|set(right.files)):
        if name not in left.files or name not in right.files: rows.append({"name":name,"present":False,"passed":False}); continue
        a,b=left[name],right[name]; row={"name":name,"present":True,"dtype":str(a.dtype),"shape":list(a.shape),"oracle_dtype":str(b.dtype),"oracle_shape":list(b.shape)}
        if a.dtype!=b.dtype or a.shape!=b.shape: row["passed"]=False; array_drifts.append(name+":schema")
        elif a.dtype.kind in "fc":
            finite=bool(np.isfinite(a).all() and np.isfinite(b).all()); delta=float(np.max(np.abs(a-b),initial=0.0)); scale=max(float(np.max(np.abs(a),initial=0.0)),float(np.max(np.abs(b),initial=0.0)),1.0); passed=finite and bool(np.allclose(a,b,rtol=rtol,atol=atol)); row.update({"numeric":True,"finite":finite,"max_abs":delta,"scale":scale,"tolerance":atol+rtol*scale,"passed":passed})
            if not passed: array_drifts.append(name+":payload")
        else:
            passed=bool(np.array_equal(a,b)); row.update({"numeric":False,"passed":passed})
            if not passed: array_drifts.append(name+":payload")
        rows.append(row)
print(json.dumps({"metadata":{"passed":not meta_drifts,"drifts":meta_drifts,"excluded_paths":["$.input_file","$.backend_metadata.run_id","$.backend_metadata.engine.build","$.diagnostics.events[].runId"]},"arrays":{"passed":not array_drifts,"drifts":array_drifts,"members":rows},"artifacts":{"candidate":{"meta":fact(left_dir+"/meta.json"),"arrays":fact(left_dir+"/arrays.npz")},"oracle":{"meta":fact(right_dir+"/meta.json"),"arrays":fact(right_dir+"/arrays.npz")}},"passed":not meta_drifts and not array_drifts},sort_keys=True,separators=(",",":")))
'''


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repo: Path, *args: str) -> str:
    return matrix._git(repo, *args)


def identity(repo: Path, commit: str) -> dict[str, str]:
    resolved = git(repo, "rev-parse", f"{commit}^{{commit}}")
    return {"commit": resolved, "tree": git(repo, "rev-parse", f"{resolved}^{{tree}}")}


def tracked_inventory(repo: Path, commit: str, archive_root: Path) -> dict[str, Any]:
    listed = matrix.subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "-z", commit], stdout=matrix.subprocess.PIPE, stderr=matrix.subprocess.PIPE, check=True).stdout
    rows = []
    for raw in listed.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8")
        payload, _ = matrix.secure_read(archive_root, relative, matrix.MAX_FILE_BYTES)
        rows.append({"path": relative, "bytes": len(payload), "sha256": sha256(payload)})
    return {"entries": len(rows), "sha256": sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode())}


def tool(path: str, role: str, args: tuple[str, ...]) -> tuple[Path, dict[str, Any]]:
    chosen = Path(path).expanduser() if Path(path).is_file() else Path(shutil.which(path) or "")
    if not chosen.is_file():
        raise RuntimeError(f"could not resolve {role}")
    executable = chosen.resolve(strict=True)
    # MSVC link.exe does not consistently return zero for its help switch.
    # The existing archive runner therefore identifies it by parsing its own
    # PE headers, while all executable tools use their normal version command.
    probe_args = ("/dump", "/headers", str(executable)) if role == "link" else args
    result = matrix.subprocess.run([str(executable), *probe_args], stdout=matrix.subprocess.PIPE, stderr=matrix.subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{role} version probe failed")
    return executable, {"role": role, "executable": executable.name, "file_sha256": sha256(executable.read_bytes()), "version_sha256": sha256(result.stdout + b"\0" + result.stderr), "version_exit": 0, "path_redacted": True}


def process_fact(value: dict[str, Any]) -> dict[str, Any]:
    return {"exit_code": value["exit_code"], "stdout": value["stdout_fact"], "stderr": value["stderr_fact"]}


def write_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise RuntimeError("report output already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")


def command(root: Path, label: str, args: list[str], cwd: Path, env: dict[str, str], timeout: int) -> dict[str, Any]:
    return matrix._capture_command(args, cwd=cwd, env=env, capture_root=matrix._fresh_child(root, label), label=label, timeout=timeout)


def run_pb01(root: Path, candidate_root: Path, upstream_root: Path, binary: Path, uv: Path, env: dict[str, str], oracle_env: dict[str, str], timeout: int) -> dict[str, Any]:
    case_root = matrix._fresh_child(root, "pb01-class-pickle")
    payload, fixture = matrix.secure_read(candidate_root, PB01_FIXTURE)
    matrix.exclusive_write(case_root, "input.yaml", payload)
    input_path = case_root / "input.yaml"; candidate_path = case_root / "candidate.pybert_data"; oracle_path = case_root / "oracle.pybert_data"
    candidate = command(case_root, "candidate", [str(binary), "sim", str(input_path), "--results", str(candidate_path)], candidate_root, env, timeout)
    oracle = command(case_root, "oracle", [str(uv), "run", "--project", str(upstream_root), "--frozen", "--offline", "--no-editable", "--extra", "native", "pybert", "sim", str(input_path), "--results", str(oracle_path)], upstream_root, oracle_env, timeout)
    result: dict[str, Any] = {"id": "pb01_class_pickle", "kind": "class_pickle", "input": {"path": PB01_FIXTURE, "bytes": len(payload), "sha256": sha256(payload), "file": fixture}, "candidate_process": process_fact(candidate), "oracle_process": process_fact(oracle)}
    if candidate["exit_code"] or oracle["exit_code"] or not candidate_path.is_file() or not oracle_path.is_file():
        result.update({"passed": False, "blockers": ["process_or_artifact_missing"]}); return result
    probe = command(case_root, "compare", [str(uv), "run", "--project", str(upstream_root), "--frozen", "--offline", "--no-editable", "--extra", "native", "python", "-c", PB01_PROBE, str(candidate_path), str(oracle_path), repr(PB01_RTOL), repr(PB01_ATOL)], upstream_root, oracle_env, timeout)
    if probe["exit_code"]:
        result.update({"passed": False, "blockers": ["comparison_probe_failed"], "comparison_process": process_fact(probe)}); return result
    comparison = json.loads(probe["stdout"])
    result.update({"comparison": comparison, "passed": comparison["passed"], "blockers": comparison["blockers"]})
    return result


def pb03_input(base: bytes, case_id: str) -> bytes:
    text = base.decode("utf-8")
    if case_id == "pb03_analytic_ctle":
        text = text.replace("ctle_enable: false", "ctle_enable: true", 1).replace("peak_mag: 1.7", "peak_mag: 4.0", 1)
    elif case_id == "pb03_gain_rejected":
        text = text.replace("gain: 0.1", "gain: 1.1", 1)
    elif case_id != "pb03_baseline":
        raise RuntimeError("unknown PB-03 case")
    return text.encode()


def run_pb03(case_id: str, root: Path, candidate_root: Path, upstream_root: Path, binary: Path, uv: Path, env: dict[str, str], oracle_env: dict[str, str], timeout: int) -> dict[str, Any]:
    case_root = matrix._fresh_child(root, case_id)
    base, _ = matrix.secure_read(candidate_root, PB03_FIXTURE)
    payload = pb03_input(base, case_id)
    fact = matrix.exclusive_write(case_root, "input.yaml", payload)
    input_path = case_root / "input.yaml"; candidate_dir = case_root / "candidate"; oracle_dir = case_root / "oracle"
    candidate = command(case_root, "candidate", [str(binary), "sim-rust", str(input_path), "--output-dir", str(candidate_dir)], candidate_root, env, timeout)
    oracle = command(case_root, "oracle", [str(uv), "run", "--project", str(upstream_root), "--frozen", "--offline", "--no-editable", "--extra", "native", "pybert", "sim-rust", str(input_path), "--output-dir", str(oracle_dir)], upstream_root, oracle_env, timeout)
    result: dict[str, Any] = {"id": case_id, "kind": "expected_rejection" if case_id == "pb03_gain_rejected" else "complete_web_artifact", "input": {"path": PB03_FIXTURE, "bytes": len(payload), "sha256": sha256(payload), "file": fact}, "candidate_process": process_fact(candidate), "oracle_process": process_fact(oracle)}
    if case_id == "pb03_gain_rejected":
        # Both CLIs may create their requested output directory before strict
        # request validation.  The source contract is that no published
        # artifact exists after rejection, not that the empty directory never
        # existed.
        absent = {
            "candidate": not (candidate_dir / "meta.json").exists() and not (candidate_dir / "arrays.npz").exists(),
            "oracle": not (oracle_dir / "meta.json").exists() and not (oracle_dir / "arrays.npz").exists(),
        }
        result.update({"no_artifacts": absent, "passed": candidate["exit_code"] != 0 and oracle["exit_code"] != 0 and all(absent.values()), "blockers": [] if candidate["exit_code"] and oracle["exit_code"] and all(absent.values()) else ["rejection_drift"]})
        return result
    if candidate["exit_code"] or oracle["exit_code"]:
        result.update({"passed": False, "blockers": ["process_failed"]}); return result
    probe = command(case_root, "compare", [str(uv), "run", "--project", str(upstream_root), "--frozen", "--offline", "--no-editable", "--extra", "native", "python", "-c", PB03_PROBE, str(candidate_dir), str(oracle_dir), repr(PB03_RTOL), repr(PB03_ATOL)], upstream_root, oracle_env, timeout)
    if probe["exit_code"]:
        result.update({"passed": False, "blockers": ["comparison_probe_failed"], "comparison_process": process_fact(probe)}); return result
    comparison = json.loads(probe["stdout"])
    result.update({"comparison": comparison, "passed": comparison["passed"], "blockers": [] if comparison["passed"] else ["artifact_drift"]})
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    candidate_repo, upstream_repo = args.candidate_repo.resolve(strict=True), args.upstream_repo.resolve(strict=True)
    candidate, upstream = identity(candidate_repo, args.candidate_commit), identity(upstream_repo, args.upstream_commit)
    if upstream != {"commit": PINNED_UPSTREAM, "tree": PINNED_TREE}:
        raise RuntimeError("upstream identity drift")
    work = args.work_root.resolve() if args.work_root else Path(matrix.tempfile.mkdtemp(prefix="sipi-pb01-03-source-"))
    if work.exists() and any(work.iterdir()): raise RuntimeError("work root must be empty")
    work.mkdir(parents=True, exist_ok=True)
    candidate_root, candidate_archive = matrix.materialize_archive(candidate_repo, candidate["commit"], work, "candidate", args.timeout_seconds)
    upstream_root, upstream_archive = matrix.materialize_archive(upstream_repo, upstream["commit"], work, "upstream", args.timeout_seconds)
    candidate_before, upstream_before = tracked_inventory(candidate_repo, candidate["commit"], candidate_root), tracked_inventory(upstream_repo, upstream["commit"], upstream_root)
    cargo, cargo_fact = tool(args.cargo, "cargo", ("--version",)); rustc, rustc_fact = tool(args.rustc, "rustc", ("-Vv",)); uv, uv_fact = tool(args.uv, "uv", ("--version",)); linker, linker_fact = tool(args.linker, "link", ("/?",))
    binary, build = matrix._build_candidate(candidate_root, work, cargo, rustc, linker, args.timeout_seconds)
    oracle_runtime = matrix._probe_oracle_runtime(upstream_root, work / "upstream-venv", work, uv, cargo, rustc, linker, args.timeout_seconds)
    env = matrix._execution_env(rustc, cargo, linker); env["CARGO_TARGET_DIR"] = str(work / "candidate-target")
    oracle_env = matrix._execution_env(rustc, cargo, linker); oracle_env["CARGO_TARGET_DIR"] = str(work / "upstream-target"); oracle_env["UV_PROJECT_ENVIRONMENT"] = str(work / "upstream-venv")
    cases = [run_pb01(work, candidate_root, upstream_root, binary, uv, env, oracle_env, args.timeout_seconds)]
    cases.extend(run_pb03(case, work, candidate_root, upstream_root, binary, uv, env, oracle_env, args.timeout_seconds) for case in ("pb03_baseline", "pb03_analytic_ctle", "pb03_gain_rejected"))
    if tracked_inventory(candidate_repo, candidate["commit"], candidate_root) != candidate_before or tracked_inventory(upstream_repo, upstream["commit"], upstream_root) != upstream_before: raise RuntimeError("tracked archive inventory drift")
    report = {"schema": SCHEMA, "version": 1, "run_id": args.run_id, "nonce": secrets.token_hex(32), "status": "passed" if all(case["passed"] for case in cases) else "blocked", "scope": {"pb01": {"fixture": PB01_FIXTURE, "canonical_names": list(PB01_NAMES), "rtol": PB01_RTOL, "atol": PB01_ATOL, "pickle_bytes_exact": False}, "pb03": {"fixture": PB03_FIXTURE, "case_ids": ["pb03_baseline", "pb03_analytic_ctle", "pb03_gain_rejected"], "rtol": PB03_RTOL, "atol": PB03_ATOL, "metadata_exclusions": list(PB03_EXCLUSIONS)}}, "candidate": {**candidate, "archive_sha256": candidate_archive["archive_sha256"]}, "upstream": {**upstream, "archive_sha256": upstream_archive["archive_sha256"]}, "toolchain": {"cargo": cargo_fact, "rustc": rustc_fact, "uv": uv_fact, "link": linker_fact}, "build": build, "oracle_runtime": oracle_runtime, "cases": cases}
    write_json(args.report, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--candidate-repo", type=Path, default=ROOT); parser.add_argument("--candidate-commit", required=True); parser.add_argument("--upstream-repo", type=Path, default=Path(r"C:\Users\z3312\code\Py-bert-agent")); parser.add_argument("--upstream-commit", default=PINNED_UPSTREAM); parser.add_argument("--run-id", required=True); parser.add_argument("--report", type=Path, required=True); parser.add_argument("--work-root", type=Path); parser.add_argument("--cargo", default=os.environ.get("CARGO", r"C:\Users\z3312\.cargo\bin\cargo.exe")); parser.add_argument("--rustc", default=os.environ.get("RUSTC", r"C:\Users\z3312\.cargo\bin\rustc.exe")); parser.add_argument("--uv", default=os.environ.get("UV", "uv")); parser.add_argument("--linker", default=os.environ.get("LINK", r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\link.exe")); parser.add_argument("--timeout-seconds", type=int, default=1200)
    report = run(parser.parse_args()); print(json.dumps({"status": report["status"], "run_id": report["run_id"]}, sort_keys=True)); return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
