# Triage run report

- Input: `demo.faa` (15 sequences)
- Target: 70.0 °C, pH 7.0
- T0 reference mode: **batch_relative**

## Funnel

| Outcome | Sequences | % of input |
|---|---:|---:|
| passed_T0_pending_T1 | 6 | 40.0% |
| passed_T1 | 3 | 20.0% |
| rejected_T0 | 6 | 40.0% |

## Top rejection reasons

| Tier | Reason | Count |
|---|---|---:|
| T0 | t0_composite_z below top-0.6 cutoff | 6 |
| T1 | no structure supplied | 6 |
| T1 | not evaluated (failed T0) | 6 |
