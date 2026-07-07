# S-Parameter Batch Fit Results

日期：2026-07-03

本轮目标是把 `user_input/spara/` 下剩余 S 参数都跑过一次 fit，并记录哪些结果可进入下一步、哪些只是摸底结果。结论先说清楚：19-port 和 30-port 目前达到 0-2GHz 目标频段 PASS，均为 `ac_only`；60/91/163/166-port 都完成了 preview fit 并生成 SPICE/HTML/JSON/log，但都只是 `report_only`。

## 输入规模

| 文件 | 端口 | 频点 | 频段 | 备注 |
| --- | ---: | ---: | --- | --- |
| `5power_19port_withcap_122324_202459_11476_DCfitted.s19p` | 19 | 826 | 0-2GHz | 已有目标频段 PASS |
| `5power_30port_wocap_121124_221036_4876_DCfitted.s30p` | 30 | 826 | 0-2GHz | 已有目标频段 PASS |
| `Test13.s60p` | 60 | 611 | 0-2GHz | preview WARN |
| `Test16.s91p` | 91 | 611 | 0-2GHz | preview WARN |
| `Test11.s163p` | 163 | 542 | 1Hz-2GHz | preview WARN，缺 DC |
| `Test3.s166p` | 166 | 542 | 1Hz-2GHz | preview WARN，缺 DC |

## Fit 结果

| Case | Fit 策略 | 状态 | RMS | 耗时 | 产物 |
| --- | --- | --- | ---: | ---: | --- |
| `5power_19port_withcap_bandpass_scaled` | auto order<=100, full 826 points, scale=0.99, 0-2GHz passivity gate | PASS, `ac_only` | 0.0430 | 见 case study | `runs-sparam/full-19port-bandpass-scaled/` |
| `5power_30port_wocap_bandpass_scaled` | auto order<=120, full 826 points, scale=0.992, 0-2GHz passivity gate | PASS, `ac_only` | 0.0483 | 716.1s | `runs-sparam/attack-30port/order120-scale0992-bandpass/` |
| `test13_60port_preview` | manual 1 real + 1 complex pair, 64 fit points, 32 comparison points, 8 quality points, no analytic passivity | WARN, `report_only` | 1.3667 | 21.2s | `runs-sparam/batch-preview-fit/test13_60port_preview/` |
| `test16_91port_preview` | same preview preset | WARN, `report_only` | 8.3921 | 54.3s | `runs-sparam/batch-preview-fit/test16_91port_preview/` |
| `test11_163port_preview` | same preview preset | WARN, `report_only` | 0.4552 | 152.0s | `runs-sparam/batch-preview-fit/test11_163port_preview/` |
| `test3_166port_preview` | same preview preset | WARN, `report_only` | 0.3035 | 150.1s | `runs-sparam/batch-preview-fit/test3_166port_preview/` |

30-port 的失败样本和最终解法：

- 失败样本：`runs-sparam/batch-fit/5power_30port_wocap_bandpass_scaled/`，order<=100 + scale=0.99，RMS 0.0756，0-2GHz 内仍有 501 个 violation bands。
- raw 改进：`runs-sparam/attack-30port/raw-order120-nopassivity/`，order<=120、target_error=0.005 后，raw RMS 降到 0.0211。
- 最终通过：`runs-sparam/attack-30port/order120-scale0992-bandpass/`，scale=0.992 后 RMS 0.0483，0-2GHz 内 violation band 数为 0，quality `PASS`，`allowed_for=ac_only`。
- 限制：仍有 47 个 analytic violation bands 在 2GHz 之外，第一组约从 2.382GHz 开始，所以这不是全局 passive/transient signoff。

60/91/163/166-port 的 warning reasons：

- `fit_frequency_subset`：只用 64 个频点做 preview。
- `comparison_rms_error`：preview 阶数太低，误差未达门限。
- `passivity_enforcement` 和 `passivity_violation_bands_after`：本轮没有做可交付 passivity 处理。
- `dc_coverage`：163/166-port 从 1Hz 开始，不含 DC。

## 本轮工程改动

- `load_touchstone_metadata()` 增加 Touchstone 1.0 fast path，不再为 metadata-only benchmark 构造完整 `skrf.Network`。
- `fit-sparam` 增加 `--skip-passivity-check`，用于 preview 阶段跳过 scikit-rf analytic passivity test。
- `fit-sparam` 增加 `--passivity-check-mode streaming`，用于按频率块采样拟合模型的最大奇异值，降低大端口 passivity 预览的峰值内存。
- `fit-sparam` 增加 `--comparison-max-frequency-points`，用于限制原始频点 RMS 对比成本。
- `fit-sparam` 增加 `--quality-max-frequency-points`，用于限制输入 SVD/质量诊断成本。
- `fit-sparam` 增加 `--max-z-comparison-rms-error` 和 `--z-required-for-signoff`，用于把 PDN 的 Z 参数误差作为主质量门禁。
- `fit-sparam` 增加 `--max-z-log-magnitude-rms-error`，用于用 `log10(|Zfit| / |Zorig|)` RMS 做 PDN 阶数筛选，避免绝对 Ohm RMS 被奇异转换点支配。
- `benchmark-sparam` 增加 `--order-sweep`，用于同一 case 下批量评估不同 `model_order_max`。
- benchmark CSV/JSONL 增加 fit/comparison/quality 采样点数字段。
- `benchmarks/sparam/cases.yaml` 增加 30/60/91/163/166-port case 和高端口 preview case。

## 经验总结

1. Metadata 不能依赖 `rf.Network`

600MB 级 Touchstone 如果只是要端口数、频点数和 Z0，完整构造矩阵代价太高。fast path 后，单个 166-port metadata 扫描约 2.1s；旧路径会卡在全量加载。

2. 30-port 的可行解来自“先提精度，再最小缩放”

order<=100 + scale=0.99 同时损失精度且没有解决带内 passivity。order<=120 + target_error=0.005 先把 raw RMS 压到 0.0211，再用尽量接近 1 的 scale=0.992 推开带内 passivity violation，最终 RMS 仍控制在 0.05 以内。

3. passivity enforcement 不能盲目开启

19-port case 已证明 enforcement 可能导致病态和误差爆炸；30-port raw/scaled 也显示 0-2GHz 内 violation bands 很多。下一步需要先理解 violation 来源和目标频带，而不是简单提高 `passivity_samples`。

4. 高端口 preview 必须降级质量检查

对 163/166-port，全量 comparison RMS 和全量输入 SVD 都会非常贵。preview 阶段必须记录“采样过”的事实，不能把 sampled 指标当 signoff。

5. 端口数比文件大小更关键

166-port 每个频点有 27,556 个 Sij response，任何逐 response 的模型评估、QR、SVD 或 passivity 分析都会呈平方或立方级放大。

## 下一步建议

1. 先对 30-port 建立 Z-domain order sweep 基线

用当前 30-port `5power_30port_wocap_z_sweep` case 扫 `20,40,60,80` 等低/中阶组合，并用 `--z-required-for-signoff` + `--max-z-log-magnitude-rms-error` 把 Z log-magnitude 误差作为主门禁。目标是确认几十阶能否接近可用质量；如果仍必须 100+ order，说明需要换模型缩减/综合路线，而不是继续堆阶。

推荐命令见 `docs/sparam-fit-performance.md` 的 “用 order sweep 判断阶数是否合理”。当前已完成 20/40 阶初步结果，Z log-magnitude RMS 分别约为 0.9737 和 0.7582 decades，均远高于暂定 0.1 decade 门限。

2. 建立三阶段 preset：`preview`、`full`、`signoff`

把现在散在 YAML 里的配置收敛成 CLI/benchmark preset。默认批量跑 `preview`，只有 preview 指标过门才升级到 `full`，只有 full raw RMS 和带内 passivity 可控才进入 `signoff`。

3. 增加每 case 子进程、timeout 和 RSS 采集

当前 benchmark 是串行进程内执行，某个大 case 卡住会拖住整批；`tracemalloc` 也不能完整代表 NumPy/scikit-rf 的 RSS。建议每 case 单独 Python 进程，记录 exit code、wall time、RSS peak、最后日志。

4. 加 NPZ 缓存和后处理复用

scikit-rf VF 结果应可缓存为 NPZ。`response_scale`、目标频段 passivity gate、HTML 报告重算不应每次重跑 auto-fit。

5. 先做端口分组/降阶，再追求全端口 signoff

60/91/163/166-port 的全矩阵 SPICE 直接落地会产生庞大的受控源网络。下一步应按电源域、物理区域或关键端口做分组，或者引入 MOR/PRIMA/SROPEE/Krylov 路线。

6. 报告拆分 in-band/out-of-band passivity

现在报告能做 `passivity_check_f_max`，streaming passivity summary 也会输出 sampled max sigma 和 sampled violation bands。下一步还需要把 analytic 与 sampled 结果统一成带内/带外摘要，方便判断是可接受的 AC-only 模型还是需要重新拟合。

7. 30-port 已完成目标频段攻关，下一阶段应把方法产品化

30-port 证明了“提高 raw 精度 + 最小 response_scale + 目标频段 passivity gate”是可行路线。建议下一步把 Z-domain order sweep、scale 搜索、NPZ 缓存、in-band/out-of-band passivity 摘要产品化，再外推到 60/91/163/166-port。
