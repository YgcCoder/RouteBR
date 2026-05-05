from __future__ import annotations

from .types import EntityMatch, RouterContext, UserRequest


class EntityGrounder:
    def ground(self, request: UserRequest, context: RouterContext) -> EntityMatch | None:
        text = request.text.lower()
        best_match: EntityMatch | None = None

        for canonical_name, aliases in context.candidate_entities.items():
            for alias in aliases:
                if alias.lower() in text:
                    score = len(alias) / max(len(text), 1)
                    match = EntityMatch(
                        mention=alias,
                        canonical_id=canonical_name.lower().replace(" ", "_"),
                        canonical_name=canonical_name,
                        score=round(score, 4),
                    )
                    if best_match is None or match.score > best_match.score:
                        best_match = match

        return best_match
