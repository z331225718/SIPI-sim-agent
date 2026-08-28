"""Mechanically validate and aggregate two fresh AS-06 ngspice replays."""
from __future__ import annotations
import argparse, hashlib, json, math, re
from pathlib import Path

HEX64=re.compile(r"^[0-9a-f]{64}$")
CANDIDATE={"commit":"aea546510d345cd7e280e55897c027be872d759a","tree":"df99e5bb1c2381bb52fe0037b7b8fbb38b7c6cb9","sha256":"4da4772366c49330679c85626b63eeccd3234643303d04bcd9b657c0d9eff326","bytes":54640640}
UPSTREAM={"commit":"2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5","tree":"b6bde97128030d6cea0d68b2f0a35d807be8c402","sha256":"a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144","bytes":120238080}
INPUTS={"deck_sha256":"4c9bcfe30462ca61c62d9ecba9c50d73311f5e18b57cc6afe7e58c76f2b56e5a","rfm_sha256":"894b5da3aba954d3d288689458be99d7434db966b4df4675db52165c4db2b55d","code_model_sha256":"a23fa36d39328c8a000eb405a66cd293dae6015f3f50df09c4ea887faa104bab","ngspice_sha256":"86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453"}
CLAIMS={"external_solver_scoped_observation":True,"solver_correctness":False,"release_acceptance":False,"s_parameter_fit":False,"as05_xyce_xdm":False,"environment_injection_resistance":False,"hostile_writer_resistance":False}
RESULT={"headers":["time","v(src)","v(out)"],"waveform_rows":1029,"float_bit_exact":True,"max_abs_error":0.0,"logical_manifest_equal":True,"runtime_semantics_equal":True,"rust_reconstruction_rms":0.0,"upstream_reconstruction_rms":0.0,"rust_reconstruction_max":0.0,"upstream_reconstruction_max":0.0}

def _hex(value): return isinstance(value,str) and HEX64.fullmatch(value) is not None
def load(path):
 raw=path.read_bytes()
 if len(raw)>2*1024*1024: raise ValueError("report over budget")
 return json.loads(raw),hashlib.sha256(raw).hexdigest()
def validate(value):
 keys={"schema","status","run_id","caller_challenge","fresh_run_nonce","runner_sha256","candidate","upstream","toolchain_pre","toolchain_post","binary_pre","binary_post","dependency_pre","dependency_post","environment","source_map","inputs","physical","canonical","result","claims"}
 if type(value) is not dict or set(value)!=keys or value["schema"]!="sipi.as-06-ngspice-result-parity.v2" or value["status"]!="passed": raise ValueError("report schema drift")
 if value["candidate"]!=CANDIDATE or value["upstream"]!=UPSTREAM or value["inputs"]!=INPUTS or value["claims"]!=CLAIMS or value["result"]!=RESULT: raise ValueError("fixed semantic drift")
 if type(value["result"]["waveform_rows"]) is not int or any(type(value["result"][key]) is not bool for key in ("float_bit_exact","logical_manifest_equal","runtime_semantics_equal")) or any(type(value["result"][key]) is not float for key in ("max_abs_error","rust_reconstruction_rms","upstream_reconstruction_rms","rust_reconstruction_max","upstream_reconstruction_max")): raise ValueError("result type drift")
 if not all(_hex(value[k]) for k in ("caller_challenge","fresh_run_nonce","runner_sha256")): raise ValueError("identity drift")
 if value["toolchain_pre"]!=value["toolchain_post"] or value["binary_pre"]!=value["binary_post"]: raise ValueError("pre/post drift")
 if set(value["toolchain_pre"])!={"cargo","rustc","python","ngspice"}: raise ValueError("toolchain roles drift")
 for role,tool in value["toolchain_pre"].items():
  if set(tool)!={"role","basename","sha256","version_exit","version_sha256","path_redacted"} or tool["role"]!=role or type(tool["version_exit"]) is not int or tool["version_exit"]!=0 or tool["path_redacted"] is not True or not _hex(tool["sha256"]) or not _hex(tool["version_sha256"]): raise ValueError("tool identity drift")
 if value["toolchain_pre"]["ngspice"]["sha256"]!=INPUTS["ngspice_sha256"]: raise ValueError("ngspice anchor drift")
 if value["source_map"]!={"path":"docs/baselines/as-06-run-rfm-source-map.v4.yaml","sha256":"9c96655e08fce504ae936b4e0c0cfb93a53ceafee7f0a3a9f848e1add0239304"}: raise ValueError("source map drift")
 if value["environment"]!={"policy":"cargo_rust_python_uv_pip_spice_prefixes_removed","cargo_target_fresh":True}: raise ValueError("environment policy drift")
 if set(value["physical"])!={"rust_waveform","upstream_waveform","rust_manifest","upstream_manifest","rust_stdout","upstream_stdout"}: raise ValueError("physical receipt drift")
 expected_basenames={"rust_waveform":"waveform.csv","upstream_waveform":"waveform.csv","rust_manifest":"rfm_run_manifest.json","upstream_manifest":"rfm_run_manifest.json","rust_stdout":"stdout.log","upstream_stdout":"stdout.log"}
 if any(value["physical"][key]["basename"]!=name for key,name in expected_basenames.items()): raise ValueError("physical basename drift")
 for receipt in [*value["physical"].values(),value["binary_pre"]]:
  if set(receipt)!={"basename","bytes","sha256","nlink","path_redacted"} or type(receipt["bytes"]) is not int or receipt["bytes"]<0 or type(receipt["nlink"]) is not int or receipt["nlink"]<1 or receipt["path_redacted"] is not True or not _hex(receipt["sha256"]): raise ValueError("receipt invalid")
 if not value["binary_pre"]["basename"].startswith("sipi-agent-spice-run-rfm"): raise ValueError("binary basename drift")
 if value["dependency_pre"]!=value["dependency_post"] or set(value["dependency_pre"])!={"files","bytes","sha256","path_redacted"} or type(value["dependency_pre"]["files"]) is not int or value["dependency_pre"]["files"]<1 or type(value["dependency_pre"]["bytes"]) is not int or value["dependency_pre"]["bytes"]<1 or not _hex(value["dependency_pre"]["sha256"]) or value["dependency_pre"]["path_redacted"] is not True: raise ValueError("dependency inventory drift")
 if set(value["canonical"])!={"rust_f64_sha256","upstream_f64_sha256"} or value["canonical"]["rust_f64_sha256"]!=value["canonical"]["upstream_f64_sha256"] or not _hex(value["canonical"]["rust_f64_sha256"]): raise ValueError("canonical digest drift")
 expected_runner=hashlib.sha256((Path(__file__).resolve().parent/"run_as_06_ngspice_result_parity.py").read_bytes()).hexdigest()
 if value["runner_sha256"]!=expected_runner: raise ValueError("runner source binding drift")
 return value
def aggregate(paths):
 loaded=[(*load(path),path.name) for path in paths];values=[validate(item[0]) for item in loaded]
 if len({item["run_id"] for item in values})!=2 or len({item["caller_challenge"] for item in values})!=2 or len({item["fresh_run_nonce"] for item in values})!=2 or len({item[1] for item in loaded})!=2: raise ValueError("two-fresh identity drift")
 stable=("runner_sha256","candidate","upstream","toolchain_pre","toolchain_post","environment","source_map","inputs","canonical","result","claims")
 if any(values[0][key]!=values[1][key] for key in stable): raise ValueError("fresh replay semantic drift")
 return {"schema":"sipi.as-06-ngspice-result-parity-aggregate.v2","status":"passed_scoped_external_observation","reports":[{"path":item[2],"sha256":item[1],"run_id":item[0]["run_id"],"caller_challenge":item[0]["caller_challenge"],"fresh_run_nonce":item[0]["fresh_run_nonce"],"binary":item[0]["binary_pre"],"dependencies":item[0]["dependency_pre"]} for item in loaded],**{key:values[0][key] for key in stable}}
def main():
 p=argparse.ArgumentParser();p.add_argument("reports",nargs=2,type=Path);p.add_argument("--output",type=Path,required=True);a=p.parse_args();out=aggregate(a.reports);payload=(json.dumps(out,sort_keys=True,indent=2)+"\n").encode();
 with a.output.open("xb") as stream: stream.write(payload)
 print(hashlib.sha256(payload).hexdigest())
if __name__=="__main__":main()
