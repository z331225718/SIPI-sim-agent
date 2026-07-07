# Modal Z-Fit Optimization Report

日期：2026-07-03

## 结论

本轮目标是寻找 30-port PDN S 参数拟合的算法突破，而不是继续扫 `model_order_max`。已实现并验证一个隔离的 reduced-basis Z-domain rational fitting prototype：`fit-modal-z`。

结论：

- **不要继续盲扫 full-matrix VF 阶数。**
- 当前 `fit-modal-z` 的 **fixed-pole LS reduced fit 不可用**，最终 Z log-magnitude RMS 为 3.5+ decades，差于元素级 VF baseline。
- 直接在 reduced matrix 上调用 scikit-rf `VectorFitting.auto_fit(parameter_type="z")` 仍然太慢：`mode=4/order=12/sample=96` 超过 180s 未完成。
- 新增的 **peak-poles + relative LS** 路线有效：从 modal Z 峰值直接选公共 pole，再对 reduced matrix 做相对加权 LS。
- 当前最佳 30-port 结果为 `hermitian mode=28/order=56/basis_samples=21/full-projected iterative max weighting/head_samples=3`：**Z log-mag RMS = 0.4439 decades**，优于元素级 VF order40 的 **0.7582 decades**，且单次运行约 6.1 秒。
- 这还不是 signoff 质量，但已经证明“Z-domain modal reduction + 数据驱动 pole 选择”比继续扫 full-matrix order 更值得推进。

## 2026-07-04 更新：19-port 自动 preset

19-port with-cap case 已不再是 `2.9+` decades 的 fit-limited 失败。当前 `fit-modal-z` 新增 bounded auto presets：

```powershell
python -m agent_spice.cli fit-modal-z .\path\to\model.s19p `
  --report runs-sparam/modal-compact/fit_report.json `
  --html-report runs-sparam/modal-compact/fit_report.html `
  --auto-preset compact `
  --fail-on-quality

python -m agent_spice.cli fit-modal-z .\path\to\model.s19p `
  --report runs-sparam/modal-highacc/fit_report.json `
  --html-report runs-sparam/modal-highacc/fit_report.html `
  --auto-preset high-accuracy `
  --fail-on-quality
```

本地 `5power_19port_withcap...s19p` 结果：

| Preset | Selected modes | Selected order | Anchors | Z log RMS | Diag Z log RMS | Projection RMS | Report |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| compact | 18 | 160 | 3,5,4 | 0.372721 | 0.021065 | 0.203891 | `runs-sparam/modal-z-19p-preset-compact-v11-quality/fit_report.html` |
| high-accuracy | 18 | 224 | 3,5,4 | 0.336418 | 0.017261 | 0.203891 | `runs-sparam/modal-z-19p-preset-highacc-v10/fit_report.html` |

关键变化：

- preset 默认搜索相邻两档 mode；低阶 mode 中真实 fit 过的 anchor 会 carry over 到高阶 mode 复测，避免 mode18 被 projection-only anchor ranking 带偏。
- `auto_basis_anchor_candidate_count` 扩大 anchor 候选端口池，配合 carryover 避免漏掉 `3,5,4` 这种真实 fit 更稳的组合。
- `auto_basis_anchor_combo_count` 保留多个候选 anchor 组合进入真实 fit，而不是只做 projection 贪心。
- `auto_basis_diagonal_weight` 让自动选择兼顾 full-matrix RMS 与 diagonal RMS。
- preset 使用 bounded order candidates，不回到 open-ended full-matrix VF order sweep。
- preset 会填入 modal-Z quality gate；`--fail-on-quality` 会在 Z RMS、diagonal RMS 或 scalar order 超标时返回非零。该门禁不证明 passivity，也不验证 SPICE 子电路。

## 2026-07-04 更新：30-port 自动 preset

30-port w/o-cap case 的最佳路线和 19-port 不同：它不需要 anchor carryover，而是需要固定 `mode=28` 后做低阶 auto-order。preset 已按端口数分流，`s30p` 默认使用单 basis 的 bounded order sweep，避免被 19-port 的高阶 anchor 搜索拖慢。

本地 `5power_30port_wocap...s30p` 结果：

| Preset | Selected modes | Selected order | Anchors | Z log RMS | Diag Z log RMS | Projection RMS | Report |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| compact | 28 | 44 | none | 0.487014 | 0.135489 | 0.325543 | `runs-sparam/modal-z-30p-preset-compact-v22/fit_report.html` |
| high-accuracy | 28 | 56 | none | 0.443910 | 0.108077 | 0.325543 | `runs-sparam/modal-z-30p-preset-highacc-v23-quality/fit_report.html` |

这把 30-port 从原 `fit-sparam` 可用路径的 order<=120 降到 modal Z 的 order 44/56，同时 Z log RMS 优于元素级 VF order40 baseline `0.7582`。

## 2026-07-04 更新：S-domain 可用性校正

新增 `fit-modal-z` 的 S-domain 回算指标：报告现在包含 `s_rms_error`，即将 fitted Z 通过 Touchstone 的 `z0` 转回 S 后，在原始频点上和原始 S 参数比较。

结论必须修正：modal-Z 当前是 **Z-domain 降阶/诊断路线**，还不能作为最终 S 参数 handoff。30-port high-accuracy preset 的 Z log RMS 虽为 `0.443910`，但回算 S RMS 为 `7.561026`，远差于原版 VF 的 S-domain fit。

因此新增 `fit-sparam --auto-preset` 和底层 `--auto-model-order-candidates`，让原版 S-domain VF 在小候选集合里自动选择最小达标阶数：

```powershell
python -m agent_spice.cli fit-sparam .\path\to\model.s30p `
  --output runs-sparam/auto-s-fit/model.sp `
  --report runs-sparam/auto-s-fit/fit_report.json `
  --html-report runs-sparam/auto-s-fit/fit_report.html `
  --log runs-sparam/auto-s-fit/fit.log `
  --auto-preset compact `
  --fail-on-quality
```

当前 30-port 现有报告给出的 S-domain 证据：

| Route | Order max | S RMS | Z log RMS | Report |
| --- | ---: | ---: | ---: | --- |
| original VF raw | 40 | 0.477138 | 0.758220 | `runs-sparam/order-sweep-30p-z/artifacts/5power_30port_wocap_z_sweep_order40/fit_report.json` |
| original VF raw | 80 | 0.047605 | 0.562484 | `runs-sparam/original-vf-30p-z-curve-v2/5power_30port_wocap_z_sweep_order80/fit_report.json` |
| original VF raw | 120 | 0.021056 | 0.460639 | `runs-sparam/attack-30port/raw-order120-nopassivity/fit_report.json` |
| modal-Z high-accuracy | 56 | 7.561026 | 0.443910 | `runs-sparam/modal-z-30p-preset-highacc-v24-squality-probe/fit_report.json` |

对“最重要的是 fitting S 参数”的目标来说，下一条主线应是 **S-domain bounded auto-order**：`compact` preset 在 30-port 上用 `40,60,75,80,120` 自动寻找第一档 `S RMS <= 0.05` 的 order；现有 30-port 证据表明 order60 未达标、order70 是非单调坏点、order75 达标并且优于 order80，所以会比 order80/order120 都少或更准。19-port refined compact 用 `40,60,62,65,70,80,100`，实跑自动停在 order62，S RMS `0.036899`，且 order61 探针为 `0.053478` 未达标。`high-accuracy` preset 用更紧的 `0.025` S RMS 目标：19-port order80 未达标、order81 达标；30-port order110 略高于门限、order115 达标。auto-order 报告会记录 `auto_model_order_trials`/`auto_model_order_selected`/`auto_model_order_stop_reason`，且所有候选都未达标时返回失败，避免把最后一档误当成功。modal-Z 暂时保留为 Z-domain 分析工具。

## Baseline：元素级 VF 30-port

来源：`runs-sparam/order-sweep-30p-z/partial_summary.csv`

| Case | Order | S RMS | Z log-mag RMS | Sampled max sigma | 结论 |
| --- | ---: | ---: | ---: | ---: | --- |
| element VF raw | 20 | 1.1509 | 0.9737 decades | 1.3102 | 明显欠拟合 |
| element VF raw | 40 | 0.4771 | 0.7582 decades | 1.3035 | 有改善但仍远离 0.1 decade |

之前 30-port 可通过目标频段 gate 的结果仍需要 order<=120、target_error=0.005 和 response_scale=0.992。该路径能产出 AC-only 结果，但没有解释为什么需要 100+ order。

## Prototype：`fit-modal-z`

新增命令：

```powershell
python -m agent_spice.cli fit-modal-z `
  user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam/modal-z-30p/fit_report.json `
  --html-report runs-sparam/modal-z-30p/fit_report.html `
  --decomposition svd `
  --mode-count 8 `
  --scalar-fit-order 24 `
  --frequency-sample-count 256
```

基础实现方式：

- 读取 Touchstone 并转换到 Z 参数。
- 通过 SVD/Hermitian proxy 构造固定端口 basis `Q`。
- 投影得到 reduced matrix：`Zr(f) = Qᴴ Z(f) Q`。
- 对 `Zr` 的 `k^2` 个 reduced traces 使用 reduced fit method：
  - `fixed`：固定几何稳定 pole，complex LS。
  - `vector`：直接对 reduced multiport Z Network 调 scikit-rf VF，已证明 30-port 诊断过慢。
  - `shared-poles`：少数 scalar surrogate VF 识别公共 pole，再对全 reduced matrix LS；仍受 scikit-rf VF 内循环拖慢。
  - `peak-poles`：从 modal Z trace 峰值直接选公共 pole，混合全带宽几何 pole，并用相对加权 LS。
- 重建：`Zfit(f) = Q Zr_fit(f) Qᴴ`。
- 输出 JSON/HTML report，不导出 SPICE，不声明 passivity。

## Prototype 结果

| Run | Decomposition | Modes | Scalar order | Z log-mag RMS | Basis projection RMS | Diagonal Z log RMS | 结论 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `runs-sparam/modal-z-30p/` | svd | 8 | 24 | 3.7241 | 0.8021 | 2.7640 | fixed-pole fit 失败 |
| `runs-sparam/modal-z-30p-mode16/` | svd | 16 | 32 | 3.5363 | 0.6701 | 2.6343 | basis 有改善，fit 仍失败 |
| `runs-sparam/modal-z-30p-hermitian8/` | hermitian | 8 | 24 | 3.7557 | 0.6713 | 3.0626 | hermitian basis projection 可用，但 fit 失败 |
| `runs-sparam/modal-z-30p-peak4-weighted/` | svd | 4 | 12 | 0.8841 | 0.7689 | 1.2642 | peak-poles 快速可用，但未过 baseline |
| `runs-sparam/modal-z-30p-peak8-weighted/` | svd | 8 | 20 | 0.8312 | 0.8021 | 0.9509 | 接近 baseline，但 basis 受限 |
| `runs-sparam/modal-z-30p-peak16-weighted/` | svd | 16 | 32 | 0.7120 | 0.6701 | 0.6448 | 优于 element VF order40 |
| `runs-sparam/modal-z-30p-peak16-hermitian/` | hermitian | 16 | 32 | 0.6307 | 0.4561 | 0.4176 | 当前最佳 |
| `runs-sparam/modal-z-30p-peak20-hermitian/` | hermitian | 20 | 40 | 0.6750 | 0.4188 | 0.3753 | mode/order 增加不单调 |
| `runs-sparam/modal-z-30p-peak-v2/` | hermitian | 20 | 44 | 0.5549 | 0.4188 | 0.3267 | 当前最佳，`relative_weight_power=0.6` |
| `runs-sparam/modal-z-30p-peak-v3/` | hermitian | 20 | 44 | 0.5184 | 0.4188 | 0.3230 | full-projected weighting |
| `runs-sparam/modal-z-30p-peak-v4/` | hermitian | 20 | 44 | 0.4993 | 0.4008 | 0.3218 | 当前最佳，basis samples=17 |
| `runs-sparam/modal-z-30p-peak-v5/` | hermitian | 28 | 52 | 0.4770 | 0.3255 | 0.1104 | 当前最佳，2 轮 max reweight |
| `runs-sparam/modal-z-30p-peak-v6/` | hermitian | 28 | 56 | 0.4729 | 0.3255 | 0.1082 | 当前最佳，damping/power 调优 |
| `runs-sparam/modal-z-30p-peak-v7/` | hermitian | 28 | 56 | 0.4439 | 0.3255 | 0.1081 | 当前最佳，强制纳入前三个 raw 低频点 |

## Cross-Case Sanity Check

用户反馈 `0.1 Hz` 低频点后，继续用其它 S 参数验证同一条 modal-Z/peak-poles 路线是否泛化。结论：**不能把 30-port V7 当成通用成功路径**。不同 case 的失败模式不一样，下一步需要先分类处理。

| Case | Ports | Points | Sampling | Z log RMS | Projection RMS | Diag Z log RMS | Worst Hz | 判断 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| `5power_19port_withcap...s19p` | 19 | 826 | 256 + head3 | 2.8056 | 0.2499 | 0.5568 | 6.91831 | reduced rational fit 崩，不是 basis floor 主导 |
| `5power_19port_withcap...s19p` | 19 | 826 | full raw | 2.9473 | 0.2499 | 0.6004 | 0.1 | 全 raw LS 没救，pole/weighting 失败 |
| `5power_30port_wocap...s30p` | 30 | 826 | 256 + head3 | 0.4439 | 0.3255 | 0.1081 | 0 | 当前 30p 最佳 |
| `Test13.s60p` | 60 | 611 | 256 + head3 | 1.2496 | 0.5797 | 0.9162 | 2.37137 | 采样不足影响很大 |
| `Test13.s60p` | 60 | 611 | full raw | 0.5812 | 0.5797 | 0.2401 | 2.37137 | fit 基本贴近 projection floor |
| `Test16.s91p` | 91 | 611 | full raw | 0.4790 | 0.4626 | 0.7051 | 1.935e9 | fit 基本贴近 projection floor，高频/对角仍差 |
| `Test11.s163p` | 163 | 542 | full raw | 1.6603 | 1.6620 | 2.3133 | 1 | basis projection 已失败 |
| `Test3.s166p` | 166 | 542 | full raw | 1.4817 | 1.4816 | 1.7447 | 1 | basis projection 已失败 |

新增观察：

1. `0.1 Hz` 不是唯一问题。19p/60p 的 worst frequency 也会落在未采样 raw 点上，但 19p 即使用 full raw LS 仍然失败。
2. 60p 从 sampled `1.2496` 降到 full raw `0.5812`，说明 reduced LS 的默认采样策略不能作为大端口默认值。对 reduced fit，full raw LS 的成本目前仍可接受，应优先用于评估。
3. 91p 的 total RMS `0.4790` 接近 projection floor `0.4626`，说明它的瓶颈主要是 basis，而不是 pole fitting。
4. 163p/166p 的 total RMS 几乎等于 projection floor，固定全频 hermitian basis 直接失效。继续调 order 没意义，必须改 basis。
5. 19p 是反例：projection floor `0.2499`，但 fit error `2.8+`。这说明当前 peak-poles + per-entry LS 在含 cap 的强动态网络上有 pole selection 或 weighting 病态，需要单独攻关。

## Bounded Auto-Order

前面的 modal-Z 数字大多来自固定 `scalar_fit_order`，只适合判断算法方向。已新增 bounded auto-order：在明确的小候选阶数集合内自动选择**第一个达到 Z-domain 目标的阶数**；如果没有候选达标，则返回已尝试候选中 Z log RMS 最好的结果。该机制不会调用原版 full-matrix scikit-rf `auto_fit` 的高阶路径。

新增 CLI：

```powershell
--auto-order
--auto-order-candidates 8,12,16,24,32,44,56
--auto-order-max-z-log-rms-error 0.5
--auto-order-max-diag-z-log-rms-error 0.2
```

30p auto-order 诊断：

| Order | Z log RMS | Diag Z log RMS | 结果 |
| ---: | ---: | ---: | --- |
| 8 | 0.7128 | 0.5085 | 未达标 |
| 12 | 0.7979 | 0.5286 | 未达标 |
| 16 | 0.7222 | 0.3404 | 未达标 |
| 24 | 0.6151 | 0.2385 | 未达标 |
| 32 | 0.5475 | 0.1747 | 未达标 |
| 44 | 0.4870 | 0.1355 | 首个通过 0.5-decade 目标 |

产物：

- `runs-sparam/modal-z-30p-auto-v1/fit_report.json`
- `runs-sparam/modal-z-30p-auto-v1/fit_report.html`

19p auto-order 诊断：

| Order | Z log RMS | Diag Z log RMS | 结果 |
| ---: | ---: | ---: | --- |
| 8 | 3.7379 | 0.9153 | 未达标 |
| 12 | 3.3565 | 0.7247 | 未达标 |
| 16 | 3.4681 | 0.7258 | 未达标 |
| 24 | 3.3419 | 0.6852 | 未达标 |
| 32 | 3.2113 | 0.5137 | 未达标 |
| 44 | 2.9762 | 0.5063 | 未达标 |
| 56 | 2.9473 | 0.6004 | best observed，但仍失败 |

产物：

- `runs-sparam/modal-z-19p-withcap-auto-v1/fit_report.json`
- `runs-sparam/modal-z-19p-withcap-auto-v1/fit_report.html`

判断：bounded auto-order 可以避免手工固定阶数，也能防止回到 100+ order；但它不会掩盖算法失败。19p 的失败仍应进入 pole/weighting 攻关，而不是继续把候选阶数往上加。

关键观察：

1. fixed-pole LS 对 PDN 的尖锐阻抗峰谷不够鲁棒；固定极点没有自适应对齐共振。
2. scikit-rf reduced multiport VF 和 scalar surrogate VF 在该数据上都不适合作为快速内循环，180s 内未完成。
3. `peak-poles` 避开 VF 主循环后，30-port 运行时间降到约 3 秒，并能超过 element VF order40 baseline。
4. Hermitian modal basis 明显优于 SVD basis：`mode=16` projection error 从 0.6701 降到 0.4561，最终 fit error 从 0.7120 降到 0.6307。
5. Relative weighting 不宜固定为 `1/|Z|`；V2 的 `relative_weight_power=0.6` 将总误差从 0.5825 降到 0.5549，同时 diagonal error 保持在 0.3267。
6. V3 的 `full-projected` 权重把 full-matrix Z 权重投影回 reduced entries，将总误差降到 0.5184。
7. V4 的 basis 频点数从 9 增加到 17，将 projection floor 从 0.4188 降到 0.4008，并让总误差首次进入 0.5 decades 以下。
8. V5 的 2 轮 `max(original, fitted)` 迭代重加权继续降低 full-matrix RMS，并且 `mode=28/basis_samples=21` 把 diagonal Z log RMS 压到 0.1104。
9. V6 验证 targeted top-k off-diagonal weighting 的收益很小：top-k 加权只能把 0.4770 推到约 0.4768，第三轮还会反弹；当前更有效的是 damping/power/order 的局部调优，得到 0.4729。
10. 原始 Touchstone 里确实有 `0.1 Hz`：频率轴前几项是 `0, 0.1, 0.120226..., 0.131825... Hz`。V6 的 256 点线性 fit sample 包含 `0 Hz` 和 `0.131825... Hz`，但跳过 `0.1 Hz` 和 `0.120226... Hz`。
11. V7 强制纳入前三个 raw 低频点后，总误差从 0.4729 降到 0.4439；这说明低频 worst point 不是文件外插值点，而是 raw 点被 fit sampling 漏掉。
12. `mode/order` 不是单调收益：`mode=30` 虽然 projection 近似为 0，但 full-matrix fit error 反而高于 `mode=28`，说明低秩 basis 带有必要的正则化。
13. 当前 prototype 不检查 passivity，不输出 SPICE，只能作为算法实验。

## 是否继续 Modal-Z 路线

建议：**继续，且把主路线改为 peak-poles reduced Z fitting。**

停止事项：

- 停止 fixed-pole LS 作为主路径。
- 停止 full-matrix VF order sweep 作为主路径。
- 停止在 30-port 内循环中直接调用 scikit-rf reduced multiport `auto_fit()`。
- 停止在未证明 reduced fit 可行前讨论 SPICE export。

继续事项：

- 保留 `fit-modal-z` 作为实验 harness。
- 保留 `basis_projection_z_log_magnitude_rms_error`，它是判断 modal basis 是否值得继续的关键指标。
- 继续推进 `peak-poles`：
  - 更好的峰值选择：按 frequency bands/trace groups 分配 pole budget，避免 mode/order 增加后过拟合局部峰。
  - 更好的 weighting：从逐 trace relative LS 升级为全 matrix Z log objective 的加权策略。
  - 更好的 basis：尝试 frequency-partitioned basis 或端口分组 basis，解决固定全频 basis 的 projection floor。

## 下一步推荐

优先级：

1. **把 modal-Z case 分类**
   - Fit-limited：19p-withcap。basis projection 可接受，但 reduced rational fit 失败。
   - Sample-limited：60p。full raw LS 明显优于 256 点采样。
   - Basis-limited：91p/163p/166p，尤其 163p/166p。
   - 30p 暂时保留为 tuned reference case。

2. **Peak-poles V8：先攻 19p-withcap**
   - 输入仍是 `Zr = Qᴴ Z Q`。
   - 显式报告 selected pole count 和 selected pole frequencies。
   - 按 trace energy、低频峰、全局峰分别分配 pole budget，而不是只靠全局 peak set。
   - 增加 pole mirroring/low-frequency pole floor，避免 0.1-10 Hz 强动态区被高频 pole budget 挤掉。
   - 目标：先把 19p full raw modal-Z 从 `2.9473` 拉回 projection floor 附近，否则该路线不能泛化。

3. **Frequency-partitioned modal basis**
   - 将低频/中频/高频分别构造 basis，再合并或分段评估。
   - 目标：降低 60p/91p/163p/166p 的 `basis_projection_z_log_magnitude_rms_error`，尤其 163p/166p 的 1.5+ decade floor。

4. **Loewner benchmark**
   - 用 same 30-port dataset 构造 Loewner reduced model。
   - 输出 numerical rank、Z log error、fit time。
   - 如果 Loewner 显示低有效秩，再考虑工程化。

5. **Passivity/synthesis 延后**
   - 只有当 reduced fitting error 明显改善后，才讨论 positive-real enforcement 或 SPICE synthesis。

## 本轮产物

- Spec：`docs/superpowers/specs/2026-07-03-modal-z-fit-design.md`
- Roundtable：`docs/superpowers/roundtables/2026-07-03-modal-z-fit-roundtable.md`
- Plan：`docs/superpowers/plans/2026-07-03-modal-z-fit.md`
- Core module：`src/agent_spice/sparam/modal.py`
- Report module：`src/agent_spice/sparam/modal_report.py`
- CLI：`python -m agent_spice.cli fit-modal-z ...`
- 新增 fit methods：`fixed`、`vector`、`shared-poles`、`peak-poles`
- Tests：
  - `tests/test_sparam_modal.py`
  - `tests/test_cli_fit_modal_z.py`
- 30-port reports：
  - `runs-sparam/modal-z-30p/fit_report.json`
  - `runs-sparam/modal-z-30p/fit_report.html`
  - `runs-sparam/modal-z-30p-mode16/fit_report.json`
  - `runs-sparam/modal-z-30p-hermitian8/fit_report.json`
  - `runs-sparam/modal-z-30p-peak16-hermitian/fit_report.json`
  - `runs-sparam/modal-z-30p-peak16-hermitian/fit_report.html`
  - `runs-sparam/modal-z-30p-peak-v2/fit_report.json`
  - `runs-sparam/modal-z-30p-peak-v2/fit_report.html`
  - `runs-sparam/modal-z-30p-peak-v3/fit_report.json`
  - `runs-sparam/modal-z-30p-peak-v3/fit_report.html`
  - `runs-sparam/modal-z-30p-peak-v4/fit_report.json`
  - `runs-sparam/modal-z-30p-peak-v4/fit_report.html`
  - `runs-sparam/modal-z-30p-peak-v5/fit_report.json`
  - `runs-sparam/modal-z-30p-peak-v5/fit_report.html`
  - `runs-sparam/modal-z-30p-peak-v6/fit_report.json`
  - `runs-sparam/modal-z-30p-peak-v6/fit_report.html`
  - `runs-sparam/modal-z-30p-peak-v7/fit_report.json`
  - `runs-sparam/modal-z-30p-peak-v7/fit_report.html`

