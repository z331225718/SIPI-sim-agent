# P5 COM source-gap audit and run-result conformance slice

本记录不提升 P5-02/05/06/08/09 的 authority、acceptance 或 release 状态；它把
pinned Agent-COM 语义与当前产品可实现边界分开记录。原项目 checkout 在观察时 dirty，
因此不使用 ignored output 或 `code_revision` 作为身份。

## 原项目身份

- origin：`https://github.com/z331225718/agent-com.git`
- commit：`5272ffe74702cd585054d975559b06f8afae7b6e`
- tree：`7094ab6e84989b218730c52432c70da10261f8ea`，object format：`sha1`
- source：`matlab_src/com_ieee8023_480.m`，Git blob
  `2e226d785c1ed2403f6d0a11288bf75939021814`，normalized SHA-256
  `88db14d7d82dab980d223a5be02a28013c11e0d0239e0e97e36c9d36fef55596`
- exact source-side reader/generator objects：
  `src/agent_com/config/excel.py` blob `1cce4365b64f3bb0ef1f7617107d2df4c929afc7`；
  `tests/test_mlse.py` blob `6628e3bbcf563fe57ea08e7af41553aa8b6c92aa`；
  `tools/run_matlab_oracle.py` blob `36d4fa55f6eaf9ecdd72ba2cebfbc1b01908e8bc`；
  `tools/matlab_oracle/run_com_oracle.m` blob
  `5845a4a088fede05e9a13ae91db7b41888a3b2be`；
  `tools/matlab_oracle/com_oracle_case_metrics.m` blob
  `9d13c8c9468a31ff9c06e2985bb6d03efc6428b6`；
  `tools/matlab_oracle/rebuild_oracle_summary.m` blob
  `114c1dc8d5041f670540e5ea40ca029b55bb7c8e`；
  `tools/prepare_instrumented_oracle.py` blob
  `d1def7e3ea0730e9086b7d39fccc2b5ae99f42e7`。

## MATLAB 语义事实与缺口

- **P5-02 warning**：source 静态 `warning(...)` call-site inventory 为 25；其中 MLSE
  运行 warning 位于 2109、2228、2238，另外包含 anti-causal、impedance、COM contribution
  和 S4P input warnings。静态 call-site 数量不等于完整运行合同；当前产品 warning detector
  只覆盖确定性的 anti-causal/non-decay 子集。
- **MLSE/DER/CDR**：主路径在 529-600，`MLSE_U1_c_178A` 在 2137；`DER_DFE <=
  param.DER_CDR` gate 在 2187；`DER_CDR` 默认 `1e-2` 在 8915，`trunc/N_tc` 默认 128
  在 8926-8927，`Q_budget_adj` 在 8930，`CDR` 默认 `MM` 在 9222，`MLSD -> MLSE`
  alias 在 9236-9237。DER/COM 输出字段在 2250-2259。source 没有产品可直接采用的
  full checkpoint alignment 或 metric tolerance policy；不能由本切片发明容差。
- **P5-05 MAT**：`src/agent_com/config/excel.py` 的 authority reader 是 MATLAB v5
  `parameter` cell；`tests/test_mlse.py` 使用 `h5py` 读取 MATLAB v7.3 HDF5 result。
  产品 `crates/sipi-com/src/mat_reader_v1.rs` 仅实现 bounded-scope MAT v5 config reader。
  `sipi-com/Cargo.toml` 没有 HDF5 依赖；因此本轮不伪造 v7.3 reader，也不引入未经 owner
  选择的 HDF5 runtime。
- **P5-06**：pinned source 可重放 candidate bundle 仍不能闭合 config/fixture、generated
  instrumented output、invocation authorization/startup isolation、完整 warning contract
  或 checkpoint alignment。
- **P5-09**：CLI manifest 的 `com.run` 仍明确 `unavailable` / `com_profile_not_admitted`；
  目前没有 owner 选定的完整 artifact/config/profile request contract，不把 unavailable
  命令伪装成产品 COM parity。

## 本轮生产切片：显式冻结 legacy v1 rejection wire

历史 P5-08b evidence 已把 `sipi.com.run-result.v1.invalid_reason` 固定为
`SchemaMismatch` 等 enum-style token。`com_run_execution_v1.rs` 因此新增私有、穷尽的
legacy v1 映射，替代对 Rust `Debug` 格式的隐式依赖，但保持 wire byte-for-byte 兼容。
P5-08a runner 是另一个已冻结为 snake_case 的 crosscheck surface，继续保留其本地映射；
没有新增 public error-code API，也没有把 v1 无版本迁移为 lowercase。P5-08b verifier 现在
精确校验三条历史 entry，并拒绝把双方 `SchemaMismatch` 篡改为 `schema_mismatch` 的伪绿。
该切片只加固既有 request/result conformance，不声称执行 MATLAB、full COM solver 或
acceptance。

## 新增 P5-08d：bounded artifact binding/report leaf

`crates/sipi-com/src/com_run_artifact_provenance_v1.rs` 只读取既有
`sipi.com.run-request.v1` 的 `artifact_root` / `artifact_id` 绑定，并委托
`sipi-artifacts` 的 `inspect_verified_v1` 做 metadata-only integrity projection。request
JSON 上限为 65536 bytes；manifest、entry count、payload 总量和 report 上限精确锁为
65536 / 64 / 16777216 / 16384。这些是文件读取预算，不是 MLSE/DER/CDR 或 COM metric
tolerance。root/id 规则与既有 artifact-report binding 对齐，且不改变旧 admission/result
wire。API 只返回 metadata report；delegated reader 可能在预算内读取 payload 文件重算
hash，但不会把 payload 返回或送入 COM pipeline。

`ArtifactReportV1.integrity_lineage` 的 `unavailable` 值不构成 external provenance；本 leaf
只声明本地 bounded metadata/hash projection，并明确不提供 hostile-writer safety、ownership、
signature 或 external-origin proof。沿用 legacy request 的 root/id surface 是因为它已经是
`sipi.com.run-request.v1` 的绑定字段；本切片不新增字段、不改变 v1 wire，也不把 root 当作
profile/config/generator authority。

本地 fixture 的 payload / manifest / report SHA-256 分别为
`23bd670b3ff114c2eeec2ce27fd6def314530f33f6a46b2c4fb05964628bba9b`、
`dc44cc8d5ded60f3cbcf4c1b85c57fdc3e6d0b902cc5569e4a91d11f48c7d89c`、
`2422c29429d48db15cf3ddb6dbba681457a367cb0c21dc0e0bb43ed2407f96f0`；它们只是仓内
bounded reader 测试材料，不是 MATLAB oracle 或 release evidence。新增 evidence
`p5-08d-com-run-artifact-provenance-bounded.v1.yaml` 与独立 verifier/mutation tests
锁定 schema、canonical Git object/content identities、预算和 non-claims。实现文件的
Git blob OID / content SHA-256 为 `092af3b18e123435c483a1a203d91b1a9f53ce40` /
`a58270e247a36f22ec768378d586f4b14ba4c6492a203fb1d8dfdecc352ef41a`；这些只绑定实现
字节，不把 base lineage 或本地 fixture 冒充 acceptance。依赖的产品基线为 commit
`b6071779d8164e685d15ddf45c19dcb6b2553c78`，`sipi-artifacts/src/lib.rs` base blob 为
`794fbecd0465bc73f33dd0264755b45b9f23366b`。

该 leaf 仍不声称 artifact existence 之外的 external provenance、COM execution、profile
selection、payload-to-COM consumption、checkpoint alignment、MLSE/DER/CDR semantics、metric
tolerance、acceptance 或 release。

产品基线对象为 `SIPI-sim-agent` commit `fbec03c7cc370a630a0869329263caf0f1294731`
（tree `324298c913e1c83483f37504d73bdfa4f32f5893`）：

- `crates/sipi-com/src/com_run_admission_v1.rs` base blob
  `3c02d61a03048264cceb5f07e53c9a08cdbad6cb`
- `crates/sipi-com/src/com_run_execution_v1.rs` base blob
  `589b9ac2b3a87fe4154e081fd91bb2e44139fcc6`
- `crates/sipi-com/tests/p5_08b_com_run_execution_runner.rs` base blob
  `358a837c6751e93bf3f61863537d328c17ec8f83`

## 验证

- `cargo fmt --all -- --check`：通过。
- `cargo test -p sipi-com --lib`：263 passed。
- `cargo clippy --workspace --all-targets --locked -- -D warnings`：通过。
- `cargo test --workspace --all-targets --locked --no-fail-fast`：通过；ignored external harness 未被冒充为 crosscheck 执行。
- `python -B -m unittest tools.test_verify_p5_08b_com_run_execution`：7 passed。
- `python -B -m unittest tools.test_verify_p5_08d_com_run_artifact_provenance_bounded`：9 passed；
  static document verifier：valid。
- P0 product-boundary / clean-room / Rust source-map / license-preflight gates：全部 valid，license 仍 provisional、`release_ready=false`。
- 同一 OMP 只读审查 staged diff：0 High / 0 Critical。
