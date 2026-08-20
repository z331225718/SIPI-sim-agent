# Argument-Required Gate Classification — Audit Record

- Date (UTC): 2026-08-16
- Scope: the 8 gates classified as RC2_NEEDS_ARGS by
  `tools/sweep_coverage_gates.py`; rationale for why they cannot run bare
  and when they can run
- Status: design behavior confirmed; no gate is broken

## Gates and their required inputs

| Gate | Required args | Dependency kind | Runnable when |
| --- | --- | --- | --- |
| verify_p4a_ibis_example_rx_candidate_inventory | --pybert-root | external repository (pybert, external-only custody) | owner provides authorized external root |
| verify_p5_agent_com_git_object_preflight | --source-root | external repository (agent-com, external-only custody) | owner provides authorized external root |
| verify_p7_windows_twin_build | --output-root --report --rustup --toolchain | release chain product (twin build outputs) | release run |
| verify_p7_release_composition | --stage --twin-report --layout-report --report | release chain products | release run |
| verify_p7_release_archive | --archive --composition-report --policy --report | release chain products | release run |
| verify_p7_isolated_install | --archive --composition-report --archive-policy --archive-report --install-prefix --report | release chain products | release run |
| verify_release_capability_publication | --command-manifest | release-time command manifest (schema sipi.command-manifest.v1) | release run |
| verify_tran_rc_pulse_acceptance | --source-root | external Git object (Agent-Spice source tree, external custody) | owner provides authorized external root |

## Classification

- 2 gates need owner-provided external repositories (pybert / agent-com):
  external_asset_oracle class; bare invocation exit 2 with empty stdout is
  the fail-closed design.
- 4 gates need release-chain products (twin build, composition, archive,
  install): release_gate class; they run at release time.
- 1 gate needs the release-time command manifest: release_gate class.
- 1 gate needs the external Agent-Spice Git object: external_asset_oracle
  class (P2-06 evidence surface).

No argument-required gate is broken; each fails closed without its
mandatory inputs, and each becomes runnable when its dependency class is
satisfied (owner-provided external root, or release execution).
