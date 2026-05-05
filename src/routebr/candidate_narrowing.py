from __future__ import annotations

from .types import ActionSpec, CueBundle, UserRequest


class CandidateNarrower:
    def __init__(self, top_k: int = 3) -> None:
        self.top_k = top_k

    def shortlist(
        self,
        request: UserRequest,
        cues: CueBundle,
        action_catalog: list[ActionSpec],
    ) -> list[tuple[ActionSpec, float]]:
        text = request.text.lower()
        scored: list[tuple[ActionSpec, float]] = []

        for action in action_catalog:
            score = 0.0
            for keyword in action.keywords:
                if keyword in text:
                    score += 1.0

            if action.action_id == "support_handoff" and (cues.support_sensitive or cues.loss_pressure):
                score += 1.5
            if action.action_id == "protected_action_flow" and cues.action_sensitive:
                score += 1.5
            if action.action_id == "advisory_service" and cues.advisory:
                score += 1.2
            if action.action_id == "clarification_flow" and cues.ambiguous_reference:
                score += 1.3

            if score > 0:
                scored.append((action, score))

        if not scored:
            fallback = next(a for a in action_catalog if a.action_id == "clarification_flow")
            return [(fallback, 1.0)]

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[: self.top_k]
