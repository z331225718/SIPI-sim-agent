# P5-06i External COM Result Custody Audit

## Result

This additive record is **partial external observation, not an oracle or
acceptance result**. It does not modify the historical T13 preflight, PLAN,
remaining-items ledger, boundary, license, or source-map records. MATLAB was
not invoked.

The machine-readable record is
`docs/baselines/p5-06i-external-result-custody.v1.yaml`; its observer is
`tools/observe_p5_06i_external_result_custody.py`. The external COM checkout
is represented only as logical root `external_com_checkout`; its result
directory is `results/100GEL_C2M_host_16-Aug-2026`, with origin
`https://github.com/z331225718/agent-com.git`, commit
`5272ffe74702cd585054d975559b06f8afae7b6e`, tree
`7094ab6e84989b218730c52432c70da10261f8ea`. The checkout was dirty only at
observation time in the existing config MAT file.

The ignored result files are not Git objects, their generator commit is
unverified, and the embedded `code_revision` field is self-declared only.
Before scipy reads any payload, the observer requires one of eight exact
filename/hash/length identities; arbitrary MAT or CSV input is rejected.

## Observed Material

The registry-bound source is `matlab_src/com_ieee8023_480.m`, SHA-256
`642b28910a6fccca4682aa0a66a6a6c00633a14c17d05d8d6ee73d2808954cad`,
469,713 bytes. The registry-bound C2M workbook is
`matlab_src/config_com_ieee8023_93a=3ck_SA_120g_C2M_tp1a_08_17_2022.xlsx`, SHA-256
`f2c4c92f9549e720fff2843df6dc861aca7a503d59b2208898c2b67fa6fc0fc9`,
63,311 bytes. The result directory contains four ignored MAT/CSV pairs. The
MAT/CSV identities are recorded in the YAML; the MAT files are MATLAB v5 with
`output_args`/`OP`/`param` field counts `98/95/177`:

| Case | MAT SHA-256 | CSV SHA-256 |
| --- | --- | --- |
| fixtures case 1 | `4735668ec3731e2181d594f54f308dbbbbfd0e7885bfdd1c780ab0d222a74c7e` | `761205c8fa02a256841a0fa0d834121c2046a3028411fc3630eee546d4cd6f64` |
| fixtures case 2 | `bcfb14b506eb481586ea6651b7c1f0f4d59845e2ee37c98e3916baa36fe7b69f` | `2d1f307bbaa3c70ab66b2845f95b9b226c1c8fc558b31ef31d15ff1ed0c7172e` |
| synthetic case 1 | `bf79a0dfeb4c4d10e7f3844e0b59ef33947d247866348d7b6359d881595d066e` | `73360aa8ec2e69f460db32435e35702d5fe05778ba7923b0443a331517b48014` |
| synthetic case 2 | `0c86b467addbf0c729f0541abbdbe9d87d27ce0828974222f10c9ce7ca0798a1` | `50c93639f0b3b8b5caec0c45d15c0e4051638315531c5f8fab67f61acf7f3652` |

The observer binds a complete `OP+param` normalized payload digest for each
MAT, the 20 canonical `needs_matlab_oracle` occurrence values, port order
`[ 1 3 2 4 ]`, six checkpoint values, and the observed C4 fields
`COM_dB`/`ICN_mV`/`ERL`. CSVs are retained as rounded textual projections, not
as exact payloads.

## Closure And Remaining Gaps

- **P5-02:** the four payloads provide fixed-run observations for all 20
  oracle-dependent default expressions; the existing static warning inventory
  remains 25 calls. This does not close generic caller-dependent defaults or
  the full MLSE/DER/CDR warning contract.
- **P5-05:** the result MAT struct surface is now evidenced, but the existing
  product MAT reader accepts the legacy `parameter` cell-array surface and does
  not ingest these result structs. No product DTO promotion was made.
- **P5-06:** external result custody, normalized payload digests, checkpoints,
  and metric observations are bound. Exact historical `matlab_oracle.mat` and
  `summary.json` payloads remain unavailable; this record is not a product
  comparison or acceptance result.
- **P5-08/P5-09:** full `sipi com run` and the COM-specific IEEE
  non-certification report wording remain open.

The following T13 blockers remain open: capability-envelope registry mismatch;
MATLAB runner startup isolation and invocation authorization; replayable
authorized external-custody manifest; generic normalized-input digest;
caller-dependent defaults; exact run warning report; checkpoint tolerances;
complete acceptance metric scope; full metric tolerances/alignment policy;
exact reference-artifact payload; and the prohibition on treating product
self-crosschecks as an oracle. P5-06i only supplies a partial observed-output
record and does not retire any of those blockers by itself.

## Verification

```text
python tools/observe_p5_06i_external_result_custody.py --write-evidence
python tools/observe_p5_06i_external_result_custody.py --verify
python -m unittest tools/test_observe_p5_06i_external_result_custody.py -q
```

The observer verification reports `external_result_custody_verified` with four
payloads; the focused test suite reports five tests passing. No commit was
created.
