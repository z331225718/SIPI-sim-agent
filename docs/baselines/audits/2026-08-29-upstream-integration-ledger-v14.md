# Upstream integration ledger v14 audit

This additive successor keeps all 15 upstream rows open or scoped and keeps `release_ready=0`.

- Candidate: `beb5b764f471ec4c9cda81dc233ac1a3d984669e`, clean Git archive only.
- AS-06: scoped external ngspice observation only; no solver correctness, release, S-parameter fit, or AS-05 Xyce/XDM claim.
- COM-02/04: scoped formal result-surface record; DFE winner taps and configured port-order execution are observed, without upstream numeric parity, a port-order result wire, acceptance, or release.
- PB-01: DuoBinary selected-array parity is scoped only.
- PB-02: thirteen blockers remain and complete typed output parity is false.
- AS-05 Xyce/XDM remains excluded. S-parameter fitting remains forbidden. Channel conversion remains one final FD-to-TD impulse.

No row is closed or promoted by this ledger.

RECIPROCAL AS06 591a2563179713a97a7b2346597a986f42bb1af9 1e2f1be2d9be730ca38cf21ce8393de02c295f6a 327a1690755dbde76698a9aa7f8cb9705bf1f1902b5161185fb2bfaf210ae0b9
RECIPROCAL COM02_04 e5d9bfe5fa946ee88b9eb06df1db3b574dd43c05 2dea3bbe6039224704f1e07aebc3ebd6c178abed 74a3dba2a02f31306db776a9ceb31acb19ad0b9eb668fdb9fe5cf8da88cab951
RECIPROCAL PB01_02 b738e983a430f98b04da066f3e9c42b8f3ee58e6 beb5b764f471ec4c9cda81dc233ac1a3d984669e 1046da4884fa2cd533ee9ecf119500177e378dfaec33d2afd94c2ce05184b297
