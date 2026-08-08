# Y 正实性 enforcement 与精确有理 LFT 设计

目标交付链为：`Y-fit -> continuous-time Y positive-real enforcement -> exact rational Y-to-S LFT -> S-RFM -> HSPICE`。

## 当前数学边界

Y 正实性不是对若干频点做 clipping。对实、稳定、proper 的实现
`Y(s)=D+C(sI-A)^-1B`，本实现使用 KYP LMI：

```text
P >= 0
[ A^T P + P A,  P B - C^T ] <= 0
[ B^T P - C,   -(D + D^T) ]
```

固定 `A/B` 后，对 `P/C/D` 是凸 SDP。成功结果保留求解器状态、KYP 最大特征值、`P` 最小特征值和校正量；这才可以称为连续频带 PR certificate。

精确转换不是重新采样再做 S vector fitting。状态空间 LFT 为
`S=(I-z0Y)(I+z0Y)^-1`，新 S 的极点来自闭环状态矩阵，而非原 Y 的 poles。`rational_lft.py` 从该状态空间直接做特征展开，生成现有 RFM writer 所需的 S pole/residue。

## 受控首版限制

- 只接受共享正实 `z0`、稳定、实系数 Y。proper Y 直接走标准状态空间 LFT；`sE` 路径在 `E` 实对称正定且条件数受控时走精确 descriptor LFT。
- KYP SDP 使用 `cvxpy` + PSD-cone solver，默认最多 128 个 dense state；超限硬失败，不退化为 sampled heuristic。
- 校正超过相对预算（默认 5%）硬失败，避免用“无源”掩盖严重保真度损失。
- 奇异/半正定的 descriptor `sE` 仍需要 QZ/index reduction，尚未实现；不得静默丢弃 E。
- 最终 S 常数项可以是 lossless 边界值，验收应允许 `sigma_max <= 1+epsilon`，不能强行投影到严格小于 1 后还称为精确 LFT。

## 验证门

1. KYP certificate 数值复核；
2. exact LFT 的 S 与直接矩阵 LFT 在输入频点、中点与 pole-neighbourhood 的误差；
3. RFM 回读对 state-space S 的误差；
4. HSPICE AC 后再进行 TRAN。

当前 VDDQ 2-port proper Y fit 的 KYP 校正量超过可接受预算，因此该真实数据集尚未产生合格的 exact Y-derived S-RFM；这是质量失败，不是回退到采样 S refit 的理由。
