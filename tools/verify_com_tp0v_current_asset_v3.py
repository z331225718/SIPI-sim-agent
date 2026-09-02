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
    require(d.get('status') in {'preparation_only_pending_clean_candidate_and_harness_commit','candidate_bound_pending_four_replays'},'status')
    if d['status']=='preparation_only_pending_clean_candidate_and_harness_commit': require(d['candidate']=={'commit':None,'tree':None,'archive_sha256':None,'archive_bytes':None},'candidate must remain null')
    else: require(d['candidate']=={'commit':'3cb373b0d4c7d33f771179650c8982303f4329a6','tree':'3b21f44768312987debdb2e18e24671c01005bd3','archive_sha256':'871f4e72011bab82bace724336724125081acf7f91270d61c5d08be19d1c3602','archive_bytes':61921280},'candidate receipt')
    require(d['matlab']=={'required_release':'R2024b','required_release_raw':'2024b','executable_mode':'explicit_only_no_path_fallback','semantic_run':'uninstrumented','trace_run':'instrumented_diagnostic_only','start_flags':['-batch'],'mw_disable_connector':'1'},'exact R2024b runtime gate')
    comparison=d['comparison']
    require(comparison['source_warning_equivalent'] is False,'source warning contract')
    scalar=comparison['scalar_surface']
    require(scalar=={'names':['COM_dB','CTLE_DC_gain_dB','ERL','FOM','ICN_mV','IL_dB_channel_only_at_Fnq','Peak_ISI_XTK_and_Noise_interference_at_BER_mV','VEC_dB','VEO_mV','fitted_IL_dB_at_Fnq','g_DC_HP','itick'],'finite_absolute_tolerance':1.0e-09,'infinity':'same_sign_same_position','nan':'rejected','candidate_extensions':'diagnostic_only_excluded_from_matlab_parity'},'scalar contract')
    require(comparison['d3_policy']=={'metrics':['COM_dB','ERL_dB','TD_ILN_dB'],'finite_absolute_tolerance_db':0.1,'td_iln_aliases_forbidden':['FOM_TDILN','ICN_mV'],'unavailable_checkpoint':'blocked'},'D3 contract')
    require(comparison['cache_bridge']=={'xlsx_to_mat':'exact_shape_row_column_kind_value','matlab_must_reload_produced_mat':True},'cache bridge contract')
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
