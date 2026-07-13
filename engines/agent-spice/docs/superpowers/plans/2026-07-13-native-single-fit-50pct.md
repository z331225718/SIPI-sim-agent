# Native 单任务 50% 提速实验计划

## 目标与判定

目标是在不改变 Native 的输出契约前提下，将一个 large-port、`passivity=enforce` 的完整单任务端到端时间降到当前单线程基线的 `50%` 或更低。

主判定 case 为 Test3 s166；复验 case 为 Test11 s163。每次比较必须保持：

- `rms-target=0.001`、`passivity=enforce`、`max-order=100`、所有频点与 Native 策略不变；
- effective order、quality status、blocking reasons、最终 RMS 和 final max sigma 满足既有质量契约；
- `OMP/MKL/OpenBLAS/NumExpr=1`，避免把线程数变化伪装成算法提速；
- 用全新子进程测量端到端 wall time，并保留报告、输入 SHA 与代码 SHA。

现有基线（Test3 s166）为 `518.94 s`，故目标为 `<=259.47 s`。

## 路线

1. 使用 cProfile 与现有阶段时间冻结真实热点和 order-search 成本。
2. 优先消除重复的确定性工作，例如重复加载、重复模型评价或可安全复用的矩阵分解；不减少验证点、不降低 passivity 采样、不修改 pole search。
3. 每个候选优化先做单元/等价测试，再做 Test3 端到端测量；只有达到质量等价且带来实测收益才保留。
4. 达到 Test3 `<=50%` 后，在 Test11 复验；若 Test11 不能保持至少 `45%` 提速，记录为 case-specific，不作为生产默认。

## 交付

- 可复现 benchmark 命令和 JSON/Markdown 结果；
- 质量等价测试；
- 实现、技术结论和提交记录。
