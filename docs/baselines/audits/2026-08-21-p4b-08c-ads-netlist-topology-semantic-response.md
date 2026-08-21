# P4B-08c ADS Netlist Topology and Semantic Response Observation

- Scope: P4B-08c external-only topology and semantic-response observation.
- Status: delivered as hash-bound evidence; no product adapter, matrix, or
  runtime admission.
- Evidence: `docs/baselines/p4b-08c-ads-netlist-topology-semantic-response-evidence.v1.yaml`.
- Verifier: `tools/verify_p4b_08c_ads_netlist_topology_semantic_response.py`.
- Mutation tests: `tools/test_verify_p4b_08c_ads_netlist_topology_semantic_response.py`.

## Authority and custody

The observation uses the owner-authorized ADS workspace through an explicitly
injected external root. The netlist is not a Git object and is represented only
by relative path, byte length, and SHA-256. The central channel S4P is not in
the authorized-material registry. All ADS inputs and generated S2P/metadata
artifacts remain external-only and are not product fixtures or release inputs.

The independent source oracle is PyBERT commit
`f6ba0311350fc67bd90fa13b8d578312f956d7e7`, tree
`ac7006ea26cf9e8d885c0e4f1b82797d2e9342a1`. Its root `LICENSE` and `NOTICE`
are bound by Git blobs `64d198ba43675ede5fbdef1ec918a63954951640` and
`d179d695538ffe55e7ca6ba8e31ea8e6b6279cad`; the license conclusion remains
`NOASSERTION`. The evidence binds the exact `ads_bench.py`,
`channel_topology.py`, `sparam.py`, and test blobs; no source was copied into
SIPI.

## Observed topology

The parsed ADS chain is `tx_drv -> SnP1 -> rx_fe` with source pair
`N__2,N__9` and load pair `N__1,N__8`:

- `tx_drv`: nodes `N__2 N__9 N__11 N__3`, order `(1,2,3,4)`;
- `SnP1`: nodes `N__11 N__7 N__3 N__4`, order `(1,3,2,4)`;
- `rx_fe`: nodes `N__7 N__4 N__1 N__8`, order `(1,2,3,4)`.

The PyBERT semantic consumer performs topology renumbering, cascade,
single-ended-to-mixed-mode conversion, SDD21 extraction, and
`2/A` open-circuit differential-voltage conversion. At frequency index `0`
(`0.0 Hz`) it observed three blocks, `z0=100 ohm`,
`|Sdd21|=0.5990020074930338`, and open-circuit differential-voltage magnitude
`0.9256036352607088`. The generated S2P and metadata are external-only files
named `semantic_channel_a88d83b4ae7e2993.s2p` and
`semantic_channel_a88d83b4ae7e2993.json` under the output root supplied to the
verifier.

The pinned oracle regeneration method is:

```text
<PyBERT venv python> -c "
from pathlib import Path
from pybert_web.ads_bench import parse_ads_netlist, build_ads_channel_topology
from pybert.utility.channel_topology import SignalIntent
from pybert.utility.sparam import build_semantic_sparam_response
root = Path('<ADS workspace root>')
bench = parse_ads_netlist((root / 'netlist.log').read_text(encoding='utf-8'))
topology = build_ads_channel_topology(bench, root, corner=0)
build_semantic_sparam_response(
    topology, SignalIntent.AMI_INIT_CHANNEL_RESPONSE,
    cache_dir=Path('<generated semantic-output root>'))
"
```

## Non-claims and blockers

This observation does not freeze victim/aggressor columns, matrix timestep,
impulse conversion policy, or a typed edge to SIPI Channel. It does not admit
vendor rights, dependency closure, `AMI_Init`/`AMI_GetWave`, product runtime,
system parity, or release evidence. P4B-02 exact parameter contract and
P4A dynamic endpoint inputs remain outside this slice.

## Verification

Static verification does not read external files:

```text
python -B tools/verify_p4b_08c_ads_netlist_topology_semantic_response.py
```

Dynamic identity verification requires explicit external roots:

```text
python -B tools/verify_p4b_08c_ads_netlist_topology_semantic_response.py \
  --ads-root <ADS workspace root> --pybert-root <PyBERT Git root> \
  --output-root <generated semantic-output root>
```

Dynamic mode requires all three roots. It rechecks every ADS input hash and
length, PyBERT commit/tree/blob identities, both generated artifact hashes and
lengths, the generated metadata topology and diagnostics, and the S2P row at
frequency index `0`. The verifier rejects mutated node maps, port reorder,
low-frequency values, generated metadata/artifact identity, partial roots, and
non-absolute dynamic roots. No absolute external path is retained in the
evidence.
