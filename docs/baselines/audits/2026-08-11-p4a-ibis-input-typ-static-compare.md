# P4A-04d IBIS Input/TYP Static Compare Audit

Date: 2026-08-11

## Scope

Commit `c288841` adds an external-only two-fresh-custody compare. An
independent raw-table observer and a test-only Rust runner compare the
selected Typical Input clamp profile. The report retains only identities and
aggregate metrics outside the worktree.

## Reviewer Result

Orca review `msg_056ba9347723` reported one P1 and zero P2 findings. The P1
was a stale `product-boundary.v1.yaml` inventory for the new comparator
material. This acceptance update regenerates the inventory and updates both
boundary-hash consumers. No protocol, custody, parser, or numeric P1/P2
finding remained.

## Verified Evidence

- Two fresh external materializations had matching asset, selector, table,
  raw-observation, and product-result identities.
- The selected six static probes were in-domain and both independent paths
  reported zero maximum absolute and relative current error.
- The product library remains in-memory. The comparison runner is an ignored
  test target and the observer tool is migration-only.
- No external asset text, selector spelling, raw table, request, probe array,
  or absolute path is committed. The report hash and derived evidence are
  recorded in the external-only evidence manifest.

## Limits

This accepts only the selected Input/TYP static DC-clamp profile. It does not
claim general IBIS compatibility, package, PVT, V-T, ramp, AMI, terminal
network, or release behavior.
