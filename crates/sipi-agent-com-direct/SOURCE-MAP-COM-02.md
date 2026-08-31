# COM-02 direct-port source map

Scope: the pinned Agent-COM `run_com` channel-to-result boundary.  This is a
per-path source and license audit, not a claim of numerical parity with every
r4.80 branch.  Portable signal/equalization/metric leaves are now direct Rust
ports or existing `sipi-com` reuse and are reachable from the run/API payload:
frequency-domain JSON uses direct FD-to-TD interpolation/IFFT (never a channel
S-parameter fit), optional Apply_EQ covers CL93/CL120d/CL120e with TX/RX FFE
role semantics, the portable non-MMSE/MMSE/RxFFE search loops are reachable
from explicit canonical candidate branches, FEXT/NEXT input waveforms are loaded into
the residual/noise PDF chain and published, and explicit `COMPUTE_TDILN` on a
trusted-workbook S4P run composes its raw SDD21 report without exposing a new
JSON input surface.  Calibration noise/controller and COM-01
workbook/CSV ingestion are also reachable. Calibration accepts source S4P
payloads and reruns each package case through the reference COM evaluator at
every sigma; precomputed case evaluations are rejected. Only plotting format, MATLAB
engine, and proprietary golden data remain external blockers.

| Upstream Git path | Reachable role audited | Git blob | Bytes | Content SHA-256 | License |
| --- | --- | --- | ---: | --- | --- |
| `src/agent_com/api.py` | `run_com` public call contract and input validation | `3e7808982a63123f2bac65a86f3abb627c287be1` | 21445 | `b7527f60d55b6f73fb449bc2472f957a6bc2a9ecf1d7bc8808756bf7fba39570` | MIT |
| `src/agent_com/pipeline.py` | channel preparation and dispatcher boundary | `c44f4a5d0e818331e843a888af2083af6c712d04` | 7178 | `6c66e5f99669ddb6b8d9bfa48bfc214339e55fa60128b702047eec490d741a1f` | MIT |
| `src/agent_com/network/mixed_mode.py` | network channel input role | `1e0cc74e9002d424497672a7b72afa9ae0d82052` | 1986 | `392afba5a580ffd7d4a343710ef7ea06b386efe8660dd85cabff1a1c70d7acaf` | MIT |
| `src/agent_com/signal/interpolation.py` | FD-to-TD magnitude/phase interpolation policies used by `fd_to_td.py` | `87898d999ec20ac8f531bba72efbbd83d9e43d43` | 8693 | `eab64c2f260778f468cef50b102749919704420d22914c1302a22a8b94da5a5b` | MIT |
| `src/agent_com/signal/fd_to_td.py` | frequency-domain to time-domain boundary | `6f3af024ea20df0011843ea19a090788f1aabbc9` | 5831 | `703a360837cbaa18494ee03ba8df8d908dc6bf3c516d80d3dddf83af6637c687` | MIT |
| `src/agent_com/equalization/apply.py` | equalization application branch (CL93/CL120d/CL120e + TX/RX FFE) | `07534980f64cbe86b6ceff3c2f5f9107d4fd7b24` | 4246 | `6d9907ce3c12cd6e4e26da2a52e7d474f829ffcecea5dc153086d8a42ef607bb` | MIT |
| `src/agent_com/equalization/ctle.py` | CTLE branch | `5c913f32563ff27cbf62c0ab0e6a8b6150df9ad5` | 1927 | `c79738b504b2967c17a6bb41e4e1f4af8e88566891ab16ba067b893ff20293f6` | MIT |
| `src/agent_com/equalization/rx_ffe.py` | RX FFE branch | `8900bd460c9347ec7551dee4224366fbb24b22df` | 12939 | `4165278cfccf21cf7e32011ecea9f368cf1ae6c442619e059b3d15480a0eb34a` | MIT |
| `src/agent_com/equalization/search.py` | portable non-MMSE/no-RxFFE search loop and receiver filter orchestration | `58f6e5e3f8f36b94faddf0248f3df2ff11e1e3cd` | 53859 | `924930c43332f169ce1d66048d3f70610c8bf459af2f0210d6995533c277003d` | MIT |
| `src/agent_com/equalization/search.py::receiver_noise` | ACCM consumer: passes `ac_common_mode_transfers` into receiver-noise evaluation; nonzero `AC_CM_RMS` without a typed transfer is an explicit source error | `58f6e5e3f8f36b94faddf0248f3df2ff11e1e3cd` | 53859 | `924930c43332f169ce1d66048d3f70610c8bf459af2f0210d6995533c277003d` | MIT |
| `src/agent_com/network/package.py::_selected_package_case,_make_full_package,_package_lengths,_package_preset` | one-based `pkg_len_select` selection plus crate-private DD package VTF/length/preset assembly consumed by the S4P run route | `55e2aae5669c4f3ba7acd453fba82f4eaebfdb4f` | 22300 | `bc3bd4bc3dd01317041a674b88690d6cd94f0589113b44576a1afee4aa8bbd32` | MIT |
| `src/agent_com/network/package.py::assemble_r480_dc_vtf` | pinned DC common-to-differential package VTF; requires full S4P plus DC-mode TX/RX package transforms and `AC_CM_RMS` | `55e2aae5669c4f3ba7acd453fba82f4eaebfdb4f` | 22300 | `bc3bd4bc3dd01317041a674b88690d6cd94f0589113b44576a1afee4aa8bbd32` | MIT |
| `src/agent_com/network/two_port.py` | crate-private checked TwoPort cascade, board insertion, package VTF denominator, exact-zero singular handling | `6b1484effc18a25fe8c28373b47f55b0b99b0f4b` | 9600 | `8889d9695a56d83a59a771d938ba8084dbdfec6a24d79e14d88b83c678ddcd6a` | MIT |
| `src/agent_com/_orchestration.py::_load_s4p_channel,_channel_amplitude,_r480_tdiln_from_network` | typed role ordering and package amplitude selection: WC_PORTZ uses `Tx_rd_sel`, otherwise one-based `pkg_len_select`; only explicit `COMPUTE_TDILN` with raw S4P SDD21 enters the private TDILN report composition, while CSV/TD inputs leave it absent | `5d260a0aab941f1a1955fe3abef36d85a56034c0` | 90877 | `069a5c08f9da6ad5b5be5648723eb05b0e3de8cf0dcb1ae7f54e23df7ab0db69` | MIT |
| `src/agent_com/io/touchstone_r480.py::apply_r480_snp_port_order` | typed workbook S4P file-to-internal port permutation before both DD and SDC mixed-mode transforms | `99300e220c937f9ff73c8e97db47581be2a68241` | 7476 | `f0e037392656a7c70de9a5a2619411f76ae9c940afb4ed3ec44448dc4595fddd` | MIT |
| `src/agent_com/equalization/mmse.py` | MMSE KKT solve and strict-best search branch | `61c54806da030dac1cb889261f344564c02f38f6` | 33933 | `d0542c3a091b5c79a1ba69270878387326dcb09c6ed2d385667709f541d9f4c9` | MIT |
| `src/agent_com/equalization/fvlms_rxffe.py` | FV-LMS fixed/floating RxFFE candidate search | `525361878ad4802bf9d4968678ebd512b7c7a527` | 19769 | `16943815872c49de3d3f73639a340adbfb635450c5a3b6f9adb3a7009cc4cb59` | MIT |
| `src/agent_com/equalization/tx_ffe.py` | search TX-FFE grid construction | `94c3e72471bfe531d1b2b9a1fd1c45c516ed903c` | 6611 | `17a9b2691fcf0281c2b065eca1fe49897866f743ca5e6bdefabb70270e532e84` | MIT |
| `src/agent_com/equalization/dfe.py` | search DFE clipping and bounds | `a930579b8b71490735c128452f326ecbd94b4b40` | 9190 | `4b9802b343e62b16d9e43341925d92b8e26fd172eb282a36bdaeed1d9019c853` | MIT |
| `src/agent_com/signal/filters.py` | receiver filter primitives used by search | `3c43bf74124fb9264576566841facc5b5259ccd7` | 4734 | `79b3218a1315b53ae0e7e518a43d62e043658c105a7022a0fa868d0b34cb74b6` | MIT |
| `src/agent_com/noise/discrete_pdf.py` | sampled/residual/noise PDF and FEXT/NEXT convolution semantics | `a13466bac4359ea1e3a29f1391604c474f2c46ca` | 23992 | `5bf331e0e515a014fa5f4d938ffe137ac1bf34c97280a19f32455b75d13e485e` | MIT |
| `src/agent_com/metrics/c2m.py` | final C2M vertical-eye reduction for nonzero `T_O` | `00c911bf4046fc1928cb2c35ebfec99877df465c` | 26089 | `52d8ad927a4f2a8c318fdd8f9171ea0ef8b2b789b75d9df54ce0c214591dd2f4` | MIT |
| `src/agent_com/metrics/com.py` | COM metric payload names and values | `c1c2d976615806910d3e9dab221641c318c4297a` | 2932 | `46727c06b46d4cb91b330bf5b26ea269d882050cf809c3c946fc2ad37b8920ea` | MIT |
| `src/agent_com/metrics/tdiln.py` | TDILN metric branch (complex IL fit + pulse/PDF report) | `53aacf1c15b57cf314f0e7db5148884bf7afe3c2` | 7068 | `d0465246f6fd5d22d5978f5cdf2a78f7fccdfbfdd7ad0676092b4494d3698873` | MIT |
| `src/agent_com/runtime.py` | provenance, warnings, and run lifecycle | `89a1866b7d81a25653bcc9ef69adaf91fbf46cb1` | 6077 | `490a02e5bbb9af30278445b8f964a9d04d617ddf20c1773a5cd51a4b1ec5fd42` | MIT |
| `src/agent_com/calibration.py` | calibration channel noise and receiver-noise outer loop | `e48994720dfae9aab0aceecff4b7677383f06648` | 6979 | `e97f0d1ee1dc563604e5954b664b465048fe431f69deed7ac580598cccf0b9a8` | MIT |
| `src/agent_com/erl/metric.py` | ERL PTDR phase/PDF selector and ERL/ERL_RMS semantics | `ee809c9f464583b850c3e585adc8a3cfc981729b` | 4029 | `4051b618324448f4968e59fbb81358eb6b62bdd58e94ddf9ab67e8cfde09b3b5` | MIT |
| `src/agent_com/erl/runner.py` | ERL runner dispatch and PTDR metric orchestration | `61d9e0cf56ce4f59b258c6d71a452a3fc762c84e` | 4974 | `b481c54c448314e926680954249ffbc7e1c963c244a1f6e2584f3a7e3d25791d` | MIT |
| `src/agent_com/erl/tdr.py` | TDR/PTDR waveform construction consumed by ERL | `fa72425790bed2c2380dc62830573eb3fe05fded` | 8007 | `b26ab25ac756592f20eb198e949fb282772ea54e84ba333566314c7abff9251d` | MIT |
| `src/agent_com/api.py::cases` / `src/agent_com/pipeline.py` | package-case fan-out and per-case channel orchestration | `3e7808982a63123f2bac65a86f3abb627c287be1` / `c44f4a5d0e818331e843a888af2083af6c712d04` | 21445 / 7178 | `b7527f60d55b6f73fb449bc2472f957a6bc2a9ecf1d7bc8808756bf7fba39570` / `6c66e5f99669ddb6b8d9bfa48bfc214339e55fa60128b702047eec490d741a1f` | MIT |
| `src/agent_com/legacy_csv.py` | source-frozen legacy output column order and MATLAB scalar/array serialization | `48b18486fc9894022200b68b0d9aed8aedf56796` | 3603 | `6afe8a86318d6614475bd1ffbbb3fd0e3e06cd0bd42ede4fa84cfbc88704dc1a` | MIT |
| `src/agent_com/reporting.py` | result payload and artifact boundary | `efbb14dda4d656a71e6915f5c5026b719e22d141` | 82620 | `14c4e4f0e5e51ee6fe76343ef133a565b8c922a0794acfe6c36ac3c7bbc1a0e1` | MIT |

The source is fixed at commit `5272ffe74702cd585054d975559b06f8afae7b6e`
(tree `7094ab6e84989b218730c52432c70da10261f8ea`) and is MIT. No upstream
Python, workbook, MATLAB, or result payload is vendored. FEXT/NEXT waveform
inputs are integrated through the direct-port `noise/discrete_pdf.py`
residual/noise-PDF stages; FD-to-TD (including its interpolation helper),
Apply_EQ, non-MMSE/MMSE/RxFFE candidate search, TDILN, calibration noise and
controller, and the COM-01 config/CSV reuse are portable semantic branches.
The legacy CSV artifact uses the source-frozen `legacy-output-r480` columns and
MATLAB-compatible scalar/array serialization.  Portable metrics populate known
columns; unavailable non-core fields remain explicit empty cells.  Plotting
format, external MATLAB, and proprietary golden data remain external blockers;
the pinned upstream Wiener-Hopf module is recorded as source-unimplemented.

The source-unimplemented row is `src/agent_com/equalization/wiener_hopf.py`
(blob `f628275663c2c11e386d52bbe2aaa608f6e07ba0`, 481 bytes,
SHA-256 `42568dce88669a1b443b7402561b731f4c41293284cd836ed673b8143a21f0fc`).
Its only public function raises `UnsupportedPathError` because r4.80 has no
Wiener-Hopf implementation; the direct leaf rejects that request rather than
inventing a solver.

The final fixed-DFE PDF path now consumes an additive opaque V2 Rust winner
handoff carrying the winning candidate's cursor, DFE taps/bounds, and
selected noise value. Its winner fields are private and it is not a request
or JSON wire surface. This matches `equalization/search.py::_peak_window` and
`noise/discrete_pdf.py::residual_channel_pdf`: normalized DFE bounds are
scaled by the selected cursor voltage before clipping. The final chain keeps
the winning candidate's `cand.sbr` coordinates without a second centering or
padding offset, and does not reselect the peak or accept a public
`cursor_index` control. This is a focused
runtime correction for the COM/sigma divergence; it does not alter the search
FOM, add a public control, fit S-parameters, or create a second channel path.

For the pinned C2M final-report branch, the opaque winner also owns a separate
final THRU pulse. It equals the selected search pulse except when source
controls simultaneously require nonzero `T_O`, zero `Min_VEO_Test`, and
floating DFE. In that branch the already-converted, already-truncated THRU
impulse is zero-padded to the selected SBR length and the winning CTLE,
high-pass, and TX-FFE settings are reapplied once, matching
`_orchestration.py::_full_tail_c2m_thru_pulse`. The final COM chain reuses the
existing `calculate_c2m_vertical_eye_v1` port and the winner's DFE/noise state;
the selected search pulse and FOM remain unchanged. This does not reread S4P,
perform another FD-to-TD conversion, or fit an S-parameter model.

Package scope is deliberately split: the selector above is reachable by the
existing SNDR search consumers. The direct S4P route admits the typed
package-case outer loop one case at a time; each selected case carries its
`pkg_len_select`, TX-FFE preset, and role amplitude (`a_thru`, `a_fext`, or
`a_next`) into the same evaluator. Missing or mismatched case controls fail
closed rather than falling back to case zero.
The subsequent `package.py` VTF assembly (`_make_full_package`, package
length/preset chains, board insertion, and S4P cascade) is now a crate-private
consumer of the typed S4P run route. It preserves the upstream order:
mixed-mode TwoPort conversion, optional board insertion, kappa reflection
scaling, package/VTF and RX-port flip, transmitter transition filter, optional
receiver-filter product and package TX-FFE preset, one role amplitude applied
to the final impulse voltage, and only then publication to the COM chain. The
admitted single-file route is typed THRU/DD; request FEXT/NEXT files use their
typed request role. It does not accept ad-hoc JSON `channel_type`,
`package_mode`, or `include_die` keys.
FD-to-TD reads only resolved workbook controls (`sample_dt`, interpolation
magnitude/phase, causality, EC tolerances, truncation, and DEBUG); candidate
local top-level `fd_to_td`/`defaults` controls are rejected. Package-case
selection is bounded before allocation and applies the selected case's
role-specific amplitude after the one impulse conversion. The package-case
index is an internal outer-loop token, never caller JSON. A direct S4P request
without that token admits only exact single-case selection. The current public
S4P workflow is single request plus typed
THRU/FEXT/NEXT files; JSON package-case fan-out remains the existing bounded
case runner, not a claim of general upstream package API parity.
`INC_PACKAGE=false` still admits the board FD path and the typed role amplitude
is applied after its final FD-to-TD conversion. The current additive ACCM scope
is limited to the typed receiver-noise transfer leaf. For nonzero resolved
`AC_CM_RMS`, the crate-private S4P route extracts SDC at the four source indices,
skips DD board/kappa, applies the common-mode TX package plus DD RX package, and
passes every loaded THRU/FEXT/NEXT transfer to the existing receiver-noise
consumer. Its frequency axis is stored with the transfer and must exactly match
the search noise axis; disabled package, selected-case errors, missing/non-S4P
role transfers, axis mismatch, and unsupported TD/calibration combinations fail
closed. The pinned canonical `cd_cm_rms` and `sigma_AC_CCM_at_rxpkg_output_mV`
result fields remain open and are not claimed here; no SDD21 fallback, untyped
JSON field, or S-parameter fit is introduced.
Malformed controls, unsupported channel roles, non-rectangular package
matrices, singular denominators, and numeric budget violations fail closed.
Focused Rust tests cover the pinned algebraic checkpoints and negative
controls; no clean-archive Python numeric replay is claimed by this source map.
The Rust cascade uses exact-zero singular rejection per the SIPI channel
policy; upstream's internal nonzero denominator guard is therefore not a
bit-identical acceptance claim.
The existing candidate-local JSON package-case route is not used as upstream
fan-out or as an oracle substitute.

The ACCM transfer is consumed by the existing receiver-noise search path; no
public diagnostics field is added for the intermediate transfer. An unbound
local CLI observation using the pinned 100G workbook and pinned four-port S4P
completed the two workbook package cases with the workbook's original
AC_CM_RMS=[0,0] controls. A separate manual observation used an explicit
caller override AC_CM_RMS=[0,0.02] and saw the selected case change FOM/COM and
sigma_N; that override is a test control, not a production default or a claim
about the workbook's original values. These observations are not clean-archive
receipts, upstream numeric parity, or release evidence; the noncanonical
explicit nonzero override/manual observation and canonical `cd_cm_rms` fields
remain unclaimed.

The focused `run_v1::tests::public_s4p_package_workflow_consumes_delayed_lowpass_and_roles`
is a scoped synthetic workflow checkpoint, not upstream numeric parity: it uses
64-point, 100 ps delayed low-pass S4P input through the public run/artifact
boundary, checks the package VTF FD-to-TD impulse source kind, 1 ps sample
interval and 1000-point published impulse receipt, and integrates the same
typed S4P input as FEXT/NEXT.  It also reruns the workflow with `a_thru` 0.5
and 1.0, checking exact two-times internal impulse samples plus changed
impulse/COM digests.  This is a bounded synthetic E2E nonclaim, not a claim of
full upstream package or numeric COM parity.

## Workbook-to-search crosswalk

The workbook-backed S4P route has a crate-private source-derived crosswalk
from COM-01 materialization into the existing `portable.search` consumer. It
does not add a public JSON field or a default profile: every required search,
receiver, candidate, CTLE, package selector, and ACCM control must be present
in the materialized workbook map, finite, and alias-consistent. The S4P axis
is read once from the staged input bytes and copied into the search frequency,
noise, and crosstalk axes; a changed file or an axis mismatch fails closed.
For a trusted materialized workbook, the source-exact (case-sensitive)
`snpPortsOrder` key is required and its one-based permutation is applied to
the parsed single-ended matrix before the mixed-mode package VTF and SDC
paths. Any case-fold duplicate is rejected. Public/legacy JSON cannot opt
into this workbook-only control: an injected key is rejected and JSON without
it retains its existing internal-order contract.
The dynamic TX grid preserves the pinned workbook's `cm1/cm2/cm3/cp1` value
arrays, while `tx_ffe_c0_min` remains the source cursor admission scalar and is
not invented as a separate grid. `dfe_first_max` is the first source `bmax`
entry, matching the pinned search evaluator. CTLE `f_HP` is preserved as the
corner-frequency vector, while `g_DC_HP_values` is carried separately as the
CL120d gain-candidate vector; they are not interchangeable. `AC_CM_RMS`, `ACCM_MAX_Freq`, and
`pkg_len_select` are cross-checked against the receiver consumer only when the
selected resolved ACCM value is nonzero.

The pinned source/control anchors used for this mapping are:

| Input or source path | Role | Git blob | Bytes | Raw SHA-256 | License |
| --- | --- | --- | ---: | --- | --- |
| `matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx` | pinned 100G materialized workbook input | `22b633b6092b4b0de0ca89273515329b362eabae` | 67087 | `e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925` | MIT project asset |
| `fixtures/synthetic/kappa_asymmetric_reflective_10db_at_26p56ghz.s4p` | pinned S4P frequency-axis/input fixture | `a1fe8618043b31f63dfb24454ac1d296000010c0` | 6457063 | `3a563543ba664fcc04c1ac5603ad305cb0b1d110c3d9020727444b1c3fd2d0ec` | MIT project asset |
| `src/agent_com/api.py` | workbook materialize/prepare-run entry path | `3e7808982a63123f2bac65a86f3abb627c287be1` | 21445 | `b7527f60d55b6f73fb449bc2472f957a6bc2a9ecf1d7bc8808756bf7fba39570` | MIT |
| `src/agent_com/_orchestration.py` | materialized parameter and receiver/search orchestration | `5d260a0aab941f1a1955fe3abef36d85a56034c0` | 90877 | `069a5c08f9da6ad5b5be5648723eb05b0e3de8cf0dcb1ae7f54e23df7ab0db69` | MIT |
| `src/agent_com/equalization/search.py` | source search/receiver-noise consumer | `58f6e5e3f8f36b94faddf0248f3df2ff11e1e3cd` | 53859 | `924930c43332f169ce1d66048d3f70610c8bf459af2f0210d6995533c277003d` | MIT |
| `tests/test_snp_ports_order.py` | source-derived ACCM package-path checkpoint | `73da0a892e7d78781ffb1077c56977ee54632889` | 41262 | `0dbbbbcc7e5188371da1b2014168c4f1c707d510f6fe360c1377c620de420b69` | MIT |

This is a scoped pinned-100G materialization route, not a claim of global
workbook coverage or upstream numeric parity. Missing workbook controls,
unsupported data-rate/case shapes, and nonzero ACCM without a real S4P
transfer remain fail-closed/open; canonical upstream `cd_cm_rms` and global
numeric parity remain unclaimed. S-parameter fitting remains forbidden and the
channel boundary remains the existing single final FD-to-TD impulse leaf.

## Pinned MATLAB warning surface

The original R4.80 MATLAB reader is separately pinned by the authorized
`com-r480-matlab-source` record: `matlab_src/com_ieee8023_480.m`, SHA-256
`642b28910a6fccca4682aa0a66a6a6c00633a14c17d05d8d6ee73d2808954cad`.
The trusted-workbook S4P read path ports one exact static predicate from that
file: `Sch.freq(end) < param.fb` at source line 9715. It publishes repeated
`COM:read_s4p:MaxFreqTooLow` events in THRU/FEXT/NEXT read order, retaining the
raw pre-interpolation maximum frequency, signalling rate, source hash, and no
absolute path. The result root's `warnings` array contains only such
source-mapped events. Each result case's
`diagnostics.sipi_runtime_observations` array retains useful SIPI phase-slope
diagnostics, but those observations explicitly do not claim source-warning
equivalence and never participate in source warning parity.

The source-local MATLAB observer is intentionally bounded to static emission
calls in that pinned file. `tools/compare_com_source_warning_observation.py`
fails closed for an observed but unmapped callsite (including the currently
unported identifier-less anti-causal warning at line 6337); it does not claim a
complete MATLAB, toolbox, or runtime warning catalog.

For that unported branch, the observer now records a bounded summary of the
caller-local `interp_Sparam` `Sin` input only at the pinned line 6337: sample
count, endpoint and sum components, and the exact positive-mean-unwrapped
phase predicate.  An R2024b original-13 index-08 observation captured one such
source input with 8,001 samples and mean phase step
`1.3335561211958429`.  This establishes the source-local stage and an input
fingerprint for follow-up work, but it is not yet a Rust mapping: the complete
five-workbook occurrence set, source-stage trace identity, and event ordering
must agree before this identifier-less warning can leave
`sipi_runtime_observations` and enter root `warnings`.
