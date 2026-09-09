# SIPI-sim-agent

面向 SI/PI、串行链路和 IEEE 802.3 COM 分析的原生仿真平台。

当前状态：`v0.2` 产品重基线。终态为 Rust-only 的统一平台：第一方源码为 MIT，逐文件获准的第三方直接移植保留其自身兼容许可证；旧项目只作为已授权源码候选或工作树外 oracle，不作为产品运行依赖。

## Windows 源码运行

**`git clone` 只下载源码，不包含 Rust、C++ Build Tools 或编译好的 `sipi.exe`。**
`target/` 是本机生成目录，不提交到 Git。下面是默认 Rust CLI 的开发构建流程，
不是已签核的发行包，也不会启用隔离中的可选 direct-port 功能。

首次在 Windows x64 机器上使用：

1. 安装 [Rust/rustup](https://rust-lang.org/tools/install/)，使用 MSVC 工具链。
2. 通过 Visual Studio Installer 安装“使用 C++ 的桌面开发”，包括 MSVC x64/x86
   编译工具和 Windows 10/11 SDK。已有 Visual Studio 也要确认这些组件已安装；
   不需要为运行仿真安装完整 IDE。参见 [Rust 官方 Windows 前置条件](https://rust-lang.github.io/rustup/installation/windows-msvc.html)。
3. 新开 PowerShell，在 clone 的仓库根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -Check
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build_windows.ps1
```

脚本识别 PATH 和 `%CARGO_HOME%\bin`（默认 `%USERPROFILE%\.cargo\bin`）中的
Cargo；缺依赖时会列出修复提示，不自动安装系统软件、不修改永久 PATH。
`-Check` 只检查前置文件；构建时 rustup 按 `rust-toolchain.toml` 选择
`1.97.0-x86_64-pc-windows-msvc`，首次下载工具链和 crates 需要联网。
安装被公司策略限制时，请由管理员配置，不必关闭系统安全策略。

构建成功后，脚本会实际验证一个 matched-through channel kernel，期望结果 `[1, 0]`。
使用明确的 exe 路径，避免和旧 Python CLI 同名入口混淆：

```powershell
$sipi = '.\target\x86_64-pc-windows-msvc\release\sipi.exe'
& $sipi version --json
& $sipi doctor --json
& $sipi capabilities --json

$example = & $sipi example channel.run --json | ConvertFrom-Json
$example.result.request | ConvertTo-Json -Depth 40 -Compress | & $sipi channel run --stdin
```

这是受限的 matched-S21 kernel 示例，不代表完整 PyBERT 链路或 ADS bench 验收。
编译需要 Rust/Build Tools；运行已构建的默认 exe 不应再调用 Cargo。
**`uv sync` 和下面的 Python 验证命令用于旧迁移设施，不会构建 Rust 主程序。**
单独开发的 `Py-bert-agent` / `pybert channel` 也不是本仓库 clone 后自动安装的组件。

## Channel 原生候选入口

Channel 主线现在直接在 **SIPI 本仓库** 接入已有 `sipi-pybert-direct`，不需要再 clone
PyBERT、安装 Python 或调用另一个仿真程序。显式启用候选模块后仍只有一个 `sipi.exe`：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -Channel
$sipi = '.\target\x86_64-pc-windows-msvc\release\sipi.exe'
& $sipi channel help
& $sipi channel init channel-request.json
& $sipi channel simulate channel-request.json --output-dir results/channel-native-run
Start-Process .\results\channel-native-run\report.html
```

示例为 32 Gbit/s NRZ、PRBS9、5 cm metallic line，共 8192 个波形样点。
输出原生 `meta.json` / `arrays.npz`、全量逐点 CSV、离线 HTML 和最后写入的哈希收据。
离线报告可浏览完整时段、切换阶段曲线和读取原始样点；随输出生成 `channel-report.js`，
无需 Node 或本地服务器，保持它与 `report.html` 同目录即可。
请求文件和输出目录均不覆盖已有内容。编译后运行不依赖 Rust/Cargo。

需要实际负载电压定义和保留 impulse 原点时，可显式选择独立的物理模式：

```powershell
& $sipi channel simulate channel-request.json --output-dir results/channel-physical-run `
  --channel-policy physical-voltage-v1
```

需要使用 Touchstone S 参数文件（.s2p / .s4p）、typed 端口映射或多级频域网络级联时，可显式选择 Touchstone 网络模式：

```powershell
& $sipi channel init channel-touchstone.json --template touchstone-network
& $sipi channel simulate channel-touchstone.json --output-dir results/channel-touchstone-run `
  --channel-policy touchstone-network-v1
```

该模式完整计算 2x2 差分 S 矩阵、频域 Redheffer 星积级联、源/负载端接加载、DC/Nyquist 覆盖诊断、离散采样无损/互易性诊断，并在最终执行一次严格保留 $t=0$ 原点的 FD-to-TD 变换；同时导出 `frequency-response.csv` 与多级节点 `cascade-nodes.csv`。启用统计分析时另导出 `eye-metrics.csv`、`bathtub.csv`、`eye-contours.csv` 并在离线报告中提供互动浴盆曲线视图。

该模式另导出完整 `frequency-response.csv`；有限带宽、窗口和 sample-hold 仍有明确边界，
不等同于连续时间 ADS Transient 已通过。未传选项的 PB-02 兼容行为不变。

这是 PB-02 的**本地候选连接**，不是完整 PyBERT/ADS parity、许可签核或发布验收；
默认构建仍不启用它，旧 `channel run --stdin` 的 kernel 合同保持不变。
参数、导出单位和剩余工作见 [原生 Channel 工作流](docs/channel-native-workflow.md)。
实际 `sipi.exe` 与 ADS 的全量逐点 bench 已接通。当前 v3 参考改用解析材料表达式，
补查网格中点、低频/带外响应及精确 RC 时域控制；旧 v1/v2 证据仍可复核，不隐式升级。
显式物理模式单独检查负载电压；实际 kernel、启动历史与连续时间 Transient
仍需逐层收口，不能把参考控制或频域通过当作整条链路通过。
**有损线的 v3 Transient 卷积参考仍未通过自检，其 TD 差异不能全部归于 SIPI。**
不能将兼容模式波形直接当作绝对传播时延或物理负载电压，详见
[ADS 数值诊断](docs/channel-native-ads-diagnostics-20260909.md)。

## 核心文档

- [SPEC.md](SPEC.md)：产品范围、目标架构、公共契约、引擎边界和验收标准。
- [PLAN.md](PLAN.md)：纵向能力计划、任务依赖、质量门禁和旧资产处置。
- [ADR-011](docs/adr/ADR-011-native-mit-rust-product-boundary.md)：MIT 第一方源码、Rust-only 终态和旧项目 oracle 边界。
- [ADR-014](docs/adr/ADR-014-selective-bsd3-direct-port-boundary.md)：按路径保留 BSD-3-Clause 的直接移植边界。
- [ADR-015](docs/adr/ADR-015-upstream-capability-first-rust-consolidation.md)：现行的三库工作流整合与逐行 Rust 替换顺序。

## 一句话架构

一个 Rust workspace 提供 `sipi` CLI、contracts、artifacts、runtime、pipeline 以及 TRAN、Channel、IBIS-AMI、COM 内核；旧 Python/MATLAB/可执行文件仅在发行边界外生成行为规格和比较证据。

## 旧项目定位

下表保留 v0.2 重基线时的定位。现行执行顺序以 ADR-015 为准：三库已有的整合代码和
Rust 候选继续复用，不因这张历史表重新实现 PyBERT 数值内核；候选是否获准发布仍单独审核。

| 项目 | v0.2 历史角色 | 当时关键约束 |
| --- | --- | --- |
| `agent-spice` | MIT Rust TRAN 候选与外部 oracle | 逐文件来源/依赖审计后才可 promotion；Python/旧 bundle 不发布 |
| `Py-bert-agent` | Channel/IBIS-AMI 黑盒 oracle | BSD/非 MIT 源码和派生历史不迁入产品；Channel 由 clean-room Rust 重做 |
| `agent-com` | MIT 行为/源码参考与外部 oracle | 最终运行时移植为 Rust；MATLAB、workbook 和私有 corpus 单独管理 |

既有 M3/M4/M5 审计、S2P/RFM/AMI compare 和 source CI 继续作为迁移证据，但不等于 Rust-only 产品已经完成。

## 目标产品面

- `sipi` 单一公开 CLI，稳定 JSON schema、capabilities、errors 和 provenance。
- TRAN、Channel、IBIS、AMI、COM 独立 Rust crates。
- typed pipeline、内容寻址工件、stage compare 和 profile 级能力认证。
- MIT 第一方源码边界；获准的第三方直接移植和依赖保留其许可证，供应商模型/DLL 默认外部提供。
- 面向 AI 的机器可发现接口，不提供隐式 fallback 或任意 shell 能力。

实施从 [PLAN.md](PLAN.md) 的 `P0` 产品/clean-room 边界开始。

## 许可边界

根 [LICENSE](LICENSE) 仅覆盖
[`product-boundary.v1.yaml`](product-boundary.v1.yaml) 中标为
`product_candidate`、`license: MIT` 的第一方文件。获准的第三方直接移植必须由
其路径记录的许可证、NOTICE 和 SBOM 覆盖，根许可证不改写它们。当前清单是
`provisional`：Python 迁移设施、旧引擎、候选 Rust crate、fixtures 和外部资产
不会因根许可证而被重新授权或纳入发行物。完整范围见
[LICENSE-SCOPE.md](LICENSE-SCOPE.md)。

## Clean-Room 门

[`clean-room-register.v1.yaml`](clean-room-register.v1.yaml) 是材料、角色和
attestation 的 fail-closed 声明门。它目前仅为 `provisional` 模板，不能证明
认知隔离、授权 release 或 promotion 任何现有 Rust candidate；完整流程见
[docs/clean-room/README.md](docs/clean-room/README.md)。

## Python 迁移设施验证

```powershell
uv run python -B tools/sync_contracts_schemas.py  # schema 变更后同步打包副本
uv run python -B tools/run_all_tests.py           # 单元测试门禁
uv run python -B tools/run_all_tests.py --full    # 含外部探针的 M1 conformance
uv run python -B tools/clean_install_smoke.py     # M2-08：wheel 构建 + 隔离 venv 冒烟
```

仓库以 `schemas/` 为权威 schema 源，打包副本 `packages/sipi-contracts/src/sipi_contracts/_schemas` 不提交到 Git；修改任何 schema 后先运行同步脚本，否则 `sipi doctor` 会按缺失报告。
