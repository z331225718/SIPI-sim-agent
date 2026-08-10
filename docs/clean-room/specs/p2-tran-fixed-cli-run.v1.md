# P2 Fixed TRAN CLI Run v1

`sipi tran run --stdin --artifact-root <external-root> --artifact-id <id>`
accepts exactly one product-owned `sipi.tran.rc-pulse-request.v1` document.
Only the independently specified RC/PULSE values are accepted; no netlist,
file path, backend, operating-point, AC, topology, or legacy field exists.

The command invokes the typed `sipi-tran` library under the fixed cooperative
run policy, computes deterministic request/result cache keys without a cache
store, and publishes `result.json` plus `provenance.json` only through the
immutable artifact primitive. The success manifest is the sole consumable
completion signal. Failure returns no success response and no consumable
artifact.

The CLI never loads, probes, or reports an external oracle. The oracle remains
an external acceptance comparator. This command is limited to the fixed
four-sample RC/PULSE profile and is not general TRAN or SPICE support.
