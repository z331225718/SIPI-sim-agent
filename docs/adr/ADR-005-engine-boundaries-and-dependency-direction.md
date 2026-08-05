# ADR-005: 引擎边界与依赖方向

状态：已接受。

依赖方向固定为 `apps -> runtime -> contracts` 与 `runtime -> adapter SPI -> adapter -> engine`。Circuit、Link 与 COM 保持独立；数值 core 禁止依赖 runtime、apps、Web 或 Agent。
