from __future__ import annotations

from .types import ActionSpec, BoundaryDecision, CueBundle, EntityMatch, RouteDecision


class Dispatcher:
    def dispatch(
        self,
        candidates: list[tuple[ActionSpec, float]],
        boundary_decisions: dict[str, BoundaryDecision],
        cues: CueBundle,
        entity: EntityMatch | None,
    ) -> RouteDecision:
        scored_allowed: list[RouteDecision] = []
        candidate_ids = [action.action_id for action, _ in candidates]

        for action, score in candidates:
            boundary = boundary_decisions[action.action_id]
            adjusted = score

            if boundary.status == "allowed":
                adjusted += 0.5
            elif boundary.status == "handoff":
                adjusted += 0.2
            elif boundary.status == "clarification-needed":
                adjusted += 0.1
            else:
                continue

            if entity is None and action.action_id == "info_lookup":
                adjusted -= 0.3
            if cues.ambiguous_reference and action.action_id == "clarification_flow":
                adjusted += 0.6

            scored_allowed.append(
                RouteDecision(
                    action_id=action.action_id,
                    action_label=action.label,
                    boundary_status=boundary.status,
                    score=round(adjusted, 4),
                    reasons=list(boundary.reasons),
                    grounded_entity=entity,
                    candidate_ids=candidate_ids,
                )
            )

        if not scored_allowed:
            return RouteDecision(
                action_id="clarification_flow",
                action_label="Clarification Flow",
                boundary_status="clarification-needed",
                score=0.0,
                reasons=["no admissible candidates remained after boundary evaluation"],
                grounded_entity=entity,
                candidate_ids=candidate_ids,
            )

        scored_allowed.sort(key=lambda item: item.score, reverse=True)
        return scored_allowed[0]
