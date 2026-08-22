#!/usr/bin/env python3
"""Validate the RouteBR benchmark before any model run.

The script is intentionally read-only. It prints validation errors, split
statistics, review-mode status, and SHA-256 hashes; it never edits the dataset.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


EXPECTED_SPLITS = {"DEV": 120, "MAIN": 300, "FLIP": 120, "ENTITY": 60}
ACTION_LABELS = {
    "A1_ADVISORY",
    "A2_INFO_LOOKUP",
    "A3_ACCOUNT_ANALYSIS",
    "A4_SUPPORT_RESPONSE",
    "A5_PROTECTED_ACTION",
}
BOUNDARY_LABELS = {"ALLOW", "CLARIFY", "DEFER", "HANDOFF", "REJECT"}
OBJECT_DIFFICULTIES = {"NONE", "EXPLICIT_NAME", "CODE_ONLY", "ANAPHORA", "UNDERSPECIFIED", "CONFLICTING"}
JSON_FIELDS = {
    "history_json",
    "runtime_context_json",
    "candidate_entities_json",
    "gold_cues_json",
    "gold_rule_ids_json",
}
REQUIRED_FIELDS = {
    "case_id",
    "split",
    "scenario_cell",
    "utterance",
    "runtime_context_json",
    "candidate_entities_json",
    "gold_cues_json",
    "gold_action",
    "gold_object_difficulty",
    "gold_boundary",
    "gold_final_path",
    "gold_rule_ids_json",
}
FINAL_REVIEW_FIELDS = {
    "annotator_1_action",
    "annotator_1_boundary",
    "annotator_2_action",
    "annotator_2_boundary",
    "adjudicated_by",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--entities", type=Path, help="versioned real-entity catalog")
    parser.add_argument(
        "--review-mode",
        choices=("joint", "independent"),
        default="joint",
        help="joint practitioner review (default) or completed independent annotation",
    )
    parser.add_argument(
        "--allow-draft",
        action="store_true",
        help="deprecated alias that skips independent-annotation requirements",
    )
    args = parser.parse_args()

    errors: list[str] = []
    cases = read_csv(args.cases)
    catalog = read_csv(args.catalog)
    rules = read_csv(args.rules)
    entities = read_csv(args.entities) if args.entities else []

    catalog_ids = {row.get("action_id", "") for row in catalog}
    rule_ids = {row.get("rule_id", "") for row in rules}
    if catalog_ids != ACTION_LABELS:
        errors.append(f"catalog action IDs differ from frozen ontology: {sorted(catalog_ids)}")
    if not rule_ids:
        errors.append("boundary rule table is empty")
    entity_ids = {row.get("object_id", "") for row in entities}
    if args.entities and (len(entities) != 40 or len(entity_ids) != 40):
        errors.append("entity catalog must contain 40 unique object IDs")
    for entity in entities:
        if not re.fullmatch(r"(?:SSE|SZSE):\d{6}", entity.get("object_id", "")):
            errors.append(f"invalid real-entity object_id {entity.get('object_id', '')!r}")
        if not re.fullmatch(r"\d{6}", entity.get("security_code", "")):
            errors.append(f"invalid entity security_code {entity.get('security_code', '')!r}")
        for field in ("exchange", "official_short_name", "source_url", "source_effective_date", "verified_on"):
            if not entity.get(field, "").strip():
                errors.append(f"entity {entity.get('object_id', '')!r}: missing {field}")

    seen_ids: set[str] = set()
    split_counts: Counter[str] = Counter()
    normalized_by_split: dict[str, set[str]] = defaultdict(set)
    flip_pairs: dict[str, list[dict[str, str]]] = defaultdict(list)
    action_counts: Counter[str] = Counter()
    boundary_counts: Counter[str] = Counter()
    object_counts: Counter[str] = Counter()
    action_disagreements = 0
    boundary_disagreements = 0
    object_disagreements = 0

    for row_number, row in enumerate(cases, start=2):
        prefix = f"row {row_number}"
        independent_review = args.review_mode == "independent" and not args.allow_draft
        required = REQUIRED_FIELDS | FINAL_REVIEW_FIELDS if independent_review else REQUIRED_FIELDS
        missing = sorted(name for name in required if not row.get(name, "").strip())
        if missing:
            errors.append(f"{prefix}: missing required values {missing}")

        case_id = row.get("case_id", "").strip()
        if case_id in seen_ids:
            errors.append(f"{prefix}: duplicate case_id {case_id!r}")
        seen_ids.add(case_id)

        split = row.get("split", "").strip().upper()
        split_counts[split] += 1
        if split not in EXPECTED_SPLITS:
            errors.append(f"{prefix}: invalid split {split!r}")

        action = row.get("gold_action", "").strip()
        boundary = row.get("gold_boundary", "").strip()
        object_type = row.get("gold_object_difficulty", "").strip()
        action_counts[action] += 1
        boundary_counts[boundary] += 1
        object_counts[object_type] += 1
        if action not in ACTION_LABELS or action not in catalog_ids:
            errors.append(f"{prefix}: invalid gold_action {action!r}")
        if boundary not in BOUNDARY_LABELS:
            errors.append(f"{prefix}: invalid gold_boundary {boundary!r}")
        if object_type not in OBJECT_DIFFICULTIES:
            errors.append(f"{prefix}: invalid gold_object_difficulty {object_type!r}")

        for field in JSON_FIELDS:
            value = row.get(field, "").strip()
            if not value:
                continue
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                errors.append(f"{prefix}: {field} is invalid JSON ({exc.msg})")
                continue
            if field == "gold_rule_ids_json" and isinstance(parsed, list):
                unknown = sorted(set(parsed) - rule_ids)
                if unknown:
                    errors.append(f"{prefix}: unknown boundary rule IDs {unknown}")
            if field == "candidate_entities_json" and isinstance(parsed, list) and args.entities:
                cited_ids = {item.get("object_id", "") for item in parsed if isinstance(item, dict)}
                unknown_entities = sorted(cited_ids - entity_ids)
                if unknown_entities:
                    errors.append(f"{prefix}: unknown candidate entity IDs {unknown_entities}")

        gold_object_id = row.get("gold_object_id", "").strip()
        if args.entities and gold_object_id not in {"NONE", "UNRESOLVED"} and gold_object_id not in entity_ids:
            errors.append(f"{prefix}: gold object absent from entity catalog {gold_object_id!r}")

        try:
            history_items = json.loads(row.get("history_json", "[]"))
            normalized_history = "\n".join(history_items)
        except (json.JSONDecodeError, TypeError):
            history_items = []
            normalized_history = ""
        if object_type == "ANAPHORA" and not history_items:
            errors.append(f"{prefix}: anaphora case lacks dialogue history")
        if object_type == "CODE_ONLY" and gold_object_id not in {"NONE", "UNRESOLVED"}:
            expected_code = gold_object_id.split(":", 1)[-1]
            if expected_code not in row.get("utterance", ""):
                errors.append(f"{prefix}: code-only case omits {expected_code}")
        normalized_utterance = normalize(normalized_history + "\n" + row.get("utterance", ""))
        if split != "FLIP":
            if normalized_utterance in normalized_by_split[split]:
                errors.append(f"{prefix}: duplicate normalized utterance within {split}")
            normalized_by_split[split].add(normalized_utterance)
        else:
            pair_id = row.get("pair_id", "").strip()
            if not pair_id:
                errors.append(f"{prefix}: FLIP row lacks pair_id")
            flip_pairs[pair_id].append(row)

        if row.get("annotator_1_action") and row.get("annotator_2_action") and row.get("annotator_1_action") != row.get("annotator_2_action"):
            action_disagreements += 1
        if row.get("annotator_1_boundary") and row.get("annotator_2_boundary") and row.get("annotator_1_boundary") != row.get("annotator_2_boundary"):
            boundary_disagreements += 1
        if row.get("annotator_1_object_id") and row.get("annotator_2_object_id") and row.get("annotator_1_object_id") != row.get("annotator_2_object_id"):
            object_disagreements += 1

    for split, expected in EXPECTED_SPLITS.items():
        actual = split_counts.get(split, 0)
        if actual != expected:
            errors.append(f"split {split}: expected {expected}, found {actual}")

    protected = ["DEV", "MAIN", "ENTITY"]
    for index, left in enumerate(protected):
        for right in protected[index + 1 :]:
            overlap = normalized_by_split[left] & normalized_by_split[right]
            if overlap:
                errors.append(f"normalized utterance overlap between {left} and {right}: {len(overlap)}")

    for pair_id, rows in flip_pairs.items():
        if len(rows) != 2:
            errors.append(f"FLIP pair {pair_id!r}: expected 2 rows, found {len(rows)}")
            continue
        if (
            normalize(rows[0].get("history_json", "") + rows[0].get("utterance", ""))
            != normalize(rows[1].get("history_json", "") + rows[1].get("utterance", ""))
        ):
            errors.append(f"FLIP pair {pair_id!r}: request histories or utterances differ")
        if rows[0].get("runtime_context_json") == rows[1].get("runtime_context_json"):
            errors.append(f"FLIP pair {pair_id!r}: runtime contexts are identical")
        boundaries = {rows[0].get("gold_boundary"), rows[1].get("gold_boundary")}
        if len(boundaries) != 2 or "ALLOW" not in boundaries:
            errors.append(f"FLIP pair {pair_id!r}: requires exactly one ALLOW and one different decision")

    print("RouteBR dataset validation")
    print(f"cases: {len(cases)}")
    print(f"splits: {dict(sorted(split_counts.items()))}")
    print(f"actions: {dict(sorted(action_counts.items()))}")
    print(f"boundaries: {dict(sorted(boundary_counts.items()))}")
    print(f"object difficulty: {dict(sorted(object_counts.items()))}")
    if args.review_mode == "independent" and not args.allow_draft:
        print("review_mode: independent annotation")
        print(
            "pre-adjudication disagreements: "
            f"action={action_disagreements}, boundary={boundary_disagreements}, object={object_disagreements}"
        )
    else:
        print("review_mode: joint practitioner review")
        print("independent-annotation agreement: not applicable")
    print(f"cases_sha256: {sha256(args.cases)}")
    print(f"catalog_sha256: {sha256(args.catalog)}")
    print(f"rules_sha256: {sha256(args.rules)}")
    if args.entities:
        print(f"entities_sha256: {sha256(args.entities)}")

    if errors:
        print(f"\nFAILED with {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("\nPASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
