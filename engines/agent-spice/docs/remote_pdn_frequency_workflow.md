# 远端 PI 网表：降阶 S 参数 + 直接 FFT 对比流程

## 目标

对固定拓扑、线性 PI 网表，将大规模 package/board S 参数和固定的 VRM、端接、RDIE/CDIE/CPM 在频域先消元为低端口数 S 参数；用**项目 sfit**拟合 reduced S 参数；再直接计算：

```text
I(f) = FFT(i(t))
V(f) = H_reduced(f) I(f)
v(t) = IFFT(V(f))
```

本流程不使用 scikit-rf vector fitting、不从目标 TRAN 识别 impulse response、不做状态空间递推。目标是让 remote agent 对同一 PWL 的 full TRAN 与直接频域乘法独立对比，并量化精度和时间。

## 已验证基线

本地 DDR case 已验证：

```text
full S30P
+ port1 = 0-ohm ideal VRM
+ 其余 28 port = 0.1 ohm
+ port6 = DDR CPM (固定线性 RC)
=> reduced S1P
=> project fit-sparam RFM
=> direct Z(f) * I(f)
```

当同一 PWL 前、后各放置 500 ns 真实零电流，且 FFT 额外保留 500 ns 虚拟尾部时：

```text
完整 RFM 直接频域：RMSE 29.7 uV，最大误差 100.9 uV
reduced S1P RFM：RMSE 0.367 mV，最大误差 1.828 mV
```

后者的误差来自 reduced S1P 的 sfit 误差，不是 FFT 本身。初始 Python 标量 RFM 的在线频域计算约 85 ms；现已将 `H(f)` 构建下沉到 native Rust，实测 native H 构建约 23 ms、NumPy FFT 约 27 ms；同一 full S30P native TRAN 约 1.965 s。

参考产物：

- [完整 RFM 直接 FFT 图](../runs/ddr_physical_zero_pad_500ns_fft_tail500ns_overlay/tran_vs_fft.png)
- [reduced S1P FFT 图](../runs/ddr_reduced_s1p_fft_compare/tran_vs_fft.png)
- [DDR 降阶脚本](../scripts/reduce_ddr_port6_to_s1p.py)

## 适用边界

可以使用：R/L/C、固定阻抗端接、固定线性 VRM、小信号线性 CPM、稳定的项目 RFM、固定拓扑。

不能直接替代 TRAN：开关 VRM、限流、控制环路、非线性电容/电感、时变端接、依赖电压/温度变化的 die 模型。此类网表保留 TRAN，或只在一个明确工作点附近做小信号线性化。

## 端口降阶决策

| 要变化的对象 | reduced 模型 |
| --- | --- |
| 一个 die rail 电流；VRM 与所有 CPM/端接固定 | S1P |
| 一个 die rail；VRM 阻抗需要扫角 | S2P，保留 VRM 与 die port |
| M 个 die rail 电流独立变化 | S(M)P，保留全部独立 rail port |
| 某些 rail/端接固定 | 在降阶时消元，不保留为 S 参数端口 |

**不要为了“方便”保留不需要变化的 port。** 降阶的收益来自先消去这些 port。反过来，也不要消去会在不同 corner 或 workload 改变的元件。

## RDIE、CDIE 与 CPM

先确定电流源和观测电压的物理位置。

- 若 RDIE/CDIE/CPM 参数固定，且电流源/观测点都在同一个 die rail 节点：在降阶时将其并入网络，输出的 S1P/S2P 已经包含 die RC；后续 FFT **不得再次外接同一 CPM**。
- 若 RDIE/CDIE 会扫角：不要固化到 reduced S 参数。保留对应 die port，或每个配置分别生成 reduced 模型。
- 若电流源位于 RDIE 之后、观测点也在 die 内部：RDIE/CDIE 必须留在“输入到观测点”的传函内，不能只用 bump port 的阻抗替代。
- 多 rail CPM 的相互耦合应保留为 M-port reduced 模型；不要错误地按每个 rail 独立 S1P 处理。

remote agent 必须在报告中明确写出：哪些元件被吸收到 reduced S 参数，哪些仍放在 FFT 外部。该清单是防止双重计算和遗漏的硬性检查项。

## 操作步骤

### 1. 冻结 reference TRAN

建立 full reference deck，记录：

- 原始 `.sNp`、项目 RFM、CPM、VRM、端接文件及 SHA256；
- port mapping、电流方向、观测节点；
- `.tran` 步长、停止时间、积分方法；
- 所有固定与会扫描的元件。

先在 full deck 运行 native TRAN，输出所有目标电压波形。此结果只用作最终独立比较，**不得**用于调 reduced fit 或调 FFT 波形。

### 2. 构造物理一致的电流

优先验证零状态版本：把同一 active current 的前、后加入真实零电流 PWL，并将这条完整 PWL 同时喂给 full TRAN 与 FFT。

```text
[0 current preamble] + [active current] + [0 current postamble]
```

Preamble 使 full TRAN 从零 DC state 启动。Postamble 长度由 response tail 决定。不要只在 FFT 中加前置零而 TRAN 仍从非零 PWL 首点启动。

FFT 还需额外的虚拟前后 tail，避免 DFT 环形卷积。不断加倍 tail，直到有效观察窗口的 RMSE/peak/timing 基本不变；该 tail 不必写入 reference TRAN。

若业务电流不能补零，则改用 SPICE 的 DC 工作点：`i(t)=I0+delta_i(t)`，求 `Vdc(I0)` 并对 `delta_i` 卷积。不要臆造未知前史。

### 3. 频域端接和降阶

在一组足够密的频率采样点上，使用 full RFM 或 full S 参数构造网络导纳/阻抗，然后施加固定元件并消元。

对保留 port 集合 `a` 与固定端接 port 集合 `b`，阻抗形式可写为：

```text
Zred = Zaa - Zab (Zbb + Zterm)^(-1) Zba
```

对固定 VRM 为理想短路，VRM port 属于 `b`，其 `Zterm=0`。复杂 CPM 建议在导纳/MNA 形式并入后求 `H(f)`，避免手写错误的串并联化简。

将得到的 `Zred(f)` 转为共享实数参考阻抗 `Z0` 下的 reduced S 参数：

```text
Sred = (Zred - Z0 I) (Zred + Z0 I)^(-1)
```

S1P 情况退化为标量：

```text
S = (Z - Z0) / (Z + Z0)
```

导出 `.s1p/.s2p/.sMp`，同时保存 `Zred(f)` CSV。对 S1P，现成示例脚本是：

```powershell
python scripts\reduce_ddr_port6_to_s1p.py `
  --rfm <full.rfm> `
  --f-max 50e9 `
  --points 5001 `
  --output runs\case\reduced.s1p
```

该脚本仅是 DDR/port6 参考实现；remote agent 必须按新网表的 port map、端接及 CPM 拓扑实现通用降阶，不能直接套用其硬编码端口。

### 4. 用项目 sfit 拟合 reduced S 参数

必须使用项目 sfit，不得改用 scikit-rf VF：

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m agent_spice.cli fit-sparam runs\case\reduced.s1p `
  --output runs\case\reduced_fit.sp `
  --fitted-touchstone runs\case\reduced_fit.s1p `
  --rfm runs\case\reduced_fit.rfm `
  --rms-target <project threshold> `
  --max-order <approved maximum> `
  --passivity check
```

验收 reduced fit：比较 raw reduced S 与 fitted S/RFM 的幅值、相位和 RMS；再比较 raw/fitted `Zred`。若 reduced fit 误差超过时域容差预算，先提高项目 sfit 精度或调整 frequency sampling/bandwidth，不能用 TRAN 波形调参补偿。

### 5. 直接频域卷积

S1P：

```text
Z(f) = Z0 (1 + S(f)) / (1 - S(f))
V(f) = -Z(f) I(f)
v(t) = IFFT(V(f))
```

S2P/M-port：在每个频点仅解 reduced 网络，再对全部电流列做矩阵乘法：

```text
V(f) = -H_reduced(f) I(f)
```

负号必须用一个 AC current probe 校准，不得凭习惯假定。所有输入电流和输出电压都必须处在降阶时定义的相同参考方向。

#### Native H 构建器

`agent-spice-sim` 已提供仅面向项目 RFM 的 native 子命令：

```powershell
agent-spice-sim rfm-response reduced_fit.rfm `
  --fft-size 203001 `
  --dt 1e-11 `
  --input-ports 1 `
  --output-ports 1 `
  --response-bin runs\case\H.bin `
  --metadata-json runs\case\H.json `
  --threads 4
```

它输出 frequency-major 的复数 `H(f)` 二进制文件；对于 S1P，`H=Z=Z0(1+S)/(1-S)`，不再在 Python 中逐频求 RFM。固定端接、VRM、RDIE/CDIE/CPM 必须已经吸收进 reduced RFM。S2P/M-port 同样支持选定的输入/输出 port 子矩阵，语义为其他 port 电流为零时的阻抗传函。

Python 侧使用：

```powershell
python scripts\native_rfm_fft.py `
  --rfm runs\case\reduced_fit.rfm `
  --current runs\case\physical_zero_padded_current.csv `
  --tail 500e-9 `
  --input-ports 1 --output-ports 1 --threads 4 `
  --comparison runs\case\full_tran.csv `
  --output runs\case\native_fft
```

脚本只做 `FFT(I)`、`H*I`、`IFFT`，并记录 native H 构建和 FFT 的独立耗时。

### 6. 对比和性能计时

至少输出：

- current waveform、FFT spectrum、`Zred/Hreduced` 幅相；
- full TRAN 与 FFT overlay；
- error waveform；
- padding 收敛图；
- reduced raw S、fitted S、RFM 的频域误差；
- RMSE、max error、peak droop、peak timing、ring frequency、settling time；
- 一次性 `reduce + sfit` 时间；
- 单条在线 FFT 时间；
- 单条 full TRAN 时间。

速度必须分开报告：

```text
preprocess = reduction + sfit
online     = current FFT + reduced-RFM evaluation + matrix multiply + IFFT
reference  = full native TRAN
```

不得把绘图、读写大 CSV 或 reference TRAN 混进 online FFT 时间。

## 必须通过的检查

1. full deck 与 FFT 使用同一条完整 PWL，或已明确采用相同 DC `I0`。
2. fixed VRM/端接/RDIE/CDIE/CPM 只出现一次：要么已吸收进 reduced S，要么仍外接，不能两边都有。
3. tail 加倍后有效窗口误差和 peak 指标收敛。
4. reduced RFM 的频域误差小于时域误差预算。
5. AC probe 与 `H_reduced(f)` 至少在三个频点吻合。
6. 只有线性、固定拓扑 case 才可声称 FFT 可替代该 case 的 TRAN。

## 禁止事项

- 不得从 `Vtran(t)` 拟合衰减正弦、包络或修正项。
- 不得用 scikit-rf vector fitting 代替项目 sfit。
- 不得只在 FFT 侧补零而 reference TRAN 不改变 PWL。
- 不得把 reduced S1P 的 CPM 再次作为外部元件连接。
- 不得把一次性降阶/fit 时间伪装成每条波形在线时间，或反过来忽略预处理成本。
