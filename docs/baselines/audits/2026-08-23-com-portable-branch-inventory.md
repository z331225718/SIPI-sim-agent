# Agent-COM Portable Branch Inventory

固定来源：Agent-COM commit `5272ffe74702cd585054d975559b06f8afae7b6e`，tree
`7094ab6e84989b218730c52432c70da10261f8ea`，MIT。此清单只覆盖可在仓库内
执行的纯 Python/Rust 数值路径，不把 MATLAB、商业 runtime 或缺失 golden
oracle 伪装成完成。

| 上游 reachable path | Rust leaf / API | 语义覆盖 | 当前边界 |
| --- | --- | --- | --- |
| `network/mixed_mode.py` | `sipi-com::com_mixed_mode_v1`, `com_mixed_mode_spectrum_v1`, `apply_r480_pn_skew_v1` | COM_T 四端口变换、SDD21、频率逐点 P/N skew 参数顺序 | 不负责文件读取、port-order 推断或连续频带证明 |
| `signal/interpolation.py` | `sipi-com::s21_to_impulse_dc_v1` 内部策略 | `linear_trend_to_DC`, `linear_trend_to_DC_log_trend_to_inf`, `trend_to_DC`, `extrap_to_DC_or_zero`, `extrap_to_DC`, `old`，以及四类 DC/趋势 phase 策略 | PCHIP 分支按上游最终 linear 输出；超大 FFT 网格有固定预算 |
| `signal/fd_to_td.py` | `sipi-com::s21_to_impulse_dc_v1` | Hermitian IFFT、causality alternating projection、修正/截断 dB、time axis、rectangular pulse；strict S2P/S4P routes 共用已校验 leaf | 不 fit S 参数；不使用 finite-band kernel 或 `NotAssessed` fallback |
| `equalization/ctle.py` | `fd_ctle_v1`, `td_ctle_v1` | CL93/CL120d/CL120e 所需 two-pole/one-zero CTLE | 不负责搜索候选或外部工具校准 |
| `equalization/rx_ffe.py` | `apply_rx_ffe_v1`, `force_rx_ffe_v1`, `force_floating_rx_ffe_v1` | UI-spaced circular FFE、fixed/floating bank solve | Wiener-Hopf 在固定来源中明确未实现，requested branch fail-closed；portable FFE 不隐藏 fallback |
| `equalization/search.py` | `search_r480_nonmmse_no_xtalk_v1` | non-MMSE/no-RxFFE TX-FFE/CTLE/high-pass/cursor/DFE candidate sweep、receiver-noise coupling | 只接受显式 canonical search controls |
| `equalization/mmse.py` | `constrained_mmse_v1`, `search_mmse_candidates_v1` | KKT solve、DFE/RxFFE bound replay、condition/FOM、strict-best candidate reduction、pre/equalized SBR payload | PSD/channel orchestration由调用者显式提供矩阵，不做S参数拟合 |
| `equalization/fvlms_rxffe.py` | `search_fvlms_rxffe_candidates_v1` | fixed/floating force、source FOM evaluator、DFE/jitter/noise/C2M payload、filtered waveform、分量及 total noise、strict-best | 输入为显式有界 candidate grid，避免隐式网络推断 |
| `calibration.py` | `calculate_r480_calibration_noise_v1`, `calibrate_receiver_noise_v1` | calibration channel noise transfer、sigma_bn/sigma_ne/sigma_hp、每 sigma 从 parsed `package_case` pulse/FEXT/NEXT state 重执行同一 channel-producing/reference COM orchestration、step sign/halving outer loop | detached `case_pulses` and precomputed evaluations/case_com_db fail-closed；512 次预算 |
| `equalization/tx_ffe.py`, `equalization/dfe.py`, `signal/filters.py` | existing `sipi-com` TX-FFE/DFE/receiver-noise stages | search loop 的网格、DFE clipping/bounds、Bessel/Butterworth/RC response | 不改 channel resolver |
| `equalization/apply.py` | `apply_r480_equalization_v1` | TX/RX FFE role semantics；NEXT 跳过 TX FFE；三种 CTLE 分支；impulse/pulse 对齐；THRU/FEXT/NEXT 结果接入 COM residual/noise-PDF | 由 canonical JSON `portable.equalization` 触发；候选选择由显式 `portable.search` 分支负责 |
| `noise/discrete_pdf.py` | `sampled_signal_pdf_v1`, `residual_channel_pdf_v1`, `build_r480_noise_pdf_v1`, `combine_r480_noise_pdf_v1` | sampled/residual PDF、FEXT/NEXT phase selection 与 Eq.93A-45 convolution | 复用既有 Rust PDF stages；FFT/fast-noise 外部后端仍 open |
| `metrics/com.py` | `calculate_com_metrics_v1` | C2C/C2M COM/VEC/VEO/threshold DER scalar payload | 输入 PDF 构造由独立 Rust stage 提供 |
| `metrics/tdiln.py` | `r480_tdiln_v1` | complex IL fit、Bessel/TX conditioning、FD-to-TD 两路、pulse/phase PDF/FOM/SNR | 该 fit 仅为 TDILN 报告定义，绝不进入 channel resolver |
| `reporting.py` / `models.py` | `DirectRunReportV1`, result JSON, artifact writer | source/profile/cases/channels/metrics/diagnostics/warnings/provenance/input/report manifest；result/report/diagnostics 三文件原子写 | plotting仅为可选格式 external blocker，manifest明确记录 |
| `api.py` / `pipeline.py` | `run_com_v1`, `load_config_run_com_write_artifacts_v1` | ordered load-config/run/write API；canonical JSON/COM-01 materializer；portable branch diagnostics 接入 payload | MATLAB engine与专有golden不在可分发叶中 |
| `api.py::cases` / `pipeline.py` | `run_package_cases_v1` | bounded multi-package fan-out；每 case 独立 thru/FEXT/NEXT pulse、case/channel/calibration identity、per-case semantic payload | package case 数量与每通道样本受既有 crosstalk budget 限制 |
| `api.py::_run_s2p_erl_only` / `erl/runner.py` / `erl/metric.py` | `portable_branch_result_v1` `erl_only` dispatch | PTDR phase selection、ERL/ERL_RMS/phase/worst-samples、dispatch provenance 与 public result metrics | 当前 JSON impulse route；真实 S2P/S4P reflection reader 仍受 strict input contract 约束 |

## Reachability

COM-02 `sipi-com-direct-run` 和 COM-04 `sipi-com-direct-public-api` 均可从
canonical JSON 的 `portable` 对象触发 `equalization`、`tdiln`、以及
non-MMSE/no-RxFFE `search`，并从
`--fext PATH`/`--next PATH` 加载、校验（包括无拟合 S4P SDD21 aggressor），并通过 residual/noise-PDF 链路影响
COM 指标，同时发布波形语义摘要；`portable.equalization` 的 THRU/FEXT/NEXT
多通道结果同样会接入该链路，而不是只写 diagnostics。频域 JSON 的
`frequency_hz` + `s21` 与 strict Touchstone S2P 均使用同一已校验的
`sipi-com::s21_to_impulse_dc_v1` FD-to-TD leaf（含 causality/truncation
metadata），不使用 finite-band kernel 或 `NotAssessed` fallback。COM-03 comparator 递归比较这些嵌套 payload，波形、
metric、artifact manifest 的变化都会产生 mismatch，而不是只比较退出码。
`package_cases` 会按 source `cases` 语义逐 case fan-out，并为 THRU/FEXT/NEXT
及 calibration channel 发布稳定 identity、digest、sample count；`erl_only`
触发 `r480.erl_only` dispatch 并把 ERL/ERL_RMS/phase/worst-samples 写入
metrics 与 diagnostics。

固定十场景 oracle corpus 另外以 `fext_next` 场景分别传入 CLI 的 JSON
FEXT/NEXT impulse，语义投影只保留 sample count、source kind 与 waveform
digest，避免临时路径污染双独立 replay；`equalization` 场景则覆盖生成的
THRU/FEXT/NEXT Apply_EQ 波形。

## Resource Budgets

每个 channel impulse 文件最多 8 MiB，config 最多 16 MiB，FEXT/NEXT 总数最多
64；result/report/diagnostics 输出上限分别为 16 MiB/64 KiB/256 KiB，FD-to-TD
FFT 单边网格最多 2,097,152 点；portable search 的频率点最多 262,144，TX-FFE
笛卡尔候选最多 1,000,000；MMSE 候选/矩阵维度最多 16,384/512，RxFFE
候选/波形最多 16,384/262,144，calibration outer-loop 最多 512 次。超过
预算在文件解析、请求校验或 artifact 写入前 fail-closed。

## Open / fail-closed

可移植 branch matrix 见
`docs/baselines/audits/2026-08-23-com-02-04-branch-coverage-matrix.v1.yaml`，其
`portable_missing` 为空。plotting 仅因非核心格式 renderer external-blocked；
MATLAB engine 与不可分发 proprietary golden 保持 external-blocked。legacy CSV
输入复用 COM-01 parser，`--legacy-csv` 输出是明确标注的安全 semantic projection，
输出复用上游 `legacy-output-r480.json` 的完整列顺序和 MATLAB scalar/array
serialization；缺少的非核心字段保持空值，不伪造指标。上游
`equalization/wiener_hopf.py` 自身明确抛出 UnsupportedPathError（r4.80 没有
实现），因此作为 source-unimplemented 记录，不计入 portable_missing。
