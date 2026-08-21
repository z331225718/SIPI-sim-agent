# P7 Current Candidate Chain: Rejected Evaluation

本记录是 candidate `167b97140d510d22c2add060a5554bdf5699d7d6` 的加法式、非发布证据。链条从 clean archive 外部构建开始，按既有 P7 工具依次完成 twin、layout-v2、composition observe、archive、isolated install 和 fixed TRAN performance observation。

Twin 为 `identical`；报告为 1255 bytes，SHA-256 为 `6cb7e762b116344767db1850f02bb9f74f3d9097318e4bd4a38286605cf4712a`。layout-v2 为 `layout_conformant`；canonical policy 为 665 bytes、SHA-256 为 `6bc3732cd128d3a16274ef02cf82e0499049a4016e83802cd07d14e75871ccf8`，layout report 为 1724 bytes、SHA-256 为 `f3becd4f393b1c5d1daa6eefa6806e690811e4c87fb741e2e8daf3c55f1e5e4c`。相同 executable 为 4194304 bytes，SHA-256 为 `5abf41c8207f13b1e33653d791a41615efa919e828b1f4330bf823786e7a4ac7`。

Composition 报告为 58358 bytes、SHA-256 为 `b9202e10cd721c3bb905c4a37c43be29f746e211e6d636b3bb437ffc3725f0bb`，状态为 `incomplete` 且 promotion blocked。Archive 报告为 1140 bytes、SHA-256 为 `e8e113a3151a9294e50efe75619eff6915992e0193b7631b8abb5e89d389bc00`，结构准入为 `conformant`，但继续绑定 incomplete composition。Isolated install 报告为 2032 bytes、SHA-256 为 `84311ee3c1ce9ce847a6af2d776f7a72751f91ff63e2f8fd826bf12d5bef5552`；它只是 same-host isolated prefix，明确不是 fresh-machine 或 loader-closure 证据。

Performance observation 为 4368 bytes、SHA-256 为 `f6d5a03e6dfb371291d8753f12e5bb8e5237d965be3126f7fd30bc69f18bf6ce`，状态为 `observed_pending_owner_budget`。3+10 observation 的 median wall time 为 26349750 ns，median peak working set 为 4681728 bytes；数值观察低于 delegated threshold，但由于 policy 所绑定的历史 baseline raw reports 不在可取得 custody 中，不能发布 `within_policy` evaluation。

现有 evaluation tool 实际返回 `status=rejected`、`reason=evidence_json_invalid`，没有生成 evaluation report。拒绝输出仅保留 126 bytes 的 hash-only external reference：`7df87668b80ed82e5f93ea673f2b7a7e8d73c8d628a89ae54d25b200499d6428`。要求的 baseline observation SHA-256 为 `f6bcef3ee820919062018a6c3d37128260ca4cc28e8bb8c8867e3e98d060ae4f`，P1 locked-build report SHA-256 为 `a17d68e504d5112b401aac970431e31460db67faecc975a19fe0d1bb6a9de1f7`；两份 raw evidence 不可用，因此没有重试、替换 baseline 或伪造 evaluation。

本记录不保存外部目录、报告 payload、executable、archive、采样明细、主机名、用户身份或其他机器身份。promotion、release candidate、strict license/NOTICE、fresh-machine、dynamic/runtime closure、certified profile 和 legacy retirement gates 均保持 blocked。
