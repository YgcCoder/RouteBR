from __future__ import annotations

from .llm_interface import StructuredLLM
from .types import CueBundle, UserRequest


class LLMCueExtractor:
    """
    Optional cue extractor that delegates cue parsing to an injected model port.

    This file intentionally does not bind to any concrete model provider.
    """

    SYSTEM_PROMPT = (
        "You are a routing-cue extractor for a customer-facing financial service "
        "system. Extract whether the request contains advisory cues, action-"
        "sensitive cues, support-sensitive cues, ambiguous references, and loss "
        "pressure. Return strict JSON with keys: advisory, action_sensitive, "
        "support_sensitive, ambiguous_reference, loss_pressure, matched_phrases."
    )

    def __init__(self, llm: StructuredLLM) -> None:
        self.llm = llm

    def extract(self, request: UserRequest) -> CueBundle:
        payload = self.llm.generate_json(
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=request.text,
        )
        matched_phrases = payload.get("matched_phrases", [])
        if not isinstance(matched_phrases, list):
            matched_phrases = []

        return CueBundle(
            advisory=bool(payload.get("advisory", False)),
            action_sensitive=bool(payload.get("action_sensitive", False)),
            support_sensitive=bool(payload.get("support_sensitive", False)),
            ambiguous_reference=bool(payload.get("ambiguous_reference", False)),
            loss_pressure=bool(payload.get("loss_pressure", False)),
            matched_phrases=[str(item) for item in matched_phrases],
        )
