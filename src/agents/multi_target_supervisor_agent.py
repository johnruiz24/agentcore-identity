"""Multi-target supervisor agent for orchestrating subagent tool plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .mcp_subagent_orchestrator import MCPSubagentOrchestrator
from .subagent_tool_router import SubagentSpec, SubagentToolRouter


@dataclass(frozen=True)
class SupervisorStep:
    logical_tool: str
    arguments: dict[str, Any]
    preferred_subagent: str | None = None
    required: bool = True


class MultiTargetSupervisorAgent:
    """Executes a sequence of logical actions across multiple MCP-backed subagents."""

    def __init__(self, *, logical_to_suffix: dict[str, str], caller: Any):
        self._router = SubagentToolRouter(logical_to_suffix)
        self._orchestrator = MCPSubagentOrchestrator(router=self._router, caller=caller)

    def execute_plan(
        self,
        *,
        steps: list[SupervisorStep],
        subagents: list[SubagentSpec],
    ) -> dict[str, Any]:
        report_steps: list[dict[str, Any]] = []

        for index, step in enumerate(steps, start=1):
            outcome = self._orchestrator.execute(
                requested_logical_tool=step.logical_tool,
                arguments=step.arguments,
                preferred_subagent=step.preferred_subagent,
                subagents=subagents,
            )

            report_item = {
                "index": index,
                "logical_tool": step.logical_tool,
                "selected_subagent": outcome.route.selected_subagent,
                "selected_tool": outcome.route.selected_tool_name,
                "status": outcome.status,
                "response": outcome.response,
                "error": outcome.error,
            }
            report_steps.append(report_item)

            if outcome.status != "ok" and step.required:
                return {
                    "status": "failed",
                    "failed_at_step": index,
                    "steps": report_steps,
                }

        return {
            "status": "ok",
            "steps": report_steps,
        }
