# S-Parameter Fit Progress And Performance Notes

日期：2026-07-10

本文记录当前生产 S 参数 fitting 基线。更早的 scikit-rf `VectorFitting`、backend 选择、relocation 选择和 `skrf` exporter 说明属于历史调研，不再作为生产用法。

## Production Baseline

`fit-sparam` 的唯一生产 fitting backend 是 Native，基线名为 `native-idem-fast-v1`。

端口规模决定 Native 内部策略：

- 小于 30 ports：使用 full streaming relocation。
- 大于等于 30 ports：优先 reciprocal relocation。
- 大于等于 30 ports 且输入不是 reciprocal：自动 fallback 到 full streaming relocation。

scikit-rf 仍是项目依赖，但只用于非 fitting 辅助能力，例如 Touchstone fallback、metrics、modal/research workflow 和兼容性验证。不要把它描述为已完全移除，也不要把它作为生产 fitting backend。

## Production Command

```powershell
python -m agent_spice.cli fit-sparam .\path\to\model.s30p `
  --rms-target 0.001 `
  --passivity check `
  --max-order 40 `
  --output runs-sparam\model.sp `
  --report runs-sparam\model.json `
  --html-report runs-sparam\model.html `
  --log runs-sparam\model.log
```

需要无源最终模型时：

```powershell
python -m agent_spice.cli fit-sparam .\path\to\model.s30p `
  --rms-target 0.001 `
  --passivity enforce `
  --max-order 40 `
  --output runs-sparam\model_passive.sp `
  --quality-profile signoff `
  --fail-on-quality
```

生产 SPICE 输出固定使用 Native writer，不提供 exporter 选择。外部 IdEM 只用于开发侧 benchmark 和算法研究，不是生产运行时依赖。

## Progress And Debug

`fit-sparam` 支持把生产流程进度写入 `--log`：

```powershell
python -m agent_spice.cli fit-sparam .\tests\fixtures\sparam\simple_through.s2p `
  --rms-target 0.001 `
  --passivity check `
  --max-order 24 `
  --output runs-sparam\simple_through.sp `
  --report runs-sparam\fit_report.json `
  --html-report runs-sparam\fit_report.html `
  --log runs-sparam\fit.log
Get-Content runs-sparam\fit.log -Wait
```

日志包含：

- Touchstone 加载开始/完成。
- Native fitting 开始/完成。
- Native relocation strategy 和 fallback 决策。
- passivity check/enforcement 开始、完成或跳过。
- SPICE、JSON、HTML 写入路径。
- 异常堆栈。

## Quality Gate

默认 `fit-sparam` 是探索模式。自动化或签核场景应显式打开门禁：

```powershell
python -m agent_spice.cli fit-sparam .\model.s2p `
  --rms-target 0.001 `
  --passivity enforce `
  --max-order 24 `
  --output runs-sparam\model.sp `
  --report runs-sparam\fit_report.json `
  --html-report runs-sparam\fit_report.html `
  --log runs-sparam\fit.log `
  --quality-profile signoff `
  --fail-on-quality
```

关键公开参数：

- `--rms-target`：最终模型在原始频点和全部 S 参数通道上的 mean S-RMS 门限。
- `--passivity off|check|enforce`：选择跳过、检查或强制无源。
- `--max-order`：目标搜索允许的最大 effective common-pole order。
- `--quality-profile explore|signoff`：`signoff` 下未知质量项不能 PASS。
- `--fail-on-quality`：质量不是 PASS 时返回非零码；配合 CI 使用。
- `--allow-quality-warnings`：允许 WARN 返回 0，但 FAIL 仍然返回非零码。

## Performance Guidance

当前生产调优应优先围绕目标、阶数和 passivity policy，而不是切换 fitting backend：

对 large-port Native fit，生产 CLI 默认将单个子进程的 BLAS 线程数限制为 `1`。实测 Test3 s166、Test11 s163、Test16 s91 的 `1/8/16/32/64` 矩阵中，`1` 线程始终最快；此前的默认 16-thread OpenBLAS 比 1-thread 慢 `23%` 至 `37%`。使用：

```powershell
agent-spice fit-sparam .\path\to\model.s166p --rms-target 0.001 --passivity enforce --max-order 100
```

该启动器在导入 NumPy 前启动新进程并固定 `OMP_NUM_THREADS`、`MKL_NUM_THREADS`、`OPENBLAS_NUM_THREADS`、`NUMEXPR_NUM_THREADS`。64-core 主机应优先并发多个独立 fit；不要为单个 fit 直接设为 64。只有复现实测矩阵后，才用 `agent-spice --blas-threads N ...` 覆盖默认值。完整证据与可恢复 benchmark 方法见 [Native 线程性能结论](sparam-native-64core-performance.md)。

- 先用 `--passivity check` 建立 order/RMS/passivity 风险，再用 `--passivity enforce` 做签核。
- 对 30-port 以上模型保留 Native 默认策略，让 reciprocal 检测和 full streaming fallback 自动选择路径。
- 用 `--max-order` 控制搜索上限；报告中的 `order_trials` 会记录每个 order 的 RMS、max sigma、耗时和内存。
- 对 CI/signoff 固定 `--rms-target`、`--passivity`、`--max-order` 和 `--quality-profile signoff`，避免依赖隐藏兼容参数。
- 对同一输入的重复生产拟合，只有在上一次完整报告已经证明低阶失败时，才传入 `--min-order N` 跳过这些已知失败 trial；输入、质量门或 Native 代码变更后必须恢复默认 `--min-order 1`。单任务 50% 提速的验证见 [Native 单任务 50% 提速结果](sparam-native-single-fit-50pct.md)。

完整 Native/IdEM 语料 benchmark 见 `docs/sparam-idem-full-benchmark.md`。
