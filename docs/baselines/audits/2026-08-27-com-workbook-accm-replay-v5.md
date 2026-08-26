schema: sipi.com.workbook-accm-replay-v5.audit.v1
manifest:
  path: docs/baselines/com-workbook-accm-replay-v5.manifest.yaml
  schema: sipi.com.workbook-accm-replay-v5.formal-manifest.v1
scope: formal_replay_observation_only
provenance:
  harness_commit: 6011374f8f84e205c19ff4f7052ab25dcd6f2cd9
  harness_tree: fee5cb6d2bdae26aa66f46ce2a3eea494827706a
  candidate_commit: bc882d2e5a19c2a844bacc485ede5b874e8f9c37
  upstream_commit: 5272ffe74702cd585054d975559b06f8afae7b6e
evidence:
  reports:
    - slot: run1
      path: docs/baselines/com-workbook-accm-replay-v5-run1.json
      bytes: 58401
      sha256: fc14c562020883d0706bfaa16c3d970cb9834bcbf971f9e57b260021a8ca1a64
      run_id: 1374cb690e7f1eb90247caa4b63ed0a6ce6873556f899452046260b8b9007868
      nonce: 03049bcdfa43e0e8907cc2a69e9265d89579be21059d18928162a9ef31302e5b
    - slot: run2
      path: docs/baselines/com-workbook-accm-replay-v5-run2.json
      bytes: 58401
      sha256: ef732c7b063a72e422aa5f68325df1d029da056b2eb092502e7a7c7eb26fda01
      run_id: 950d932509047d64c89177cc54146d1a65301068c88c3f8bdcba1fe916328f77
      nonce: 8289a1caa5ac62c36229b62cce2dc9a43dac4f355f5d021ac8683ce9841d71c5
  aggregate:
    path: docs/baselines/com-workbook-accm-replay-v5-aggregate.json
    bytes: 113947
    sha256: 6ec879783ef1ef2310b72c4bbc19e590b84c727055e374af0f59913a8fdb2242
result:
  status: scoped_mismatch_observed
  matched: false
  acceptance: false
  blockers:
    - candidate_dfe_taps_not_published
  port_order: not_observed
  dfe_publication: candidate_not_published
  no_s_parameter_fit: true
  channel_policy: one_final_fd_to_td_impulse
non_claims:
  - no S-parameter fit
  - channel uses one final FD-to-TD impulse
  - no upstream or global numeric parity
  - no release or promotion claim
  - candidate DFE publication is not inferred from hidden state
# HARNESS_ANCHOR: 6011374f8f84e205c19ff4f7052ab25dcd6f2cd9|fee5cb6d2bdae26aa66f46ce2a3eea494827706a
# REPORT_ANCHOR: run1|docs/baselines/com-workbook-accm-replay-v5-run1.json|58401|fc14c562020883d0706bfaa16c3d970cb9834bcbf971f9e57b260021a8ca1a64|1374cb690e7f1eb90247caa4b63ed0a6ce6873556f899452046260b8b9007868|03049bcdfa43e0e8907cc2a69e9265d89579be21059d18928162a9ef31302e5b
# REPORT_ANCHOR: run2|docs/baselines/com-workbook-accm-replay-v5-run2.json|58401|ef732c7b063a72e422aa5f68325df1d029da056b2eb092502e7a7c7eb26fda01|950d932509047d64c89177cc54146d1a65301068c88c3f8bdcba1fe916328f77|8289a1caa5ac62c36229b62cce2dc9a43dac4f355f5d021ac8683ce9841d71c5
# AGGREGATE_ANCHOR: docs/baselines/com-workbook-accm-replay-v5-aggregate.json|113947|6ec879783ef1ef2310b72c4bbc19e590b84c727055e374af0f59913a8fdb2242
