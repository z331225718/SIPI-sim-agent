# 19-Port S-Parameter Fit Case Study

日期：2026-07-03

输入文件：

```text
user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p
```

输入摘要：

- 端口数：19
- 频点数：826
- 频率范围：0 Hz 到 2 GHz
- Z0：0.1 ohm，频率上恒定
- 输入采样最大奇异值：0.9999999944613438

## 结论

可生成一版目标频带内通过质量门禁的 SPICE 模型：

```powershell
python -m agent_spice.cli fit-sparam user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p `
  --output runs-sparam/full-19port-bandpass-scaled/model.sp `
  --report runs-sparam/full-19port-bandpass-scaled/fit_report.json `
  --html-report runs-sparam/full-19port-bandpass-scaled/fit_report.html `
  --log runs-sparam/full-19port-bandpass-scaled/fit.log `
  --quality-profile signoff `
  --fail-on-quality `
  --require-dc `
  --model-order-max 100 `
  --target-error 0.01 `
  --skip-passivity-enforce `
  --response-scale 0.99 `
  --passivity-check-f-max 2000000000
```

产物：

- `runs-sparam/full-19port-bandpass-scaled/model.sp`
- `runs-sparam/full-19port-bandpass-scaled/fit_report.json`
- `runs-sparam/full-19port-bandpass-scaled/fit_report.html`
- `runs-sparam/full-19port-bandpass-scaled/fit.log`

质量结果：

- `quality.status`: `PASS`
- `allowed_for`: `ac_only`
- `comparison_rms_error`: 0.04300741032679117
- `response_scale`: 0.99
- `passivity_check_f_max`: 2 GHz
- 0 到 2 GHz 内无 passivity violation band

注意：这不是严格的全频无源模型。scikit-rf analytic passivity 在 2 GHz 以上仍报告 violation bands，所以该产物只应按 `ac_only`/目标频带模型使用，不应自动升级为宽带 transient signoff 模型。

## 失败路径

### 默认完整 auto fit

命令特征：

- 全 826 点
- `auto`
- `model_order_max=100`
- `target_error=0.01`
- `passivity_samples=200`
- preserve DC

结果：

- SPICE 生成成功
- `comparison_rms_error`: 1.2994050182997781e11
- `passive_after_enforce`: false
- enforcement 后 violation bands：125
- `quality.status`: `FAIL`

关键日志：

- 拟合模型 DC 点不是 passive，无法 preserve DC。
- passivity enforcement 条件数约 `2.65e17`。
- scikit-rf 建议 `n_samples > 34101571`，不可作为实用路线。

### 不 preserve DC

`--no-preserve-dc` 没有改善：

- `comparison_rms_error`: 1.2994050182997781e11
- enforcement 后 violation bands：125
- `quality.status`: `FAIL`

判断：问题不是单纯 preserve DC，而是高阶模型的 passivity enforcement 线性系统病态。

### no-enforce raw fit

跳过 passivity enforcement 后：

- `comparison_rms_error`: 0.013082831374396083
- `passive_after_enforce`: false
- violation bands：37
- `quality.status`: `FAIL`

判断：raw fit 精度足够，主要风险集中在 passivity。

### manual 低阶 sweep

低阶 manual 模型无法达到误差门限：

| case | comparison RMS | violation bands |
|---|---:|---:|
| r1_c0 | 4.187061412185382 | 5 |
| r1_c1 | 2.483437813644811 | 23 |
| r2_c1 | 2.3222785974972573 | 31 |
| r2_c2 | 1.8547830591157584 | 58 |
| r4_c4 | 0.5223732104762459 | 85 |
| r8_c4 | 0.8289176927284988 | 156 |

判断：简单降阶不能表达这个 19-port 网络。

### auto 限阶 no-enforce sweep

| model_order_max | comparison RMS | violation bands |
|---:|---:|---:|
| 20 | 0.31876770947802086 | 121 |
| 30 | 0.1272316290463749 | 86 |
| 40 | 0.06369316498649599 | 114 |
| 60 | 0.08439121316411045 | 284 |
| 80 | 0.024351958155799668 | 210 |
| 100 | 0.013082831374396083 | 37 |

判断：

- `model_order_max=80` 首次让 raw RMS 明显过门，但 passivity violation 更多。
- `model_order_max=100` raw RMS 最好，violation band 数更少。

### fit_constant=False

scikit-rf 曾建议 unbounded violation 时可尝试 `fit_constant=False`，但本例无效：

| case | comparison RMS | violation bands after enforcement |
|---|---:|---:|
| order80 noconst | 6.376307559338286e10 | 58 |
| order100 noconst | 3.2546734468973286e10 | 148 |

判断：本例不要优先走 `fit_constant=False`。

## 有效修正

raw order100 模型的采样最大奇异值只轻微超过 1：

- 原始频点 sampled max sigma：1.0025942194943582
- 密集采样 sampled max sigma：1.002592995168608
- 峰值频点约 2.3 kHz

将 fitted S 响应整体缩放到 `0.99` 后：

- `comparison_rms_error`: 0.04300741032679117
- 第一个 analytic violation band 移到 2.0325778236248257 GHz 以上
- 0 到 2 GHz 目标频带内无 violation band

这就是当前推荐命令使用 `--response-scale 0.99` 和 `--passivity-check-f-max 2000000000` 的原因。

## 一次成功率建议

对类似 PDN S 参数，建议按以下顺序：

1. 先跑 metadata benchmark，确认端口数、频点数、Z0、DC 覆盖。
2. 跑 no-enforce raw fit，先确认 `comparison_rms_error` 是否过门。
3. 如果 raw RMS 过门但 passivity enforcement 打爆误差，不要盲目提高 `passivity-samples`。
4. 检查 raw model 的 sampled max singular value；如果只轻微超过 1，可尝试 `--response-scale 0.99` 到 `0.995`。
5. 对 Touchstone 原始有效频带设置 `--passivity-check-f-max`，避免把输入数据带外的 analytic violation 当成同等级阻断。
6. 报告中 `allowed_for=ac_only` 时，不要自动进入 transient signoff。
7. 只有全频 passivity 也通过时，才升级为 `tran_candidate`。

## 后续工程改进

- 保存 scikit-rf `VectorFitting.write_npz()` 中间模型，避免每次 passivity 参数试验都重跑 auto-fit。
- 在 HTML 报告中显示 analytic violation bands 的频带内/频带外拆分。
- 增加 sampled max singular value after-fit 诊断。
- 研究可验证的高频滚降模型，目标是在不破坏 0 到 2 GHz 误差的前提下消除带外 violation。
