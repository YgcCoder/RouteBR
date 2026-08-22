"""RouteBR: compact fail-closed routing with primary-route commitment."""

from __future__ import annotations

import json
from typing import Any, Callable

from .backend import PromptBackend
from .models import CatalogEntry, RouteRequest, RouteResult, StageTrace, Terminal
from .policy import PolicyEngine


Validator = Callable[[dict[str, Any]], list[str]]


class Controller:
    """Validate one semantic proposal and let code own the transition.

    The model proposes a primary action, a diagnostic top-k, and a closed-list
    object. Code validates the contract, evaluates the versioned policy for the
    primary action only, and emits a dispatch or bounded terminal. Lower-ranked
    candidates can never replace a blocked primary action.
    """

    def __init__(
        self,
        backend: PromptBackend,
        catalog: list[CatalogEntry],
        policy: PolicyEngine,
        fallback_terminal: Terminal = Terminal.CLARIFY,
        *,
        enforce_state: bool = True,
        enable_grounding: bool = True,
    ) -> None:
        self.backend = backend
        self.catalog = {entry.action_id: entry for entry in catalog}
        self.policy = policy
        self.fallback_terminal = fallback_terminal
        self.enforce_state = enforce_state
        self.enable_grounding = enable_grounding
        if not self.catalog:
            raise ValueError("catalog cannot be empty")
        if fallback_terminal is Terminal.DISPATCH:
            raise ValueError("fail-closed fallback cannot be DISPATCH")

    @staticmethod
    def _parse(raw: Any) -> tuple[dict[str, Any] | None, list[str]]:
        if isinstance(raw, dict):
            return raw, []
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                return None, [f"invalid JSON: {exc.msg}"]
            if isinstance(parsed, dict):
                return parsed, []
        return None, ["output must be one JSON object"]

    def _stage(
        self,
        stage: str,
        payload: dict[str, Any],
        validator: Validator,
        traces: list[StageTrace],
    ) -> dict[str, Any] | None:
        raw = self.backend.complete(stage, payload)
        parsed, errors = self._parse(raw)
        if parsed is not None:
            errors.extend(validator(parsed))
        if parsed is not None and not errors:
            traces.append(StageTrace(stage=stage, valid=True, raw_output=raw, accepted_output=parsed))
            return parsed

        repair_payload = {
            "invalid_output": raw,
            "validation_errors": errors,
            "constraint": "format-only repair; preserve semantic choice and closed IDs",
            "original_stage": stage,
            "original_payload": payload,
        }
        repaired_raw = self.backend.complete(f"REPAIR_{stage}", repair_payload)
        repaired, repaired_errors = self._parse(repaired_raw)
        if repaired is not None:
            repaired_errors.extend(validator(repaired))
        if repaired is not None and not repaired_errors:
            traces.append(
                StageTrace(
                    stage=stage,
                    valid=True,
                    repaired=True,
                    validation_errors=errors,
                    raw_output=raw,
                    accepted_output=repaired,
                )
            )
            return repaired
        traces.append(
            StageTrace(
                stage=stage,
                valid=False,
                repaired=True,
                validation_errors=errors + repaired_errors,
                raw_output=raw,
            )
        )
        return None

    def _fallback(self, request: RouteRequest, traces: list[StageTrace]) -> RouteResult:
        return RouteResult(
            request_id=request.request_id,
            terminal=self.fallback_terminal.value,
            reason_codes=["FAIL_CLOSED_ROUTEBR"],
            traces=traces,
        )

    def route(self, request: RouteRequest) -> RouteResult:
        traces: list[StageTrace] = []
        entities_by_id = {item.object_id: item for item in request.entity_candidates}
        entity_ids = set(entities_by_id)

        def validate_route(output: dict[str, Any]) -> list[str]:
            errors: list[str] = []
            action_id = output.get("action_id")
            if action_id not in self.catalog:
                errors.append("action_id is outside the closed catalog")

            topk = output.get("topk")
            if not isinstance(topk, list) or not 1 <= len(topk) <= 3:
                errors.append("topk must contain one to three action IDs")
            elif (
                len(topk) != len(set(topk))
                or any(item not in self.catalog for item in topk)
                or (action_id in self.catalog and topk[0] != action_id)
            ):
                errors.append("topk must be unique, closed-list, and primary-first")

            object_id = output.get("object_id")
            if action_id in self.catalog:
                entry = self.catalog[action_id]
                if entry.requires_object:
                    if object_id not in entity_ids | {"UNRESOLVED"}:
                        errors.append("object_id is outside the closed entity list")
                    elif object_id in entities_by_id and (
                        entities_by_id[object_id].object_type not in entry.required_object_types
                    ):
                        errors.append("object type violates the primary action contract")
                elif object_id != "NONE":
                    errors.append("object-free primary action must use NONE")
            return errors

        proposal = self._stage(
            "ROUTEBR",
            {
                "request": request.utterance,
                "history": request.history,
                "catalog": [entry.__dict__ for entry in self.catalog.values()],
                "entities": [entity.__dict__ for entity in request.entity_candidates],
                "contract": {
                    "primary_action_only": True,
                    "lower_ranked_candidates_are_diagnostic_only": True,
                    "object_ids_are_closed_list": True,
                },
            },
            validate_route,
            traces,
        )
        if proposal is None:
            return self._fallback(request, traces)

        action_id = proposal["action_id"]
        object_id = proposal["object_id"]
        boundary, rule_id = self.policy.evaluate(action_id, request.runtime_context)
        traces[-1].policy_overrides = [
            {
                "action_id": action_id,
                "enforced_boundary": boundary.value,
                "rule_id": rule_id,
                "applied": self.enforce_state,
                "primary_committed": True,
            }
        ]

        if self.enforce_state and boundary.value != "ALLOW":
            return RouteResult(
                request_id=request.request_id,
                terminal=boundary.value,
                action_id=action_id,
                object_id=object_id,
                reason_codes=["PRIMARY_BOUNDARY_TERMINAL", rule_id],
                traces=traces,
            )

        entry = self.catalog[action_id]
        if entry.requires_object:
            if not self.enable_grounding:
                object_id = "UNRESOLVED"
            if object_id == "UNRESOLVED":
                return RouteResult(
                    request_id=request.request_id,
                    terminal=Terminal.CLARIFY.value,
                    action_id=action_id,
                    object_id="UNRESOLVED",
                    reason_codes=["PRIMARY_OBJECT_UNRESOLVED"],
                    traces=traces,
                )

        return RouteResult(
            request_id=request.request_id,
            terminal=Terminal.DISPATCH.value,
            action_id=action_id,
            object_id=object_id,
            reason_codes=["PRIMARY_BOUNDARY_OK", rule_id],
            traces=traces,
        )
