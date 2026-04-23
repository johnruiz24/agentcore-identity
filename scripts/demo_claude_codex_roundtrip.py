#!/usr/bin/env python3
"""
Demo: Claude Code -> Codex -> Claude Code round-trip.

Runs against the installed codex-delegator skill in ~/.claude/skills/codex-delegator.

Modes:
- real: call Codex CLI for real execution
- dry-run: simulate Codex response (no network dependency)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime
from pathlib import Path


SKILL_DIR = Path.home() / ".claude" / "skills" / "codex-delegator"
OUTPUT_DIR = Path.cwd() / "demo_output"


def _require_skill_files() -> None:
    required = [
        SKILL_DIR / "codex_delegator.py",
        SKILL_DIR / "context_preparer.py",
        SKILL_DIR / "codex_executor.py",
        SKILL_DIR / "validator.py",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError("Missing codex-delegator files: " + ", ".join(missing))


def _build_task() -> dict:
    return {
        "task_description": (
            "Create a JavaScript function validateEmail(email) that returns true "
            "for a valid email and false otherwise."
        ),
        "previous_attempts": 2,
        "progress_blocked": True,
        "task_type": "backend",
        "context_details": {
            "success_criteria": [
                "validateEmail('<EMAIL_PLACEHOLDER>') returns true",
                "validateEmail('a@b') returns false",
                "validateEmail('invalid') returns false",
            ],
            "architecture": "vanilla JavaScript",
            "attempt_1": {
                "approach": "Used regex only",
                "error": "Accepted invalid short domain",
                "why_failed": "Regex too permissive",
            },
            "attempt_2": {
                "approach": "String split checks",
                "error": "Missed TLD validation",
                "why_failed": "Did not verify final segment length",
            },
            "test_command": "echo 'demo mode: no test suite bound'",
            "constraints": ["Output only JavaScript code"],
        },
    }


def _print_stage(title: str, body: str) -> None:
    print(f"\n=== {title} ===")
    print(body)


def run_demo(mode: str) -> dict:
    _require_skill_files()
    sys.path.insert(0, str(SKILL_DIR))

    import codex_delegator as cd  # type: ignore
    from codex_executor import ExecutionResult, ExecutionStatus  # type: ignore

    task = _build_task()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    demo_log = OUTPUT_DIR / f"delegation-{timestamp}.log"

    _print_stage(
        "1) Claude receives task",
        f"Task: {task['task_description']}\nAttempts: {task['previous_attempts']}\nBlocked: {task['progress_blocked']}",
    )

    # Show prepared prompt before execution.
    skill_preview = cd.CodexDelegatorSkill(log_file=str(demo_log))
    preparer = skill_preview._prepare_context(  # noqa: SLF001 - demo intentionally introspects
        task["task_description"], task["previous_attempts"], task["context_details"]
    )
    prompt = preparer.prepare_prompt()
    _print_stage("2) Claude prepares prompt for Codex", prompt[:900] + ("..." if len(prompt) > 900 else ""))

    if mode == "dry-run":
        def fake_execute_codex(_: str, timeout: int = 120) -> ExecutionResult:
            _ = timeout
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                output=(
                    "function validateEmail(email) {\n"
                    "  if (typeof email !== 'string' || email.length === 0) return false;\n"
                    "  const at = email.indexOf('@');\n"
                    "  if (at <= 0 || at !== email.lastIndexOf('@')) return false;\n"
                    "  const local = email.slice(0, at);\n"
                    "  const domain = email.slice(at + 1);\n"
                    "  if (!local || !domain || domain.startsWith('.') || domain.endsWith('.')) return false;\n"
                    "  const parts = domain.split('.');\n"
                    "  if (parts.length < 2 || parts.some(p => p.length === 0)) return false;\n"
                    "  return parts[parts.length - 1].length >= 2;\n"
                    "}\n"
                ),
                code=(
                    "function validateEmail(email) {\n"
                    "  if (typeof email !== 'string' || email.length === 0) return false;\n"
                    "  const at = email.indexOf('@');\n"
                    "  if (at <= 0 || at !== email.lastIndexOf('@')) return false;\n"
                    "  const local = email.slice(0, at);\n"
                    "  const domain = email.slice(at + 1);\n"
                    "  if (!local || !domain || domain.startsWith('.') || domain.endsWith('.')) return false;\n"
                    "  const parts = domain.split('.');\n"
                    "  if (parts.length < 2 || parts.some(p => p.length === 0)) return false;\n"
                    "  return parts[parts.length - 1].length >= 2;\n"
                    "}\n"
                ),
            )

        cd.execute_codex = fake_execute_codex
        _print_stage("3) Claude delegates to Codex", "DRY-RUN mode: simulated Codex response")
    else:
        _print_stage("3) Claude delegates to Codex", "REAL mode: invoking codex exec --full-auto")

    skill = cd.CodexDelegatorSkill(log_file=str(demo_log))
    result = skill.delegate_task(**task)

    code = result.get("generated_code") or ""
    out_file = OUTPUT_DIR / f"generated-{timestamp}.js"
    if code:
        out_file.write_text(code, encoding="utf-8")

    _print_stage(
        "4) Codex returns to Claude",
        textwrap.dedent(
            f"""
            status: {result.get('status')}
            validation_passed: {result.get('validation_passed')}
            validation_status: {result.get('validation_status')}
            generated_code_length: {len(code)}
            file: {out_file if code else '(no file written)'}
            log: {demo_log}
            """
        ).strip(),
    )

    if code:
        _print_stage("5) Returned code preview", code[:800] + ("..." if len(code) > 800 else ""))

    summary = {
        "mode": mode,
        "timestamp": timestamp,
        "result": result,
        "output_file": str(out_file) if code else None,
        "log_file": str(demo_log),
    }
    summary_file = OUTPUT_DIR / f"summary-{timestamp}.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSummary JSON: {summary_file}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo Claude <-> Codex round-trip")
    parser.add_argument(
        "--mode",
        choices=["real", "dry-run"],
        default=os.getenv("DEMO_MODE", "real"),
        help="Execution mode (default: real)",
    )
    args = parser.parse_args()

    try:
        run_demo(args.mode)
        return 0
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
