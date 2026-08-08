# PDN FFT 卷积与 TRAN 对比方法

## 目的与结论

本文定义一套可复用的实验方法，用于比较：

1. 从 Touchstone/RFM 直接计算的频域卷积；
2. Agent-Spice 的 RFM transient；
3. 对同一 Agent-Spice 线性电路提取单位响应后得到的离散 FFT 卷积。

最重要的结论是：**`V(f)=Z(f)I(f)` 只有在连续时间 LTI 模型、频率范围、采样及初始状态全部一致时，才与 TRAN 等价。** 对一个实际 SPICE/RFM 仿真，直接使用 sampled S 参数通常不满足这些条件。

若目标是复现 Agent-Spice 对一个固定线性 PDN+CPM 电路的 TRAN 波形（包含启动包络），应使用本文的“原生单位响应 FFT”法。该方法不是对目标 TRAN 波形做曲线拟合，而是一次性测得该电路和该积分器的离散传递核；之后任意同采样网格的电流都可用 FFT 卷积计算。

它不能替代对物理模型正确性的验证：它复现的是 **Agent-Spice 已加载的 RFM 电路**，而不是独立证明 raw Touchstone 与该 RFM 完全相同。

## 范围与前提

可用范围：

- PDN S 参数已经由项目的 `sfit` 生成 Agent-Spice 可用于 transient 的 RFM；
- CPM、端接、VRM 和被观测电路全部为线性时不变元件，例如 R/L/C、线性受控源、固定阻抗端接、固定理想 VRM；
- 电流以等间隔 PWL knot 输入；
- 每次比较使用相同电路、RFM、步长、积分方法和观测点。

不适用或需分段重新建核：非线性 VRM、限流、开关电源、时变阻抗、饱和、二极管、数字控制环路，以及随电压/温度改变的 CPM。它们不存在一个对全幅值有效的单一 `H(f)`。

## 三个不同层次，不能混淆

### 1. 连续时间 raw-S 卷积

对端口 6 的加载阻抗，先由多端口 S 参数得到网络阻抗并施加端接，再并入 CPM 导纳：

```text
Zload(f) = Zpdn_loaded(f) || 1/Ycpm(f)
V(f) = -Zload(f) I(f)
v(t) = IFFT(V(f))
```

这回答的是“raw S 数据代表的连续 LTI 网络在指定频带内会怎样响应”。它对 DC、频带外延拓、负频率共轭、FFT 窗口及初始状态很敏感。

### 2. RFM transient

Agent-Spice transient 运行的是 RFM 的有理状态空间加上电路 MNA 和积分器，而非逐点直接读取 raw S 参数。RFM 有极点、残量和常数项；积分器又产生离散状态更新。因此其有效传递函数是模型、端接、CPM 和数值积分共同决定的。

### 3. 原生单位响应 FFT

对完整 SP 电路施加单位 PWL 基函数，得到 `h[n]`，并计算：

```text
H_native[k] = FFT(h[n])
V_native[n] = IFFT(FFT(i[n]) * H_native[k])
```

这里的 `H_native` 是 Agent-Spice 在当前步长下的离散传递核。它自然包含：RFM、有理拟合、端接、CPM、电路初始化和积分器特性。因此适合验证“为何 raw FFT 与 TRAN 不同”，以及加速同一线性电路下的大量电流扫角。

## 为什么简单 FFT 常常没有 TRAN 包络

### FFT 默认周期延拓

有限段 FFT 隐含 `i(t+T)=i(t)`。若 CPM 电流截取于已经运行的业务波形、首尾不相等，则频谱等价于在边界额外加了跳变。直接 FFT 得到的是周期稳态响应，不是从某一初始状态启动的自然响应。

补零只能避免循环卷积卷回观察窗口，并不能凭空恢复真实的历史状态。前置零的物理含义是“仿真在零电流静止状态启动”；若真实系统此前已运行，这一假设仍然错误。

### TRAN 有状态

电容、电感和 RFM 极点都有状态。对任意线性系统：

```text
x_dot = A x + B i(t)
v(t) = C x(t) + D i(t)

v(t) = v_forced(t) + C exp(A t) [x(0) - x_forced(0)]
```

直接 `Z(f)I(f)` 只覆盖与它选择的边界条件相容的强迫响应。启动包络通常就是第二项的自然响应。

对本项目的普通 TRAN deck，**不应凭空假设有一段未知前置电流历史**。如果 PWL 在 `t=0` 的首值为 `I0`，SPICE 的 `.op`/初始解就是将该源取为 `I0` 后得到的 DC 状态；这已经唯一确定了 `x(0)`。正确的频域等价写法是：

```text
i(t) = I0 + delta_i(t),   delta_i(0) = 0
V(t) = Vdc(I0) + IFFT[ Z(jw) FFT(delta_i(t)) ]
```

多输入时 `I0` 和 `Vdc` 是向量。`delta_i` 的左侧为零并不表示“真实系统之前零电流”，而是表示“从 SPICE 已建立的 DC operating point 开始的扰动为零”。只有当用户明确要复现一段从长期运行波形中截取、且其 TRAN 起点并未重新做 `.op` 的数据时，才需要额外 prehistory 或周期状态。

还必须在 `delta_i` 的**前后**补足覆盖 PDN 脉冲响应尾部的零区。这里的补零不是构造前置电流历史，而是让 FFT 的周期长度大于线性卷积长度，避免很晚才衰减的 ringing 从数组尾部回卷到 `t=0`。尾部长度应由 impulse response 或 tail-sweep 收敛确定。

### S 参数 transient 并非 raw S 的逐点 IFFT

S 参数只在有限频点和有限带宽给出。Transient 必须使用因果、稳定的时间域表示；项目 RFM 会给出这样的有理模型。不同工具还可能执行拟合、因果化、无源化和 DC/高频延拓。因此应分别比较：

- raw S -> 端口加载后的 `Z_raw(f)`；
- 项目 sfit RFM -> `Z_rfm(f)`；
- native unit response -> `FFT(h_native)`。

三者不一致时，先定位是模型差异还是初始状态差异，不能用目标 TRAN 波形去反向调一个包络参数。

## 原生单位响应 FFT 的原理

把等间隔 PWL 电流 knot 记为 `i[0], i[1], ...`。线性求解器对这些 knot 是线性的，但 transient 最开始的若干步使用启动积分格式（例如首步 backward-Euler，随后 Trap/Gear）。因此最初几步并不严格是时间平移不变的。

当前脚本保守地取得 `t=0, dt, 2dt, 3dt` 的四个单位基响应：`h0, h1, h2, h3`。它们不是四个物理脉冲，也不是四个需要拟合的参数；它们是 PWL 电流前四个采样点的四个“基向量”。例如 `h2` 是把电流序列设为 `[0, 0, 1, 0, 0, ...]` 时得到的电压序列。线性系统对任意电流的响应就是这些基响应的线性叠加。

之所以不只跑一个单位响应，是 transient 的离散积分在启动时并不完全平移不变：`t=0` 先做 DC 初始化，首个时间步通常用 backward-Euler，Gear2 还需要额外历史。因此先把启动的前三个 knot 单独处理；从 `3dt` 起，将 `h3[3:]` 当作平移不变核：

```text
v[n] = i[0] h0[n] + i[1] h1[n] + i[2] h2[n]
     + sum(k=3..n) i[k] h3[n-k+3]
```

最后一项通过零填充 FFT 实现线性卷积，而不是循环卷积。四次单位响应和被比较的目标电流使用完全相同的 SP 模板、RFM、步长、端接和 probe。

“四个”不是物理常数。对当前 Agent-Spice、等步长、连续 PWL、无后续事件重启的线性 deck，四个是覆盖 DC + 启动积分历史的保守值；其他 CPM 不会因为 RC 支路更多而需要更多单位响应。移植到其他求解器时，应增加单位响应数量，直到后续基响应互为时间平移且误差满足目标；Gear 阶数更高或存在事件重启时，启动区应相应加长。若波形含重复边界跳变、PULSE、开关或改变步长，则每个重启点附近均可能破坏单一核，需要分段建核或直接保留 TRAN。

## 已验证的 DDR_VDD0P8 基线

电路配置：

- `5power_30port_wocap_121124_221036_4876_DCfitted.s30p` 的项目 sfit RFM；
- port 1 为 0 ohm 理想 VRM；
- port 6 接 DDR_VDD0P8 CPM；
- 其余 28 port 各接 0.1 ohm；
- 观测 `v(p6)`；
- 10 ps 等间隔电流、30 ns 窗口。

旧 RFM 文件曾有 complex residue 虚部符号约定问题；经 `scripts/repair_legacy_rfm.py` 修复后，RFM 对 fitted S30P 的误差约为 RMS `1.17e-8`，最大 `1.44e-7`。这一步必须在所有 FFT/TRAN 对比前完成，否则 transient 本身可能不稳定。

原生单位响应法的结果：

```text
RMSE              3.58 uV
最大绝对误差      21.1 uV
FFT peak droop    138.942 mV
TRAN peak droop   138.940 mV
```

产物：

- `runs/generic_impulse_fft_ddr_30ns_v3/tran_vs_impulse_fft.png`
- `runs/generic_impulse_fft_ddr_30ns_v3/comparison.csv`
- `runs/generic_impulse_fft_ddr_30ns_v3/discrete_kernel.csv`

## 时间收益

在上述 DDR 基线、30 ns / 10 ps（3001 点，FFT 长度 8192）、本机 Windows 原生求解器上的实测：一次完整 native TRAN 平均约 `146.6 ms`；一次已知离散核的 NumPy FFT 卷积约 `0.146 ms`。因此，对同一拓扑、RFM、步长和 probe 的后续电流，卷积核心约快 `1000x`。

这组 `1000x` 数字只适用于已经由 native 单位响应得到的 **离散核**，不能误用于直接 RFM 频域求解。后者需要在每个 FFT bin 求 S/RFM、加载网络并解复数矩阵。对当前 DDR S30P、30 ns / 10 ps、`I0+delta_I` 和 500 ns 双侧 padding 的实测，直接 RFM 频域脚本端到端耗时约 `32.1 s`，而同一 native TRAN 平均约 `118.8 ms`；当前 Python 原型约慢 `270x`。它验证了精度，不是性能实现。

单位响应核需要预付四次 TRAN，约 `586 ms`。若只分析一个电流，直接 TRAN 更快；若要比较 `M` 个电流：

```text
全部 TRAN:          M * 146.6 ms
预提核 + FFT:       4 * 146.6 ms + M * 0.146 ms
```

直接 RFM 频域卷积的初始条件/补零验证（同一 repaired RFM、同一 30-port 拓扑、10 ps、30 ns 窗口）：

| 频域输入处理 | 双侧补零 | RMSE | 最大误差 | 结论 |
| --- | ---: | ---: | ---: | --- |
| 直接卷积 `I(t)` | 20 ns | 145.0 mV | 221.5 mV | 错误地忽略 DC 初值且有回卷 |
| `I0 + delta_i(t)` | 20 ns | 56.34 mV | 80.18 mV | DC 修正有效，但尾部严重回卷 |
| `I0 + delta_i(t)` | 100 ns | 12.94 mV | 19.60 mV | 尾部仍不足 |
| `I0 + delta_i(t)` | 250 ns | 0.574 mV | 0.871 mV | 已接近 |
| `I0 + delta_i(t)` | 500 ns | 0.104 mV | 0.259 mV | 与 native TRAN 高度一致 |

同时用 Agent-Spice AC 在 1 MHz、500.5 MHz、1 GHz 对 loaded `Z_rfm(f)` 做了独立交叉检查；500.5 MHz 和 1 GHz 与 Python 的 RFM/端接/CPM 计算差小于 `4e-14 ohm`，说明上述收敛主要来自初始 DC 和 FFT 回卷处理，而非端口加载公式错误。500 ns 后的残差包括连续频域计算与 native 离散积分之间的差别。

进一步将真实 PWL 在前、后各写入 `500 ns` 零电流，并在同一输入上同时运行 TRAN 和频域法；频域另使用 `500 ns` 虚拟 tail 避免循环卷积。得到 RMSE `29.7 uV`、最大误差 `100.9 uV`，FFT/TRAN peak droop 分别为 `423.775/423.801 mV`。这验证了“手动前后补零”在本例中可以直接消除初始条件歧义；虚拟 FFT tail 仍不可省略。

约从第 `5` 个不同电流开始打平。100 个电流时，估算为 `14.66 s` 对 `0.60 s`，约 `24x`；1000 个电流时约 `146.6 s` 对 `0.73 s`，约 `200x`。这些数字不含 Python 启动、CSV I/O、画图和首次加载 RFM 的固定开销，应按实际 deck 重新 benchmark。任何拓扑、端接、CPM、RFM、积分步长、积分方法或 probe 改变，都必须重新提取单位核。

### MIMO 重要限制

若一份 S48P deck 在一次 TRAN 中同时驱动 24 个独立电流源，并同时输出 24 个 node，则它是一个 24 输入、24 输出的 MIMO 问题。原始 1.5 us TRAN 已经一次得到全部 node；把它错误地拆成“每个 node 跑 4 次单位响应”会变成 96 次 1.5 us TRAN，**没有加速，反而更慢**。

要用单位响应完全表征这个 MIMO 网络，需要每个独立输入一个传递矩阵列：

```text
V_out(f) = H_24x24(f) I_24(f)
```

每个输入列可在一次仿真中记录所有 24 个输出，因此至少需要约 24 组独立激励来识别一般的 24x24 核（启动 stencil 还会增加固定成本）。Hadamard/PRBS 编码可让每次仿真同时激励多个输入并在后处理中解码，但一般仍需要与独立输入数同数量级的独立编码；它不会把一般 24 输入系统压缩成 4 次 TRAN。

所以单位响应 FFT 的速度收益只在以下情况成立：同一 MIMO 网络会被用于远多于其输入数的不同 workload、Monte-Carlo 电流、时序/幅度 sweep，或各场景只改变一个已知空间电流模式的整体标量。对于一个固定空间模式 `i(t)=a*s(t)`，只需为该模式提一个核，后续不同 `s(t)` 才能以很低成本计算。

若要让“一个 24 曲线、1.5 us”的首次分析本身变快，正确方向不是 native 单位响应识别，而是直接从项目 sfit RFM 和 CPM 组装完整 MIMO 离散状态空间，计算矩阵 `H(f)` 或递推 `x[k+1]=A_d x[k]+B_d i[k]`。这样不需要用 96 个完整 TRAN 去测核；但必须独立验证其与 native TRAN 的初始状态、积分器和 RFM 约定一致。

另一条更适合固定端接的路线是先做网络消元：将不需要变化的 VRM、端接和 CPM 在频域吸收，把 S48P 降成实际独立输入/输出数的 S 参数，再用项目 sfit 对 reduced S 参数拟合。若 VRM 固定为理想短路且只观察一个 die port，最终应为 S1P，而不是 S2P；若要保留可变 VRM/die 两端，则保留 S2P。这样后续波形计算不再在每个 FFT bin 解原始 48x48 网络。DDR S30P 试验中，预处理后 scalar RFM 的 203001 点 FFT 计算约 85 ms，相比 1.965 s native TRAN 约 23x；其精度由 reduced-model sfit 误差决定。

## 工具使用

通用脚本：[scripts/spice_impulse_fft.py](../scripts/spice_impulse_fft.py)。它不使用 scikit-rf vector fitting；`--rfm` 必须是项目 `sfit` 的输出。

SP 模板必须含有这三个占位符：

```text
{{CURRENT_FILE}}  两列、无表头的 PWL 文件绝对路径
{{STEP_S}}        秒
{{STOP_S}}        秒
```

DDR 示例模板：[scripts/templates/ddr_vdd0p8_port6.sp.template](../scripts/templates/ddr_vdd0p8_port6.sp.template)。`{{WORKSPACE_ROOT}}` 是脚本额外支持的便利占位符。

```powershell
python scripts\spice_impulse_fft.py `
  --template scripts\templates\ddr_vdd0p8_port6.sp.template `
  --current <time_current.csv> `
  --rfm <project_sfit_output.rfm> `
  --probe-column p6 `
  --jobs 4 `
  --output runs\case_name
```

输出中的 `tran_target.sp` 是已展开占位符、可直接用于对比的 SP 电路文件；`voltage_fft.csv` 为 FFT 结果，`voltage_tran.csv` 为验证 TRAN，`comparison.csv` 和 `metrics.json` 为判定依据。

四个 cardinal response 彼此独立，脚本可用 `--jobs 4` 并行运行；并行降低墙钟时间，不降低总 CPU 时间。它适合 SISO 或固定空间电流模式的核提取。对 S48P 的一般多输入 case，必须先按上文 MIMO 限制评估所需核列数，不能把并行的 96 个任务误认为算法加速。

## 面向后续复杂实验的标准流程

1. 固定拓扑、端接、VRM、CPM、RFM、积分方法、步长和观测点；记录版本与文件 hash。
2. 先检查 RFM 对其 fitted Touchstone 的频域误差、稳定性和无源性；禁止以目标 TRAN 波形调 fit。
3. 用 raw S 得到 `Z_raw(f)`，用 RFM 得到 `Z_rfm(f)`，画幅值、相位和脉冲响应。先回答模型是否相同。
4. 对同一 SP 电路运行原生单位响应 FFT，并与 TRAN 比较。若该层不一致，先查步长、事件、非线性、PWL 网格和 probe，而不是修改频域结果。
5. 再运行 raw-S FFT，系统改变前置补零、后置补零、周期扩展、窗口和 prehistory。将每个选择视为一种明确物理假设。
6. 报告至少包含：电流、频谱、`Z_raw/Z_rfm/H_native`、单位脉冲响应、TRAN/FFT overlay、误差、RMSE、peak droop、peak timing、ring frequency 和 settling time。

## 初始条件实验规则

比较与标准 `.tran` deck 一致的启动状态时，推荐把电流拆为：

```text
i(t) = I_bias + delta_i(t)
```

先用 `I_bias=I(0)` 求 DC operating point，再对 `delta_i` 建响应并卷积；这就是标准 SPICE 在 `t=0` 的物理假设，不需要人为添加前置电流。若用户明确要比较未重新做 `.op` 的长期运行截取波形，才先用足够 prehistory 运行至周期状态，再从周期边界截取；raw FFT 的周期解也应在同一周期边界比较。

当前脚本默认复现的是 SPICE 在 `t=0` 对首个 PWL 电流值做的 DC 初始化。它与该 deck 的 TRAN 可精确对比；只有目标数据被定义为“未重新初始化的长期运行截取”时，才不自动恢复那段历史状态。

## 给后续 Agent 的任务约束

- 不得用待比较的 `Vtran(t)` 拟合指数、正弦、包络或任何补偿项后再宣称 FFT 对上。
- 必须区分“复现某求解器离散输出”与“验证 raw S 的物理响应”。原生单位响应 FFT 只解决前者。
- 新 CPM 必须以 SP 模板描述完整线性拓扑；不要在 Python 中硬编码其 RC 支路。
- 任何 RFM 修复、sfit 参数或带宽外推都必须独立于目标 transient 波形完成，并保留频域误差图。
- 若存在非线性或时变元件，应明确报告单一 FFT 卷积不成立；可考虑工作点线性化、小信号核、分段线性核或保留 TRAN。

## 交付验收标准

一个新案例只有同时满足下列条件，才能声称“FFT 复现 TRAN”：

1. 输入、拓扑、初始状态、步长和积分方法明确且一致；
2. 原生单位响应 FFT 对 native TRAN 的 RMSE、峰值和时刻均在项目阈值内；
3. raw-S FFT 与 RFM FFT 的差异已量化并解释；
4. prehistory/周期状态假设已声明；
5. 所有脚本、SP deck、RFM、CSV 和图片均可复跑。
