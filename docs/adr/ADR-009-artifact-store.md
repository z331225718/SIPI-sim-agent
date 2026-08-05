# ADR-009: 外部内容寻址工件存储

状态：已接受（M0 原型范围）。

## 决策

大型、私有和外部 golden 使用由 manifest 固定 SHA-256 的外部 CAS；Git 仅保留小型、已授权 fixture、索引和 provenance。本轮不采用 Git LFS，也不绑定生产云厂商或凭据。

对象路径为 `sha256/<digest 前两位>/<digest>`；不得使用 `latest`、浮动路径或由 manifest 提供任意 URL。descriptor 是期望大小和 hash 的唯一权威，文件名、ETag 和服务端元数据均不可信。

## 策略

- `blocked_unknown`：在 cache lookup 和网络 I/O 前拒绝。
- `external_reference_only`：仅允许用户明确提供的 allowlist 路径做本地校验；不得进入 store、cache 或 bundle。
- `authorized_private`：只允许受控私有 store 和消费。
- `authorized_public`：仅在正式授权证据、hash 和 availability 都满足时可进入公开 bundle。
- offline 模式绝不调用 provider；验证过的 cache 可成功，miss 为类型化失败，损坏 cache 为 integrity failure。
- raw transport blob 的 `transport_sha256` 不等同于未来 bundle 解包后的 `inventory_sha256`。

## M0 原型边界

`tools/m0_artifact_mock.py` 只验证 loopback mock 的 raw-blob 下载、流式 hash、原子 cache publish 和 offline 语义。它不是 M1 的公共 API、不会读取 M0-07 的未授权资产、不会上传、解包 archive 或处理生产凭据。

M0 中 `authorization_evidence_ref` 只做非空的合成 descriptor 检查，不是正式授权裁定。原型只允许无重定向的 `http://127.0.0.1:<port>` provider；生产 HTTPS、凭据、同源 redirect 和 entitlement 留给后续里程碑。

M1 冻结 schema/API；M6-02 决定实际 provider、凭据、保留和生产发布。
