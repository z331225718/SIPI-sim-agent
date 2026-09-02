"""R2024b-only TP0V v3 preparation gate; no formal replay is accepted here."""
from __future__ import annotations
import argparse, hashlib, json, tarfile
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'docs/baselines/com-tp0v-current-asset-scoped-acceptance.v3.yaml'
def require(ok, msg):
    if not ok: raise ValueError(msg)
def validate(d):
    require(d.get('schema')=='sipi.com.tp0v-current-asset-scoped-acceptance-prep.v3','schema')
    require(d.get('status')=='preparation_only_pending_clean_candidate_and_harness_commit','status')
    require(d['candidate']=={'commit':None,'tree':None,'archive_sha256':None,'archive_bytes':None},'candidate must remain null')
    require(d['matlab']=={'required_release':'R2024b','required_release_raw':'2024b','executable_mode':'explicit_only_no_path_fallback','semantic_run':'uninstrumented','trace_run':'instrumented_diagnostic_only','start_flags':['-batch'],'mw_disable_connector':'1'},'exact R2024b runtime gate')
    require(d['comparison']['source_warning_equivalent'] is False and d['comparison']['scalar_surface_count']==21,'comparison contract')
    assets=d['upstream']['assets']; require([a['role'] for a in assets]==['THRU','FEXT','NEXT'],'asset role/order')
    for a in assets: require(a['port_order']==[1,2,3,4] and a['header']=='# Hz S RI R 50.0' and len(a['sha256'])==64,'asset contract')
    for p in d['formal_paths_absent']: require(not (ROOT/p).exists(),f'formal path exists: {p}')
    for name,item in d['tools'].items():
     if name!='verifier': require(hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()==item['sha256'],f'tool hash: {name}')
def verify_archive(d,path):
 raw=path.read_bytes(); u=d['upstream']; require(len(raw)==u['archive_bytes'] and hashlib.sha256(raw).hexdigest()==u['archive_sha256'],'archive')
 with tarfile.open(path) as t:
  for item in [u['workbook'],*u['assets']]:
   m=None
   for candidate in t.getmembers():
    if candidate.isfile() and (candidate.name==item['path'] or candidate.name.endswith('/'+item['path'])):
     m=candidate; break
   require(m is not None,'member')
   b=t.extractfile(m).read(); require(len(b)==item['bytes'] and hashlib.sha256(b).hexdigest()==item['sha256'],'member hash')
   if 'header' in item: require(next(x.decode().strip() for x in b.splitlines() if x.strip() and not x.startswith(b'!'))==item['header'],'header')
def main():
 p=argparse.ArgumentParser();p.add_argument('--upstream-archive',type=Path);a=p.parse_args(); d=yaml.safe_load(MANIFEST.read_text()); validate(d)
 if a.upstream_archive: verify_archive(d,a.upstream_archive)
 print(json.dumps({'valid':True,'status':d['status']}))
if __name__=='__main__': main()
