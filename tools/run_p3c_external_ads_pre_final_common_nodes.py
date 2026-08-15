"""Observe exact 4:1 common-node S0-to-final ADS spectrum differences only."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, subprocess
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]; SOURCE=ROOT/"tools/run_p3c_external_ads_fixed_pulse_passivity_surface.py"; EXTRACTOR=ROOT/"tools/extract_p3c_ads_pre_final_common_nodes.py"
spec=importlib.util.spec_from_file_location("surface",SOURCE); assert spec and spec.loader; SURFACE=importlib.util.module_from_spec(spec); spec.loader.exec_module(SURFACE)
ADS_PYTHON=Path(r"C:\Program Files\Keysight\ADS2026_Update1\tools\python\python.exe"); API_DOC=Path(r"C:\Program Files\Keysight\ADS2026_Update1\doc\python\dataset\html\apidoc.html")
PYTHON_ID=(91136,"8c3fda8eb64fd1ccec107c3903a24060715604cca8b8649743cac5d0df271384"); DOC_ID=(62006,"86577ec72abb6d49926722968043d7b3d639eabc624c031bfd015f827a32894f")
class CommonNodeError(RuntimeError): pass
def identity(path:Path)->tuple[int,str]:
 d=hashlib.sha256(path.read_bytes()).hexdigest(); return path.stat().st_size,d
def extract(dataset:Path)->dict[str,Any]:
 if identity(ADS_PYTHON)!=PYTHON_ID or identity(API_DOC)!=DOC_ID: raise CommonNodeError("ads_dataset_api_identity_mismatch")
 r=subprocess.run([str(ADS_PYTHON),"-B",str(EXTRACTOR),"--dataset",str(dataset)],check=False,capture_output=True,text=True,encoding="utf-8",errors="strict")
 if r.returncode: raise CommonNodeError("ads_dataset_common_node_rejected")
 try: v=json.loads(r.stdout)
 except json.JSONDecodeError as e: raise CommonNodeError("ads_dataset_common_node_output_invalid") from e
 if not isinstance(v,dict) or v.get("common_node_count")!=1024 or v.get("mapping")!="fft_imp_index_equals_4_times_s0_index": raise CommonNodeError("ads_dataset_common_node_mapping_invalid")
 return v
def materialize(source:Path,destination:Path,invoke_ads:bool)->dict[str,Any]:
 v=SURFACE.materialize_probe(source,destination,invoke_ads=invoke_ads)
 if invoke_ads: v["common_node_comparison"]=extract(destination/"p3c_prbs9.ds"); v["ads_dataset_api"]={"python": {"byte_length":PYTHON_ID[0],"sha256":PYTHON_ID[1]},"api_doc":{"byte_length":DOC_ID[0],"sha256":DOC_ID[1]}}
 (destination/"manifest.json").write_text(json.dumps(v,sort_keys=True,indent=2)+"\n",encoding="ascii",newline="\n"); return v
def main(argv:list[str]|None=None)->int:
 p=argparse.ArgumentParser();p.add_argument("--s4p",type=Path,required=True);p.add_argument("--output-root",type=Path,required=True);p.add_argument("--run-id",required=True);p.add_argument("--run",action="store_true");a=p.parse_args(argv)
 try:
  if not SURFACE.PULSE.ads.valid_run_id(a.run_id): raise CommonNodeError("run_id_invalid")
  v=materialize(SURFACE.PULSE.require_external(a.s4p,"s4p"),SURFACE.PULSE.require_external(a.output_root,"output_root")/a.run_id,a.run)
 except (OSError,ValueError,CommonNodeError,SURFACE.PassivitySurfaceError,SURFACE.PULSE.FixedPulseError,SURFACE.PULSE.ads.ExternalReferenceError) as e: print(json.dumps({"status":"rejected","reason":str(e)},sort_keys=True));return 2
 print(json.dumps({"status":"ads_run_completed" if a.run else "generated","common_node_comparison":v.get("common_node_comparison")},sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
