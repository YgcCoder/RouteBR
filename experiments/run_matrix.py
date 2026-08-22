#!/usr/bin/env python3
"""Run the frozen final RouteBR matrix with bounded process concurrency."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "experiments/run_case.py"
PROFILES = ROOT / "experiments/api_profiles.json"
SELECT = ROOT / "data/routebr_select_160.csv"
CONFIRM = ROOT / "data/routebr_confirm_320.csv"
RUN_ROOT = ROOT / "experiments/results"


@dataclass(frozen=True)
class Task:
    name: str
    profile: str
    system: str
    split: str
    cases: Path
    output: Path


SELECT_PROFILES = (
    "deepseek_v4_primary",
    "deepseek_v4_flash_efficiency",
    "ohmygpt_gpt4o_historical",
    "ohmygpt_gpt52_frontier",
)
QWEN_PROFILES = (
    "qwencloud_qwen38max_robustness",
    "qwencloud_qwen37plus_robustness",
)


def select_tasks(profiles: tuple[str, ...]) -> list[Task]:
    tasks: list[Task] = []
    for profile in profiles:
        for split in ("MAIN", "FLIP", "ENTITY"):
            name = f"select__{profile}__{split.lower()}"
            tasks.append(
                Task(
                    name,
                    profile,
                    "routebr",
                    split,
                    SELECT,
                    RUN_ROOT / "select" / profile / split.lower(),
                )
            )
    return tasks


def confirm_tasks() -> list[Task]:
    specs = [
        ("routebr", "MAIN"),
        ("b1_direct", "MAIN"),
        ("b2_direct_guard", "MAIN"),
        ("routebr", "FLIP"),
        ("b1_direct", "FLIP"),
        ("b2_direct_guard", "FLIP"),
        ("a_state", "FLIP"),
        ("routebr", "ENTITY"),
        ("a_ground", "ENTITY"),
    ]
    return [
        Task(
            f"confirm__{system}__{split.lower()}",
            "deepseek_v4_primary",
            system,
            split,
            CONFIRM,
            RUN_ROOT / "confirm" / system / split.lower(),
        )
        for system, split in specs
    ]


def run_task(task: Task) -> dict[str, object]:
    task.output.mkdir(parents=True, exist_ok=True)
    prediction_path = task.output / "predictions.csv"
    command = [
        sys.executable,
        str(RUNNER),
        "--profiles",
        str(PROFILES),
        "--profile",
        task.profile,
        "--system",
        task.system,
        "--split",
        task.split,
        "--cases",
        str(task.cases),
        "--output-dir",
        str(task.output),
        "--confirm-author-reviewed-prompts",
        "--confirm-three-engineer-joint-review",
        "--timeout",
        "120",
        "--max-retries",
        "3",
        "--retry-backoff",
        "1",
    ]
    if prediction_path.exists() and prediction_path.stat().st_size:
        command.append("--resume")
    completed = subprocess.run(command, text=True, capture_output=True)
    log_path = task.output / "process.log"
    log_path.write_text(completed.stdout + "\n[stderr]\n" + completed.stderr, encoding="utf-8")
    actual = 0
    if prediction_path.exists():
        actual = max(0, len(prediction_path.read_text(encoding="utf-8").splitlines()) - 1)
    return {
        "task": task.name,
        "profile": task.profile,
        "system": task.system,
        "split": task.split,
        "returncode": completed.returncode,
        "actual_rows": actual,
        "tail": (completed.stdout + "\n" + completed.stderr).splitlines()[-8:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scope",
        choices=("available-select", "qwen-select", "confirm", "available-and-confirm", "all"),
        required=True,
    )
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if args.jobs < 1:
        raise SystemExit("--jobs must be positive")

    tasks: list[Task] = []
    if args.scope in {"available-select", "available-and-confirm", "all"}:
        tasks.extend(select_tasks(SELECT_PROFILES))
    if args.scope in {"qwen-select", "all"}:
        tasks.extend(select_tasks(QWEN_PROFILES))
    if args.scope in {"confirm", "available-and-confirm", "all"}:
        tasks.extend(confirm_tasks())

    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"launching {len(tasks)} tasks with jobs={args.jobs}", flush=True)
    results: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run_task, task): task for task in tasks}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                f"{result['task']}: rc={result['returncode']} rows={result['actual_rows']}",
                flush=True,
            )

    receipt = {
        "scope": args.scope,
        "jobs": args.jobs,
        "tasks": sorted(results, key=lambda item: str(item["task"])),
    }
    receipt_path = RUN_ROOT / f"matrix_{args.scope}.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failures = [item for item in results if item["returncode"] != 0]
    print(f"complete tasks={len(results)} failures={len(failures)} receipt={receipt_path}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
