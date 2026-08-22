"""Backend protocol, deterministic replay, and hosted-API adapter."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any, Callable, Mapping, Protocol
from urllib.request import Request, urlopen


class PromptBackend(Protocol):
    def complete(self, stage: str, payload: dict[str, Any]) -> Any:
        """Return a JSON object or JSON string for one controller stage."""


class ReplayBackend:
    """Return preloaded outputs by stage for deterministic tests and dry runs."""

    def __init__(self, outputs: dict[str, list[Any]]) -> None:
        self.outputs = defaultdict(deque)
        for stage, values in outputs.items():
            self.outputs[stage].extend(values)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def complete(self, stage: str, payload: dict[str, Any]) -> Any:
        self.calls.append((stage, payload))
        if not self.outputs[stage]:
            raise RuntimeError(f"no replay output remaining for stage {stage}")
        return self.outputs[stage].popleft()


Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


def _urlopen_transport(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError("API response must be a JSON object")
    return decoded


class OpenAICompatibleBackend:
    """Minimal Chat Completions adapter shared by the confirmed API panel.

    The adapter performs no provider-specific semantic prompting. Callers pass
    frozen stage instructions and provider request options explicitly. API keys
    are used only in the authorization header and are never retained in logs.
    """

    RESERVED_OPTIONS = {"model", "messages", "stream"}

    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        stage_instructions: Mapping[str, str | Callable[[dict[str, Any]], str]],
        request_options: Mapping[str, Any] | None = None,
        timeout_seconds: float = 60.0,
        transport: Transport = _urlopen_transport,
    ) -> None:
        if not api_key:
            raise ValueError("api_key cannot be empty")
        if not stage_instructions:
            raise ValueError("stage_instructions cannot be empty")
        options = dict(request_options or {})
        forbidden = self.RESERVED_OPTIONS.intersection(options)
        if forbidden:
            raise ValueError(f"reserved request options: {sorted(forbidden)}")
        self.provider = provider
        self.url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self.model = model
        self.stage_instructions: dict[str, str | Callable[[dict[str, Any]], str]] = dict(stage_instructions)
        self.request_options = options
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.calls: list[dict[str, Any]] = []
        self.responses: list[dict[str, Any]] = []

    def _instruction(self, stage: str, payload: dict[str, Any]) -> str:
        if stage in self.stage_instructions:
            instruction = self.stage_instructions[stage]
            return instruction(payload) if callable(instruction) else instruction
        if stage.startswith("REPAIR_"):
            if "REPAIR" in self.stage_instructions:
                instruction = self.stage_instructions["REPAIR"]
                return instruction(payload) if callable(instruction) else instruction
            original = stage.removeprefix("REPAIR_")
            if original in self.stage_instructions:
                instruction = self.stage_instructions[original]
                base = instruction(payload) if callable(instruction) else instruction
                return (
                    base
                    + "\nRepair formatting only. Preserve the supplied evidence and IDs; return one JSON object."
                )
        raise KeyError(f"no frozen instruction for stage {stage}")

    def complete(self, stage: str, payload: dict[str, Any]) -> Any:
        request_body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._instruction(stage, payload)},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                },
            ],
            "stream": False,
            "response_format": {"type": "json_object"},
            **self.request_options,
        }
        self.calls.append(
            {
                "provider": self.provider,
                "model": self.model,
                "stage": stage,
                "url": self.url,
                "request_body": request_body,
            }
        )
        response = self.transport(
            self.url,
            {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            request_body,
            self.timeout_seconds,
        )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("API response lacks choices[0].message.content") from exc
        self.responses.append(
            {
                "provider": self.provider,
                "requested_model": self.model,
                "reported_model": response.get("model"),
                "response_id": response.get("id"),
                "usage": response.get("usage"),
                "stage": stage,
                "raw_response": response,
            }
        )
        return content
