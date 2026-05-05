from __future__ import annotations

import re

from .types import CueBundle, UserRequest


class CueExtractor:
    advisory_terms = {"advice", "suitable", "direction", "analysis", "allocation", "plan"}
    action_terms = {"buy", "sell", "redeem", "execute", "handle", "order", "next step"}
    support_terms = {"stress", "loss", "anxious", "panic", "human", "support"}
    ambiguity_patterns = (
        r"\bthis one\b",
        r"\bthat one\b",
        r"\bwhat about this\b",
        r"\bwhat about that\b",
    )

    def extract(self, request: UserRequest) -> CueBundle:
        text = request.text.lower()
        tokens = re.findall(r"[a-zA-Z]+", text)
        matched_phrases: list[str] = []

        def hit_terms(terms: set[str]) -> bool:
            hits = sorted(term for term in terms if term in text)
            matched_phrases.extend(hits)
            return bool(hits)

        ambiguous_reference = any(re.search(pattern, text) for pattern in self.ambiguity_patterns)
        if ambiguous_reference:
            matched_phrases.append("ambiguous_reference")

        loss_pressure = "loss" in text or "losing" in text or "under pressure" in text
        if loss_pressure:
            matched_phrases.append("loss_pressure")

        return CueBundle(
            advisory=hit_terms(self.advisory_terms),
            action_sensitive=hit_terms(self.action_terms),
            support_sensitive=hit_terms(self.support_terms),
            ambiguous_reference=ambiguous_reference,
            loss_pressure=loss_pressure,
            tokens=tokens,
            matched_phrases=matched_phrases,
        )
