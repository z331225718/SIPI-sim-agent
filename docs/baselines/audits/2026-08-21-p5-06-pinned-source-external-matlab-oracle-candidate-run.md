# P5-06 pinned-source external MATLAB oracle candidate run

状态：`pinned_source_external_matlab_oracle_candidate_run_observed`。这是一份
candidate observation，不是 authoritative、acceptance 或 release 证据；对应的
checked-in document gate 是
[`p5-06-pinned-source-external-matlab-oracle-candidate-run.v1.yaml`](../p5-06-pinned-source-external-matlab-oracle-candidate-run.v1.yaml)，独立 verifier 是
`tools/verify_p5_06_pinned_source_external_oracle_candidate_document.py`。

## 身份与来源

- canonical origin：`https://github.com/z331225718/agent-com.git`
- commit：`5272ffe74702cd585054d975559b06f8afae7b6e`
- tree：`7094ab6e84989b218730c52432c70da10261f8ea`，object format：`sha1`
- `matlab_src/com_ieee8023_480.m` Git blob：
  `2e226d785c1ed2403f6d0a11288bf75939021814`，normalized SHA-256
  `88db14d7d82dab980d223a5be02a28013c11e0d0239e0e97e36c9d36fef55596`
- source checkout 在观察时为 dirty；因此使用 pinned Git object 作为 source anchor，
  不使用 `code_revision` 作为权威身份。
- 四个 oracle tool Git object 及 normalized SHA-256 已在 YAML 中逐项锁定；instrumentation
  generator object 也已锁定，但 generated output 未 Git-bound。

## 候选运行观察

场景为 F01、单 case、MATLAB R2024b；记录了 MLSE 路由、DER/CDR 门控、14 个输出
指标、6 个 MLSE checkpoint、`1e-12` metric repeatability tolerance、network SDD
`1e-12` 与 SDC `1e-14` 容差。观察到的 warning 是
`MLSE truncation failed. Try increasing trunc`；这不是完整 warning contract。

`manifest.json`、`comparison_report.json`、invocation/summary、MATLAB v7.3 result、
log 与 `case-001-core.mat` 共 7 个文件仅按 YAML 中的 exact SHA-256 和 byte size 锁定。
HDF5 结构预算锁定为 result 112 fields、summary 13、MLSE 10、core output_args 112，
checkpoint 14,275 个且预算上限 15,000；JSON 与日志读取均有 64 KiB budget。

## 尚未闭合

config/fixture、generated instrumented output、MATLAB invocation authorization 与
startup isolation 尚未形成完整 Git-bound provenance；完整 warning、checkpoint 对齐
容差、Rust MATLAB v7.3 result reader、product parity、IEEE certification、release
acceptance 仍未声明。动态 external verifier 不能替代 checked-in baseline document gate，
P5-06 主项仍保持 blocked。
