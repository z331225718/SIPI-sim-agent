"""R2024b v3 aggregate hard-gates identical MATLAB runtimes and Rust speed."""
def aggregate(records):
    if len(records)!=4 or {r.get('run_id') for r in records}!={'matlab-01','matlab-02','rust-01','rust-02'} or len({r.get('nonce') for r in records})!=4: raise ValueError('fixed run id/nonce gate')
    matlab=[r for r in records if r['engine']=='matlab']; rust=[r for r in records if r['engine']=='rust']
    required={'release','release_raw','arch','exe_bytes','exe_sha256','full_version_sha256','start_flags','mw_disable_connector','matlab_prefdir_isolated','path_redacted'}
    if len(matlab)!=2 or len(rust)!=2 or set(matlab[0]['runtime'])!=required or matlab[0]['runtime']!=matlab[1]['runtime']: raise ValueError('MATLAB runtime identity drift')
    for case in ('0','1'):
        if any(r['cases'][case]['wall_clock_s']>=m['cases'][case]['wall_clock_s'] for r in rust for m in matlab): raise ValueError('Rust performance gate')
    return {'status':'pending_cross_engine_comparison'}
