# AS-06 current-candidate ngspice parity

Status: `passed_scoped_external_observation`.

Candidate archive: `a9543da167895a04077bb796c4942feec95e9b89` (`d0863f62973ba02a28c6fbe10718292bc0ab3f2dc5a2f43794c2edceab33385b`, 59975680 bytes).
Pinned upstream archive: `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5` (`a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144`, 120238080 bytes).
Replay runner: `tools/run_as_06_ngspice_current_candidate.py`, committed at `36621b76ff400aad406575dc9b392cc794d2e593`, content SHA-256 `cafd4b98898dbac7a5b229aa0ed2ff2a38759679161c573dd0f9784a37ea4191`.

Two fresh immutable replays were copied from validated temporary outputs:

- `docs/baselines/as06-specific/as06-ngspice-current-candidate-run-01.v1.json`: `c4005814660f0cfaaaaaac90f9c84defd77e4117606d90a0671d5a4f25b7cfe6`
- `docs/baselines/as06-specific/as06-ngspice-current-candidate-run-02.v1.json`: `3b1c15eaaf6e415ad843d19409b4d1c1661bc618a021fe9d8cb1c96151e4bd5b`
- `docs/baselines/as06-specific/as06-ngspice-current-candidate-aggregate.v1.json`: `59647b791187c9d36676c9cf39cfa8ecec27ef04b3bb821b8043d38c7f572953`

Both reports passed the runner's bounded comparison: 1029 waveform rows, headers `time/v(src)/v(out)`, zero maximum absolute error, bit-exact canonical float payloads, equal logical manifests, and equal runtime reconstruction semantics. Toolchain, input, source-map, and pre/post integrity receipts are validated by the formal verifier.

This is an external ngspice observation for the named candidate and pinned upstream Git archives only. It does not claim solver correctness, release acceptance, hostile-writer resistance, environment-injection resistance, S-parameter fitting, or AS-05 Xyce/XDM support.
