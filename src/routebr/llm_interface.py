from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class StructuredLLM(ABC):
    """
    Generic model integration port.

    Repository users can implement this interface with their own gateway,
    SDK wrapper, or internal model service without changing the routing stack.
    """

    @abstractmethod
    def generate_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        Return a structured JSON-like dictionary for the given prompts.
        """
        raise NotImplementedError
