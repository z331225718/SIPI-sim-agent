# s19 Tangential Loewner 共享极点验证结果

## 结论

**判定：`NO-GO`（`no_order74_candidate`）。**

在冻结的 s19 输入、固定 order `56/60/68/74` 和 10 个方向/partition 配置下，40 个矩阵值双侧 Tangential Loewner 候选全部产生右半平面广义特征值，状态均为 `unstable_pencil`。所有 order 74 候选因此不可用，按 spec 的直接停止规则没有运行 residue LS 或 passivity enforcement。该路线不进入 Native；下一步转独立 RKFIT 共享极点 spike。

## 输入与基线

- 输入：`5power_19port_withcap_122324_202459_11476_DCfitted.s19p`
- SHA-256：`87fccc96196d8c149d1b3ba985701dd56a78f5d9904984f55f8161c39cdd7c7e`
- 规模：19 ports、826 个原始频点；全部频点参与 pencil。
- 固定 order：`56/60/68/74`。
- IdEM RMS：order 56 `0.001452594546`，60 `0.001244555245`，68 `0.001037690482`，74 `0.0009369159680584244`。
- IdEM order-74 的 1.25 倍质量门：`0.0011711449600730305`。
- canonical Native order-74 RMS：`0.0017218406847641665`。

以上身份和基线均由 case config 指向的 canonical artifact 逐字节 SHA 校验后写入 manifest；未将 IdEM 或 Native pole 用作发现 oracle。

## 发现结果

方向网格严格为两种 interleaved partition 乘以随机 seeds `17/29/43/71` 和 `global_svd`，共 10 个配置。每个配置均计算四个冻结阶数，共 40 个候选。

| Order | 候选数 | accepted | unstable | RHP 特征值范围 | `cond(E_r)` 范围 | `sigma_r/sigma_1` 范围 |
|---:|---:|---:|---:|---:|---:|---:|
| 56 | 10 | 0 | 10 | 15-20 | `2.826e5`-`3.657e6` | `2.734e-7`-`3.539e-6` |
| 60 | 10 | 0 | 10 | 14-21 | `3.633e5`-`4.850e6` | `2.062e-7`-`2.753e-6` |
| 68 | 10 | 0 | 10 | 17-21 | `5.388e5`-`7.893e6` | `1.267e-7`-`1.856e-6` |
| 74 | 10 | 0 | 10 | 17-23 | `7.093e5`-`1.148e7` | `8.712e-8`-`1.410e-6` |

相邻截断奇异值比 `sigma_r/sigma_(r+1)` 在四个阶数上的总范围约为 `1.018-1.136`，没有清晰的阶数分离。所有候选的 near-infinite 和 nonfinite 拒绝数均为 0；失败来源明确是 RHP 特征值，而不是 generalized eig 的非有限数值。

## 验收门

机器 `summary.json` 的六项门中，仅 `oracle_clean=true` 通过。absolute RMS、passivity、IdEM 1.25x、minimum passing order 和双方向复现均因不存在合法候选而失败。`best_order74_final_rms` 与 `minimum_passing_order` 均为 `null`，不是零，也不能解释为已执行拟合。

按 spec，“所有方向/partition 在 order 74 都是 `unstable_pencil` 或 `order_unavailable`”直接构成 NO-GO。因此没有为不合法极点运行 fixed-pole LS，也没有通过 pole flipping、人工补极点、自动加阶或额外参数 sweep 绕过停止门。

## 与 D15 的关系

既有 D15 artifact（本次未重跑）记录的是标量随机投影后纵向堆叠 Loewner blocks；它在 Test16 上 12 个候选全部因 `unstable_eigenvalue` 被拒绝。本次实现使用矩阵值双侧切向插值公式、左右方向和 reduced generalized pencil，并未调用 D15 stacked-scalar helper。两条数学路径不同，但各自的已有证据都显示：在禁止 pole flipping 时，相应 Loewner 截断不能给出可进入共享 residue LS 的稳定极点集。

## 证据边界

运行 artifact 位于 `runs-sparam/tangential-loewner-s19-validation/`，不提交仓库。manifest 记录代码提交 `49198bacecca49be16ea19d930912b6db1984d64` 及三个生产者文件 SHA；由于工作树中已有未跟踪的审查 diff，`code_identity.dirty=true`，但生产者文件自身 SHA 已固化。当前 runner 未将 discovery 阶段耗时写入 artifact，因此本报告不据命令行观测值宣称可审计的算法耗时。
