# HSPICE/Sigrity RFM 直接接入 ngspice 瞬态仿真技术报告

日期：2026-07-14  
分支：`codex/rfm-ngspice-exploration`

## 1. 结论先行

推荐路线已经收敛为 **B：XSPICE 动态 N-port rational code model**。

- **[实验验证]** 已构建 `nport_rfm` 自定义器件和 Windows `rfm.cm`，由项目默认的离线 ngspice-46 在不修改核心源码的条件下加载并完成 AC、TRAN。
- **[实验验证]** 器件在 `INIT` 阶段直接读取项目生成的 `.rfm` pole/residue，不执行 vector fitting，也不先转换成 `.sp`。
- **[实验验证]** 2/8/16-port 固定步长规模实验中，直接器件相对同源 `.sp` 宏模型的分析时间中位数分别加速 `1.50x`、`2.22x`、`2.13x`。
- **[实验验证]** 16-port、effective order 6 时，全局 MNA 未知量由宏模型的 146 降至直接器件的 18；96 个有理状态保留在器件内部。
- **[推断]** B 已证明接口、部署和性能方向成立，下一阶段应产品化 B，而不是把 RFM 再转成已有 `.sp`。
- **[推断]** C 暂不推荐。当前没有必须修改 ngspice 核心的硬阻塞；只有 B 无法补齐内部 LTE/步长控制或代表性密集多端口基准不达标时，才应重新评估原生 device。

路线 A 在 Agent-Spice 当前工作流中没有新增的用户价值：`fit-sparam` 已经同时生成 `.sp`。本报告保留 A 只作为同源数值 oracle 和性能基线，不把它作为交付路线。

必须明确：**`.rfm` 不是 ngspice 原生可读格式**。本 PoC 是自定义 XSPICE `.cm` 读取 RFM；不能把 HSPICE `S` element、`FQMODEL` 或 `RFMFILE` 直接交给 ngspice。

## 2. 证据等级

- **[文档证据]**：ngspice 官方手册、官网或官方源码明确支持。
- **[实验验证]**：已在本仓库和 Windows 离线 ngspice-46 上运行，并保留输入、命令、日志和结果。
- **[推断]**：基于接口、方程或实验外推的工程判断，尚未被完整产品场景验证。

## 3. 已完成实现

### 3.1 RFM 读取与频响重构

- `src/agent_spice/sparam/rfm.py` 读取项目兼容的 `VERSION 200600`、`MATRIX_TYPE S`、共享 `Z0`、实 pole、复共轭 pole 和 residue。
- Python importer 支持 response-specific pole set，并提升到 pole union；缺失 residue 补零。
- `RfmModel.evaluate_s()` 直接计算 `S(j2*pi*f)`，不拟合。
- `RfmModel.write_spice_subcircuit()` 仅用于 oracle/基准，不是推荐执行路径。

**[实验验证]** 对稳定、被动 2-port 样例：

| 项目 | 结果 |
| --- | ---: |
| fit effective order | 6 |
| fit mean S-RMS | `9.66637e-9` |
| 最大奇异值 | `0.80999980025215` |
| RFM 对 fitted Touchstone RMS | `1.22626e-14` |
| RFM 对 fitted Touchstone最大绝对误差 | `2.10960e-14` |

原始输入、fit 命令、HTML/JSON/log 和全部产物位于 `artifacts/rfm-ngspice-poc/input` 与 `source-fit`。

### 3.2 动态 N-port XSPICE 器件

`poc/xspice-rfm` 包含：

- `ifspec.ifs`：一个无固定上限的 vector `inout gd` port，实际 N 由 `PORT_SIZE(port)` 决定；模型参数 `rfm_file` 为 string。
- `cfunc.mod`：直接 RFM parser、DC、AC、TRAN、旋转状态、端口电流和完整 N×N Jacobian。
- `Dockerfile` 和 `build-windows.ps1`：从 ngspice-46 官方源码交叉构建 Windows `.cm`。
- `modpath.lst`/`udnpath.lst`：构建独立 `rfm.cm`，不把模型编进 `analog.cm`，也不改 ngspice 核心。

当前 C parser 的 PoC 边界：

- 支持项目自身生成的共享 pole set RFM；
- 只支持 `MATRIX_TYPE S`、共享标量 `Z0`；
- 暂不支持 response-specific pole set、proportional term 和第三方扩展 header；
- 这些限制会显式报错，不会静默重拟合。

### 3.3 状态更新算法

RFM 表示为：

```text
S(s) = D + C (sI - A)^-1 B
```

PoC 没有先形成稠密的 Y-domain `A_y`，也没有在每步求解 `N*order` 维稠密状态矩阵。它保留散射波状态：

```text
xdot = A x + B a
b    = C x + D a
v/sqrt(Z0) = a + b
i*sqrt(Z0) = a - b
```

梯形规则下，先利用 pole block 对角结构得到：

```text
x_n = x_base + W(h) a_n
K(h) = I + D + C W(h)
K(h) a_n = v_n/sqrt(Z0) - C x_base
i_n = 2 a_n/sqrt(Z0) - v_n/Z0
J_n = d(i_n)/d(v_n) = (2 K(h)^-1 - I) / Z0
```

**[实验验证]** ngspice 每次调用时，器件向 `OUTPUT(port[i])` 写端口电流，向 `PARTIAL(port[i], port[j])` 写完整 Jacobian。内部 `x` 与上一接受时间点的 `a` 使用 `cm_analog_alloc/get_ptr` 旋转存储；时间步拒绝时从 `timepoint=1` 重新计算。

复杂度：

- pole block 更新约为 `O(N*order)`；
- 形成端口 Schur 矩阵约为 `O(N^2*order)`；
- 当前 dense pivoted LU 为 `O(N^3)`；
- 全局 MNA 不包含 rational states。

**[推断]** 对非常大且稀疏耦合的 N-port，dense N×N LU 可能成为瓶颈；后续可按耦合结构分块、复用相同步长的分解，或使用低秩/稀疏策略。不能从当前 16-port 结果外推到任意 N。

## 4. 官方接口证据与实际验证

| 需求 | 结论 | 证据等级 | 依据 |
| --- | --- | --- | --- |
| 动态 N-port | 已支持并实测到 16-port | 文档证据 + 实验验证 | vector port、`Vector_Bounds: [1 -]`、`PORT_SIZE`；2/8/16-port TRAN 成功 |
| 直接 pole/residue | 已支持 | 实验验证 | `rfm_file` 在 `INIT` 直接解析；无 VF 调用 |
| 每步状态更新与回滚 | 已支持基本路径 | 文档证据 + 实验验证 | `cm_analog_alloc/get_ptr` current/previous；真实 TRAN 成功 |
| MNA 电流和 Jacobian | 已支持 | 文档证据 + 实验验证 | vector `OUTPUT`/`PARTIAL`；完整 N×N stamp 实际收敛 |
| 公共地 | 已支持 | 实验验证 | `%gd[p1 0 p2 0 ...]` AC/TRAN 成功 |
| 差分端口 | 接口支持，未完成产品验证 | 文档证据 + 推断 | `gd` 本身是 differential conductance port；需 wrapper 提供正负 pin |
| 多参考拓扑 | 需要显式映射 | 推断 | RFM 不携带任意 reference topology；需 incidence matrix 或 wrapper |
| Windows 离线 DLL | 已支持 | 文档证据 + 实验验证 | 独立 `rfm.cm` 被官方 ngspice-46 加载并运行 |

官方手册给出的关键事实：

- **[文档证据]** vector port 支持动态宽度；vector output 对 vector input 可双循环写 `PARTIAL`。
- **[文档证据]** 模拟 code model 的 partial derivative 用于模拟节点方程；`inout gd` 的 input 是电压、output 是电流、partial 是电导。
- **[文档证据]** 模拟状态只在接受时间点后旋转，`T(1)` 指向最后接受时间点。
- **[文档证据]** code-model library 可用 `codemodel` 在运行时加载，不要求重编 ngspice 核心。
- **[文档证据]** string model parameter 可由 `PARAM()` 读取，官方 `file_source` 等模型已有先例。

## 5. 数值对比

### 5.1 AC 与 TRAN

同一 2-port RFM 同时驱动直接 XSPICE 器件和同源 `.sp` 宏模型：

| 项目 | 结果 | 证据等级 |
| --- | ---: | --- |
| AC 点数 | 87 | 实验验证 |
| AC 输出最大复数差 | `0 V`（ngspice print 精度内） | 实验验证 |
| TRAN 点数 | 2138 | 实验验证 |
| TRAN 输入最大差 | `2.22e-17 V` | 实验验证 |
| TRAN 输出 RMS 差 | `1.32e-6 V` | 实验验证 |
| TRAN 输出最大差 | `1.34e-5 V` | 实验验证 |

TRAN 最大差出现在 PULSE 下降沿附近，相对约 `0.4 V` 峰值为 `3.35e-5`。这说明直接状态更新已正确到工程可比量级，但还不能把 PoC 宣称为生产级数值等价。

**[推断]** 下一阶段必须增加 timestep sweep、Gear/Trap 对比、step rejection、高 Q pole、强反射、长时间稳定性和误差阈值。当前 code model 没有像显式 C 状态节点那样自动进入 ngspice 全局 LTE/truncation 估计，这是 B 最重要的剩余数值问题。

### 5.2 规模与性能

规模模型由同一个稳定、被动 2-port RFM 做 block-diagonal 重复，不增加拟合，也不改变每个 block 的 pole/residue。每种模式独立运行 5 次，表中为分析时间中位数；`.tran 10p 20n` 固定最大步长，单线程。

| N | order | 内部状态 | MNA 未知量 B/A | B 时间 | A 时间 | 加速 | B/A 最大进程内存 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 6 | 12 | 4 / 20 | 5.87 ms | 8.78 ms | `1.50x` | 10.262 / 10.301 MB |
| 8 | 6 | 48 | 10 / 74 | 15.70 ms | 34.80 ms | `2.22x` | 10.332 / 10.906 MB |
| 16 | 6 | 96 | 18 / 146 | 52.58 ms | 112.18 ms | `2.13x` | 10.414 / 12.195 MB |

**[实验验证]** 结果保存在 `artifacts/rfm-ngspice-poc/xspice-scaling/report.json`，每次运行日志、生成的 RFM、宏模型、网表和命令均在同目录。

**[推断]** 该实验支持“把 rational states 移出 MNA 能带来实际收益”，但 block-diagonal 模型不是密集串扰模型。密集 N-port、不同 order、不同端接和真实 PCB/封装 RFM 仍需基准。A 的稀疏矩阵和 B 的 dense 端口 LU 存在模型相关交叉点，不能承诺固定倍数。

## 6. Windows 构建与部署

### 6.1 已验证构建

- ngspice-46 官方源码 SHA-256：`a0d1699af1940b06649276dcd6ff5a566c8c0cad01b2f7b5e99dedbb4d64c19b`。
- 编译器：`x86_64-w64-mingw32-gcc 12-win32`。
- 产品化加固后的 `rfm.cm` SHA-256：`166dbcd5dbdf7859d69608f8aacb21a13004ac3288de786d4495640060254d2c`。
- 输出 DLL 只导入 `KERNEL32.dll` 与 `msvcrt.dll`，导出标准 `CMdevs/CMdevNum/CMudns/CMudnNum/CMgetCoreItfPtr`。

**[实验验证]** 构建工具只存在于 Docker 发布流程；运行端仍只需要默认离线 ngspice 和随 Agent-Spice 发布的 `rfm.cm`，不要求用户安装 Xyce/XDM、C compiler 或 `cmpp`。

### 6.2 ABI 关键发现

**[实验验证]** 用同一 ngspice-46 源码但关闭 `CIDER` 构建 `.cm` 时，官方 Windows ngspice 在 initial transient solution 后发生 `0xC0000005`；保留 cdb 日志。改为与官方 Windows 构建一致的 `--with-wingui --enable-xspice --enable-cider` 后，同一模型正常完成 TRAN。

这不是模型方程错误，而是 code-model `SPICEdev` 描述结构受编译配置影响造成的 ABI 不一致。发布流程必须同时锁定：

- ngspice release/source hash；
- XSPICE/CIDER 等影响头文件结构的 configure flags；
- 目标架构、编译器与 runtime；
- `.cm` SHA-256；
- 对目标 ngspice 二进制的加载、DC、AC、TRAN smoke test。

### 6.3 加载路径

**[实验验证]** 官方包的默认 `spinit` 使用 `../lib/ngspice/*.cm` 相对路径，从普通 run cwd 启动会加载失败。PoC 用 `SPICE_SCRIPTS` 指向 run-local scripts，并在 `spinit` 中使用 `rfm.cm` 绝对路径，运行成功。

产品实现不应修改用户全局配置。推荐由 backend 为每次 run 生成隔离的 `spinit`，其中写入已校验 DLL 的绝对路径；backend 继续使用现有 Windows 离线 ngspice。

## 7. A/B/C 比较

| 路线 | 性能 | 数值稳定性 | 维护成本 | 是否改核心 | 结论 | 证据等级 |
| --- | --- | --- | --- | --- | --- | --- |
| A：RFM -> `.sp` | 重复现有 fit 输出；状态进入 MNA，规模随 N/order 增长 | 继承现有宏模型和 ngspice LTE | 低 | 否 | 仅 oracle/回退，不是目标路线 | 实验验证 |
| B：XSPICE direct RFM | 2/8/16-port 已有 `1.50x` 至 `2.22x`；显著减小 MNA | AC 已等价；TRAN 尚需 LTE/极端场景验证 | 中 | 否 | **推荐继续产品化** | 实验验证 |
| C：原生 ngspice device | 理论优化上限最高，可接入原生 truncation | 可与 solver 生命周期深度集成 | 很高，需长期维护 fork/Windows 发布 | 是 | 当前不推荐 | 推断 |

## 8. 产品化状态与下一阶段最小计划

**[实现事实，2026-07-14]** B1 已交付稳定 `run-rfm` 入口：Python importer 将 response-specific pole set 无损规范化为共享 union（缺项 residue 补零），运行前以 65 点频响重构门验证；backend 自动生成 run-local `spinit`、暂存 DLL、递归暂存相对 include/lib，并保留原始输入、规范化 RFM、hash、日志和报告。整个路径不调用 vector fitting。

**[实现事实]** C device 增加 finite/规模检查、相对 pivot 病态判定和显式 `nport_rfm ERROR:`；CLI 即使遇到 ngspice 返回码为 0，也会把 device 错误提升为失败。随包 DLL 仍不修改 ngspice 核心。

下一阶段最小计划：

1. **B2 数值门**：增加 Trap/Gear、timestep sweep、rejected step、高 Q、强反射、DC 初值和长时稳定性矩阵，形成正式签核阈值。
2. **B2 真实大 N**：用真实 4/8/16/32-port PCB、封装和连接器 RFM 测 setup、accepted/rejected steps、analysis/wall time、峰值内存和 MNA unknowns。
3. **B2 步长控制**：评估 XSPICE breakpoint/LTE 接口；若无法可靠约束当前步，再把它列为评估 C 的明确接口阻塞。
4. **B2 优化**：缓存相同步长的 pole companion 与 N x N LU；评估对称性、block structure 和稀疏耦合。
5. **B3 差分/多参考**：增加显式 incidence mapping，不能从 RFM 猜测参考拓扑。

进入 C 的条件必须是可复现的硬证据，例如：XSPICE 无法实现可靠 LTE/step rejection、动态 vector cross-Jacobian 存在核心缺陷，或真实大 N 基准被 code-model 调用/端口 LU 开销系统性压制。当前没有这些证据。

## 9. 测试与复现

- **[实验验证]** 新增聚焦测试：`10 passed`，覆盖 RFM parser、无重拟合重构、pole union、Schur 公式、block-diagonal 扩展和动态 vector deck。
- **[实验验证]** Windows `rfm.cm` 构建成功；direct AC、direct TRAN、direct-vs-macro AC/TRAN 均 return code 0。
- **[实验验证]** 规模基准 2/8/16-port，各模式 5 次，全部成功。
- **[实验验证]** `compileall` 与 `git diff --check` 通过。
- **[实验验证]** 产品化增量后的全量测试为 `825 passed, 5 skipped, 4 xfailed, 3 failed`；三个失败均为本分支开始前已存在的 CLI 能力缺口，详见 `artifacts/rfm-ngspice-poc/product-run/full-test-results.txt`。

产品化增量回归（2026-07-14）：

- **[实验验证]** `run-rfm` 使用随包 DLL 在官方 Windows ngspice-46 完成真实 TRAN，return code `0`，输出 `1029` 行 waveform；runtime RFM 65 点无损规范化最大误差 `0`。
- **[实验验证]** 最新 direct-vs-macro TRAN 共 `1033` 点，输出 RMS 差 `1.42739e-6 V`，最大差 `5.1e-6 V`。
- **[实验验证]** 最新 2/8/16-port 五次中位数加速为 `1.52x`、`2.23x`、`2.11x`；16-port MNA unknowns 为 direct `18`、macro `146`。
- **[实现事实]** Python 运行入口、run-local DLL 加载、错误提升、相对依赖暂存和无损规范化均有聚焦单元测试；完整使用说明见 `docs/rfm-ngspice-usage.md`。
- **[实验验证]** 构建 wheel 后在全新 venv 安装，使用 wheel 提供的 `agent-spice.exe run-rfm` 和包内 DLL 再次完成 ngspice-46 TRAN，排除了仅源码树可运行的问题。

核心复现命令：

```powershell
poc/xspice-rfm/build-windows.ps1 `
  -NgspiceArchive "$env:TEMP/ngspice-46-source.tar.gz" `
  -OutputDirectory artifacts/rfm-ngspice-poc/xspice-direct/build

python scripts/rfm_xspice_scaling_poc.py `
  --source artifacts/rfm-ngspice-poc/source-fit/source_model.rfm `
  --output artifacts/rfm-ngspice-poc/xspice-scaling `
  --ngspice C:/Users/z3312/tools/agent-spice-solvers/ngspice-46/Spice64/bin/ngspice_con.exe `
  --spice-scripts artifacts/rfm-ngspice-poc/xspice-direct/scripts `
  --ports 2 8 16 --repetitions 5
```

## 10. 官方资料

- [ngspice-46 User Manual](https://ngspice.sourceforge.io/docs/ngspice-46-manual.pdf)，XSPICE code model element、vector port、CMPP、state、partial 与 runtime library 章节。
- [ngspice 官方 XSPICE 页面](https://ngspice.sourceforge.io/xspice.html)。
- [ngspice 官方 XSPICE HOWTO](https://ngspice.sourceforge.io/xspicehowto.html)。
- [ngspice 官方下载页](https://ngspice.sourceforge.io/download.html)。
- [官方 `s_xfer` code model](https://github.com/ngspice/ngspice/blob/master/src/xspice/icm/analog/s_xfer/cfunc.mod)。
- [官方 `s_xfer` IFS](https://github.com/ngspice/ngspice/blob/master/src/xspice/icm/analog/s_xfer/ifspec.ifs)。
- [官方 `file_source` code model](https://github.com/ngspice/ngspice/blob/master/src/xspice/icm/analog/file_source/cfunc.mod)。
- [官方 inout `gd` memristor 示例](https://github.com/ngspice/ngspice/blob/master/src/xspice/icm/xtradev/memristor/cfunc.mod)。
