# RouteBR Framework

`RouteBR` is a de-identified companion repository for the paper idea of **route before response** in boundary-sensitive financial service systems.

The paper studies a production routing problem in customer-facing financial services: a mixed-intent request may look answerable in natural language while still being sent to an inadmissible downstream service path. The repository mirrors that control structure with a lightweight, publishable scaffold.

## What This Repository Contains

- a minimal multi-stage routing pipeline
- example action and entity configuration
- a generic model integration port
- representative paper examples in resource form

## What This Repository Does Not Contain

- proprietary prompts
- internal service identifiers
- raw user logs
- production policies
- internal evaluation data
- the full proprietary deployment stack

## Relation To The Paper

The paper argues that, in high-stakes customer-facing financial systems, route selection should happen before response generation. This repository reflects that architecture through the following routing chain:

1. `routing-cue extraction`
2. `candidate narrowing`
3. `boundary evaluation`
4. `entity grounding`
5. `final dispatch`
6. `bounded downstream handoff before response generation`

This repository is therefore a **runnable research scaffold**, not a turn-key production package and not an end-to-end reproduction of the proprietary deployment environment.

## Repository Structure

```text
routebr_framework/
├── README.md
├── pyproject.toml
├── .gitignore
├── examples/
│   └── demo.py
├── resources/
│   └── paper_examples_zh.json
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
```

## Mapping From Code To Paper

- `cue_extractor.py` corresponds to `mixed-intent decomposition`
- `candidate_narrowing.py` corresponds to `candidate narrowing`
- `boundary_evaluator.py` corresponds to `boundary evaluation`
- `entity_grounder.py` corresponds to `entity grounding`
- `dispatcher.py` corresponds to `final dispatch`
- `router.py` corresponds to the end-to-end `pre-response routing layer`

The control flow aligns with the paper, while sensitive prompts, deployment rules, production identifiers, and internal datasets remain excluded.

## Model Integration Port

This repository does not bind to any specific model provider. If you want to connect your own model gateway, use:

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

The rest of the routing chain does not need to change.

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

## Scope And Limitations

This repository is intended to support:

- structural inspection of the routing architecture
- component replacement and local experimentation
- understanding of how the paper's control stages fit together

It is not intended to:

- reproduce the paper's proprietary production deployment
- reproduce internal evaluation data or exact industrial metrics
- serve as a drop-in financial production system

## Resources

Representative mixed-intent Chinese publication examples are stored in:

- `resources/paper_examples_zh.json`

These examples are de-identified and generalized. They are not raw user logs.

## Suggested GitHub Positioning

If you publish this repository with the paper, describe it as:

> a de-identified companion scaffold that mirrors the route-before-response control structure without exposing proprietary data, prompts, or production policies

## License

MIT License
