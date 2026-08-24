"""Scoped clean-archive TDMODE crosstalk stage replay."""
from __future__ import annotations
import argparse, hashlib, json, os, secrets, subprocess, sys, tarfile, tempfile, io
from pathlib import Path
from typing import Any
import numpy as np
from com_erl_exact_profile_replay_v3_support import path_free, sha256_bytes, sha256_file, tool_identity
from pb_03_replay_common import windows_pe_replay_custody

SCHEMA = "sipi.com.td-crosstalk-stage-replay.v1"
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
CANDIDATE_COMMIT = "e1a9ca876c57bdf196974ae7b640e5ae73b6f18c"
FB = 53125000000.0
F2_VALUES = (50000000000.0, 13000000000.0)
FIXTURE_PATHS = ("fixtures/synthetic/td_thru_pulse.csv", "fixtures/synthetic/td_fext_pulse.csv", "fixtures/synthetic/td_next_pulse.csv")

def digest(values: Any) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes(order="C")).hexdigest()

def source_inventory(root: Path) -> dict[str, Any]:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".rs", ".toml", ".lock"}:
            entries.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)})
    return {"count": len(entries), "combined_sha256": sha256_bytes(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode())}

def path_inventory(value: str, kind: str) -> dict[str, Any]:
    roots = [Path(x).resolve() for x in value.split(os.pathsep) if x]
    if not roots or any(not root.is_dir() for root in roots): raise RuntimeError("native environment directory missing")
    allowed = {"LIB": {".lib", ".dll"}, "INCLUDE": {".h", ".hpp", ".inl", ".inc"}, "PATH": {".exe", ".com", ".bat", ".cmd"}}[kind]
    entries = []
    for root in roots:
        files = []
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in allowed:
                if path.stat().st_size > 64 * 1024 * 1024: raise RuntimeError("native environment file too large")
                files.append({"name": path.relative_to(root).as_posix(), "sha256": sha256_file(path)})
                if len(files) > 10000: raise RuntimeError("native environment inventory too large")
        if not files: raise RuntimeError("native environment inventory empty")
        entries.append({"root_label": root.name, "files": files})
    return {"count": len(entries), "combined_sha256": sha256_bytes(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode())}

def materialize(git: Path, repo: Path, rev: str, dest: Path) -> tuple[str, str]:
    payload = subprocess.run([str(git), "-C", str(repo), "archive", "--format=tar", rev], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as handle:
        dest.mkdir(parents=True)
        base = dest.resolve()
        for member in handle.getmembers():
            if member.issym() or member.islnk(): raise RuntimeError("archive link")
            target = (dest / member.name).resolve()
            if target != base and base not in target.parents: raise RuntimeError("archive escape")
        handle.extractall(dest)
    tree = subprocess.run([str(git), "-C", str(repo), "rev-parse", f"{rev}^{{tree}}"], capture_output=True, check=True).stdout.decode().strip()
    return sha256_bytes(payload), tree

def make_input(upstream: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = {name: np.loadtxt(upstream / name, dtype=np.float64, delimiter=",") for name in FIXTURE_PATHS}
    n_full, n_short = 64, 8
    frequency = np.linspace(0.0, 80e9, n_full)
    dt = float(raw[FIXTURE_PATHS[0]][1, 0] - raw[FIXTURE_PATHS[0]][0, 0])
    base_frequency = np.fft.rfftfreq(raw[FIXTURE_PATHS[0]].shape[0], dt)
    def response(name: str) -> np.ndarray:
        spectrum = np.fft.rfft(raw[name][:, 1])
        values = np.interp(np.linspace(0.0, base_frequency[-1], n_short), base_frequency, np.abs(spectrum))
        return values / max(float(np.max(values)), 1.0)
    thru, fext, nxt = (response(name) for name in FIXTURE_PATHS)
    h_ctf = np.interp(frequency, np.linspace(0.0, 80e9, n_short), thru)
    tx_filter = np.ones(n_full)
    sinc = np.sinc(frequency / FB)
    channels = [{"role": "FEXT", "response": [{"real": float(v), "imag": 0.0} for v in fext], "amplitude": 0.25}, {"role": "NEXT", "response": [{"real": float(v), "imag": 0.0} for v in nxt], "amplitude": 0.17}]
    payload = {"td_crosstalk": {"frequency": frequency.tolist(), "h_ctf": [{"real": float(v), "imag": 0.0} for v in h_ctf], "tx_filter": [{"real": float(v), "imag": 0.0} for v in tx_filter], "sinc": sinc.tolist(), "channels": channels, "parameters": {"fb": FB, "f2": F2_VALUES[0], "sigma_x": 0.1}}}
    stages = {"short_response": {"count": n_short, "sha256": digest(fext), "roles": {"FEXT": digest(fext), "NEXT": digest(nxt)}}, "full_noise_axis": {"count": n_full, "sha256": digest(frequency)}, "outer_product": {"rows": n_short, "columns": n_full, "elements": n_short * n_full, "order": "column-major-linear", "role_sum": {"FEXT": digest(fext[:, None] * h_ctf[None, :]), "NEXT": digest(nxt[:, None] * h_ctf[None, :])}}, "fixtures": {path: sha256_file(upstream / path) for path in FIXTURE_PATHS}}
    return payload, stages

def upstream_probe(root: Path, input_path: Path, python: Path, uv: Path, uv_cache_dir: Path, f2: float) -> dict[str, Any]:
    code = """import json,sys,numpy as np
from agent_com.equalization.search import _td_source_crosstalk_noise
d=json.load(open(sys.argv[1],encoding="utf-8"))["td_crosstalk"]
arr=lambda x: np.asarray(x,dtype=np.float64)
channels=tuple((q["role"],np.asarray([v["real"]+1j*v["imag"] for v in q["response"]],dtype=np.complex128),float(q["amplitude"])) for q in d["channels"])
f=arr(d["frequency"]); h=np.asarray([v["real"]+1j*v["imag"] for v in d["h_ctf"]]); t=np.asarray([v["real"]+1j*v["imag"] for v in d["tx_filter"]]); s=arr(d["sinc"])
noise=_td_source_crosstalk_noise(f,h,t,s,channels,{"fb":float(d["parameters"]["fb"]),"f2":float(sys.argv[2]),"sigma_X":float(d["parameters"]["sigma_x"])})
print(json.dumps({"noise":float(noise),"short_count":len(channels[0][1]),"full_count":len(f),"numpy_version":np.__version__,"numpy_version_sha256":__import__('hashlib').sha256(np.__version__.encode()).hexdigest(),"numpy_module_sha256":__import__('hashlib').sha256(open(np.__file__,'rb').read()).hexdigest(),"numpy_core_basename":__import__('pathlib').Path(np.core._multiarray_umath.__file__).name,"numpy_core_sha256":__import__('hashlib').sha256(open(np.core._multiarray_umath.__file__,'rb').read()).hexdigest()},separators=(",",":")))"""
    env = {"PYTHONPATH": str(root / "src"), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "UV_OFFLINE": "1", "UV_CACHE_DIR": str(uv_cache_dir.resolve())}
    completed = subprocess.run([str(uv), "run", "--frozen", "--offline", "--project", ".", "--python", str(python), "python", "-c", code, str(input_path), str(f2)], cwd=root, env=env, capture_output=True, timeout=180, check=False)
    if completed.returncode: raise RuntimeError("upstream oracle failed: " + completed.stderr.decode(errors="replace")[-1000:])
    return json.loads(completed.stdout.decode().splitlines()[-1])

def candidate_probe(candidate: Path, input_path: Path, cargo: Path, rustc: Path, linker: Path, lib: str, include: str, native_path: str, f2: float) -> tuple[float, str, dict[str, Any]]:
    target = candidate / "target-evidence"
    env = {"PATH": native_path, "CARGO_NET_OFFLINE": "true", "CARGO_INCREMENTAL": "0", "CARGO_TARGET_DIR": str(target), "RUSTC": str(rustc.resolve()), "CARGO_BUILD_RUSTC": str(rustc.resolve()), "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER": str(linker.resolve()), "RUSTFLAGS": "", "CARGO_ENCODED_RUSTFLAGS": "", "LIB": lib, "INCLUDE": include, "RUSTC_WRAPPER": "", "RUSTC_WORKSPACE_WRAPPER": "", "CARGO_BUILD_RUSTC_WRAPPER": ""}
    build = subprocess.run([str(cargo), "test", "--manifest-path", str(candidate / "crates/sipi-com/Cargo.toml"), "--test", "p5_04p_crosstalk_runner", "--no-run", "--locked", "--offline"], cwd=candidate, env=env, capture_output=True, timeout=900, check=False)
    if build.returncode: raise RuntimeError("candidate build failed: " + build.stderr.decode(errors="replace")[-1500:])
    binaries = sorted(target.glob("debug/deps/p5_04p_crosstalk_runner-*.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not binaries: raise RuntimeError("candidate binary missing")
    output = candidate / "candidate-output.json"
    run = subprocess.run([str(binaries[0]), "--input", str(input_path), "--report", str(output)], capture_output=True, timeout=180, check=False)
    if run.returncode: raise RuntimeError("candidate stage failed: " + run.stderr.decode(errors="replace")[-1000:])
    return float(json.loads(output.read_text(encoding="utf-8"))["td_crosstalk"]["noise"]), sha256_file(binaries[0]), windows_pe_replay_custody(binaries[0])

def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.run_id not in ("com-td-crosstalk-stage-v1-run1", "com-td-crosstalk-stage-v1-run2"): raise ValueError("strict run id")
    with tempfile.TemporaryDirectory(prefix="com-td-stage-") as name:
        temp = Path(name); upstream = temp / "upstream"; candidate = temp / "candidate"
        upstream_archive, upstream_tree = materialize(args.git.resolve(), args.upstream.resolve(), UPSTREAM_COMMIT, upstream)
        candidate_archive, candidate_tree = materialize(args.git.resolve(), args.repo.resolve(), CANDIDATE_COMMIT, candidate)
        payload, stages = make_input(upstream)
        candidate_input, upstream_input = temp / "candidate-input.json", temp / "upstream-input.json"
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        candidate_input.write_bytes(raw); upstream_input.write_bytes(raw)
        candidate_input.chmod(0o444); upstream_input.chmod(0o444)
        upstream_out, candidate_out, input_hashes = {}, {}, {}
        candidate_inventory = source_inventory(candidate)
        binary_sha, binary_custody = None, None
        for f2 in F2_VALUES:
            changed = json.loads(raw)
            changed["td_crosstalk"]["parameters"]["f2"] = f2
            staged = json.dumps(changed, sort_keys=True, separators=(",", ":")).encode()
            for path in (candidate_input, upstream_input):
                path.chmod(0o644); path.write_bytes(staged); path.chmod(0o444)
            input_hashes[str(f2)] = {"candidate": sha256_file(candidate_input), "upstream": sha256_file(upstream_input)}
            upstream_out[str(f2)] = upstream_probe(upstream, upstream_input, args.python, args.uv, args.uv_cache_dir, f2)
            candidate_out[str(f2)], binary_sha, binary_custody = candidate_probe(candidate, candidate_input, args.cargo, args.rustc, args.linker, args.lib, args.include, args.native_path, f2)
        differences = {k: {"upstream": upstream_out[k]["noise"], "candidate": candidate_out[k]} for k in upstream_out if not np.isclose(upstream_out[k]["noise"], candidate_out[k], rtol=1e-12, atol=1e-12)}
        tools = {name: tool_identity(path.resolve(), 180) for name, path in {"git": args.git, "cargo": args.cargo, "rustc": args.rustc, "linker": args.linker, "python": args.python, "uv": args.uv}.items()}
        for role, value in tools.items(): value["role"] = role
        tools["numpy"] = {"role": "numpy", "basename": "numpy", "file_sha256": upstream_out[str(F2_VALUES[0])]["numpy_module_sha256"], "version_output_sha256": sha256_bytes(upstream_out[str(F2_VALUES[0])]["numpy_version"].encode()), "version_exit": 0, "core_basename": upstream_out[str(F2_VALUES[0])]["numpy_core_basename"], "core_binary_sha256": upstream_out[str(F2_VALUES[0])]["numpy_core_sha256"], "status": "ok", "path_redacted": True}
        pe_helper = {"path": "tools/pb_03_replay_common.py", "sha256": sha256_file(Path(__file__).with_name("pb_03_replay_common.py"))}
        if binary_custody is not None: binary_custody["canonical_helper"] = pe_helper
        report = {"schema": SCHEMA, "run_id": args.run_id, "fresh_run_nonce": secrets.token_hex(32), "status": "matched" if not differences else "numeric_mismatch_open", "path_policy": {"mode": "repo-relative identities only", "absolute_paths_emitted": False}, "candidate": {"commit": CANDIDATE_COMMIT, "tree": candidate_tree, "archive_sha256": candidate_archive, "materialization": "git archive; no working-tree overlay", "binary_sha256": binary_sha, "binary_custody": binary_custody, "source_inventory": candidate_inventory}, "upstream": {"commit": UPSTREAM_COMMIT, "tree": upstream_tree, "archive_sha256": upstream_archive, "materialization": "git archive; no working-tree overlay", "oracle_role": "pinned_agent_com_pure_leaf", "oracle": "agent_com.equalization.search._td_source_crosstalk_noise"}, "input": {"fixture_paths": list(FIXTURE_PATHS), "fixture_sha256": stages["fixtures"], "fixture_source_archive_sha256": upstream_archive, "f2_copy_sha256": input_hashes, "independent_read_only": True, "channel_policy": "TD pulse-derived; no S-parameter fit"}, "stages": stages, "stage_observation": "shared exact short-response/full-noise input; candidate expanded matrix is not exposed", "upstream_output": upstream_out, "candidate_output": candidate_out, "parity": {"numeric_policy": {"f2_values_hz": list(F2_VALUES), "atol": 1e-12, "rtol": 1e-12}, "differences": differences, "matched": not differences}, "toolchain": tools, "execution": {"runner": {"path": "tools/run_com_td_crosstalk_stage_replay_v1.py", "sha256": sha256_file(Path(__file__).resolve())}, "helper": {"path": "tools/com_erl_exact_profile_replay_v3_support.py", "sha256": sha256_file(Path(__file__).with_name("com_erl_exact_profile_replay_v3_support.py"))}, "pe_helper": pe_helper, "upstream_runtime": "uv run --frozen --offline --project . --python <pinned-python> python -c <pinned-pure-leaf>", "uv_actual_execution": True, "wrappers": {"RUSTC_WRAPPER": "", "RUSTC_WORKSPACE_WRAPPER": "", "CARGO_BUILD_RUSTC_WRAPPER": ""}, "build_environment": {"RUSTC": {"basename": tools["rustc"]["basename"], "sha256": tools["rustc"]["file_sha256"]}, "CARGO_BUILD_RUSTC": {"basename": tools["rustc"]["basename"], "sha256": tools["rustc"]["file_sha256"]}, "LINKER": {"basename": tools["linker"]["basename"], "sha256": tools["linker"]["file_sha256"]}, "RUSTFLAGS": "", "CARGO_ENCODED_RUSTFLAGS": "", "LIB": path_inventory(args.lib, "LIB"), "INCLUDE": path_inventory(args.include, "INCLUDE"), "PATH": {"inventory": path_inventory(args.native_path, "PATH"), "tool_basenames": [tools[name]["basename"] for name in ("cargo", "rustc", "linker")] }}, "timeout_s": 180, "build_timeout_s": 900, "cargo_offline": True}, "non_claims": ["scoped TDMODE crosstalk stage only", "no full COM parity", "no release or promotion", "no S-parameter fit"]}
        if not path_free(report): raise RuntimeError("absolute path leaked")
        return report

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--repo", type=Path, required=True); p.add_argument("--upstream", type=Path, required=True); p.add_argument("--cargo", type=Path, required=True); p.add_argument("--rustc", type=Path, required=True); p.add_argument("--linker", type=Path, required=True); p.add_argument("--uv", type=Path, required=True); p.add_argument("--uv-cache-dir", type=Path, required=True); p.add_argument("--python", type=Path, required=True); p.add_argument("--git", type=Path, required=True); p.add_argument("--lib", required=True); p.add_argument("--include", required=True); p.add_argument("--native-path", required=True); p.add_argument("--run-id", required=True); p.add_argument("--report", type=Path, required=True)
    a = p.parse_args(); report = run(a); a.report.parent.mkdir(parents=True, exist_ok=True); a.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"); print(json.dumps({"run_id": a.run_id, "status": report["status"], "report_sha256": sha256_file(a.report)}, sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
