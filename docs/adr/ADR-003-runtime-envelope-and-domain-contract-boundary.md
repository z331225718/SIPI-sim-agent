# ADR-003: 运行信封与领域契约边界

状态：已接受。

平台拥有 run/backend execution 信封；runtime 是唯一 selection、fallback、compare 与结果聚合者。adapter 只消费/产生 strict backend execution。平台信封只包装、不替换或扩写既有领域 request/result；领域 request/result 保持版本化独立，领域结果不压平为语义不明的平台指标。
