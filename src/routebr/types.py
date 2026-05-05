from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class UserRequest:
    text: str
    context: Dict[str, str] = field(default_factory=dict)


@dataclass
class RouterContext:
    user_id: Optional[str] = None
    risk_level: Optional[str] = None
    agreements_signed: bool = False
    support_requested: bool = False
    service_relationship: bool = False
    candidate_entities: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class CueBundle:
    advisory: bool = False
    action_sensitive: bool = False
    support_sensitive: bool = False
    ambiguous_reference: bool = False
    loss_pressure: bool = False
    tokens: List[str] = field(default_factory=list)
    matched_phrases: List[str] = field(default_factory=list)


@dataclass
class ActionSpec:
    action_id: str
    label: str
    description: str
    keywords: List[str]
    allowed_risk_levels: List[str] = field(default_factory=list)
    requires_agreement: bool = False
    requires_service_relationship: bool = False
    handoff_only: bool = False
    clarification_only: bool = False
    protected_action: bool = False


@dataclass
class BoundaryDecision:
    action_id: str
    status: str
    reasons: List[str] = field(default_factory=list)


@dataclass
class EntityMatch:
    mention: str
    canonical_id: str
    canonical_name: str
    score: float


@dataclass
class RouteDecision:
    action_id: str
    action_label: str
    boundary_status: str
    score: float
    reasons: List[str] = field(default_factory=list)
    grounded_entity: Optional[EntityMatch] = None
    candidate_ids: List[str] = field(default_factory=list)
