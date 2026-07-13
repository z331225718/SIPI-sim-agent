# Native S 参数线程性能结论

日期：2026-07-13

## 结论

Native 已具备可控的 BLAS 多线程启动器，但在当前算法与数据形状下，**不要把单个 large-port fit 配置为 64 个 BLAS 线程**。在本机的三组完整矩阵中，`1` 线程始终最快；相对于当前 OpenBLAS 默认 `16` 线程，设为 `1` 线程可缩短总墙钟时间 `23%` 至 `37%`。

生产命令应使用新启动器，并从 `1` 开始：

```powershell
agent-spice-native --blas-threads 1 fit-sparam .\path\to\model.s166p `
  --rms-target 0.001 `
  --passivity enforce `
  --max-order 100 `
  --output runs-sparam\model.sp `
  --report runs-sparam\fit_report.json `
  --html-report runs-sparam\fit_report.html `
  --log runs-sparam\fit.log
```

该命令在新 Python 子进程启动前同时固定 `OMP_NUM_THREADS`、`MKL_NUM_THREADS`、`OPENBLAS_NUM_THREADS` 和 `NUMEXPR_NUM_THREADS`，因此不会受到已导入 NumPy 后环境变量失效的问题影响。`agent-spice-native` 的默认值就是 `1`。

## 测量方法

- 机器：Windows，1 个处理器、16 logical processors；OpenBLAS `0.3.31`，SkylakeX。
- 固定输入：Test3 s166、Test11 s163、Test16 s91；`rms-target=0.001`、`passivity=enforce`、`max-order=100`、`quality-profile=signoff`。
- 每个格子为全新子进程，记录输入 SHA、Native 核心文件 SHA、BLAS 环境、CPU 秒、进程峰值 RSS、全部原始输出和 JSON 结果。
- 每一组保持 effective order 不变、没有 quality blocking reason；Test3 的 RMS 在线程之间有最大 `0.28%` 的浮点差异，仍远低于 `0.001` 目标。Test11 与 Test16 的 RMS 和最终 sigma 在各线程下相同。
- Test3/Test11 的 signoff `WARN` 仅因原始文件不含 DC 样本；Test16 在所有线程均因既有 `comparison_rms_error` 门禁为 `FAIL`。这些输入质量状态没有因线程而改变，故本报告不把它们误写为签核通过。

## 完整矩阵

| Case | Ports | Threads | Wall s | Fit s | Check s | Enforce s | 相对 1-thread | CPU % | Peak RSS MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Test3 | 166 | 1 | 518.94 | 193.38 | 96.02 | 108.29 | 1.00x | 96.39 | 3376.71 |
| Test3 | 166 | 8 | 673.04 | 415.73 | 45.38 | 84.03 | 0.77x | 146.32 | 3208.80 |
| Test3 | 166 | 16 | 637.20 | 363.09 | 47.73 | 100.79 | 0.81x | 201.12 | 3109.52 |
| Test3 | 166 | 32 | 628.93 | 354.59 | 46.79 | 101.80 | 0.83x | 202.68 | 3267.13 |
| Test3 | 166 | 64 | 636.35 | 361.96 | 46.51 | 101.65 | 0.82x | 201.54 | 3432.89 |
| Test11 | 163 | 1 | 366.35 | 172.66 | 46.02 | 50.73 | 1.00x | 99.58 | 3251.07 |
| Test11 | 163 | 8 | 558.65 | 387.88 | 23.27 | 36.08 | 0.66x | 130.04 | 3377.18 |
| Test11 | 163 | 16 | 578.98 | 387.22 | 25.36 | 43.81 | 0.63x | 156.75 | 3420.66 |
| Test11 | 163 | 32 | 577.34 | 385.61 | 25.41 | 43.58 | 0.63x | 161.29 | 3301.37 |
| Test11 | 163 | 64 | 577.93 | 385.84 | 26.42 | 42.72 | 0.63x | 158.33 | 3273.47 |
| Test16 | 91 | 1 | 249.82 | 88.78 | 55.47 | 59.52 | 1.00x | 99.79 | 1432.55 |
| Test16 | 91 | 8 | 325.23 | 190.42 | 34.46 | 47.36 | 0.77x | 154.88 | 1256.99 |
| Test16 | 91 | 16 | 352.96 | 191.31 | 42.06 | 61.51 | 0.71x | 210.96 | 1345.12 |
| Test16 | 91 | 32 | 362.44 | 192.85 | 44.44 | 64.76 | 0.69x | 220.85 | 1455.16 |
| Test16 | 91 | 64 | 351.76 | 190.63 | 41.61 | 60.22 | 0.71x | 201.91 | 1405.38 |

原始可恢复矩阵保存在 `runs-sparam/native-thread-*`（不提交）；运行器为 `scripts/sparam_native_thread_benchmark.py`，固定 cases 为 `scripts/sparam_native_thread_cases.json`。

## 决策

1. 当前收益已经落地为可控的 `agent-spice-native --blas-threads 1`。在这台机器上，避免默认 16-thread OpenBLAS 比尝试 64 线程更快。
2. 不做 Python 改写、response-block 多进程或 C++/Rust 重写。三组数据中 fit 阶段虽然最大，但请求 8--64 线程反而从约 `89--193 s` 增至约 `191--416 s`；CPU 也只升到约 1.3--2.2 个核心，没有可供外层并行直接收割的证据。response-block 还会重复矩阵分解，并改变数值归约路径。
3. 64-core 生产机仍应复跑相同矩阵后再改变策略。本机只有 16 logical processors，不能把本机的 32/64 oversubscription 误称为 64-core 可扩展性证明。当前可安全部署的初始策略是每个并发 fit 一个 BLAS 线程；64 核吞吐应来自最多 64 个独立作业，而不是一个 fit 内开 64 个线程。
4. 若生产 workload 是单个超大模型且必须进一步降低单 job 延迟，下一个研究必须先用 profiler 定位具体 NumPy/SciPy 调用，再独立实现并验收一个 compiled kernel；这不是当前证据支持的直接重写任务。
