from __future__ import annotations

from .types import ActionSpec, BoundaryDecision, CueBundle, RouterContext


class BoundaryEvaluator:
    def evaluate(
        self,
        action: ActionSpec,
        context: RouterContext,
        cues: CueBundle,
    ) -> BoundaryDecision:
        reasons: list[str] = []

        if action.clarification_only:
            return BoundaryDecision(action_id=action.action_id, status="clarification-needed")

        if action.handoff_only and (context.support_requested or cues.support_sensitive or cues.loss_pressure):
            reasons.append("support-sensitive request")
            return BoundaryDecision(action_id=action.action_id, status="handoff")

        if action.requires_agreement and not context.agreements_signed:
            reasons.append("required agreement missing")
            return BoundaryDecision(action_id=action.action_id, status="blocked", reasons=reasons)

        if action.requires_service_relationship and not context.service_relationship:
            reasons.append("required service relationship missing")
            return BoundaryDecision(action_id=action.action_id, status="blocked", reasons=reasons)

        if action.allowed_risk_levels and context.risk_level not in action.allowed_risk_levels:
            reasons.append("risk level not eligible")
            return BoundaryDecision(action_id=action.action_id, status="blocked", reasons=reasons)

        if action.protected_action and cues.support_sensitive:
            reasons.append("support-sensitive language conflicts with protected action")
            return BoundaryDecision(action_id=action.action_id, status="handoff", reasons=reasons)

        return BoundaryDecision(action_id=action.action_id, status="allowed", reasons=reasons)
