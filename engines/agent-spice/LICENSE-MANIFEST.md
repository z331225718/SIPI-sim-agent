# 许可分类清单 (M0-09)

- **状态**：cleanroom 边界用途的事实分类与证据记录。本清单**不**单边宣称
  certified，也不对外 advertise；仅记录每项资产的分类态与授权依据，
  缺口（`blocked_unknown`）标注 gap owner 与升级路径。
- **范围依据**：
  - `setup.py` 的 `package_data` 与 `pyproject.toml` 的 `[tool.setuptools.package-data]`
    定义发布 wheel 只打包：`src/agent_spice/**` 运行时代码、
    `lib/ngspice/*.cm|*.txt` 生成配置、`lib/native/<rid>/agent-spice-sim(.exe)`
    引擎可执行文件。`third_party/`、`native/AgentSpice.Engine/`、`tests/`、
    `tools/`、`scripts/`、`artifacts/`、`pdn_analysis/` 等**不进入 wheel**。
  - `.gitignore` 排除 `runs/`、`user_input/`、`native/**/bin|obj|target`、
    `src/agent_spice/lib/native/win-*`、`dist/`、`build/` 等构建与本地资产。
  - `LICENSE`（MIT，Copyright (c) 2026 z331225718）为本仓运行时代码的授权证据。
- **分类态定义**：
  - `authorized_public`：已获授权的公开许可（如 MIT/Apache，有明确授权证据）
  - `authorized_private`：已获授权的私有/内部资产（本仓自有 IP 或内部授权）
  - `external_reference_only`：仅作外部引用、不进入分发包的资产
  - `blocked_unknown`：授权状态未知或受限、需升级处理的资产

---

## 1. authorized_public — 已获授权的公开许可（外部依赖）

均为宽松许可（BSD / MIT / Apache）的公开开源包，运行时经 `pip` 解析安装，
**不 vendored 入库**。

| 资产 | 版本要求 | 许可 | 证据 |
|---|---|---|---|
| numpy | >=1.26 | BSD-3-Clause | `pyproject.toml` dependencies；PyPI |
| pyyaml | >=6.0 | MIT | 同上 |
| scipy | >=1.13 | BSD-3-Clause | 同上 |
| scikit-rf | >=1.6 | BSD-3-Clause | 同上 |
| cvxpy | >=1.6 | Apache-2.0 | 同上 |
| setuptools | >=69 | MIT | `pyproject.toml` build-system |
| wheel | — | MIT | `pyproject.toml` build-system |

> 注：上表为**声明依赖**。本地测试/开发环境额外安装的 pytest（MIT）、
> psutil（BSD-3-Clause）、h5py（BSD-3-Clause）等同样经 `pip` 解析、不入库。
> 完整的传递依赖 SBOM 未固化（见升级项 U-1）。

---

## 2. authorized_private — 已获授权的私有/内部资产（本仓自有 IP）

| 资产 | 许可/授权 | 证据 |
|---|---|---|
| `src/agent_spice/**`（运行时代码，含 `lib/native` 目录载体） | MIT，Copyright (c) 2026 z331225718 | `LICENSE` |
| `../../native/crates/sipi-circuit/**`（M5A-07 迁入后的 Rust 引擎源码、`Cargo.toml` 声明 `license = "MIT"`） | MIT | `LICENSE`；`../../native/crates/sipi-circuit/Cargo.toml` |
| `native/AgentSpice.Engine/**`（C# 参考实现 + `fixtures/` 65 个自著测试网表） | 本仓自有（未打包） | `LICENSE`；仓库内文件 |
| `tests/**`、`tools/**`、`scripts/**`、`docs/**`、`configs/**`、`skills/**`、`poc/**`、`benchmarks/**` | 本仓自有 | `LICENSE` |
| `src/agent_spice/lib/ngspice/{rfm.cm,compiler.txt,sha256.txt}` | 本仓自 ngspice-46 源码生成的配置产物（`sha256.txt` 记录输入/输出 hash），自著 | `src/agent_spice/lib/ngspice/sha256.txt` |
| `LICENSE` | 本仓 MIT 许可证文件，自有 | 文件本身 |

> 注：wheel 只打包 `src/agent_spice/**` + `lib/ngspice` 配置 + `lib/native/<rid>` 引擎；
> `third_party/`、`AgentSpice.Engine/`、`tests/` 等均不入 wheel。

---

## 3. external_reference_only — 仅外部引用，不进入发布物

| 资产 | 说明 | 证据 |
|---|---|---|
| `artifacts/**`（181 项：基准日志/golden/.cir/.rfm/.json 等） | 实验与基准产物，入库但不进 wheel | `setup.py` package-data 范围 |
| `pdn_analysis/**` | 本地 PDN 分析产物（7 项，已入库） | 同上 |
| `runs/`、`user_input/` | 本地运行/输入目录 | `.gitignore` |
| `native/**/bin`、`native/**/obj`、`native/**/target` | 构建中间产物 | `.gitignore` |
| `src/agent_spice/lib/native/win-*` | 本机构建的引擎二进制（发布由 CI 重建） | `.gitignore` |
| `original-vf-30p-z-curve-v2.{stderr,stdout}.log` | 本地运行日志（已入库，不进 wheel） | `setup.py` package-data 范围 |
| `dist/`、`build/` | 本地打包产物 | `.gitignore` |

---

## 4. blocked_unknown — 授权状态未知/受限，需升级处理

> 每项均指定 gap owner 与升级路径；完成后应移出本类。

### B-1. `third_party/solver-shims/**` 嵌入式 solver 运行时闭包
- **资产**：`third_party/solver-shims/python39-xdm/**`（嵌入式 Python 3.9 运行时：
  `python39.dll`、`base_library.zip`、`PYZ-00.pyz`、`*_sock`/`_ssl` 等 `.pyd`；
  `boost_python39-vc142-mt-gd-x64-1_77.dll`、`libcrypto-1_1.dll`、`libssl-1_1.dll`、
  `VCRUNTIME140.dll`、`SpiritCommon.pyd`/`SpiritExprCommon.pyd`/`XdmRapidXmlReader.pyd`；
  `xdm_bdl_bootstrap.py`）及 `win64/ucrtbased.dll`、`win64/xdm_bdl_launcher.exe`。
- **问题**：该闭包为 PyInstaller 打包的 XDM 2.6.0 运行环境（GPL-3.0-or-later），
  混入 Python（PSF）、Boost（BSL-1.0）、OpenSSL（Apache-2.0）等组件；各组件
  打包来源与整体再分发范围未逐一确认。`ucrtbased.dll` 为微软 Debug UCRT，
  **不具再分发许可**（`ucrtbased-shim/` 自著 C 源码为替代方案，但 win64 下
  仍保留 debug DLL）。`xdm-launcher/`、`ucrtbased-shim/` 的 C 源码为本仓自著，
  但编译产物与嵌入运行时闭包作为一个整体分类为 unknown。
- **Gap owner**：仓库所有者（z331225718）
- **升级路径**：逐一核对 PyInstaller 打包清单与各组件许可（PSF-2.0 /
  BSL-1.0 / Apache-2.0 / GPL-3.0）；以 `ucrtbased-shim` 替代 `ucrtbased.dll`
  并移除 debug 运行库；确认 XDM 闭包仅作本地工具（不进入任何发布物/CI 产物
  分发）或将再分发范围书面化。

### B-2. `third_party/solver-packages/**` 与 `solvers.lock.json` 外部求解器包
- **资产**：`third_party/solver-packages/agent-spice-solvers-win64.zip`（Git LFS，
  便携打包 ngspice 46 / XyceNF 7.10.0 / XDM 2.6.0 工具链）及
  `third_party/solvers.lock.json` 记录的下载包（ngspice-46_64.7z、
  xyce-windows.zip、xdm-2.6.0-win64.zip，均含 sha256 与 license_summary）。
- **问题**：许可混合（`solvers.lock.json` 已记录）：ngspice 46 核心为 Modified
  BSD，但捆绑子目录含 LGPL/GPL/MPL/MIT 组件；XyceNF 源码 GPL-3.0 且 Windows
  包携带 Sandia/NTESS 非自由与出口管制通知；XDM GPL-3.0-or-later。作为
  打包 zip 的**再分发**范围未获外部书面确认；本仓仅本地安装与 oracle 比对使用。
- **Gap owner**：仓库所有者（z331225718）
- **升级路径**：按 `solvers.lock.json` 的 `license_summary` 逐包核验再分发权；
  维持"安装脚本 `tools/install-solvers.ps1` 从官方下载/或使用本地 zip"的现状
  并书面确认 zip 不进入任何发布物（wheel/CI artifact）；或移除 Git LFS zip，
  仅保留官方下载锁定。

---

## 升级项（非 blocked，但建议跟进）

- **U-1**：固化 Python 传递依赖 SBOM（`uv.lock`/`pip freeze` 级），
  补全逐包许可，替代当前仅覆盖声明依赖的清单。
- **U-2**：确认 `native/AgentSpice.Engine/fixtures/**` 65 个网表均为自著
  （当前无外部来源证据，分类为 authorized_private，但建议留存来源记录）。

---

## 结论

- 进入发布物（wheel）的代码为本仓自有 MIT 代码（`src/agent_spice/**` +
  生成配置 + Rust 引擎）+ 宽松许可的公开依赖；**无** copyleft / 受限依赖
  vendored 入库。
- `third_party/` 求解器闭包与打包 zip **均不进入 wheel 与 CI 发布产物**，
  仅本地工具链使用；但其再分发状态未确认，列为 `blocked_unknown`（B-1、B-2）。
- 四态分类齐备；`blocked_unknown` 共 2 项，均已有 gap owner 与升级路径。
- 本清单为 cleanroom 事实分类与证据记录，**不构成 certified 声明**。
