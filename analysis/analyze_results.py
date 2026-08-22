#!/usr/bin/env python3
"""Audit and score the final single-method RouteBR rerun."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "experiments/results"
SELECT_CSV = ROOT / "data/routebr_select_160.csv"
CONFIRM_CSV = ROOT / "data/routebr_confirm_320.csv"
OUT_DIR = ROOT / "analysis/results"

PROFILE_LABELS = {
    "deepseek_v4_primary": "DeepSeek V4 Pro",
    "deepseek_v4_flash_efficiency": "DeepSeek V4 Flash",
    "ohmygpt_gpt4o_historical": "GPT-4o",
    "ohmygpt_gpt52_frontier": "GPT-5.2",
    "qwencloud_qwen38max_robustness": "Qwen3.8 Max",
    "qwencloud_qwen37plus_robustness": "Qwen3.7 Plus",
}
EXPECTED_MODELS = {
    "deepseek_v4_primary": {"deepseek-v4-pro"},
    "deepseek_v4_flash_efficiency": {"deepseek-v4-flash"},
    "ohmygpt_gpt4o_historical": {"gpt-4o-2024-11-20"},
    "ohmygpt_gpt52_frontier": {"gpt-5.2", "gpt-5.2-2025-12-11"},
    "qwencloud_qwen38max_robustness": {"qwen3.8-max"},
    "qwencloud_qwen37plus_robustness": {"qwen3.7-plus"},
}
SYSTEM_LABELS = {
    "routebr": "RouteBR",
    "b1_direct": "B1 Direct",
    "b2_direct_guard": "B2 Direct+Guard",
    "a_state": "RouteBR w/o state enforcement",
    "a_ground": "RouteBR w/o closed grounding",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def macro_f1(gold: list[str], pred: list[str]) -> float:
    labels = sorted(set(gold) | set(pred))
    scores: list[Fraction] = []
    for label in labels:
        tp = sum(g == label and p == label for g, p in zip(gold, pred))
        fp = sum(g != label and p == label for g, p in zip(gold, pred))
        fn = sum(g == label and p != label for g, p in zip(gold, pred))
        denominator = 2 * tp + fp + fn
        scores.append(Fraction(2 * tp, denominator) if denominator else Fraction(0, 1))
    # Compute from exact integer counts so supported Python versions serialize
    # the same float instead of differing in an irrelevant last binary digit.
    return float(sum(scores, Fraction(0, 1)) / len(scores)) if scores else 0.0


def wilson(success: int, total: int) -> list[float]:
    if total == 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = success / total
    den = 1 + z * z / total
    center = (p + z * z / (2 * total)) / den
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / den
    return [center - margin, center + margin]


def mcnemar_exact(a_correct: dict[str, bool], b_correct: dict[str, bool]) -> dict[str, Any]:
    keys = sorted(set(a_correct) & set(b_correct))
    b = sum(a_correct[k] and not b_correct[k] for k in keys)
    c = sum(not a_correct[k] and b_correct[k] for k in keys)
    n = b + c
    if n == 0:
        p = 1.0
    else:
        tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / (2**n)
        p = min(1.0, 2 * tail)
    return {"a_only_correct": b, "b_only_correct": c, "discordant": n, "p_two_sided": p}


def load_task(path: Path, gold_rows: dict[str, dict[str, str]]) -> dict[str, Any]:
    predictions_path = path / "predictions.csv"
    manifest_path = path / "run_manifest.json"
    predictions = read_csv(predictions_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_id = {row["case_id"]: row for row in predictions}
    raw_paths = sorted((path / "raw").glob("*.json"))
    reported: set[str] = set()
    calls = 0
    leakage_hits: list[str] = []
    for raw_path in raw_paths:
        receipt = json.loads(raw_path.read_text(encoding="utf-8"))
        reported.update(receipt.get("reported_models", []))
        calls += len(receipt.get("calls", []))
        for call in receipt.get("calls", []):
            body = json.dumps(call.get("request_body", {}), ensure_ascii=False)
            if any(token in body for token in ('"gold_', 'annotator_', 'adjudicated_by')):
                leakage_hits.append(f"{raw_path.name}:{call.get('stage')}")
    expected_ids = {case_id for case_id, row in gold_rows.items() if row["split"] == manifest["split"]}
    actual_ids = set(by_id)
    if actual_ids != expected_ids:
        raise RuntimeError(
            f"{path}: case mismatch missing={sorted(expected_ids-actual_ids)} extra={sorted(actual_ids-expected_ids)}"
        )
    if len(raw_paths) != len(predictions):
        raise RuntimeError(f"{path}: raw receipt count differs from prediction count")
    if leakage_hits:
        raise RuntimeError(f"{path}: gold-field leakage in calls: {leakage_hits}")
    profile = manifest["profile_name"]
    if reported and not reported <= EXPECTED_MODELS[profile]:
        raise RuntimeError(f"{path}: unexpected reported models {sorted(reported)}")
    return {
        "path": path,
        "manifest": manifest,
        "predictions": predictions,
        "by_id": by_id,
        "reported_models": sorted(reported),
        "calls": calls,
        "raw_receipts": len(raw_paths),
    }


def score(rows: list[dict[str, str]], gold_rows: dict[str, dict[str, str]]) -> dict[str, Any]:
    gold = [gold_rows[row["case_id"]] for row in rows]
    gold_path = [item["gold_final_path"] for item in gold]
    pred_path = [item["pred_final_path"] for item in rows]
    correct = [g == p for g, p in zip(gold_path, pred_path)]
    gold_dispatch = [not item.startswith("T_") for item in gold_path]
    pred_dispatch = [not item.startswith("T_") for item in pred_path]
    non_dispatch_n = sum(not item for item in gold_dispatch)
    dispatch_n = sum(gold_dispatch)
    false_dispatch = sum((not g) and p for g, p in zip(gold_dispatch, pred_dispatch))
    false_block = sum(g and (not p) for g, p in zip(gold_dispatch, pred_dispatch))
    valid_json = sum(item["valid_json"].lower() == "true" for item in rows)
    fallback = sum(item["fallback_used"].lower() == "true" for item in rows)
    tokens = [int(item["input_tokens"] or 0) + int(item["output_tokens"] or 0) for item in rows]
    latency = [float(item["latency_ms"] or 0) for item in rows]
    result = {
        "n": len(rows),
        "contract_exact": sum(correct),
        "contract_exact_rate": sum(correct) / len(rows),
        "contract_exact_wilson95": wilson(sum(correct), len(rows)),
        "path_macro_f1": macro_f1(gold_path, pred_path),
        "action_accuracy": sum(p["pred_action"] == g["gold_action"] for p, g in zip(rows, gold)) / len(rows),
        "object_accuracy": sum(p["pred_object_id"] == g["gold_object_id"] for p, g in zip(rows, gold)) / len(rows),
        "boundary_accuracy": sum(p["pred_boundary"] == g["gold_boundary"] for p, g in zip(rows, gold)) / len(rows),
        "false_dispatch": false_dispatch,
        "false_dispatch_denominator": non_dispatch_n,
        "false_dispatch_rate": false_dispatch / non_dispatch_n if non_dispatch_n else 0.0,
        "false_block": false_block,
        "false_block_denominator": dispatch_n,
        "false_block_rate": false_block / dispatch_n if dispatch_n else 0.0,
        "valid_json": valid_json,
        "valid_json_rate": valid_json / len(rows),
        "fallback": fallback,
        "fallback_rate": fallback / len(rows),
        "tokens_per_case_mean": statistics.mean(tokens),
        "latency_ms_median": statistics.median(latency),
        "correct_by_case": {row["case_id"]: ok for row, ok in zip(rows, correct)},
    }
    return result


def flip_pairs(rows: list[dict[str, str]], gold_rows: dict[str, dict[str, str]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[gold_rows[row["case_id"]]["pair_id"]].append(row)
    if any(len(items) != 2 for items in grouped.values()):
        raise RuntimeError("FLIP packet contains an incomplete pair")
    pair_correct = {
        pair_id: all(item["pred_final_path"] == gold_rows[item["case_id"]]["gold_final_path"] for item in items)
        for pair_id, items in grouped.items()
    }
    return {
        "pairs": len(pair_correct),
        "pair_exact": sum(pair_correct.values()),
        "pair_exact_rate": sum(pair_correct.values()) / len(pair_correct),
        "pair_exact_wilson95": wilson(sum(pair_correct.values()), len(pair_correct)),
        "correct_by_pair": pair_correct,
    }


def pct(value: float) -> str:
    return f"{100*value:.1f}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-six", action="store_true")
    args = parser.parse_args()
    select_rows = read_csv(SELECT_CSV)
    confirm_rows = read_csv(CONFIRM_CSV)
    select_gold = {row["case_id"]: row for row in select_rows}
    confirm_gold = {row["case_id"]: row for row in confirm_rows}

    audit: dict[str, Any] = {"select": {}, "confirm": {}}
    screening: dict[str, Any] = {}
    for profile, label in PROFILE_LABELS.items():
        base = RUN_ROOT / "select" / profile
        if not base.exists():
            continue
        all_predictions: list[dict[str, str]] = []
        task_calls = 0
        models: set[str] = set()
        for split in ("main", "flip", "entity"):
            task = load_task(base / split, select_gold)
            all_predictions.extend(task["predictions"])
            task_calls += int(task["calls"])
            models.update(task["reported_models"])
        metrics = score(all_predictions, select_gold)
        metrics["calls"] = task_calls
        metrics["calls_per_case"] = task_calls / len(all_predictions)
        metrics["reported_models"] = sorted(models)
        screening[label] = metrics
        audit["select"][profile] = {"rows": len(all_predictions), "calls": task_calls, "models": sorted(models)}

    if args.require_six and len(screening) != 6:
        raise RuntimeError(f"six backends required, found {len(screening)}")

    confirm_specs = [
        ("routebr", "main"),
        ("b1_direct", "main"),
        ("b2_direct_guard", "main"),
        ("routebr", "flip"),
        ("b1_direct", "flip"),
        ("b2_direct_guard", "flip"),
        ("a_state", "flip"),
        ("routebr", "entity"),
        ("a_ground", "entity"),
    ]
    confirm_tasks: dict[tuple[str, str], dict[str, Any]] = {}
    for system, split in confirm_specs:
        task = load_task(RUN_ROOT / "confirm" / system / split, confirm_gold)
        metrics = score(task["predictions"], confirm_gold)
        metrics["calls"] = task["calls"]
        metrics["calls_per_case"] = task["calls"] / len(task["predictions"])
        if split == "flip":
            metrics["flip_pairs"] = flip_pairs(task["predictions"], confirm_gold)
        confirm_tasks[(system, split)] = {"task": task, "metrics": metrics}
        audit["confirm"][f"{system}:{split}"] = {
            "rows": len(task["predictions"]),
            "calls": task["calls"],
            "models": task["reported_models"],
        }

    comparisons = {
        "rq1_routebr_vs_b1": mcnemar_exact(
            confirm_tasks[("routebr", "main")]["metrics"]["correct_by_case"],
            confirm_tasks[("b1_direct", "main")]["metrics"]["correct_by_case"],
        ),
        "rq1_routebr_vs_b2": mcnemar_exact(
            confirm_tasks[("routebr", "main")]["metrics"]["correct_by_case"],
            confirm_tasks[("b2_direct_guard", "main")]["metrics"]["correct_by_case"],
        ),
        "rq3_routebr_vs_no_state": mcnemar_exact(
            confirm_tasks[("routebr", "flip")]["metrics"]["correct_by_case"],
            confirm_tasks[("a_state", "flip")]["metrics"]["correct_by_case"],
        ),
        "rq3_routebr_vs_no_ground": mcnemar_exact(
            confirm_tasks[("routebr", "entity")]["metrics"]["correct_by_case"],
            confirm_tasks[("a_ground", "entity")]["metrics"]["correct_by_case"],
        ),
    }

    compact_confirm = {
        f"{system}:{split}": data["metrics"] for (system, split), data in confirm_tasks.items()
    }
    result = {
        "status": "COMPLETE_SIX_BACKENDS" if len(screening) == 6 else "PARTIAL_QWEN_AUTH_PENDING",
        "hashes": {
            "select_csv": sha256(SELECT_CSV),
            "confirm_csv": sha256(CONFIRM_CSV),
            "prompt": sha256(ROOT / "experiments/prompts.json"),
            "controller": sha256(ROOT / "src/routebr/controller.py"),
        },
        "screening": screening,
        "confirm": compact_confirm,
        "comparisons": comparisons,
        "audit": audit,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "FINAL_RESULTS.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Final RouteBR results",
        "",
        f"Status: **{result['status']}**",
        "",
        "## Backend screening on SELECT-160",
        "",
        "| Backend | Contract | Path F1 | FD | FB | Valid JSON | Calls/case | Tokens/case | Median latency (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, m in sorted(screening.items(), key=lambda item: -item[1]["contract_exact_rate"]):
        lines.append(
            f"| {label} | {pct(m['contract_exact_rate'])} | {pct(m['path_macro_f1'])} | "
            f"{m['false_dispatch']}/{m['false_dispatch_denominator']} ({pct(m['false_dispatch_rate'])}) | "
            f"{m['false_block']}/{m['false_block_denominator']} ({pct(m['false_block_rate'])}) | "
            f"{pct(m['valid_json_rate'])} | {m['calls_per_case']:.2f} | "
            f"{m['tokens_per_case_mean']:.0f} | {m['latency_ms_median']:.0f} |"
        )

    lines.extend([
        "",
        "## RQ1--RQ2 on CONFIRM",
        "",
        "| System | MAIN contract | MAIN path F1 | FLIP pair | FD | FB |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for system in ("routebr", "b1_direct", "b2_direct_guard"):
        main_m = compact_confirm[f"{system}:main"]
        flip_m = compact_confirm[f"{system}:flip"]
        pair = flip_m["flip_pairs"]
        pooled_fd = main_m["false_dispatch"] + flip_m["false_dispatch"]
        pooled_fd_n = main_m["false_dispatch_denominator"] + flip_m["false_dispatch_denominator"]
        pooled_fb = main_m["false_block"] + flip_m["false_block"]
        pooled_fb_n = main_m["false_block_denominator"] + flip_m["false_block_denominator"]
        lines.append(
            f"| {SYSTEM_LABELS[system]} | {pct(main_m['contract_exact_rate'])} | "
            f"{pct(main_m['path_macro_f1'])} | {pair['pair_exact']}/{pair['pairs']} "
            f"({pct(pair['pair_exact_rate'])}) | {pooled_fd}/{pooled_fd_n} "
            f"({pct(pooled_fd/pooled_fd_n if pooled_fd_n else 0)}) | {pooled_fb}/{pooled_fb_n} "
            f"({pct(pooled_fb/pooled_fb_n if pooled_fb_n else 0)}) |"
        )

    lines.extend([
        "",
        "## RQ3 safeguards",
        "",
        "| Variant | Split | Contract | Object accuracy | FD | FB |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for system, split in (("routebr", "flip"), ("a_state", "flip"), ("routebr", "entity"), ("a_ground", "entity")):
        m = compact_confirm[f"{system}:{split}"]
        lines.append(
            f"| {SYSTEM_LABELS[system]} | {split.upper()} | {pct(m['contract_exact_rate'])} | "
            f"{pct(m['object_accuracy'])} | {m['false_dispatch']}/{m['false_dispatch_denominator']} | "
            f"{m['false_block']}/{m['false_block_denominator']} |"
        )
    lines.extend([
        "",
        "## Integrity",
        "",
        f"- SELECT backends present: {len(screening)}/6.",
        f"- Audited SELECT rows: {sum(item['rows'] for item in audit['select'].values())}.",
        f"- Audited CONFIRM rows: {sum(item['rows'] for item in audit['confirm'].values())}.",
        "- No gold, annotator, or adjudication field was found in a model request body.",
        "- Every audited prediction has one raw receipt and an accepted reported model identity.",
    ])
    md_path = OUT_DIR / "FINAL_RESULTS.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    freeze = {
        "status": result["status"],
        "inputs": {
            str(path.relative_to(ROOT)): sha256(path)
            for path in sorted(RUN_ROOT.rglob("predictions.csv"))
        },
        "outputs": {
            str(json_path.relative_to(ROOT)): sha256(json_path),
            str(md_path.relative_to(ROOT)): sha256(md_path),
        },
    }
    (OUT_DIR / "RESULT_FREEZE_MANIFEST.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(md_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
