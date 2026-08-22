"""Typed records for the RouteBR controller."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Boundary(str, Enum):
    ALLOW = "ALLOW"
    CLARIFY = "CLARIFY"
    DEFER = "DEFER"
    HANDOFF = "HANDOFF"
    REJECT = "REJECT"


class Terminal(str, Enum):
    DISPATCH = "DISPATCH"
    CLARIFY = "CLARIFY"
    DEFER = "DEFER"
    HANDOFF = "HANDOFF"
    REJECT = "REJECT"


@dataclass(frozen=True)
class CatalogEntry:
    action_id: str
    service_name: str
    description: str
    required_object_types: tuple[str, ...] = ()

    @property
    def requires_object(self) -> bool:
        return bool(self.required_object_types) and "NONE" not in self.required_object_types


@dataclass(frozen=True)
class EntityCandidate:
    object_id: str
    object_type: str
    display_name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rule:
    rule_id: str
    priority: int
    applies_to: tuple[str, ...]
    condition: dict[str, Any]
    decision: Boundary
    version: str = "v1"


@dataclass(frozen=True)
class RouteRequest:
    request_id: str
    utterance: str
    history: tuple[str, ...]
    runtime_context: dict[str, Any]
    entity_candidates: tuple[EntityCandidate, ...]


@dataclass
class StageTrace:
    stage: str
    valid: bool
    repaired: bool = False
    validation_errors: list[str] = field(default_factory=list)
    raw_output: Any = None
    accepted_output: dict[str, Any] | None = None
    policy_overrides: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RouteResult:
    request_id: str
    terminal: str
    action_id: str = "NONE"
    object_id: str = "NONE"
    reason_codes: list[str] = field(default_factory=list)
    traces: list[StageTrace] = field(default_factory=list)

    @property
    def dispatched(self) -> bool:
        return self.terminal == Terminal.DISPATCH.value

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "terminal": self.terminal,
            "action_id": self.action_id,
            "object_id": self.object_id,
            "reason_codes": list(self.reason_codes),
            "traces": [
                {
                    "stage": trace.stage,
                    "valid": trace.valid,
                    "repaired": trace.repaired,
                    "validation_errors": list(trace.validation_errors),
                    "policy_overrides": list(trace.policy_overrides),
                }
                for trace in self.traces
            ],
        }
