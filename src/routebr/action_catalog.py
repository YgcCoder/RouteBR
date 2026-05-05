from __future__ import annotations

from .types import ActionSpec


def build_default_action_catalog() -> list[ActionSpec]:
    return [
        ActionSpec(
            action_id="advisory_service",
            label="Advisory Service",
            description="General recommendation-oriented or analysis-oriented downstream path.",
            keywords=["suitable", "direction", "analysis", "allocation", "plan", "advice"],
        ),
        ActionSpec(
            action_id="info_lookup",
            label="Information Lookup",
            description="Card or topic lookup for products, sectors, concepts, or market information.",
            keywords=["why", "theme", "concept", "today", "news", "weak", "strong"],
        ),
        ActionSpec(
            action_id="account_analysis",
            label="Account Analysis",
            description="Account, watchlist, or holdings-related downstream service.",
            keywords=["position", "holding", "portfolio", "my account", "watchlist"],
        ),
        ActionSpec(
            action_id="support_handoff",
            label="Support Handoff",
            description="Support-oriented or human-support entry path.",
            keywords=["human", "support", "stress", "loss", "help me", "advisor"],
            handoff_only=True,
        ),
        ActionSpec(
            action_id="protected_action_flow",
            label="Protected Action Flow",
            description="Action-sensitive or execution-related protected path.",
            keywords=["buy", "sell", "redeem", "handle now", "next step", "set order", "execute"],
            allowed_risk_levels=["balanced", "aggressive"],
            requires_agreement=True,
            requires_service_relationship=True,
            protected_action=True,
        ),
        ActionSpec(
            action_id="clarification_flow",
            label="Clarification Flow",
            description="Fallback clarification path when references or intent remain unresolved.",
            keywords=["this one", "that one", "what about this", "which one"],
            clarification_only=True,
        ),
    ]
