from __future__ import annotations

import unittest

from routebr import (
    Boundary,
    CatalogEntry,
    Controller,
    EntityCandidate,
    PolicyEngine,
    ReplayBackend,
    RouteRequest,
    Rule,
)


def catalog() -> list[CatalogEntry]:
    return [
        CatalogEntry("A1_ADVISORY", "Advisory", "Advisory response", ("PRODUCT",)),
        CatalogEntry("A4_SUPPORT_RESPONSE", "Support", "Support response", ("NONE",)),
    ]


def policy() -> PolicyEngine:
    return PolicyEngine(
        [
            Rule("R001", 10, ("*",), {"safety_escalation_required": True}, Boundary.HANDOFF),
            Rule("R002", 20, ("A1_ADVISORY",), {"entity_resolved": False}, Boundary.CLARIFY),
            Rule("R999", 999, ("*",), {}, Boundary.ALLOW),
        ]
    )


def request(**context_overrides) -> RouteRequest:
    context = {"safety_escalation_required": False, "entity_resolved": True}
    context.update(context_overrides)
    return RouteRequest(
        request_id="T001",
        utterance="Please explain Product Alpha and tell me where support is",
        history=(),
        runtime_context=context,
        entity_candidates=(EntityCandidate("P_ALPHA", "PRODUCT", "Product Alpha"),),
    )


def proposal(
    action_id: str = "A1_ADVISORY",
    object_id: str = "P_ALPHA",
    topk: list[str] | None = None,
) -> dict[str, object]:
    return {
        "action_id": action_id,
        "object_id": object_id,
        "topk": topk or [action_id, "A4_SUPPORT_RESPONSE"],
    }


class RouteBRControllerTest(unittest.TestCase):
    def test_primary_allow_dispatches(self) -> None:
        backend = ReplayBackend({"ROUTEBR": [proposal()]})
        result = Controller(backend, catalog(), policy()).route(request())
        self.assertTrue(result.dispatched)
        self.assertEqual(result.action_id, "A1_ADVISORY")
        self.assertEqual(result.object_id, "P_ALPHA")
        self.assertEqual([stage for stage, _ in backend.calls], ["ROUTEBR"])

    def test_blocked_primary_cannot_promote_allowed_secondary(self) -> None:
        backend = ReplayBackend({"ROUTEBR": [proposal()]})
        result = Controller(backend, catalog(), policy()).route(
            request(safety_escalation_required=True)
        )
        self.assertEqual(result.terminal, "HANDOFF")
        self.assertEqual(result.action_id, "A1_ADVISORY")
        self.assertNotEqual(result.action_id, "A4_SUPPORT_RESPONSE")
        self.assertTrue(result.traces[0].policy_overrides[0]["primary_committed"])

    def test_unresolved_primary_object_clarifies(self) -> None:
        backend = ReplayBackend({"ROUTEBR": [proposal(object_id="UNRESOLVED")]})
        result = Controller(backend, catalog(), policy()).route(request())
        self.assertEqual(result.terminal, "CLARIFY")
        self.assertEqual(result.reason_codes, ["PRIMARY_OBJECT_UNRESOLVED"])

    def test_closed_entity_validation_fails_closed_after_repair(self) -> None:
        invalid = proposal(object_id="OUTSIDE")
        backend = ReplayBackend({"ROUTEBR": [invalid], "REPAIR_ROUTEBR": [invalid]})
        result = Controller(backend, catalog(), policy()).route(request())
        self.assertEqual(result.terminal, "CLARIFY")
        self.assertEqual(result.reason_codes, ["FAIL_CLOSED_ROUTEBR"])
        self.assertFalse(result.traces[0].valid)

    def test_state_ablation_ignores_blocking_rule(self) -> None:
        backend = ReplayBackend({"ROUTEBR": [proposal()]})
        result = Controller(
            backend,
            catalog(),
            policy(),
            enforce_state=False,
        ).route(request(safety_escalation_required=True))
        self.assertTrue(result.dispatched)
        self.assertFalse(result.traces[0].policy_overrides[0]["applied"])

    def test_grounding_ablation_forces_bounded_terminal(self) -> None:
        backend = ReplayBackend({"ROUTEBR": [proposal()]})
        result = Controller(
            backend,
            catalog(),
            policy(),
            enable_grounding=False,
        ).route(request())
        self.assertEqual(result.terminal, "CLARIFY")
        self.assertEqual(result.object_id, "UNRESOLVED")

    def test_object_free_action_requires_none(self) -> None:
        backend = ReplayBackend(
            {"ROUTEBR": [proposal("A4_SUPPORT_RESPONSE", "NONE", ["A4_SUPPORT_RESPONSE"])]}
        )
        result = Controller(backend, catalog(), policy()).route(request())
        self.assertTrue(result.dispatched)
        self.assertEqual(result.object_id, "NONE")


if __name__ == "__main__":
    unittest.main()
