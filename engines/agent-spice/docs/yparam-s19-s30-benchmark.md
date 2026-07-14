# Y 与 S 拟合的 S19/S30P 基准

## 协议

输入为仓库内的完整 826 点 Touchstone 数据：

- `user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p`；
- `user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p`。

两条路径均调用同一个 `NativeVectorFitting`，使用相同的对数初始极点、零实极点、
20 个复极点代表、10 次最多 relocation、完整频率网格、无 passivity enforcement。
Y 路径额外保留比例项 `sE`，因为该项对电容导纳是必要的。主指标为完整矩阵
`log10(|Zfit| / |Zref|)` RMS（decades）；Y 的 Z 由数学模型直接求逆，未从 SPICE
反解。

可复现命令：

```powershell
python scripts/benchmark_yparam_vs_sfit.py <input.sNp> `
  --pairs 20 --iterations 10 --output runs-yparam-benchmark/<case>.json
```

## 结果（effective order 40）

| Case | S-fit Z log RMS | Y-fit Z log RMS | Y 相对改善 | S-fit 秒数 | Y-fit 秒数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| S19 with cap | 1.35549 | 1.26713 | 6.5% | 18.23 | 18.62 |
| S30 without cap | 2.18770 | 1.19503 | 45.4% | 45.24 | 46.20 |

S19 的 Y 拟合对角 Z log RMS 为 `0.55488`，S-fit 为 `0.51956`；因此 S19 的总量改善
来自非对角项，并非所有观察量均优于 S。S30 的 Y 拟合对角指标也更低（`1.35360`
对 `1.87614`）。

Y 拟合的最大 `cond(Yfit)` 分别为 `1.331e12`（S19）和 `1.903e16`（S30）。原始
数据在 DC 已分别达到 `1.330e12` 和 `2.648e17`，所以绝对条件数阈值不能用作这类
PDN 输入的简单拒绝门；报告会同时保留原始与拟合条件数。

## 结论与边界

在该固定预算和完整训练网格上，Y 域比同预算 S 域给出更低的全矩阵 Z log RMS，
S30 的改善尤其明显。但这只是表示域基准，不等同于生产替代：尚未做 held-out
频点、Y 正实性 enforcement、互易约束或完整 SPICE/TRAN 签核。当前 `fit-yparam`
已经输出 Z log RMS 与条件数，因此可直接用于这两份输入的可复现诊断拟合。

## Held-out 更新

基准脚本现在默认采用 `--holdout-stride 5`：保留第 2、7、12… 个频点，共 165/826
点，只用其余 661 点拟合。S19、effective order 20、6 次最大 relocation 的 held-out
Z log RMS 为 S-fit `1.45682`、Y-fit `1.20810`，Y 的改善为 `17.1%`。这证明前述
Y 优势并非只由同一训练网格的评分产生；S30 的 held-out 运行仍待 HSPICE/签核阶段
一并执行。
