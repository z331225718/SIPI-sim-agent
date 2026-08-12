# Independent Audit: P4B-05c Dual-AMI PE Loader Declarations

审计对象：两个已由 P4B-05b 绑定的 Windows x64 AMI DLL 的 external-only
static PE loader-declaration observer。两次 fresh private custody 均获得同一
canonical declaration payload；仓库仅保存报告摘要哈希与结构事实。

| Check | Result | Evidence |
| --- | --- | --- |
| identity and custody | pass | TX/RX logical name, byte length and SHA-256 bind P4B-05b; copy-before/after/copy checks and two private materializations agree |
| PE declaration surface | pass | bounded PE32+ RVA parsing covers normal/delay/bound imports, name-or-ordinal thunks, export forwarders, RT_MANIFEST resources, TLS and CLR directories |
| observed facts | pass | both DLLs have three normal import modules, no delay/bound imports, no export forwarders or embedded manifests, TLS present and CLR absent; per-DLL symbol digest remains distinct |
| no runtime | pass | observer has no DLL load, ADS, worker or subprocess execution route |
| gate preservation | pass | dynamic dependency closure stays `blocked_not_assessed`; worker, AMI runtime, product runtime and release promotion remain false/blocked |
| sidecars and custody | pass | no sidecar name is admitted; vendor DLL/report hashes are rejected if tracked |

OpenCode 只读审计结论：`0 P1 / 0 P2`。

已执行并通过：

```text
python -B tools/observe_p4b_dual_ami_pe_loader_declarations.py --external-root <external-ADS-asset-root> --report <external-report>
python -B tools/verify_p4b_dual_ami_pe_loader_declarations.py
python -B tools/test_verify_p4b_dual_ami_pe_loader_declarations.py
python -B tools/verify_p4b_ads_pcie_gen5_dual_ami_asset_preflight.py
python -B tools/test_verify_p4b_ads_pcie_gen5_dual_ami_asset_preflight.py
python -B tools/verify_clean_room_register.py
python -B tools/verify_product_boundary.py
```

仍未完成：完整静态/动态 dependency closure、rights、sidecar admission、DLL/AMI load、GetWave、compatibility、TX-to-RX composition、numerical parity 与任何 release/product admission。
