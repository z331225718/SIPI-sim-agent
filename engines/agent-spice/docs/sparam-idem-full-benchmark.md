<!-- GENERATED FROM summary.json; DO NOT EDIT -->
# Native vs IdEM Full-Corpus S-Parameter Benchmark

Canonical data: `runs-sparam/full-corpus-target-0p001/summary.json`

## Contract

- Mean S-RMS target: `0.001` on every original frequency and port pair.
- Passivity: enforced; authoritative check plus sampled `max_sigma <= 1.000001`.
- Maximum effective order: `100`; computational threads: `8`.
- Search: even orders from 4, then adjacent odd-order backfill after the first even pass.
- Parity gates: Native/IdEM order `<= 1.25`, time `<= 2.0`, memory `<= 1.5`.

Native command: `python -m agent_spice.cli fit-sparam <INPUT> --rms-target 0.001 --passivity enforce --max-order 100 --resume-target-search`

Benchmark command: `python scripts/sparam_full_corpus_benchmark.py --corpus-root user_input/spara --rms-target 0.001 --passivity-epsilon 1e-06 --max-order 100 --threads 8 --resume`

IdEM enforcement/check options: `idemmp_passivity.exe -hamSolver 3 -DC 1 -nThreads <THREADS>` followed by `-onlyCheck 1`; accepted models are exported with `idemmp_export.exe -type 2` and independently audited.

## Results

| Input | SHA-256 | Native | IdEM | Native order | IdEM order | Native RMS | IdEM RMS | Native sigma | IdEM sigma | Native time (s) | IdEM time (s) | Native peak (MiB) | IdEM peak (MiB) | Order ratio | Time ratio | Memory ratio | Comparison |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5power_19port_withcap_122324_202459_11476_DCfitted.s19p | 87fccc96196d8c149d1b3ba985701dd56a78f5d9904984f55f8161c39cdd7c7e | FAIL | FAIL | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | INVALID |
| 5power_30port_wocap_121124_221036_4876_DCfitted.s30p | f2da3db961cc8f0fdd29eeb3ad2870a0d4ef97db7f7f11e148d80c854a8c2f0b | PASS | FAIL | 83 | N/A | 0.000918440268 | N/A | 1.00000001 | N/A | 1820.11654 | N/A | 947.328125 | N/A | N/A | N/A | N/A | INVALID |
| Test13.s60p | 8717614eea43f4ce342772330de8217834b39fa514c48be27caf150f348adb43 | PASS | PASS | 8 | 7 | 0.000516017662 | 0.000737076014 | 0.999977674 | 0.999696292 | 52.7829764 | 35.4216266 | 206.128906 | 197.253906 | 1.14285714 | 1.49013418 | 1.04499277 | PASS |
| Test16.s91p | f8055fe88d5aa9e1212359c53f37c9f261c07f156f1d7b1f8d4991ea08047996 | PASS | PASS | 13 | 10 | 0.000707378591 | 0.000597697267 | 0.9999989 | 0.999998073 | 335.953691 | 79.618002 | 423.699219 | 418.714844 | 1.3 | 4.21956948 | 1.01190398 | FAIL |
| Test11.s163p | 8f4d47475667d79870b7b8f02a07a6919908b4e535630c52dd487fd339507e67 | PASS | PASS | 10 | 6 | 0.000197399324 | 0.000696814561 | 0.999965329 | 0.999999875 | 608.595759 | 211.092171 | 1075.35547 | 1133.32422 | 1.66666667 | 2.88308068 | 0.948850692 | FAIL |
| Test3.s166p | b5eae90b53cb815bf0cb645774cd3686422fad00bfc8850482d2f8731728dc7c | PASS | PASS | 9 | 4 | 0.000271430739 | 0.000902467234 | 0.9999814 | 0.999999831 | 656.734625 | 199.755046 | 1128.40625 | 1173.11719 | 2.25 | 3.2876998 | 0.961887066 | FAIL |

Overall six-case parity: **FAIL**.
