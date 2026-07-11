# MFT-NNLS S19 Gate B

## Result

**FIT_FAILURE** on the frozen 19-port promotion input. No tested order met the
full-grid RMS target of `0.001`, so this gate stops before any promotion or
default-backend decision.

## Run

| Setting | Value |
| --- | --- |
| Input | `5power_19port_withcap_122324_202459_11476_DCfitted.s19p` |
| Frequency points | 826 |
| Ports | 19 |
| Orders | 8, 10, 12, 14, 16 |
| RMS target | `<= 0.001` |
| Passivity target | `max_sigma <= 1 + 1e-6` |

## Evidence

| Order | Fit RMS | Final RMS | Final max sigma | Gate result |
| ---: | ---: | ---: | ---: | --- |
| 8 | 0.034786 | 0.039791 | 1.037537 | FIT_FAILURE |
| 10 | 0.027530 | 0.027530 | 1.182536 | FIT_FAILURE |
| 12 | 0.021848 | 0.025496 | 1.061823 | FIT_FAILURE |
| 14 | 0.027758 | 0.029740 | 1.072926 | FIT_FAILURE |
| 16 | 0.035920 | 0.035920 | 1.403148 | FIT_FAILURE |

All tested models had stable poles. RP-NNLS reduced the passivity excess in
some trials, but none reached the passivity target and all were already far
above the RMS target. The observed failure is therefore fitting quality first,
not evidence that passivity correction alone can rescue the collapse path.

The local JSON artifact is `runs-sparam/mft-nnls-s19-gate-b.json`, generated
with:

```powershell
python scripts/sparam_mft_s19_gate_b.py `
  --touchstone C:\Users\z3312\code\agent-spice\user_input\spara\5power_19port_withcap_122324_202459_11476_DCfitted.s19p `
  --output runs-sparam\mft-nnls-s19-gate-b.json
```
