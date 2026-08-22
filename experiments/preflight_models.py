#!/usr/bin/env python3
"""Validate API profiles and optionally archive a read-only model-list receipt."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def load_profiles(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        parsed = json.load(stream)
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError("profile file must contain a non-empty JSON object")
    return parsed


def validate_profile(name: str, profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("provider", "base_url", "api_key_env", "model", "request_options"):
        if field not in profile:
            errors.append(f"missing {field}")
    base_url = profile.get("base_url")
    if not isinstance(base_url, str) or not base_url.startswith("https://"):
        errors.append("base_url must be an HTTPS URL")
    elif "{" in base_url or "}" in base_url:
        errors.append("base_url still contains an unresolved placeholder")
    key_env = profile.get("api_key_env")
    if not isinstance(key_env, str) or not key_env:
        errors.append("api_key_env must be a non-empty environment-variable name")
    model = profile.get("model")
    if not isinstance(model, str) or not model:
        errors.append("model must be a non-empty string")
    if errors:
        errors = [f"{name}: {error}" for error in errors]
    return errors


def fetch_models(profile: dict[str, Any], timeout: float) -> tuple[list[str], dict[str, Any]]:
    key_env = profile["api_key_env"]
    api_key = os.environ.get(key_env, "")
    if not api_key:
        raise RuntimeError(f"credential environment variable is unset: {key_env}")
    url = f"{profile['base_url'].rstrip('/')}/models"
    request = Request(url, headers={"Authorization": f"Bearer {api_key}"}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"GET /models returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"GET /models failed: {exc.reason}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("GET /models response is not a JSON object")
    items = payload.get("data")
    if not isinstance(items, list):
        raise RuntimeError("GET /models response lacks a data list")
    model_ids = sorted(
        item["id"] for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)
    )
    return model_ids, {"http_status": status, "response_object": payload.get("object")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--profile", action="append", dest="selected")
    parser.add_argument("--no-network", action="store_true")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    profiles = load_profiles(args.profiles)
    selected = args.selected or list(profiles)
    unknown = sorted(set(selected) - set(profiles))
    if unknown:
        raise SystemExit(f"unknown profiles: {', '.join(unknown)}")

    receipt: dict[str, Any] = {
        "profile_file": args.profiles.name,
        "network_enabled": not args.no_network,
        "profiles": {},
    }
    any_failure = False
    for name in selected:
        profile = profiles[name]
        errors = validate_profile(name, profile)
        entry: dict[str, Any] = {
            "provider": profile.get("provider"),
            "base_url": profile.get("base_url"),
            "requested_model": profile.get("model"),
            "api_key_env": profile.get("api_key_env"),
            "credential_present": bool(os.environ.get(profile.get("api_key_env", ""))),
            "formal_result_eligible_in_config": bool(profile.get("formal_result_eligible", False)),
            "profile_valid": not errors,
            "validation_errors": errors,
        }
        if errors:
            any_failure = True
        elif args.no_network:
            entry["model_list_status"] = "SKIPPED_NO_NETWORK"
        else:
            try:
                model_ids, response_meta = fetch_models(profile, args.timeout)
                entry["model_list_status"] = "OK"
                entry["selected_model_present"] = profile["model"] in model_ids
                entry["available_model_ids"] = model_ids
                entry.update(response_meta)
                if not entry["selected_model_present"]:
                    any_failure = True
            except RuntimeError as exc:
                entry["model_list_status"] = "FAILED"
                entry["error"] = str(exc)
                any_failure = True
        receipt["profiles"][name] = entry

    rendered = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(rendered + "\n", encoding="utf-8")
    return 1 if any_failure else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"preflight error: {exc}", file=sys.stderr)
        raise SystemExit(2)
