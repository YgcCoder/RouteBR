from __future__ import annotations

from .action_catalog import build_default_action_catalog
from .types import RouterContext


def build_demo_context() -> RouterContext:
    return RouterContext(
        user_id="demo-user",
        risk_level="balanced",
        agreements_signed=True,
        support_requested=False,
        service_relationship=True,
        candidate_entities={
            "Growth Technology Fund": ["technology fund", "growth fund"],
            "Semiconductor Theme": ["semiconductor", "chip theme"],
            "Alpha Brokerage Account": ["my account", "account"],
        },
    )


def build_demo_catalog():
    return build_default_action_catalog()
