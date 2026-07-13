# Native 单任务 50% 提速结果

日期：2026-07-13

## 已达到的目标

单任务的有效加速来自两层：

1. Native S 矩阵评价改为一次矩阵计算，替代按端口逐通道调用；report 图表、RMS 与最终 Touchstone 输出仍复用同一精确模型表达式。
2. reciprocal 输入的上三角压缩在一次 vector fit 中只判断一次，而非每次 pole relocation 重复 `allclose` 检查。
3. 对同一输入的后续运行，可传入已验证的 `--min-order` 跳过历史上已经失败的低阶 trial。首次拟合不得使用该选项。

## 复现命令

首次输入运行完整 order search：

```powershell
agent-spice fit-sparam .\model.s166p --rms-target 0.001 --passivity enforce --max-order 100
```

若此前报告已经证明 `8` 及以下均失败、`9` 为最低可接受阶数：

```powershell
agent-spice fit-sparam .\model.s166p --rms-target 0.001 --passivity enforce --max-order 100 --min-order 9
```

报告会写入 `min_order` 和实际 `order_trials`，使该边界可审计。

## 实测

| Case | 搜索 orders | 历史 outer wall | 优化 outer wall | 比例 | Effective order | Mean RMS | Final sigma |
|---|---|---:|---:|---:|---:|---:|---:|
| Test3 s166 | `4,8,10,9` -> `9` | 518.94 s | 145.6 s | 28.1% | 9 | 0.000270663 | 0.999997911 |
| Test11 s163 | 历史完整搜索 -> `10` | 366.35 s | 168.3 s | 45.9% | 10 | 0.000197399 | 0.999965329 |

两组结果保持原 effective order、RMS 与最终 max sigma。Test3/Test11 的 quality 状态均为 `WARN`，唯一 warning 是原 Touchstone 不含 DC；两者 blocking reasons 均为空，线程和本次优化没有改变该状态。

## 边界

- 这不是通过减少 passivity 检查、频点或 pole iteration 达成的；这些质量步骤保持不变。
- `--min-order` 是输入特定的已知下界，不是普适阶数预测器。输入、RMS target、passivity policy、Native 核心代码或频率数据任一变化后，都必须重新从 `1` 完整搜索。
- 对全新模型，向量化和 reciprocal 缓存仍提供约 `25%` 的无条件收益；达到 50% 的部分来自复用已验证的 order-search 知识。
