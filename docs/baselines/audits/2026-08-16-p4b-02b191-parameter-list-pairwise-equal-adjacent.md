# Audit：P4B-02b191 parameter-list-pairwise-equal-adjacent

## 切片语义
- **值级切片**：`parameter_list_pairwise_equal_adjacent_v1` 返回 `Vec<(String, String)>`，
  对每个相邻下标 i 且 `item[i] == item[i+1]` 返回 `(item[i], item[i+1])`，保序含重复。
- **伴侣关系**：02b184 pairwise-distinct-adjacent 的等值镜像（同窗口，互补谓词）；
  对数恒等于 02b134 equal-adjacent count；每对为 02b157 的长度-2 窗口。
- **空结果合法**：单项目 / 全不同列表返回空列表（镜像 02b40 空搜索语义）。
- **规则绑定**：02b1 列表规则（`(item, item, ...)`，项 trim 非空）；02b0 原始字节相等。
- **fail-closed**：非 List 值 → `NotAList`；token 不匹配 List 形态 → `MalformedList`（防御性，不可达）。

## 工件清单
- 实现：`crates/sipi-ami-text/src/parameter_list_pairwise_equal_adjacent_v1.rs`（6 Rust 单测）
- runner：`tests/p4b_02b191_parameter_list_pairwise_equal_adjacent_runner.rs`（harness=false，单值 JSON 输入）
- crosscheck：`tools/run_p4b_02b191_parameter_list_pairwise_equal_adjacent_crosscheck.py`（4/4 matched_hash_bound）
- verifier/unittest：`tools/verify_p4b_02b191_...py` + `test_verify_...py`（6 tests，含篡改拒绝）
- charter（based_on=190 条）+ source map（mapping×2）+ evidence（CRLF）

## 门禁结果
- `cargo test -p sipi-ami-text --lib`：1091 + 6 = 1097 全绿
- 单切片 verifier valid + pytest 6/6；coverage gates=361
- session health 6/6：TOTAL=343, VALID_KEY=319, gates=361, links=413, BAD=0

## 登记
- ledger note 追加 pairwise-equal-adjacent (02b191, 4/4 crosscheck) delivered；gate 条目更新
- PLAN.md 叙事插入 02b190 审计链接之后；CRLF 字节级断言通过（二进制读写 + CRLF 感知 line_end）
