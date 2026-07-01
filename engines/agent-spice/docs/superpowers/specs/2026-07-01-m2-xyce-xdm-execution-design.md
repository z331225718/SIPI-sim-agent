# M2 Xyce XDM Execution Design

## Goal

Add a first M2 execution path that can run an HSPICE deck through XDM and then Xyce with one CLI command:

```powershell
agent-spice run-hspice legacy.sp --backend xyce-xdm --execute
```

## Non-Goals

- Do not add a real-deck corpus in this slice.
- Do not expand HSPICE syntax support beyond what is needed for the execution path.
- Do not change the existing `ngspice` and direct `xyce` execution behavior.

## Behavior

For each expanded HSPICE case, the run directory should contain:

- `case.sp`: expanded HSPICE case text used as XDM input.
- `xdm-out/case.sp`: raw same-name XDM output, matching XDM's documented `-d` behavior.
- `case.cir`: normalized copy of the XDM-generated Xyce netlist used for Xyce execution.
- `compat_report.json`: existing compatibility report for the lightweight converter output.
- `xdm.stdout.log` and `xdm.stderr.log`: XDM process streams.
- `xyce.stdout.log` and `xyce.stderr.log`: Xyce process streams when XDM succeeds.
- `run_summary.json`: machine-readable status for the two-stage execution.

If XDM fails, the CLI returns the XDM exit code and does not run Xyce.
If XDM succeeds but Xyce fails, the CLI returns the Xyce exit code.
If both stages pass for all cases, the CLI returns `0`.

## Architecture

`XyceBackend` remains the owner of Xyce and XDM command construction. It gains a two-stage helper that runs XDM first into a staging directory, copies the generated same-name deck to the requested Xyce deck path, writes stage logs, then runs Xyce if the generated deck exists and XDM returned success.

`run_hspice()` keeps the existing converter artifact path for `ngspice` and `xyce`. For `xyce-xdm`, it additionally preserves the expanded HSPICE case as `case.sp` and executes the two-stage backend against that file.

`VALID_BACKENDS` and CLI parser choices include `xyce-xdm`, so project manifests and commands agree on the supported backend names.

## Open Follow-Up

The next M2 slice should add a small real-deck corpus and golden compatibility reports. That corpus can then exercise this execution path instead of building a separate read-only pipeline first.
