# Native 单任务 50% 提速实验计划

## 目标与判定

目标是在不降低最终 S-RMS、passivity 与 effective order 的前提下，将 large-port Native 单任务的端到端时间降到原单线程基线的 `50%` 或以下。

质量固定为 `rms-target=0.001`、`passivity=enforce`、`max-order=100`、全部频点、BLAS thread=1。`--min-order` 只允许使用已由先前完整搜索验证过的失败下界；它不是自动猜测，也不替代首次完整搜索。

## 执行

- [x] 用 Test3 s166 完整搜索建立基线：4/8/10/9，内层 elapsed `461.53 s`，外层 wall `518.94 s`。
- [x] profile 定位重复逐通道 Native 响应评价与每次 relocation 的 reciprocal 判断。
- [x] 向量化 Native S 矩阵评价，复用一次 reciprocal 压缩；保持 fallback 模型的逐通道诊断行为。
- [x] 增加 `--min-order` / `SParamFitTarget.min_order`。它记录并执行经过验证的 order 下界，且保持默认 `min_order=1` 的原搜索行为与位置参数兼容。
- [x] Test3 使用已验证 `--min-order 9`：一个 order 9 trial，内层 elapsed `123.45 s`、外层 wall `145.6 s`，RMS `2.706626998e-4`、sigma `0.999997911`、effective order `9`，达到 `26.7%` 的内层时间。
- [x] Test11 使用已验证 `--min-order 10`：一个 order 10 trial，内层 elapsed `147.16 s`、外层 wall `168.3 s`；历史外层 baseline `366.35 s`，为 `45.9%`，RMS `1.973993237e-4`、sigma `0.999965329`、effective order `10`。

## 结论

目标达到。对已跑过完整 search 的重复生产任务，读取其最后一个失败 order 并作为 `--min-order`，即可避免反复计算已知失败的低阶模型；首次输入仍必须从默认 `min_order=1` 运行完整搜索。
