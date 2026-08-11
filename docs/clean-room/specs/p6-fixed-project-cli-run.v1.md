# P6-04c/P6-05b Fixed Project CLI Run v1

This specification exposes exactly one product-owned project command:

```text
sipi project run --stdin --artifact-root <external-root> --artifact-id <id>
```

The request is `sipi.project.fixed-tran-causal-fir-run-request.v1`. It carries
one declarative `sipi.project.v1` plan and one explicit causal-FIR consumer
policy. The only admitted plan is the existing
`project.tran-rc-pulse-to-causal-fir` composite: its fixed TRAN source is
converted only to the existing DirectLaunch causal-FIR edge. The route rejects
every extra node, edge, input, output, consumer interval, or stage shape.

The command creates a cooperative runtime with the exact resource policy and
project id declared by the admitted plan, performs attempt `1` once, and never
retries or consults a cache. A completed attempt is published only through the
existing immutable artifact protocol. A successful artifact has exactly the
product-owned `request.json`, `received-waveform.json`, `edge-record.json`,
and `provenance.json` payloads plus its success manifest. The response exposes
only the opaque artifact id and digests; it does not reveal the artifact root.

Malformed input and topology admission failures are contract rejections.
Runtime, resource, and publication failures return no successful artifact.
The command accepts no file, URL, external asset, legacy profile selector,
generic project graph, worker, cache, retry, or domain fallback. In particular,
it is not a general project executor and does not activate Channel S2P, RFM,
IBIS, AMI, or COM execution.
