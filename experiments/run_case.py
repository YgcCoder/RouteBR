#!/usr/bin/env python3
"""Resume-safe API runner for RouteBR, two baselines, and two ablations.

Dry-run mode performs no network calls. Result-bearing non-DEV runs require
either populated independent-adjudication fields or explicit confirmation that
the frozen labels were jointly reviewed by three engineers. The manifest
records the actual review basis and never converts collaborative review into an
inter-rater agreement claim.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from routebr import (  # noqa: E402
    Boundary,
    CatalogEntry,
    Controller,
    EntityCandidate,
    OpenAICompatibleBackend,
    PolicyEngine,
    RouteRequest,
    Rule,
)
from routebr.backend import _urlopen_transport  # noqa: E402


PREDICTION_FIELDS = [
    "case_id",
    "system_id",
    "repeat_id",
    "pred_action",
    "pred_object_id",
    "pred_boundary",
    "pred_final_path",
    "topk_json",
    "valid_json",
    "retry_count",
    "fallback_used",
    "input_tokens",
    "output_tokens",
    "latency_ms",
    "estimated_cost_usd",
    "error_code",
    "raw_output_path",
]

SYSTEM_TO_PROMPT = {
    "b1_direct": "B1_DIRECT",
    "b2_direct_guard": "B2_DIRECT_GUARD",
}

ROUTEBR_SYSTEMS = {"routebr", "a_state", "a_ground"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def parse_json_field(row: dict[str, str], field: str) -> Any:
    try:
        return json.loads(row[field])
    except (KeyError, json.JSONDecodeError) as exc:
        raise ValueError(f"{row.get('case_id', 'UNKNOWN')}: invalid {field}") from exc


def load_catalog(path: Path) -> list[CatalogEntry]:
    entries = []
    for row in read_csv(path):
        required = tuple(item for item in row["required_object_types"].split("|") if item)
        entries.append(
            CatalogEntry(
                action_id=row["action_id"],
                service_name=row["service_name"],
                description=row["description"],
                required_object_types=required,
            )
        )
    return entries


def load_policy(path: Path) -> PolicyEngine:
    rules = []
    for row in read_csv(path):
        rules.append(
            Rule(
                rule_id=row["rule_id"],
                priority=int(row["priority"]),
                applies_to=tuple(row["applies_to"].split("|")),
                condition=json.loads(row["condition_json"]),
                decision=Boundary(row["decision"]),
                version=row.get("version", "v1"),
            )
        )
    return PolicyEngine(rules)


def make_request(row: dict[str, str]) -> RouteRequest:
    candidates = parse_json_field(row, "candidate_entities_json")
    entities = tuple(
        EntityCandidate(
            object_id=item["object_id"],
            object_type=item["object_type"],
            display_name=item["display_name"],
            aliases=tuple(item.get("aliases", [])),
        )
        for item in candidates
    )
    return RouteRequest(
        request_id=row["case_id"],
        utterance=row["utterance"],
        history=tuple(parse_json_field(row, "history_json")),
        runtime_context=parse_json_field(row, "runtime_context_json"),
        entity_candidates=entities,
    )


def catalog_payload(catalog: list[CatalogEntry]) -> list[dict[str, Any]]:
    return [
        {
            "action_id": item.action_id,
            "service_name": item.service_name,
            "description": item.description,
            "required_object_types": item.required_object_types,
        }
        for item in catalog
    ]


def rules_payload(policy: PolicyEngine) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": rule.rule_id,
            "priority": rule.priority,
            "applies_to": rule.applies_to,
            "condition": rule.condition,
            "decision": rule.decision.value,
            "version": rule.version,
        }
        for rule in policy.rules
    ]


def is_independently_adjudicated(row: dict[str, str]) -> bool:
    required = (
        "annotator_1_action",
        "annotator_1_object_id",
        "annotator_1_boundary",
        "annotator_2_action",
        "annotator_2_object_id",
        "annotator_2_boundary",
        "adjudicated_by",
    )
    return all(row.get(field, "").strip() for field in required)


class RetryingTransport:
    """Retry transient transport failures without exposing credentials."""

    TRANSIENT_HTTP = {408, 409, 429, 500, 502, 503, 504}

    def __init__(self, max_retries: int, backoff_seconds: float) -> None:
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.retry_total = 0
        self.events: list[dict[str, Any]] = []

    def __call__(
        self,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                return _urlopen_transport(url, headers, body, timeout)
            except HTTPError as exc:
                retryable = exc.code in self.TRANSIENT_HTTP
                reason = f"HTTP_{exc.code}"
                error: Exception = exc
            except (URLError, TimeoutError, OSError) as exc:
                retryable = True
                reason = type(exc).__name__
                error = exc
            if not retryable or attempt >= self.max_retries:
                raise RuntimeError(f"API transport failed after {attempt} retries: {reason}") from error
            delay = self.backoff_seconds * (2**attempt)
            self.retry_total += 1
            self.events.append({"attempt": attempt + 1, "reason": reason, "delay_seconds": delay})
            time.sleep(delay)
        raise AssertionError("unreachable retry loop")


def parse_object(raw: Any) -> tuple[dict[str, Any] | None, list[str]]:
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


def complete_validated(
    backend: OpenAICompatibleBackend,
    stage: str,
    payload: dict[str, Any],
    validator: Callable[[dict[str, Any]], list[str]],
) -> tuple[dict[str, Any] | None, bool, int, list[str]]:
    raw = backend.complete(stage, payload)
    parsed, errors = parse_object(raw)
    if parsed is not None:
        errors.extend(validator(parsed))
    if parsed is not None and not errors:
        return parsed, True, 0, []
    repaired_raw = backend.complete(
        f"REPAIR_{stage}",
        {
            "invalid_output": raw,
            "validation_errors": errors,
            "constraint": "format-only repair",
            "original_payload": payload,
        },
    )
    repaired, repaired_errors = parse_object(repaired_raw)
    if repaired is not None:
        repaired_errors.extend(validator(repaired))
    if repaired is not None and not repaired_errors:
        return repaired, True, 1, errors
    return None, False, 1, errors + repaired_errors


def token_totals(responses: list[dict[str, Any]]) -> tuple[int, int]:
    input_tokens = 0
    output_tokens = 0
    for response in responses:
        usage = response.get("usage") or {}
        input_tokens += int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
        output_tokens += int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
    return input_tokens, output_tokens


def direct_validator(
    output: dict[str, Any],
    catalog_ids: set[str],
    entity_ids: set[str],
    rule_ids: set[str],
    require_rules: bool,
) -> list[str]:
    errors: list[str] = []
    terminals = {"DISPATCH", "CLARIFY", "DEFER", "HANDOFF", "REJECT"}
    boundaries = {"ALLOW", "CLARIFY", "DEFER", "HANDOFF", "REJECT"}
    if output.get("terminal") not in terminals:
        errors.append("invalid terminal")
    if output.get("boundary") not in boundaries:
        errors.append("invalid boundary")
    if output.get("action_id") not in catalog_ids:
        errors.append("action_id is outside the catalog")
    object_id = output.get("object_id")
    if object_id not in entity_ids | {"NONE", "UNRESOLVED"}:
        errors.append("object_id is outside the entity list")
    topk = output.get("topk")
    if not isinstance(topk, list) or not 1 <= len(topk) <= 3:
        errors.append("topk must contain one to three action IDs")
    elif len(topk) != len(set(topk)) or any(item not in catalog_ids for item in topk):
        errors.append("topk contains duplicate or unknown IDs")
    elif output.get("action_id") != topk[0]:
        errors.append("action_id must equal topk[0]")
    if output.get("terminal") == "DISPATCH" and output.get("boundary") != "ALLOW":
        errors.append("DISPATCH requires ALLOW")
    if output.get("boundary") != "ALLOW" and output.get("terminal") != output.get("boundary"):
        errors.append("non-ALLOW terminal must equal boundary")
    if require_rules:
        cited = output.get("rule_ids")
        if not isinstance(cited, list) or not cited or any(item not in rule_ids for item in cited):
            errors.append("rule_ids must cite known rules")
    return errors


def run_case(
    *,
    system: str,
    row: dict[str, str],
    backend: OpenAICompatibleBackend,
    catalog: list[CatalogEntry],
    policy: PolicyEngine,
    transport: RetryingTransport,
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = make_request(row)
    before_calls = len(backend.calls)
    before_responses = len(backend.responses)
    before_retries = transport.retry_total
    started = time.perf_counter()
    error_code = ""

    if system in ROUTEBR_SYSTEMS:
        result = Controller(
            backend,
            catalog,
            policy,
            enforce_state=system != "a_state",
            enable_grounding=system != "a_ground",
        ).route(request)
        topk: list[str] = []
        object_id = result.object_id
        for trace in result.traces:
            if trace.stage == "ROUTEBR" and trace.accepted_output:
                topk = list(trace.accepted_output.get("topk", []))
        semantic_action = result.action_id
        terminal = result.terminal
        boundary = "ALLOW" if terminal == "DISPATCH" else terminal
        valid_json = all(trace.valid for trace in result.traces)
        repair_count = sum(trace.repaired for trace in result.traces)
        fallback = any(code.startswith("FAIL_CLOSED_") for code in result.reason_codes)
        if fallback:
            error_code = result.reason_codes[0]
        summary = {
            "pred_action": semantic_action,
            "pred_object_id": object_id,
            "pred_boundary": boundary,
            "pred_final_path": result.action_id if terminal == "DISPATCH" else f"T_{terminal}",
            "topk": topk,
            "valid_json": valid_json,
            "repair_count": repair_count,
            "fallback_used": fallback,
            "controller_result": result.as_dict(),
        }
    else:
        prompt_stage = SYSTEM_TO_PROMPT[system]
        entity_payload = [item.__dict__ for item in request.entity_candidates]
        payload: dict[str, Any] = {
            "request": request.utterance,
            "history": request.history,
            "runtime_context": request.runtime_context,
            "catalog": catalog_payload(catalog),
            "entities": entity_payload,
        }
        catalog_ids = {item.action_id for item in catalog}
        entity_ids = {item.object_id for item in request.entity_candidates}
        rule_ids = {item.rule_id for item in policy.rules}
        if system == "b2_direct_guard":
            payload["rules"] = rules_payload(policy)
        require_rules = system == "b2_direct_guard"
        output, valid_json, repair_count, validation_errors = complete_validated(
            backend,
            prompt_stage,
            payload,
            lambda value: direct_validator(value, catalog_ids, entity_ids, rule_ids, require_rules),
        )
        if output is None:
            semantic_action = "NONE"
            object_id = "NONE"
            topk = []
            boundary = "CLARIFY"
            terminal = "CLARIFY"
            fallback = True
            error_code = f"FAIL_CLOSED_{prompt_stage}"
        else:
            semantic_action = output["action_id"]
            object_id = output["object_id"]
            topk = output["topk"]
            boundary = output["boundary"]
            terminal = output["terminal"]
            fallback = False
        summary = {
            "pred_action": semantic_action,
            "pred_object_id": object_id,
            "pred_boundary": boundary,
            "pred_final_path": semantic_action if terminal == "DISPATCH" else f"T_{terminal}",
            "topk": topk,
            "valid_json": valid_json,
            "repair_count": repair_count,
            "fallback_used": fallback,
            "baseline_output": output,
            "validation_errors": validation_errors,
        }

    latency_ms = (time.perf_counter() - started) * 1000
    case_calls = backend.calls[before_calls:]
    case_responses = backend.responses[before_responses:]
    input_tokens, output_tokens = token_totals(case_responses)
    reported_models = sorted(
        {item.get("reported_model") for item in case_responses if item.get("reported_model")}
    )
    receipt = {
        "case_id": row["case_id"],
        "system": system,
        "calls": case_calls,
        "responses": case_responses,
        "reported_models": reported_models,
        "transport_retries": transport.events[-(transport.retry_total - before_retries) :]
        if transport.retry_total > before_retries
        else [],
        "summary": summary,
    }
    prediction = {
        "case_id": row["case_id"],
        "pred_action": summary["pred_action"],
        "pred_object_id": summary["pred_object_id"],
        "pred_boundary": summary["pred_boundary"],
        "pred_final_path": summary["pred_final_path"],
        "topk_json": json.dumps(summary["topk"], ensure_ascii=False, separators=(",", ":")),
        "valid_json": str(summary["valid_json"]).lower(),
        "retry_count": transport.retry_total - before_retries,
        "fallback_used": str(summary["fallback_used"]).lower(),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": f"{latency_ms:.3f}",
        "estimated_cost_usd": "",
        "error_code": error_code,
    }
    return prediction, receipt


def append_prediction(path: Path, row: dict[str, Any]) -> None:
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=PREDICTION_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profiles",
        type=Path,
        default=ROOT / "experiments/api_profiles.json",
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument(
        "--prompts",
        type=Path,
        default=ROOT / "experiments/prompts.json",
    )
    parser.add_argument("--cases", type=Path, default=ROOT / "data/routebr_600.csv")
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog.csv")
    parser.add_argument("--rules", type=Path, default=ROOT / "data/boundary_rules.csv")
    parser.add_argument("--system", choices=[*sorted(ROUTEBR_SYSTEMS), *SYSTEM_TO_PROMPT], required=True)
    parser.add_argument("--split", choices=["DEV", "MAIN", "FLIP", "ENTITY"], default="DEV")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--repeat-id", default="0")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--sealed-predictions-only",
        action="store_true",
        help="permit blind non-DEV prediction generation before adjudication; never implies score eligibility",
    )
    parser.add_argument("--confirm-author-reviewed-prompts", action="store_true")
    parser.add_argument("--confirm-three-engineer-joint-review", action="store_true")
    parser.add_argument("--allow-provisional-profile", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-backoff", type=float, default=1.0)
    args = parser.parse_args()

    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit must be positive")
    profiles = json.loads(args.profiles.read_text(encoding="utf-8"))
    if args.profile not in profiles:
        raise SystemExit(f"unknown profile: {args.profile}")
    profile = profiles[args.profile]
    if "{" in profile["base_url"] or "}" in profile["base_url"]:
        raise SystemExit("profile base_url contains an unresolved placeholder")

    prompt_doc = json.loads(args.prompts.read_text(encoding="utf-8"))
    stage_instructions = {key: value for key, value in prompt_doc.items() if key != "metadata"}
    required_prompts = (
        {"ROUTEBR", "REPAIR"}
        if args.system in ROUTEBR_SYSTEMS
        else {SYSTEM_TO_PROMPT[args.system], "REPAIR"}
    )
    missing_prompts = sorted(required_prompts - set(stage_instructions))
    if missing_prompts:
        raise SystemExit(f"missing prompts: {', '.join(missing_prompts)}")

    rows = [row for row in read_csv(args.cases) if row.get("split") == args.split]
    if args.case_id:
        selected_ids = set(args.case_id)
        rows = [row for row in rows if row["case_id"] in selected_ids]
        missing_ids = sorted(selected_ids - {row["case_id"] for row in rows})
        if missing_ids:
            raise SystemExit(f"case IDs not found in split {args.split}: {', '.join(missing_ids)}")
    rows.sort(key=lambda row: row["case_id"])
    if args.limit is not None:
        rows = rows[: args.limit]
    if not rows:
        raise SystemExit("no cases selected")

    independent_gate = all(is_independently_adjudicated(row) for row in rows)
    joint_review_gate = args.split != "DEV" and args.confirm_three_engineer_joint_review
    annotation_gate = args.split == "DEV" or independent_gate or joint_review_gate
    sealed_unscored = args.split != "DEV" and not annotation_gate and args.sealed_predictions_only
    if not args.dry_run and not annotation_gate and not sealed_unscored:
        raise SystemExit(
            "non-DEV result-bearing run refused: neither independent adjudication fields nor the "
            "explicit three-engineer joint-review confirmation is present"
        )
    if not args.dry_run and not args.confirm_author_reviewed_prompts:
        raise SystemExit("paid run refused: pass --confirm-author-reviewed-prompts after author review")
    if not profile.get("formal_result_eligible", False) and not args.allow_provisional_profile and not args.dry_run:
        raise SystemExit("provisional proxy profile refused; preflight it and pass --allow-provisional-profile for DEV smoke only")
    if not profile.get("formal_result_eligible", False) and args.split != "DEV" and not args.dry_run:
        raise SystemExit("provisional proxy profiles are restricted to DEV")

    manifest = {
        "dry_run": args.dry_run,
        "profile_name": args.profile,
        "provider": profile["provider"],
        "requested_model": profile["model"],
        "accepted_reported_models": profile.get("accepted_reported_models", [profile["model"]]),
        "formal_result_eligible_in_config": bool(profile.get("formal_result_eligible", False)),
        "system": args.system,
        "split": args.split,
        "repeat_id": args.repeat_id,
        "case_ids": [row["case_id"] for row in rows],
        "annotation_gate_passed": annotation_gate,
        "label_review_basis": (
            "DEV_ONLY"
            if args.split == "DEV"
            else "INDEPENDENT_ADJUDICATION_FIELDS"
            if independent_gate
            else "AUTHOR_CONFIRMED_THREE_ENGINEER_JOINT_REVIEW"
            if joint_review_gate
            else "INCOMPLETE"
        ),
        "sealed_predictions_only": sealed_unscored,
        "score_eligible": annotation_gate and args.split != "DEV",
        "evidence_status": (
            "SEALED_UNSCORED_PENDING_ADJUDICATION"
            if sealed_unscored
            else "DEV_DIAGNOSTIC"
            if args.split == "DEV"
            else "JOINTLY_REVIEWED_RESULT_BEARING"
            if joint_review_gate and not independent_gate
            else "ADJUDICATED_RESULT_BEARING"
        ),
        "gold_fields_passed_to_model": False,
        "prompt_status": prompt_doc.get("metadata", {}).get("status"),
        "hashes": {
            "profiles": sha256(args.profiles),
            "prompts": sha256(args.prompts),
            "cases": sha256(args.cases),
            "catalog": sha256(args.catalog),
            "rules": sha256(args.rules),
            "runner": sha256(Path(__file__)),
            "controller": sha256(ROOT / "03_artifact/routebr/controller.py"),
        },
        "timeout_seconds": args.timeout,
        "max_retries": args.max_retries,
        "retry_backoff_seconds": args.retry_backoff,
        "concurrency": 1,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0

    key_env = profile["api_key_env"]
    api_key = os.environ.get(key_env, "")
    if not api_key:
        raise SystemExit(f"credential environment variable is unset: {key_env}")

    catalog = load_catalog(args.catalog)
    policy = load_policy(args.rules)
    transport = RetryingTransport(args.max_retries, args.retry_backoff)
    backend = OpenAICompatibleBackend(
        provider=profile["provider"],
        base_url=profile["base_url"],
        api_key=api_key,
        model=profile["model"],
        stage_instructions=stage_instructions,
        request_options=profile.get("request_options", {}),
        timeout_seconds=args.timeout,
        transport=transport,
    )

    predictions_path = args.output_dir / "predictions.csv"
    raw_dir = args.output_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    completed: set[tuple[str, str, str]] = set()
    if predictions_path.exists():
        if not args.resume:
            raise SystemExit("predictions.csv already exists; use a new output directory or --resume")
        completed = {
            (item["case_id"], item["system_id"], item["repeat_id"])
            for item in read_csv(predictions_path)
        }

    for index, row in enumerate(rows, start=1):
        key = (row["case_id"], args.system, args.repeat_id)
        if key in completed:
            print(f"skip {row['case_id']} (already complete)")
            continue
        prediction, receipt = run_case(
            system=args.system,
            row=row,
            backend=backend,
            catalog=catalog,
            policy=policy,
            transport=transport,
        )
        reported = receipt["reported_models"]
        accepted_reported = set(profile.get("accepted_reported_models", [profile["model"]]))
        if profile.get("formal_result_eligible", False) and reported and any(
            item not in accepted_reported for item in reported
        ):
            receipt["model_identity_error"] = {
                "requested": profile["model"],
                "reported": reported,
                "accepted_reported_models": sorted(accepted_reported),
            }
        raw_path = raw_dir / f"{row['case_id']}.json"
        raw_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        prediction.update(
            {
                "system_id": args.system,
                "repeat_id": args.repeat_id,
                "raw_output_path": str(raw_path.relative_to(args.output_dir)),
            }
        )
        append_prediction(predictions_path, prediction)
        print(f"[{index}/{len(rows)}] {row['case_id']} -> {prediction['pred_final_path']}")
        if receipt.get("model_identity_error"):
            raise SystemExit("reported model ID differs from the frozen formal profile; run stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
