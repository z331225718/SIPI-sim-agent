# MFT-NNLS Test16 Pole-Collapse Probe

## Scope

This is the Task 4b pole-collapse gate, not a fit-quality or passivity claim. It probes the Python MFT `vectfit4` relocation port on the complete reciprocal `Test16.s91p` grid.

| Setting | Value |
| --- | ---: |
| Frequency samples | 611 |
| Ports | 91 |
| Frequency span | 0 to 2 GHz |
| Initial common-pole order | 8 |
| Initialization | `linlogcmplx` |
| Relocation iterations | 8 |
| Backend | Python / OpenBLAS |

## Result

**Classification: reproduced.** The edge complex pair first reaches 2.021398188 GHz, above the 2 GHz input maximum, then falls below the configured 0.85 input-band threshold by iteration 4 and continues to 1.382298840 GHz at iteration 8.

| Iteration | Edge pair frequency (GHz) | Relocation condition number |
| --- | ---: | ---: |
| 1 | 2.021398 | 1.824e7 |
| 2 | 1.799622 | 1.720e3 |
| 3 | 1.729873 | 2.564e4 |
| 4 | 1.606237 | 2.150e3 |
| 8 | 1.382299 | 3.591e3 |

The iteration-3 sigma coefficients also grow sharply (up to approximately `1.05e8`), consistent with the observed native collapse signature. Therefore the port has demonstrated MATLAB-equivalent single-step behavior but has **not** shown a relocation-stage cure for the native high-frequency collapse. The subsequent RP-NNLS work must be evaluated against this reproduced starting-point limitation; no promotion claim may rely on Task 4b.

The full JSON artifact is generated locally by:

```powershell
python scripts/sparam_mft_pole_trajectory.py `
  --touchstone C:\Users\z3312\code\agent-spice\user_input\spara\Test16.s91p `
  --order 8 --iterations 8 `
  --output runs-sparam\mft-nnls-test16-trajectory.json
```
