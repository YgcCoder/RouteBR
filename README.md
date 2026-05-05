# RouteBR Framework

`RouteBR` is a de-identified code scaffold for the paper idea of **route before response** in boundary-sensitive financial service systems.

This repository contains:

- a minimal multi-stage routing pipeline
- example action and entity configuration
- a generic model integration port

This repository does **not** contain:

- proprietary prompts
- internal service identifiers
- raw user logs
- production policies
- internal evaluation data

## What The Framework Demonstrates

The scaffold follows the paper's high-level routing chain:

1. `routing-cue extraction`
2. `candidate narrowing`
3. `boundary evaluation`
4. `entity grounding`
5. `final dispatch`
6. `response-stage handoff to a bounded downstream path`

The framework is intentionally lightweight. It is meant to show system structure, control flow, and extensibility rather than to reproduce the proprietary production stack.

## Project Layout

```text
routebr_framework/
├── README.md
├── pyproject.toml
├── .gitignore
├── examples/
│   └── demo.py
└── src/
    └── routebr/
        ├── __init__.py
        ├── action_catalog.py
        ├── boundary_evaluator.py
        ├── candidate_narrowing.py
        ├── cue_extractor.py
        ├── defaults.py
        ├── dispatcher.py
        ├── entity_grounder.py
        ├── llm_cue_extractor.py
        ├── llm_interface.py
        ├── router.py
        └── types.py
├── resources/
│   └── paper_examples_zh.json
```

## Repository Scope

This repository is a structural research scaffold, not a turn-key production package.

It is intended to expose:

- the routing stages
- the component boundaries
- the model integration port
- representative paper resources

It is not intended to reproduce the proprietary deployment environment end to end.

## Where The Files Are

The scaffold lives under:

`/Users/moriflare/Desktop/quant/intern/routebr_framework`

Core code is under:

`/Users/moriflare/Desktop/quant/intern/routebr_framework/src/routebr`

Representative paper examples are stored as JSON content under:

`/Users/moriflare/Desktop/quant/intern/routebr_framework/resources/paper_examples_zh.json`

## How This Maps To The Paper

The repository is intentionally aligned with the paper structure:

- `cue_extractor.py` corresponds to `mixed-intent decomposition`
- `candidate_narrowing.py` corresponds to `candidate narrowing`
- `boundary_evaluator.py` corresponds to `boundary evaluation`
- `entity_grounder.py` corresponds to `entity grounding`
- `dispatcher.py` corresponds to `final dispatch`
- `router.py` corresponds to the end-to-end `pre-response routing layer`

The current code is a de-identified scaffold, not the proprietary production implementation. That means the control flow matches the paper, while prompts, policies, service identifiers, and data remain excluded.

## Model Integration Port

If you only want a provided model-access interface and do not want any model-specific code in the repository, use:

- `llm_interface.py` for the abstract model port
- `llm_cue_extractor.py` for an optional cue extractor built on top of that port

You only need to implement:

```python
from routebr import StructuredLLM


class MyModelGateway(StructuredLLM):
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        ...
```

Then inject it into the router:

```python
from routebr import BoundaryAwareRouter, LLMCueExtractor

gateway = MyModelGateway()
router = BoundaryAwareRouter(cue_extractor=LLMCueExtractor(gateway))
```

The main routing chain does not need to change.

## Core Concepts

### `Action`

The downstream service class that may be invoked, such as advisory, information lookup, human handoff, or protected action flow.

### `Object`

The product, topic, symbol, concept, or account-related entity referenced by the request.

### `Boundary`

The runtime control state that determines whether a candidate action is:

- allowed
- clarification-needed
- deferred
- handoff-only
- blocked

## Extending The Scaffold

You can replace any stage without changing the overall contract:

- replace `CueExtractor` with an LLM-backed structured extractor
- replace `CandidateNarrower` with embedding search or retrieval over a larger service catalog
- replace `BoundaryEvaluator` with policy-engine integration
- replace `EntityGrounder` with a knowledge base or alias resolver
- replace `Dispatcher` with a learned ranker or business-priority controller

## Suggested GitHub Positioning

If you publish this repository with the paper, describe it as:

> a de-identified research scaffold that mirrors the route-before-response control structure without exposing proprietary data or production policies

## License

Choose the license you want before publishing. No license file is included by default.
