from __future__ import annotations

from dataclasses import dataclass

from .action_catalog import build_default_action_catalog
from .boundary_evaluator import BoundaryEvaluator
from .candidate_narrowing import CandidateNarrower
from .cue_extractor import CueExtractor
from .dispatcher import Dispatcher
from .entity_grounder import EntityGrounder
from .types import RouteDecision, RouterContext, UserRequest


@dataclass
class RouteTrace:
    cues: object
    candidate_scores: list[tuple[str, float]]
    boundary_statuses: dict[str, str]
    decision: RouteDecision


class BoundaryAwareRouter:
    def __init__(
        self,
        cue_extractor=None,
        candidate_narrower=None,
        boundary_evaluator=None,
        entity_grounder=None,
        dispatcher=None,
    ) -> None:
        self.action_catalog = build_default_action_catalog()
        self.cue_extractor = cue_extractor or CueExtractor()
        self.candidate_narrower = candidate_narrower or CandidateNarrower()
        self.boundary_evaluator = boundary_evaluator or BoundaryEvaluator()
        self.entity_grounder = entity_grounder or EntityGrounder()
        self.dispatcher = dispatcher or Dispatcher()

    def route(self, request: UserRequest, context: RouterContext) -> RouteDecision:
        return self.trace(request, context).decision

    def trace(self, request: UserRequest, context: RouterContext) -> RouteTrace:
        cues = self.cue_extractor.extract(request)
        candidates = self.candidate_narrower.shortlist(request, cues, self.action_catalog)
        boundaries = {
            action.action_id: self.boundary_evaluator.evaluate(action, context, cues)
            for action, _ in candidates
        }
        entity = self.entity_grounder.ground(request, context)
        decision = self.dispatcher.dispatch(candidates, boundaries, cues, entity)
        return RouteTrace(
            cues=cues,
            candidate_scores=[(action.action_id, score) for action, score in candidates],
            boundary_statuses={key: value.status for key, value in boundaries.items()},
            decision=decision,
        )
