# PB external AMI adapter source map

This additive adapter reuses the existing sipi-ami-worker one-job protocol
and does not load, copy, or emulate vendor AMI code. The pinned upstream
repository is `5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`. Upstream declares BSD-3-Clause;
the root `LICENSE` blob is `64d198ba43675ede5fbdef1ec918a63954951640`,
1466 bytes. No vendor DLL, AMI model, or upstream Python source is vendored.

| Pinned PyBERT branch | Git blob / bytes | Existing host/worker route | PB adapter |
| --- | --- | --- |
| `src/pybert/utility/ibisami.py` | `9f1fb3b1496fd192b77207ffcecc4b2478d5f64e`, 5557 | sipi-ami-host Init/GetWave ABI | `PybertAmiModeV1` |
| `src/pybert/models/bert.py` | `f04340c1028078175b26d7882efeeaf96f001abf`, 70571 | sipi-ami-worker job lifecycle | `prepare_pybert_ami_launch` |
| `src/pybert/engine/hybrid_ami.py` | `303ced44487329687941d161014a63961200006d`, 11705 | worker closure and artifact boundary | `supervise_prepared_pybert_ami_job` |

The bundle explicitly includes the .ibs selection file, source .ami declaration,
caller-supplied runtime parameter text, and vendor DLL identity. The adapter
writes the runtime text as a separate bounded job input instead of passing the
whole .ami declaration to `AMI_Init`; this is a caller-supplied raw-declaration
experiment, not a claim of PyBERT's full `_ads_style_ami_init_parameters`
table semantics. The closure is re-bound into the worker job; the
launch also carries a fresh nonce and request SHA-256. Init-only is rejected
because the existing one-job worker currently expresses Init followed by
GetWave only; there is no silent fallback. The typed result contract requires
waveform, model clocks, parameters-out, and successful Close.

The production worker now publishes bounded waveform/clocks payloads and an
ordered per-GetWave `parameters_out` artifact (including empty blocks) in its
sealed result envelope, together with job/request/DLL/ordered-job-closure
digests and successful Close status. The supervisor receipt carries the
manifest digest and pre/post worker identity. This adapter consumes that typed
handoff only; it does not claim numerical parity or promotion. The vendor DLL
and its AMI model remain an external execution boundary. Because the current
host route does not parse IBIS selection semantics, the `.ibs`, `.ami`, and
DLL entries are a caller-supplied bundle, not a claimed closure-discovery
algorithm. Init-only is explicitly fail-closed; only the nonzero
`block_size_bits` Init+GetWave profile is expressible here.

The closure digest is the exact ordered `job.closure` sequence (IBS then AMI);
the DLL digest is carried separately. The canonical sealed-root path digest is
bound into both launch and job, and job publication is the final ready step.
The V2 job/launch/result schemas are additive; the legacy worker V1 structs
and `supervise_test_only` return type remain unchanged for compatibility.
The external host exports only the explicit V2 adapter result/schema.
The caller-supplied vendor DLL is not part of the closure-discovery claim and its
system runtime dependencies are not included in the sealed closure. TS4 and
any other GetWave-side extension are likewise not included and are not claimed.
Generic model clocks may be empty; this adapter does not claim an RX-clock
guarantee.
The caller owns the init-matrix units, channel ordering (`chnl_h`) and `ts`
interpretation. `InitOut`, `h`, and `out_h` are not returned by this typed
handoff and are not claimed.
The worker path is pre-hashed and rechecked before and after supervision under
the existing non-hostile-writer artifact-root contract; this is not a hostile
writer sandbox or a snapshot/TOCTOU-proof process boundary.
