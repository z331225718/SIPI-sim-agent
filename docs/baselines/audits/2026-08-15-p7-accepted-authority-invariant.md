# P7 Accepted-Authority Invariant Audit

- Scope: `docs/clean-room/specs/p7-release-capability-publication.v1.md`,
  `tools/verify_release_capability_publication.py`, and
  `tools/test_verify_release_capability_publication.py`.
- Reviewer: user-authorized OMP, reused terminal
  `term_fa7831f5-ec22-4b3d-8737-25a919226b8b`.
- Result: no High/Critical findings. The explicit authority set contains only
  `tran-rc-pulse`, whose existing exact external-evidence verifier remains
  authoritative and still fail-closes on current source drift.
- Verification: `python -B -m unittest
  tools.test_verify_release_capability_publication` passed (13 tests). The
  accepted-state mutation pass rate was zero across all 23 available routes.

This audit seals only P7 v1 acceptance authority. It does not accept TRAN,
Channel, IBIS, AMI, COM, project, report, P3C, or any release capability.
