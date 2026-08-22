# Final RouteBR results

Status: **COMPLETE_SIX_BACKENDS**

## Backend screening on SELECT-160

| Backend | Contract | Path F1 | FD | FB | Valid JSON | Calls/case | Tokens/case | Median latency (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DeepSeek V4 Pro | 97.5 | 97.3 | 0/84 (0.0) | 1/76 (1.3) | 100.0 | 1.00 | 762 | 1367 |
| DeepSeek V4 Flash | 97.5 | 97.4 | 0/84 (0.0) | 2/76 (2.6) | 99.4 | 1.01 | 767 | 996 |
| Qwen3.8 Max | 97.5 | 97.2 | 0/84 (0.0) | 0/76 (0.0) | 100.0 | 1.00 | 737 | 1930 |
| GPT-4o | 96.9 | 96.7 | 0/84 (0.0) | 2/76 (2.6) | 100.0 | 1.00 | 730 | 1853 |
| Qwen3.7 Plus | 96.2 | 95.9 | 0/84 (0.0) | 1/76 (1.3) | 100.0 | 1.00 | 739 | 2293 |
| GPT-5.2 | 95.6 | 95.9 | 0/84 (0.0) | 5/76 (6.6) | 100.0 | 1.00 | 742 | 2329 |

## RQ1--RQ2 on CONFIRM

| System | MAIN contract | MAIN path F1 | FLIP pair | FD | FB |
|---|---:|---:|---:|---:|---:|
| RouteBR | 97.5 | 96.3 | 37/40 (92.5) | 0/166 (0.0) | 1/114 (0.9) |
| B1 Direct | 41.0 | 36.2 | 4/40 (10.0) | 127/166 (76.5) | 2/114 (1.8) |
| B2 Direct+Guard | 95.5 | 94.5 | 40/40 (100.0) | 1/166 (0.6) | 2/114 (1.8) |

## RQ3 safeguards

| Variant | Split | Contract | Object accuracy | FD | FB |
|---|---|---:|---:|---:|---:|
| RouteBR | FLIP | 96.2 | 100.0 | 0/40 | 0/40 |
| RouteBR w/o state enforcement | FLIP | 46.2 | 100.0 | 40/40 | 0/40 |
| RouteBR | ENTITY | 100.0 | 95.0 | 0/18 | 0/22 |
| RouteBR w/o closed grounding | ENTITY | 45.0 | 42.5 | 0/18 | 22/22 |

## Integrity

- SELECT backends present: 6/6.
- Audited SELECT rows: 960.
- Audited CONFIRM rows: 1000.
- No gold, annotator, or adjudication field was found in a model request body.
- Every audited prediction has one raw receipt and an accepted reported model identity.
