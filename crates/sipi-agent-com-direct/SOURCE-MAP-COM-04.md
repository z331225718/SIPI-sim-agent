# COM-04 direct-port source map

Scope: the pinned public API sequence `load_config -> run_com ->
write_artifacts`.  The direct leaf preserves the upstream result payload
semantics that matter to callers: source/profile, contiguous cases, channel
identity, metrics, diagnostics, warnings, provenance, input manifest, report
manifest, and deterministic artifact names.  It uses the existing Rust config
materializer and COM execution core; a canonical JSON parameter document is
also admitted for a bounded API test fixture.  The portable mixed-mode,
FD-to-TD, Apply_EQ, residual/noise-PDF, COM metric, TDILN, MMSE/RxFFE search,
calibration controller, and COM-01 workbook/CSV paths reachable from that
document are listed below rather than being hidden behind a COM-02-only status
envelope.  Plotting format, MATLAB engine, and proprietary golden data remain
explicit external blockers.

| Upstream Git path | Reachable role audited | Git blob | Bytes | Content SHA-256 | License |
| --- | --- | --- | ---: | --- | --- |
| `src/agent_com/__init__.py` | public symbol exposure | `19942e5cc8e9ffa6572dd0ee6fc0861250ccf58b` | 1719 | `0608729cb58b26107264c005cb362f713635783cca01f70967ecf0fa8253a0e0` | MIT |
| `src/agent_com/api.py` | `load_config`, `run_com`, and API validation | `3e7808982a63123f2bac65a86f3abb627c287be1` | 21445 | `b7527f60d55b6f73fb449bc2472f957a6bc2a9ecf1d7bc8808756bf7fba39570` | MIT |
| `src/agent_com/models.py` | `RunResult`, `CaseResult`, channels, profile, and artifact payload model semantics | `92167e385db50c76a9999c2df5118d46951b8243` | 6994 | `e97bd1c67fbf53f940e45fb94905e6bd5e924b164a3eecf1548a652ba0f327af` | MIT |
| `src/agent_com/config/excel.py` | workbook source loading boundary | `1cce4365b64f3bb0ef1f7617107d2df4c929afc7` | 12218 | `2886e9986b9c3a7c1fbdc6179878679ae26bb92f511c6b0689644f9a6c053c4d` | MIT |
| `src/agent_com/config/materialize.py` | source-order materialization and defaults | `a8856f91fe9208738446f539aa52ade2ea2c0bcf` | 19030 | `42f85e3cd5df74158acc10b9388f663419740b374756cdbd8332f052063d265c` | MIT |
| `src/agent_com/pipeline.py` | channel/run dispatch | `c44f4a5d0e818331e843a888af2083af6c712d04` | 7178 | `6c66e5f99669ddb6b8d9bfa48bfc214339e55fa60128b702047eec490d741a1f` | MIT |
| `src/agent_com/network/mixed_mode.py` | portable COM_T/SDD21 and P/N skew branch reachable from canonical API input | `1e0cc74e9002d424497672a7b72afa9ae0d82052` | 1986 | `392afba5a580ffd7d4a343710ef7ea06b386efe8660dd85cabff1a1c70d7acaf` | MIT |
| `src/agent_com/signal/interpolation.py` | FD-to-TD magnitude/phase interpolation policies | `87898d999ec20ac8f531bba72efbbd83d9e43d43` | 8693 | `eab64c2f260778f468cef50b102749919704420d22914c1302a22a8b94da5a5b` | MIT |
| `src/agent_com/signal/fd_to_td.py` | portable frequency-domain to impulse channel route, without S-parameter fit | `6f3af024ea20df0011843ea19a090788f1aabbc9` | 5831 | `703a360837cbaa18494ee03ba8df8d908dc6bf3c516d80d3dddf83af6637c687` | MIT |
| `src/agent_com/equalization/apply.py` | CL93/CL120d/CL120e Apply_EQ and TX/RX FFE role semantics | `07534980f64cbe86b6ceff3c2f5f9107d4fd7b24` | 4246 | `6d9907ce3c12cd6e4e26da2a52e7d474f829ffcecea5dc153086d8a42ef607bb` | MIT |
| `src/agent_com/equalization/ctle.py` | portable CTLE response branch reused by Apply_EQ | `5c913f32563ff27cbf62c0ab0e6a8b6150df9ad5` | 1927 | `c79738b504b2967c17a6bb41e4e1f4af8e88566891ab16ba067b893ff20293f6` | MIT |
| `src/agent_com/equalization/rx_ffe.py` | portable RX FFE filtering branch reused by Apply_EQ | `8900bd460c9347ec7551dee4224366fbb24b22df` | 12939 | `4165278cfccf21cf7e32011ecea9f368cf1ae6c442619e059b3d15480a0eb34a` | MIT |
| `src/agent_com/equalization/search.py` | portable non-MMSE/no-RxFFE search loop and receiver filter orchestration | `58f6e5e3f8f36b94faddf0248f3df2ff11e1e3cd` | 53859 | `924930c43332f169ce1d66048d3f70610c8bf459af2f0210d6995533c277003d` | MIT |
| `src/agent_com/equalization/mmse.py` | MMSE KKT solve and strict-best search branch | `61c54806da030dac1cb889261f344564c02f38f6` | 33933 | `d0542c3a091b5c79a1ba69270878387326dcb09c6ed2d385667709f541d9f4c9` | MIT |
| `src/agent_com/equalization/fvlms_rxffe.py` | FV-LMS fixed/floating RxFFE candidate search | `525361878ad4802bf9d4968678ebd512b7c7a527` | 19769 | `16943815872c49de3d3f73639a340adbfb635450c5a3b6f9adb3a7009cc4cb59` | MIT |
| `src/agent_com/equalization/tx_ffe.py` | search TX-FFE grid construction | `94c3e72471bfe531d1b2b9a1fd1c45c516ed903c` | 6611 | `17a9b2691fcf0281c2b065eca1fe49897866f743ca5e6bdefabb70270e532e84` | MIT |
| `src/agent_com/equalization/dfe.py` | search DFE clipping and bounds | `a930579b8b71490735c128452f326ecbd94b4b40` | 9190 | `4b9802b343e62b16d9e43341925d92b8e26fd172eb282a36bdaeed1d9019c853` | MIT |
| `src/agent_com/signal/filters.py` | receiver filter primitives used by search | `3c43bf74124fb9264576566841facc5b5259ccd7` | 4734 | `79b3218a1315b53ae0e7e518a43d62e043658c105a7022a0fa868d0b34cb74b6` | MIT |
| `src/agent_com/noise/discrete_pdf.py` | sampled/residual/noise PDFs and FEXT/NEXT convolution semantics | `a13466bac4359ea1e3a29f1391604c474f2c46ca` | 23992 | `5bf331e0e515a014fa5f4d938ffe137ac1bf34c97280a19f32455b75d13e485e` | MIT |
| `src/agent_com/metrics/com.py` | COM/VEC/VEO scalar payload semantics | `c1c2d976615806910d3e9dab221641c318c4297a` | 2932 | `46727c06b46d4cb91b330bf5b26ea269d882050cf809c3c946fc2ad37b8920ea` | MIT |
| `src/agent_com/metrics/tdiln.py` | portable TDILN fit/filter/pulse/PDF report fields | `53aacf1c15b57cf314f0e7db5148884bf7afe3c2` | 7068 | `d0465246f6fd5d22d5978f5cdf2a78f7fccdfbfdd7ad0676092b4494d3698873` | MIT |
| `src/agent_com/reporting.py` | `_result_payload`, `write_artifacts`, and report semantics | `efbb14dda4d656a71e6915f5c5026b719e22d141` | 82620 | `14c4e4f0e5e51ee6fe76343ef133a565b8c922a0794acfe6c36ac3c7bbc1a0e1` | MIT |
| `src/agent_com/runtime.py` | provenance and warnings | `89a1866b7d81a25653bcc9ef69adaf91fbf46cb1` | 6077 | `490a02e5bbb9af30278445b8f964a9d04d617ddf20c1773a5cd51a4b1ec5fd42` | MIT |
| `src/agent_com/calibration.py` | calibration channel noise and receiver-noise outer loop | `e48994720dfae9aab0aceecff4b7677383f06648` | 6979 | `e97f0d1ee1dc563604e5954b664b465048fe431f69deed7ac580598cccf0b9a8` | MIT |
| `src/agent_com/legacy_csv.py` | source-frozen legacy output column order and MATLAB scalar/array serialization | `48b18486fc9894022200b68b0d9aed8aedf56796` | 3603 | `6afe8a86318d6614475bd1ffbbb3fd0e3e06cd0bd42ede4fa84cfbc88704dc1a` | MIT |
| `src/agent_com/_orchestration.py` | pure dispatcher and calibration/search ordering audit | `5d260a0aab941f1a1955fe3abef36d85a56034c0` | 90877 | `069a5c08f9da6ad5b5be5648723eb05b0e3de8cf0dcb1ae7f54e23df7ab0db69` | MIT |
| `src/agent_com/erl/metric.py` / `src/agent_com/erl/runner.py` | ERL-only dispatch and semantic ERL payload | `ee809c9f464583b850c3e585adc8a3cfc981729b` / `61d9e0cf56ce4f59b258c6d71a452a3fc762c84e` | 4029 / 4974 | `4051b618324448f4968e59fbb81358eb6b62bdd58e94ddf9ab67e8cfde09b3b5` / `b481c54c448314e926680954249ffbc7e1c963c244a1f6e2584f3a7e3d25791d` | MIT |
| `src/agent_com/api.py::cases` / `src/agent_com/pipeline.py` | multi-package case fan-out and channel/calibration identity | `3e7808982a63123f2bac65a86f3abb627c287be1` / `c44f4a5d0e818331e843a888af2083af6c712d04` | 21445 / 7178 | `b7527f60d55b6f73fb449bc2472f957a6bc2a9ecf1d7bc8808756bf7fba39570` / `6c66e5f99669ddb6b8d9bfa48bfc214339e55fa60128b702047eec490d741a1f` | MIT |

The source is fixed at commit `5272ffe74702cd585054d975559b06f8afae7b6e`
(tree `7094ab6e84989b218730c52432c70da10261f8ea`) and is MIT.  The Rust
workflow atomically replaces the artifact directory with `result.json`,
`report.html`, `diagnostics.json`, and optional `legacy.csv`.  Workbook/CSV/MAT loading reuses the COM-01 materializer;
the listed portable branches contribute semantic result/diagnostic fields and,
where applicable, the COM metric chain.  The legacy CSV writer uses the
source-frozen column schema and MATLAB-compatible scalar/array serialization;
unknown non-core fields are explicit empty cells.  Plotting format, MATLAB
engine, and proprietary golden data remain external blockers, while the pinned
upstream Wiener-Hopf module is recorded as source-unimplemented.  No upstream
source or golden payload is copied into the candidate.

The source-unimplemented row is `src/agent_com/equalization/wiener_hopf.py`
(blob `f628275663c2c11e386d52bbe2aaa608f6e07ba0`, 481 bytes,
SHA-256 `42568dce88669a1b443b7402561b731f4c41293284cd836ed673b8143a21f0fc`).
Its only public function raises `UnsupportedPathError` because r4.80 has no
Wiener-Hopf implementation; the public API rejects that request rather than
inventing a solver.

For trusted workbook runs only, the dynamic-TXFFE lookup in the separately
authorized MATLAB source `matlab_src/com_ieee8023_480.m:10494-10515`
(raw SHA-256 `642b28910a6fccca4682aa0a66a6a6c00633a14c17d05d8d6ee73d2808954cad`)
uses `eval` on a string cell. `run_v1.rs` preserves only the four dynamic
tap-cell lexemes (`c(-1)`, `c(-2)`, `c(-3)`, `c(1)`) privately and accepts a
bounded plain decimal `start:step:end` grid at that direct-runtime boundary.
It does not change the public COM-01 Python-compatible materialization JSON
or fingerprint, does not extend JSON/override inputs, and rejects any other
expression. This narrow rule exists because the Python materializer's binary
range arithmetic is not raw-f64 identical to the MATLAB runtime grid.
