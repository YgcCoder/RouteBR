from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from routebr.defaults import build_demo_context
from routebr.router import BoundaryAwareRouter
from routebr.types import UserRequest


def main() -> None:
    router = BoundaryAwareRouter()
    context = build_demo_context()

    requests = [
        "Is this technology fund still suitable for medium-term planning?",
        "I have been under pressure for a while. Can someone help me with this account?",
        "What about this semiconductor theme today?",
        "Can you help me handle the next step for this growth fund now?",
    ]

    for text in requests:
        trace = router.trace(UserRequest(text=text), context)
        payload = {
            "request": text,
            "cues": trace.cues.__dict__,
            "candidate_scores": trace.candidate_scores,
            "boundary_statuses": trace.boundary_statuses,
            "decision": {
                "action_id": trace.decision.action_id,
                "action_label": trace.decision.action_label,
                "boundary_status": trace.decision.boundary_status,
                "score": trace.decision.score,
                "reasons": trace.decision.reasons,
                "grounded_entity": (
                    None
                    if trace.decision.grounded_entity is None
                    else trace.decision.grounded_entity.__dict__
                ),
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("-" * 80)


if __name__ == "__main__":
    main()
