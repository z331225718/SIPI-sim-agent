# Native 离线运行清单

## 运行模式

Agent-Spice 的离线部署分成两个边界明确的模式。

1. 只运行自主仿真内核：使用平台 wheel 中的 `agent-spice-sim`。目标机不需要 Python 科学计算包、Rust、.NET、ngspice、HSPICE、Xyce 或 XDM。
2. 使用 `agent-spice` Python CLI、`run-hspice` 编排或 sfit：需要 Python 3.11 及以上版本，并在 wheelhouse 中准备本项目 wheel、`numpy`、`pyyaml`、`scipy`、`scikit-rf`、`cvxpy` 及 pip 解析出的全部传递依赖。

自主仿真 wheel 与目标操作系统和 CPU 架构绑定。Python 科学计算依赖还与 Python 版本和 ABI 绑定，不能在 Windows 上下载一组 wheel 后直接拿到 Linux 使用。

## 服务器预检

Linux x64 服务器先记录：

```bash
uname -s
uname -m
python3 --version
ldd --version | head -n 1
```

Windows x64 服务器先记录：

```powershell
[System.Runtime.InteropServices.RuntimeInformation]::OSDescription
[System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
python --version
```

当前 CI 直接在 GitHub Linux runner 上构建 `linux_x86_64` wheel，它不是 musl wheel，也尚未声明 manylinux 基线。服务器的 glibc 不能比构建机更旧；首次部署应先执行下面的内核 smoke，再投入长任务。Windows x64 wheel 已完成干净环境实跑。

## 在联网机器准备 wheelhouse

先从 CI 下载与离线服务器匹配的 Agent-Spice 平台 wheel，再在相同操作系统、CPU 架构和 Python 次版本的联网机器上执行：

```bash
python -m pip download --only-binary=:all: --dest wheelhouse path/to/agent_spice-0.1.0-py3-none-PLATFORM.whl
```

pip 会把项目声明的直接依赖和传递依赖一起放入 `wheelhouse`。若只测试自主内核，只需传递这个平台 wheel，不需要下载 Python 依赖。

## 无网安装

完整 Python CLI 与 sfit 环境：

```bash
python -m venv .venv
.venv/bin/python -m pip install --no-index --find-links wheelhouse agent-spice
```

Windows 将最后一行改为：

```powershell
.venv\Scripts\python -m pip install --no-index --find-links wheelhouse agent-spice
```

安装过程不得访问网络；缺少任何传递 wheel 时 pip 会立即报出缺失包名。

## 验证

先定位并直接运行包内 Rust 内核。Linux x64：

```bash
ENGINE=$(find .venv -path '*/site-packages/agent_spice/lib/native/linux-x64/agent-spice-sim' -print -quit)
"$ENGINE" native/AgentSpice.Engine/fixtures/rc.cir --output-json native-smoke.json
```

Windows x64：

```powershell
$engine = '.venv\Lib\site-packages\agent_spice\lib\native\win-x64\agent-spice-sim.exe'
& $engine native\AgentSpice.Engine\fixtures\rc.cir --output-json native-smoke.json
```

随后验证 Python CLI 与 sfit 依赖：

```bash
.venv/bin/python -m agent_spice.cli --help
.venv/bin/python -c "import numpy, yaml, scipy, skrf, cvxpy; print('offline dependencies ok')"
```

Windows 使用 `.venv\Scripts\python`。native smoke 成功而 Python CLI 失败，通常表示平台 wheel 正常但 wheelhouse 缺少 Python 依赖；内核本身不会因此回退到 ngspice。
