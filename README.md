
# RouteBR

RouteBR is a reference implementation and reproducibility artifact for fail-closed pre-response routing in LLM-enabled customer-service software. One model call proposes a primary action and a closed-list object. Deterministic code commits to that primary action, evaluates versioned runtime rules, validates the object contract, and emits either a typed dispatch or a bounded terminal. Lower-ranked candidates are audit-only and cannot replace a blocked primary action.

## Repository contents

- `src/routebr/`: dependency-free controller, policy engine, typed records, replay backend, and hosted-API adapter.
- `tests/`: deterministic unit tests for contract, state, grounding, repair, and primary-route commitment.
- `data/`: 600 privacy-preserving synthetic scenarios, frozen SELECT/CONFIRM subsets, catalogs, rules, and validator.
- `experiments/`: frozen prompts, credential-free API profiles, rerun scripts, and normalized case-level receipts for 1,960 system-case executions.
- `analysis/`: result reconstruction and integrity checks.
- `paper/`: LaTeX source and figures matching the audited manuscript. The compiled PDF is intentionally excluded because PDF build metadata contains wall-clock timestamps.

## Quick verification

```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests -v
python3 data/validate_dataset.py   --cases data/routebr_600.csv   --catalog data/catalog.csv   --rules data/boundary_rules.csv   --entities data/entity_catalog.csv   --review-mode joint
python3 analysis/analyze_results.py --require-six
```

The verification commands do not call a hosted model. Rerunning the hosted matrix requires the environment variables named in `.env.example`; keys are never stored by the repository.

## Reproducing hosted runs

Validate profiles without network access:

```bash
python3 experiments/preflight_models.py   --profiles experiments/api_profiles.json   --no-network
```

Run one dry case without a network call:

```bash
python3 experiments/run_case.py   --profiles experiments/api_profiles.json   --profile deepseek_v4_primary   --system routebr   --split MAIN   --cases data/routebr_confirm_320.csv   --output-dir /tmp/routebr-dry-run   --limit 1   --dry-run
```

For a paid rerun, remove `--dry-run`, supply the required credential in the environment, use a new output directory, and pass the explicit prompt-review and joint-review confirmations described by `python3 experiments/run_case.py --help`. Hosted aliases may change after the frozen run, so exact regeneration is not guaranteed.

## Results retained in this artifact

- Backend screening: 960 SELECT executions across six hosted backends.
- Confirmatory matrix: 1,000 executions for RouteBR, B1 Direct, B2 Direct+Guard, state enforcement removal, and closed-grounding removal.
- Each public receipt retains the synthetic request payload, output content, token counts, reported model identity, retry events, and controller trace.
- Wall-clock timestamps, endpoint URLs, provider response IDs, system fingerprints, absolute paths, credentials, and process logs are removed.

## Data and provenance

The scenarios are not raw customer logs. They are privacy-preserving synthetic reconstructions informed by recurring confidential-request patterns at one real financial institution. The authors report that three engineers from that institution jointly reviewed the scenarios and labels for practice relevance. The release does not claim independent annotation, adjudication, or inter-annotator agreement. See `data/README.md` and `data/PROVENANCE.md`.

## License

This repository retains the project's existing MIT License. See `LICENSE`.
