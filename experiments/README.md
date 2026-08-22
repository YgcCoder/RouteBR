
# Experiments

`run_case.py` executes RouteBR, B1 Direct, B2 Direct+Guard, or one of the two safeguard removals on a selected split. `run_matrix.py` reconstructs the SELECT and CONFIRM task matrix. `preflight_models.py` validates credential-free API profiles and can optionally query `/models` when credentials are supplied.

The `results/` directory contains 27 completed tasks and 1,960 normalized case-level receipts. The normalization removes wall-clock and tracking metadata but leaves every semantic input, model output, token count, duration, retry event, model identity, and controller trace used by `analysis/analyze_results.py`.

API aliases and provider behavior may change. A new hosted run should be written to a new directory and compared against the frozen result manifest rather than overwriting this evidence.
