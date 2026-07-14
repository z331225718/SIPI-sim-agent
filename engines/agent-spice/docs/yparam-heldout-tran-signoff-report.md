# Y-parameter fit: held-out、enforcement 与 TRAN 签核报告

日期：2026-07-15  
结论：Y-fit 在独立频点上的 Z 域误差有改善，但本轮不能给出 enforcement 或 TRAN 通过签核。

## 范围和基准

本报告比较三条路径：

1. 原始采样 Touchstone；
2. S-fit 的 HSPICE RFM；
3. Y-fit 的 common-ground Norton/MNA SPICE 宏。

这里需要澄清术语。HSPICE 不能直接把多端口采样 `.sNp` 当作“直接卷积”元件使用；TRAN 的原始参考是 HSPICE `S` 元件读取 Touchstone 后进行的原生 IFFT 时域求解。因此它是本次可执行的 sampled-Touchstone transient reference，而不是另行实现并验证过的数学直接卷积 oracle。RFM 是有理模型格式，当前只支持 S 参数；Y-fit 不能物理正确地直接导出成 `MATRIX_TYPE Y` RFM，故第三条路径使用 Norton/MNA 宏，而不是伪造 Y RFM。

## 产物和可复现命令

完整运行目录为 `runs/yparam-tran-signoff/`。2-port 规约输入为 `vddq_port3_port10.s2p`，对应 VDDQ port 3 到 port 10；使用同一 CPM、0.8 V VRM、`method=gear`、`reltol=1e-5`、`10 ps` 输出步长、`14 ns` 停止时间。

S-fit：

```powershell
python -m agent_spice.cli fit-sparam runs/hspice-native-fit-comparison/vddq_port3_port10.s2p `
  --output runs/yparam-tran-signoff/sfit.sp `
  --fitted-touchstone runs/yparam-tran-signoff/sfit.s2p `
  --rfm runs/yparam-tran-signoff/sfit.rfm `
  --report runs/yparam-tran-signoff/sfit.json `
  --rms-target 0.005 --passivity enforce --max-order 60 --subckt-name sfit_model
```

Y-fit：

```powershell
python -m agent_spice.cli fit-yparam runs/hspice-native-fit-comparison/vddq_port3_port10.s2p `
  --output runs/yparam-tran-signoff/yfit.sp `
  --report runs/yparam-tran-signoff/yfit.json `
  --n-poles-real 0 --n-poles-cmplx 30 --fit-iterations 20 `
  --passivity check --subckt-name yfit_model
```

HSPICE 使用 PrimeSim HSPICE `T-2022.06-1 win64`，许可证为 `27000@zzm-minicenter`。执行过的网表是 `sfit_vs_raw_tran.sp` 和 `three_way_tran.sp`，测量窗口均为 CPM presimulation 后的 `3.5 ns` 至 `14 ns`。

## Held-out 频点结果

S19 用每 5 个频点留出 1 个（从索引 1 开始），总共 826 个频点，其中 165 个未参与拟合。比较指标是从拟合的 S/Y 换算得到的 Z 的逐元素对数 RMS；数值越低越好。

| 数据集 | S-fit held-out Z-log RMS | Y-fit held-out Z-log RMS | Y-fit 改善 |
| --- | ---: | ---: | ---: |
| S19 | 1.45682 | 1.20810 | 17.1% |

这说明“先拟合 Y、再以 Z 指标评估”的方向对未见频点是有价值的；并不等价于已经获得可用于 transient 的稳定、被动有理模型。完整的固定预算 S19/S30 对比见 `docs/yparam-s19-s30-benchmark.md`。

## Enforcement 结果

S-fit 请求了 `--passivity enforce`，但目标 RMS `0.005` 未达到：有效阶数 60 时 S 参数平均 RMS 为 `0.00602983`。实现按策略跳过 enforcement（`pre_rms_above_target`），所以 `passive_after_enforce` 和 after-passivity 指标均为 unknown。该 RFM 可用于比较，但不得标为“已 enforcement”。

Y-fit 的采样 positive-real 检查通过：最小 Hermitian 特征值为 `0.4274696 S`（2 GHz），违规数为 0；但当前实现只有 `off/check`，报告明确记录 `enforcement: not implemented`。采样点 PR 检查也不能证明连续频带上的正实性。因此，Y-fit 同样不得标为“已 enforcement”。

## HSPICE TRAN 结果

S-fit RFM 与原始 sampled-Touchstone 在同一 HSPICE 网表中完成至 14 ns：

| 测量（3.5-14 ns） | 结果 |
| --- | ---: |
| 原始 Touchstone `V(cpm_raw)` 最小值 | 0.6969 V |
| S-RFM `V(cpm_sfit)` 最小值 | 0.6975 V |
| S-RFM 对原始参考 RMS 差 | 0.0006793 V |
| S-RFM 对原始参考峰值差 | 0.001294 V |

对应证据为 `runs/yparam-tran-signoff/sfit_vs_raw_tran.mt0` 和 `.lis`。该项仅说明此 2-port CPM 激励下 S-RFM 与 HSPICE 原始参考接近，不替代被动性签核。

Y-fit Norton/MNA 宏没有通过 TRAN：三路网表在约 `4.2 ns` 中止，未生成 `.mt0`，也没有 `hspice job concluded`。将 `RESMIN` 从默认值降低到 `1e-20` 后仍复现。日志同时记录宏中大量极小电阻和巨大伴随电容；HSPICE 对这些元件进行了恢复/限制，说明当前非缩放的直接电路实现数值刚性很强。故无法给出 Y-fit 对原始参考的完整 3.5-14 ns RMS，也不能将其视为 transient 合格。

## 最终判定

- Held-out：**Y-fit 改善 17.1%，通过研究性比较。**
- S-fit enforcement：**未通过/未完成。** enforcement 因拟合精度门限未满足而跳过。
- Y-fit enforcement：**未实现，未通过。** 仅完成采样 PR 检查。
- S-fit TRAN：**完成比较，但不是完整 signoff。**
- Y-fit TRAN：**失败。** 当前宏在标准 14 ns CPM 场景无法完成。

因此本功能的研究性目标已经验证：Y-fit 对 held-out Z 指标有提升；生产签核目标尚未完成，不能把本轮结果宣称为 “enforced” 或 “TRAN signed off”。

## Y-derived S enforcement 试跑

按后续确定的交付路线，已在同一 2-port 上执行 `Y fit -> 严格 LFT 采样 S -> S refit + --passivity enforce`。中间 S 与最终 S-RFM 的平均 RMS 为 `0.0070106`，S-RFM 相对原始 S 的平均 RMS 为 `0.252786`，而 Y-derived S 相对原始 S 为 `0.252912`。因此 enforcement/refit 没有显著恶化转换后的原始 S 误差（变化 `-0.000126`），但两者相对原始 S 都过大，绝不能以“前后接近”取代绝对质量门。

该试跑的 `passivity_max_sigma` 在 enforcement 前后均约 `0.995113`；它验证了 S-domain 路径可执行，而非证明 Y 已 enforcement。命令、字段定义与门槛见 `docs/yderived-s-enforcement-workflow.md`。

该 Y-derived S-RFM 也已完成 HSPICE 14 ns TRAN：相对原始 sampled-Touchstone reference 的波形 RMS 差为 `3.474 mV`，峰值差为 `5.169 mV`。它避开了 Y Norton/MNA 宏在 4.2 ns 的数值中止，但在这个 CPM 场景中仍明显劣于直接 S-fit RFM 的 `0.6793 mV` RMS；因此它是可运行的交付路径验证，不是质量签核通过。

## 下一步

1. 为 Y 有理模型实现真正的连续频带正实 enforcement（例如 KYP/LMI 或等价有理 PR 判定与受约束校正），并将未完成 enforcement 作为硬失败而非 warning。
2. 先做 HSPICE AC 宏对解析 Y 的逐点回归，量化 `RESMIN` 前后的误差；随后重标度每个状态（固定目标电阻，再同步调整电容、输入 VCCS 与复极点交叉项），并让 exporter 拒绝会触发 `RESMIN` 的元件。通过 AC 后先用半程 TRAN 回归，再恢复至 14 ns。
3. S-fit 需在 RMS `<=0.005` 前提下真正完成 passivity 后检查，再重跑同一张 TRAN 网表。
4. 若需要“直接卷积”字面意义的黄金基准，应单独实现并验证 Touchstone IFFT/convolution 参考；在此之前，报告应明确使用 HSPICE 原生 sampled-Touchstone reference。
