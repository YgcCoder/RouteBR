"""Deterministic boundary-rule evaluation."""

from __future__ import annotations

from typing import Any

from .models import Boundary, Rule


class PolicyEngine:
    def __init__(self, rules: list[Rule]) -> None:
        self.rules = sorted(rules, key=lambda item: (item.priority, item.rule_id))
        if not self.rules:
            raise ValueError("at least one boundary rule is required")
        ids = [rule.rule_id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("boundary rule IDs must be unique")

    @staticmethod
    def _matches(condition: dict[str, Any], runtime_context: dict[str, Any]) -> bool:
        return all(runtime_context.get(key) == value for key, value in condition.items())

    def evaluate(self, action_id: str, runtime_context: dict[str, Any]) -> tuple[Boundary, str]:
        for rule in self.rules:
            applies = "*" in rule.applies_to or action_id in rule.applies_to
            if applies and self._matches(rule.condition, runtime_context):
                return rule.decision, rule.rule_id
        raise ValueError(f"no boundary rule matched action {action_id}; add an explicit default rule")
