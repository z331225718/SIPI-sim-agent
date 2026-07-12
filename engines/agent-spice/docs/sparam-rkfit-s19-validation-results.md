# s19 RKFIT 固定阶数共享极点验证结果

## 结论

**NO-GO**。官方 RKToolbox 2.9 在 `stable=0`、`reduction=0`、order 74 下，两组冻结初始化都返回了右半平面极点。因此不存在符合主路径纪律的稳定候选，实验按预定规则停止，未执行 full-grid residue LS、passivity enforcement 或低阶运行。

这说明 RKFIT 能把多响应相对 misfit 降到较低水平，但当前无稳定约束的原始极点发现结果不能直接作为 Native 的稳定共享极点集。`stable=1` 会执行极点反射，按 spec 不得用于本次 GO 判定，故未用它补救结果。

## 环境与前置验证

- 数据：s19，19 ports、826 points、361 条矩阵响应。
- 输入 SHA-256：`87fccc96196d8c149d1b3ba985701dd56a78f5d9904984f55f8161c39cdd7c7e`。
- MATLAB：R2024b。
- RKToolbox：官方 2.9，仓库外固定归档 SHA-256 `BEC5E488C47C3FE24D4430FB21C67F8C3A36D8109645C00398FAF8978D77A2DB`。
- 本次 runtime API probe：`which('rkfit')` 与 `which('rkfun/poles')` 分别精确解析到固定工具箱根的 `rkfit.m` 与 `@rkfun/poles.m`；MATLAB version 为 `24.2.0.2712019 (R2024b)`。
- 本次 runtime synthetic smoke：4 个响应、120 个频点、4 个共享极点，恢复误差达到机器精度；`stable=0`、`reduction=0`，misfit `9.8685e-16`。新 wrapper 同时在调用前强制核验上述两个 API 的 canonical path。
- 单元与集成测试：`47 passed`。

## Order 74 结果

| 初始化 | 官方状态 | 最终阶数 | RHP 极点数 | 最大实部（归一化） | 最终 RKFIT misfit | RKFIT 时间 | RKFIT 结束时 MATLAB 已用内存快照 |
|---|---|---:|---:|---:|---:|---:|---:|
| `log_damped` | completed，主路径拒绝 | 74 | 16 | `1.748198e-3` | `0.007934321` | `23.495 s` | `2310.0 MB` |
| `linear_damped` | completed，主路径拒绝 | 74 | 1 | `2.143630e-5` | `0.0003502409` | `22.297 s` | `2319.5 MB` |

两组输出都没有 nonfinite pole，但均违反 `real(pole) < 0`。此外，原始复数多响应计算并未形成可直接规范化的完整共轭 pole 集；即使忽略 RHP 问题，也不能进入要求实系数共享极点的 attribution 主路径。

`linear_damped` 的最终 RKFIT misfit 已低于 IdEM order-74 RMS 数值，但两者不是同一指标：前者是 RKFIT 内部多响应相对 2-norm，后者是最终 S 参数模型 RMS。由于候选在 pole validation 阶段已失败，不能据此声称达到 IdEM 质量。

## 决策边界

- 没有运行 pole flipping、pole reflection、裁剪或 Native/IdEM pole 补齐。
- 没有运行 full-grid residue LS，因此 raw RMS、LS condition 和 residue 指标均为 N/A。
- 没有运行 passivity enforcement，因此 pre/final sigma 与 final RMS 均为 N/A。
- 没有运行 orders `68/60/56`；order 74 未过稳定性首门，按冻结顺序 early stop。
- 机器判定为 `NO-GO / no_stable_order74_candidate`。

## Artifact

运行 artifact 位于未提交目录 `runs-sparam/rkfit-s19-validation/`：

- `toolbox.json`：工具箱归档、解压树与 MATLAB 路径 preflight；
- `preflight/api-probe.json`：本次 MATLAB API 精确解析与版本证据；
- `preflight/synthetic-smoke.json`：本次加固 wrapper 的官方 synthetic smoke；
- `orders/<init>/74/rkfit-invalid.json`：官方原始 completed 输出及全部 poles/misfit/runtime/memory；
- `orders/<init>/74/rkfit.json`：规范化后的结构化拒绝记录；
- `orders/<init>/74/process.json`：完整命令、stdout、stderr 与返回码；
- `summary.json`、`report.md`：机器决策与 summary-only 报告。

`rkfit-invalid.json` 中沿用字段名 `peak_memory_mb` 以保持 artifact 兼容，但新增 `memory_measurement_scope=end_snapshot_matlab`；该值是 RKFIT 结束时 MATLAB `memory` 的进程已用内存快照，不是运行期 peak RSS。

## 路线判断

RKFIT 作为“原始稳定共享极点发现器”在 s19 上终止，不进入 Native 生产化。若未来另行研究稳定 RKFIT，应把稳定性作为算法约束本身重新立项，而不能用 `stable=1` 的事后反射结果替代本次结论。
