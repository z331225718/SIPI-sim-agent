# COM-02 direct-port source map

Scope: the pinned Agent-COM `run_com` channel-to-result boundary.  This is a
per-path source and license audit, not a claim of numerical parity with every
r4.80 branch.  Portable signal/equalization/metric leaves are now direct Rust
ports or existing `sipi-com` reuse and are reachable from the run/API payload:
frequency-domain JSON uses direct FD-to-TD interpolation/IFFT (never a channel
S-parameter fit), optional Apply_EQ covers CL93/CL120d/CL120e with TX/RX FFE
role semantics, the portable non-MMSE/MMSE/RxFFE search loops are reachable
from explicit canonical candidate branches, FEXT/NEXT input waveforms are loaded into
the residual/noise PDF chain and published, and optional TDILN reports expose
fit/ILN/pulse/PDF semantic fields.  Calibration noise/controller and COM-01
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
| `src/agent_com/network/package.py::_selected_package_case` | one-based `pkg_len_select` to zero-based package-case selection used by search SNDR/ACCM consumers; network/package VTF assembly remains outside this leaf | `55e2aae5669c4f3ba7acd453fba82f4eaebfdb4f` | 22300 | `bc3bd4bc3dd01317041a674b88690d6cd94f0589113b44576a1afee4aa8bbd32` | MIT |
| `src/agent_com/network/package.py::_make_full_package,_package_lengths,_package_preset` | audited package VTF/length/preset assembly; blocked because the current Rust S4P route discards the retained FD network after SDD21->impulse and has no TwoPort cascade consumer | `55e2aae5669c4f3ba7acd453fba82f4eaebfdb4f` | 22300 | `bc3bd4bc3dd01317041a674b88690d6cd94f0589113b44576a1afee4aa8bbd32` | MIT |
| `src/agent_com/equalization/mmse.py` | MMSE KKT solve and strict-best search branch | `61c54806da030dac1cb889261f344564c02f38f6` | 33933 | `d0542c3a091b5c79a1ba69270878387326dcb09c6ed2d385667709f541d9f4c9` | MIT |
| `src/agent_com/equalization/fvlms_rxffe.py` | FV-LMS fixed/floating RxFFE candidate search | `525361878ad4802bf9d4968678ebd512b7c7a527` | 19769 | `16943815872c49de3d3f73639a340adbfb635450c5a3b6f9adb3a7009cc4cb59` | MIT |
| `src/agent_com/equalization/tx_ffe.py` | search TX-FFE grid construction | `94c3e72471bfe531d1b2b9a1fd1c45c516ed903c` | 6611 | `17a9b2691fcf0281c2b065eca1fe49897866f743ca5e6bdefabb70270e532e84` | MIT |
| `src/agent_com/equalization/dfe.py` | search DFE clipping and bounds | `a930579b8b71490735c128452f326ecbd94b4b40` | 9190 | `4b9802b343e62b16d9e43341925d92b8e26fd172eb282a36bdaeed1d9019c853` | MIT |
| `src/agent_com/signal/filters.py` | receiver filter primitives used by search | `3c43bf74124fb9264576566841facc5b5259ccd7` | 4734 | `79b3218a1315b53ae0e7e518a43d62e043658c105a7022a0fa868d0b34cb74b6` | MIT |
| `src/agent_com/noise/discrete_pdf.py` | sampled/residual/noise PDF and FEXT/NEXT convolution semantics | `a13466bac4359ea1e3a29f1391604c474f2c46ca` | 23992 | `5bf331e0e515a014fa5f4d938ffe137ac1bf34c97280a19f32455b75d13e485e` | MIT |
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

Package scope is deliberately split: the selector above is reachable by the
existing SNDR/ACCM search consumers and preserves upstream outer-loop order;
the subsequent `package.py` VTF assembly (`_make_full_package`, package
length/preset chains, and S4P cascade) is not claimed here because the current
Rust runtime has no corresponding package-network consumer. The existing
candidate-local JSON package-case route is not used as upstream fan-out or as
an oracle substitute.
