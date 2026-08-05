# ADR-008: 默认进程隔离边界

状态：已接受。

默认使用进程隔离。作为平台 in-process 执行模式的 FFI/PyO3 仅在 profiling、panic、cancel 与资源门禁证明后开放，不影响既有实现作为进程 adapter 的引擎资产；本 ADR 不承诺 hard resource enforcement，也不重复 ADR-010 的平台选择。
