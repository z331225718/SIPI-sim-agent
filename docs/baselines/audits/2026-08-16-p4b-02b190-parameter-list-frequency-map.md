# Audit：P4B-02b190 parameter-list-frequency-map

## 切片语义
- **值级切片**：`parameter_list_frequency_map_v1` 返回 `BTreeMap<String, usize>`，
  键为每个 distinct trimmed item，值为该项出现总次数。
- **伴侣关系**：02b121 frequency 的 map 形态伴侣（相同数据，BTreeMap 按键 O(1) 查找 vs Vec 首现序迭代）；
  逐项计数 == 02b188 occurrence-indices-map 的 `indices.len()`；全计数和 == 02b083 item count。
- **规则绑定**：02b1 列表规则（`(item, item, ...)`，项 trim 非空）；02b0 原始字节相等。
- **fail-closed**：非 List 值 → `NotAList`；token 不匹配 List 形态 → `MalformedList`（防御性，不可达）。

## 工件清单
- 实现：`crates/sipi-ami-text/src/parameter_list_frequency_map_v1.rs`（6 Rust 单测）
- runner：`tests/p4b_02b190_parameter_list_frequency_map_runner.rs`（harness=false，单值 JSON 输入）
- crosscheck：`tools/run_p4b_02b190_parameter_list_frequency_map_crosscheck.py`（4/4 matched_hash_bound）
- verifier/unittest：`tools/verify_p4b_02b190_...py` + `test_verify_...py`（6 tests，含篡改拒绝）
- charter（based_on=189 条）+ source map（mapping×2）+ evidence（CRLF）

## 门禁结果
- `cargo test -p sipi-ami-text --lib`：1085 + 6 = 1091 全绿
- 单切片 verifier valid + pytest 6/6；coverage gates=360
- session health 6/6：TOTAL=342, VALID_KEY=318, gates=360, links=412, BAD=0

## 登记
- ledger note 追加 frequency-map (02b190, 4/4 crosscheck) delivered；gate 条目更新
- PLAN.md 叙事插入 02b189 审计链接之后；CRLF 字节级断言通过（二进制读写 + CRLF 感知 line_end）
