# ADR-010: M0 首签核平台与认证环境

状态：已接受（M0 选择；尚未认证）。

## 决策

首个签核目标选择 `Windows x86_64 + CPython cp312 ABI`，M0 的具体证据实现固定为
`CPython 3.12.13`。这是一项复验目标选择，不是发布支持承诺，也不把任何已有
baseline 提升为 certified。

支持键与一次环境实现分层：

- 长期支持键：OS family、architecture、Python implementation/ABI 和 execution
  mode。M0 的键为 `windows/x86_64/CPython/cp312/managed_worker`。
- 复验证据实现：Python patch、Rust target/toolchain、MSVC 版本、lock digest、
  native DLL closure、BLAS 及其线程设置。任一项变更都需要重新取得证据。

M0 的可机器读取记录是
[`platform-support.v1.json`](../baselines/platform-support.v1.json)，其验证器是
[`verify_m0_platform_support.py`](../../tools/verify_m0_platform_support.py)。记录
引用现有锁和三份 baseline 的内容哈希，而不复制本机绝对路径或共享虚拟环境。

## 支持层级

| 范围 | M0 状态 | 含义 |
| --- | --- | --- |
| Windows x86_64 / CPython cp312 / managed worker | `tier_1_certification_target` | 已选为首签核目标；managed worker 尚未验证，整体尚未 certified |
| Linux、macOS | `portability_intent_unverified` | 有移植意图，未作支持承诺 |
| 其他平台、ABI、执行模式 | `unassessed` | 没有 M0 结论 |

`Tier 1` 在 M0 仅表示认证优先级。只有 M2 bundle attestation、对应 capability
key 的通过证据和生命周期/资源故障 fixture 齐备后，才可以把特定组合标为
`certified`。

## 认证环境边界

- 三个引擎始终使用独立 lock 与独立环境；不得建立共享 venv，亦不得以 sibling
  editable/path dependency 作为发布证据。
- Rust native 工具链为 `1.97.0-x86_64-pc-windows-msvc`，MSVC Build Tools 为
  `17.14.34`；它们属于本轮 evidence realization，不是对所有 Windows 编译器的
  兼容声明。
- Python、Rust、MSVC、Windows runner/image、Windows SDK/CRT、每个引擎 lock、
  BLAS/线程变量、native DLL closure、fixture hash、source tag 或 solver binary
  改变时，候选发布必须重新验证。
- M0 已记录工具链版本、Rust commit、MSVC installation version 和输入 lock hash；
  Windows edition/build、SDK/CRT manifest、CI runner image identity 和 DLL closure
  尚未被完整封存，故不能称为发布认证环境。

## Native 与外部 Solver

Agent-Spice Rust CLI/wheel、PyBERT PyO3 与 agent-com SciPy 都只能引用各自有限
baseline；baseline 中的通过范围、失败、资产阻断和 lock provenance 缺口保持原样。
它们不是平台或 capability certification。

ngspice、Xyce、XDM 与 MATLAB 只为 `observed_local`。HSPICE 和 ADS 当前为
`unavailable`。solver capability 必须另行固定版本、binary hash、许可证状态、probe
fixture 和 capability evidence 后才可 advertise；绝对路径、本机安装或单次可调用
均不构成支持或再分发承诺。

## 复验与非声明

每个 release candidate 都必须重新验证记录引用的环境/锁与相应 native evidence；
在干净环境中安装 wheel，且没有源码仓或 sibling repo，才是后续发布门禁的一部分。
本 ADR 不声明：正式 release support、跨平台兼容、任一 operation/capability
certified、资源限制 hard enforcement、solver 可用性、solver 再分发或许可证授权。
