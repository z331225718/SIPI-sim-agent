# S-Parameter Fit Progress And Performance Notes

日期：2026-07-02

下一阶段质量门禁计划见 `docs/sparam-quality-gate-plan.md`。

19-port PDN 样例的完整调参记录见 `docs/sparam-19port-fit-case-study.md`。

全部本地 S 参数的批量 fit 摸底记录见 `docs/sparam-batch-fit-results.md`。

30-port PDN 的目标频段 PASS 命令：

```powershell
python -m agent_spice.cli fit-sparam user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p --output runs-sparam/attack-30port/order120-scale0992-bandpass/model.sp --report runs-sparam/attack-30port/order120-scale0992-bandpass/fit_report.json --html-report runs-sparam/attack-30port/order120-scale0992-bandpass/fit_report.html --log runs-sparam/attack-30port/order120-scale0992-bandpass/fit.log --quality-profile signoff --fail-on-quality --model-order-max 120 --target-error 0.005 --skip-passivity-enforce --response-scale 0.992 --passivity-check-f-max 2000000000 --quality-max-frequency-points 16 --max-comparison-rms-error 0.05 --require-dc --subckt-name s_5power_30port_order120_scale0992_bandpass
```

## 进度与 Debug

`fit-sparam` 支持把进度和 scikit-rf 内部 `skrf.vectorFitting` 日志写入文件：

```powershell
python -m agent_spice.cli fit-sparam .\tests\fixtures\sparam\simple_through.s2p --output runs-sparam/simple_through.sp --report runs-sparam/fit_report.json --html-report runs-sparam/fit_report.html --log runs-sparam/fit.log
Get-Content runs-sparam/fit.log -Wait
```

日志包含：

- Touchstone 加载开始/完成。
- Vector fitting 开始/完成。
- scikit-rf 内部 pole relocation 日志。
- passivity enforcement 开始/完成或跳过。
- SPICE、JSON、HTML 写入路径。
- 异常堆栈。

## 质量门禁

默认 `fit-sparam` 是探索模式：即使报告里出现 `WARN` 或 `FAIL`，命令也会保持原有工作流，继续写出 `.sp`、JSON、HTML 和日志。自动化或签核场景应显式打开门禁：

```powershell
python -m agent_spice.cli fit-sparam .\model.s2p --output runs-sparam/model.sp --report runs-sparam/fit_report.json --html-report runs-sparam/fit_report.html --log runs-sparam/fit.log --quality-profile signoff --fail-on-quality --max-comparison-rms-error 0.05 --require-dc
```

关键参数：

- `--quality-profile explore|signoff`：`signoff` 下未知质量项不能 PASS。
- `--fail-on-quality`：质量不是 PASS 时返回非零码；配合 CI 使用。
- `--allow-quality-warnings`：允许 WARN 返回 0，但 FAIL 仍然返回非零码。
- `--max-comparison-rms-error`：原始频点对比 RMS 的门限。
- `--max-z-comparison-rms-error`：原始频点 Z 参数幅值对比 RMS 的门限，单位 Ohm。
- `--max-z-log-magnitude-rms-error`：原始频点 `log10(|Zfit| / |Zorig|)` RMS 门限，单位 decades。PDN 阶数筛选优先用这个指标；绝对 Ohm RMS 容易被接近奇异的 Z 转换点支配。
- `--z-required-for-signoff`：把 Z 参数误差作为 signoff 主门禁。适合 PDN 场景；此时 S 参数误差仍会报告，但不再作为主要阻断项。
- `--max-passivity-epsilon`：输入采样最大奇异值检查的无源性容差。
- `--passivity-check-mode analytic|streaming|skip`：选择 scikit-rf analytic passivity check、Agent-Spice 分块采样检查，或完全跳过检查。
- `--passivity-sample-chunk-size`：streaming passivity check 每批评估的频点数。值越小，峰值内存越低。
- `--require-dc`：缺少 DC 点时直接 FAIL。

注意：`--skip-passivity-enforce` 只能生成 preview/debug 产物。`signoff` profile 下跳过 passivity enforcement 会被标记为 blocking diagnostic。

## 当前可用加速旋钮

### 0. 频带裁剪和频点抽样

这是当前在 Agent-Spice 封装层能安全实现的最大加速点：减少传给 `VectorFitting.auto_fit()` 的频点数。

```powershell
--fit-f-min 1e6 --fit-f-max 5e9 --fit-frequency-stride 2 --fit-max-frequency-points 512
```

注意：

- 这会改变拟合输入数据，所以要用 HTML 的 `Original vs Fitted` 图在原始频点上复核误差。
- 建议先用抽样结果确定端口顺序、阶数和大致趋势，再用更密频点跑最终模型。
- JSON 和 HTML 报告都会同时记录原始 `frequency_points` 和实际用于 fit 的 `fit_frequency_points`。
- 频点筛选后必须至少保留 2 个点；否则 CLI 会提前报错，不会把无效输入交给 scikit-rf。
- `rms_error` 是 fit 样本上的训练误差；报告里的 `comparison_rms_error` 是在原始频点上重新评估的误差，更适合判断抽样后的全频段质量。

### 1. 限制模型阶数

`--model-order-max` 是大模型最直接的上限。scikit-rf 的 `auto_fit()` 会自动加/删极点，阶数越高，拟合和导出子电路都会变慢。

建议：

```powershell
--model-order-max 40 --target-error 0.05
```

如果误差报告和 HTML 图可接受，再逐步放宽。

### 2. 降低自动加极点速度

`--n-poles-add` 控制 auto-fit 每轮最多添加多少新极点。较大的值可能更快接近高阶模型，但也可能造成后续 skimming 和求解成本上升。

建议：

```powershell
--n-poles-add 1
```

适合先跑粗 fit 或大端口模型。

### 3. 控制迭代次数

`--fit-max-iterations` 设置 scikit-rf `VectorFitting.max_iterations`。`--iters-start`、`--iters-inter`、`--iters-final` 控制 auto-fit 各阶段 pole relocation 次数。

建议先用：

```powershell
--fit-max-iterations 30 --iters-start 2 --iters-inter 2 --iters-final 3
```

如果日志显示未收敛，再增加这些值。

### 4. 降低 passivity enforcement 采样成本

`--passivity-samples` 控制 passivity enforcement 采样数。采样数越大，越容易发现很窄的 violation band，但越慢。

建议先用：

```powershell
--passivity-samples 80
```

对最终质量签核再提高到默认或更高值。

### 5. 限制 passivity enforcement 频带

`--passivity-f-max` 可以只在关心频带内 enforce passivity。对 PI 目标频带明确的大模型，这通常比全带处理更实际。

示例：

```powershell
--passivity-f-max 5e9
```

### 6. 先跳过 passivity enforcement 做快速预览

如果只是检查端口顺序、趋势和大致拟合难度：

```powershell
--skip-passivity-enforce
```

注意：这个输出不应进入 transient 仿真闭环。

如果只跳过 enforcement 但仍保留 passivity check，Agent-Spice 会复用 enforcement 前的 passivity 结果，不再重复运行同一个 analytic passivity test。

### 7. 用 streaming passivity check 做大端口预览

对 30-port 以上模型，scikit-rf analytic passivity check 和 enforcement 都可能占用大量内存。现在可以先用分块采样方式检查拟合模型在原始频点上的最大奇异值：

```powershell
--passivity-check-mode streaming --passivity-sample-chunk-size 16 --skip-passivity-enforce
```

这个检查通过 `VectorFitting.get_model_response()` 按频率块生成 S 矩阵，再对每个频点做 SVD。它能降低峰值内存，并在 JSON/HTML 报告中记录 sampled max sigma、最严重频点和 sampled violation bands。

限制：

- 这是采样检查，不是严格全频解析 passivity 证明。
- 它不替代 `passivity_enforce()`；只用于 preview、阶数筛选和定位问题频段。
- 对最终 transient signoff，仍需要更严格的 passivity enforcement 或后续的正实/无源综合路线。

### 8. 用 order sweep 判断阶数是否合理

30-port 如果需要 100+ order 才能过门，必须先量化“阶数-误差-无源性”的关系，而不是直接继续抬阶。benchmark 支持同一 case 下批量扫阶：

```powershell
python -m agent_spice.cli benchmark-sparam `
  --manifest benchmarks/sparam/cases.yaml `
  --case 5power_30port_wocap_z_sweep `
  --run-fit `
  --order-sweep 20,40,60,80 `
  --output runs-sparam/order-sweep-30p.jsonl `
  --csv runs-sparam/order-sweep-30p.csv `
  --output-root runs-sparam/order-sweep-30p
```

输出 CSV/JSONL 会记录每个阶数的 `sweep_model_order_max`、S/Z 对比误差、Z log-magnitude RMS、质量状态、耗时和产物目录。PDN 推荐先用 `--z-required-for-signoff --max-z-log-magnitude-rms-error <decades>` 收敛门限，再看最低可接受阶数。

本地 `5power_30port_wocap_z_sweep` 的初步结果保存在 `runs-sparam/order-sweep-30p-z/partial_summary.csv`。已完成的 20/40 阶 raw-response 结果均未达标：

| Order | S RMS | Z log-mag RMS | Sampled max sigma | 结论 |
| ---: | ---: | ---: | ---: | --- |
| 20 | 1.1509 | 0.9737 decades | 1.3102 | 明显欠拟合 |
| 40 | 0.4771 | 0.7582 decades | 1.3035 | 有改善但仍远离 0.1 decade |

如果目标是先得到 S-domain 可用拟合，而不是继续做研究型 sweep，可以直接用自动 preset：

```powershell
python -m agent_spice.cli fit-sparam .\path\to\model.s30p `
  --output runs-sparam/auto-s-fit/model.sp `
  --report runs-sparam/auto-s-fit/fit_report.json `
  --html-report runs-sparam/auto-s-fit/fit_report.html `
  --log runs-sparam/auto-s-fit/fit.log `
  --auto-preset compact `
  --fail-on-quality
```

`compact` 会按端口数选择候选阶数，并在第一个满足 S RMS 门限的 order 停止。30-port 现有证据是 order40 S RMS `0.4771`、order60 S RMS `0.1040`、order70 S RMS `0.2602`、order75 S RMS `0.0291`、order80 S RMS `0.0476`、order120 raw S RMS `0.0211`，所以 `compact` 的 `0.05` S RMS 目标会跳过非单调坏点 order70，并在 order75 停止。该 preset 默认跳过 passivity enforcement/check，把 passivity 作为后续 PI 应用约束处理。

自动 order 的最终 JSON 会写入 `auto_model_order_trials`、`auto_model_order_selected` 和 `auto_model_order_stop_reason`。如果所有候选阶数都没有达到配置的 S RMS 目标，CLI 会返回非零退出码，而不是把最后一个候选静默当作成功。19-port refined 实跑 `runs-sparam/auto-s-fit-19p-compact-v2-refined/fit_report.json` 显示 order40 S RMS `0.061694` 未达标、order60 S RMS `0.084725` 未达标、order62 S RMS `0.036899` 达标并停止；单档探针显示 order61 S RMS `0.053478`，因此当前 19-port 最小达标候选是 order62。

30-port refined 实跑 `runs-sparam/auto-s-fit-30p-compact-v1-refined/fit_report.json` 显示 order40 S RMS `0.477138` 未达标、order60 S RMS `0.104034` 未达标、order75 S RMS `0.029135` 达标并停止。单档探针 `runs-sparam/s-fit-30p-order70-compact-probe-v1/fit_report.json` 显示 order70 S RMS `0.260239`，这是非单调坏点，因此 30-port compact 候选显式跳过 70。

`high-accuracy` preset 使用更紧的 `0.025` S RMS 目标，也做成 bounded auto-order。19-port 当前配置下 order80 S RMS `0.029608` 未达标，order81 S RMS `0.015045` 达标，因此候选为 `80,81,85,90,100,120`。30-port 当前配置下 order75 S RMS `0.029135` 未达标、order110 S RMS `0.026438` 仍略高于门限、order115 S RMS `0.022807` 达标，因此候选为 `75,110,115,120`。

### 9. 用 manual mode 做可控试跑

`auto_fit` 适合最终自动定阶；大模型探索时可以先用手动极点数快速试跑：

```powershell
--mode manual --n-poles-real 2 --n-poles-cmplx 4 --skip-passivity-enforce
```

## `auto_fit` 本身能不能并行

结论：可以局部并行，但不适合在 Agent-Spice 里直接 monkey-patch scikit-rf 私有实现。

原因：

- `auto_fit()` 的 adding/skimming 主循环是串行依赖：每轮新增/剔除极点后，下一轮必须基于更新后的公共极点继续。
- scikit-rf 的 `_pole_relocation()` 内部有一个按 response 做 QR 分解的循环。这个循环理论上可以并行，因为每个 Sij response 的 QR 可独立计算，再汇总到公共线性系统。
- 后续 `_fit_residues()` 已经用 `np.linalg.lstsq(..., b.T)` 一次解多个右端项，主要依赖 BLAS/LAPACK。这里更现实的并行方式是让 NumPy/BLAS 使用多线程，而不是 Python 层拆任务。
- passivity enforcement 内部包含每个频点/迭代的 SVD 和矩阵逆，也更适合 BLAS 线程和降低 `--passivity-samples`，不适合简单 Python 多进程复制大矩阵。

短期建议：

```powershell
$env:OMP_NUM_THREADS="8"
$env:MKL_NUM_THREADS="8"
$env:OPENBLAS_NUM_THREADS="8"
python -m agent_spice.cli fit-sparam ...
```

这些环境变量要在 Python 进程启动前设置。实际是否生效取决于当前 Python/NumPy 链接的 BLAS 实现。

中期可以做的工程路线：

- 给 scikit-rf 提 upstream PR：把 `_pole_relocation()` 中 response-wise QR 分解改成可选线程池实现。
- 在 Agent-Spice 侧不要复制整段私有 `_pole_relocation()`，否则会和 scikit-rf 版本强绑定，维护风险高。
- 对真实 16/32/64-port 数据建立 benchmark 后，再决定是否值得维护一个 fork 或上游补丁。

## 后续加速方向

- 输入抽样/频带裁剪：先对 Touchstone 做目标频带裁剪和频点抽样，再 fit。
- 分块/端口分组：对 32/64-port 以上模型按电源域或物理区域分块。
- MOR：评估 SROPEE 或自研 Block SAPOR/Krylov 路线，减少生成 SPICE 子电路的节点和受控源数量。
- 并行批处理：不同端口分组或候选参数组合可以并行跑，当前单个 scikit-rf fit 仍是单进程主路径。

## 参考

- scikit-rf `VectorFitting.auto_fit`：`n_poles_add`、`model_order_max`、`iters_*`、`target_error`、`alpha`、`gamma` 会影响收敛、最终误差和模型阶数。
- scikit-rf `VectorFitting.passivity_enforce`：`n_samples` 和 `f_max` 控制 passivity enforcement 的采样量和最高频率。
- scikit-rf `VectorFitting.max_iterations`：可在 `vector_fit()` 或 `passivity_enforce()` 前调整最大迭代次数。
