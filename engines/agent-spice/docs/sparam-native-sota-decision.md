# Native S 参数 SOTA 路线阶段决策

日期：2026-07-11

## 决策

**不把本轮 NNLS 或 relocation-frontier 实验提升为 Native 默认。** 两项能力保留为内部实验代码和后续研究基础。

## 证据链

1. [S19 NNLS 试验](/C:/Users/z3312/code/agent-spice/docs/sparam-native-nnls-s19-results.md) 在两个有足够 raw-RMS 余量的 frontier candidate 上均未通过最小产品契约：`RMS <= 0.001` 且 `max sigma <= 1 + 1e-6`。
2. 压缩确实发生：order-93 active-mode solve 从完整 33,573 变量缩到 372 变量；但端到端 enforcement 仍约 117 秒、约 549 MB。当前主要成本仍在 legacy projection 候选、全频评估和 line search，而不是 NNLS 子问题。
3. relocation-frontier 已能保存并按 raw-RMS/pre-sigma 代理排序 checkpoint，且不会突破 post-relocation 阶数上限；但 s19 当前 topology 仍选到最后 checkpoint，不能解决 gate 失败。
4. 既有完整语料基线见 [Native vs IdEM Full-Corpus Benchmark](/C:/Users/z3312/code/agent-spice/docs/sparam-idem-full-benchmark.md)。其中 60+ port 的 Native 已可接受，但 91/163/166 port 在时间或阶数对标上落后；该数据不是 NNLS/frontier 的 cross-corpus 胜利，不能拿来为新实验背书。

## 对 Task 7 的处理

本计划原本规定在 s19/s30/s60/s91/s163 上运行 NNLS/frontier 的完整对比。该 sweep **未启动**，原因不是缺少数据，而是 Gate B 已失败：新路径连定义它的 s19 强制无源契约都不满足。此时花费数小时跑大端口只能扩大失败样本，不能构成默认升级证据。

因此本阶段的 cross-corpus 结论是 **early reject，不推广**，而非“NNLS 已在完整语料验证”。这一措辞很重要。

## 下一次进入该路线的前置条件

满足下面任一条件后再启动完整 sweep：

- fit-aware frontier 使用实际 NNLS 修正后的 RMS/sigma 成本，而非只使用 pre-sigma 代理，并在 s19 先得到 accepted model；或
- 引入与公开 RP-NNLS 数学更接近的 residue 特征值扰动/QR 消元实现，s19 达到 Gate B；或
- 选择新的 raw model，实测具有足以覆盖 residue-only 无源修正的 RMS 余量。

届时完整语料 benchmark 必须以相同输入 hash、全频训练/评估、RMS/sigma 定义、阶数限制和 passivity policy 重跑，且只比较 accepted model。
