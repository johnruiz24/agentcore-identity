"""Runtime orchestrator for MCP subagents using deterministic routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .subagent_tool_router import RouteDecision, SubagentSpec, SubagentToolRouter


class MCPCaller(Protocol):
    """Protocol for MCP tools/call execution used by orchestrator."""

    def call_tool(self, *, subagent_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class OrchestrationResult:
    status: str
    route: RouteDecision
    response: dict[str, Any] | None
    error: dict[str, Any] | None


class MCPSubagentOrchestrator:
    """Orchestrates logical requests across subagents and MCP targets.

    Responsibilities:
    - Resolve logical tool intent to concrete tool name and subagent route
    - Prevent outbound tool call when no route exists
    - Return stable error contract on unavailable tools
    """

    def __init__(self, *, router: SubagentToolRouter, caller: MCPCaller):
        self.router = router
        self.caller = caller

    def execute(
        self,
        *,
        requested_logical_tool: str,
        arguments: dict[str, Any],
        subagents: list[SubagentSpec],
        preferred_subagent: str | None = None,
    ) -> OrchestrationResult:
        decision = self.router.route(
            requested_logical_tool=requested_logical_tool,
            subagents=subagents,
            preferred_subagent=preferred_subagent,
        )

        if decision.status != "ok" or not decision.selected_subagent or not decision.selected_tool_name:
            return OrchestrationResult(
                status="tool_not_available",
                route=decision,
                response=None,
                error=SubagentToolRouter.as_error_payload(decision),
            )

        response = self.caller.call_tool(
            subagent_name=decision.selected_subagent,
            tool_name=decision.selected_tool_name,
            arguments=arguments,
        )
        return OrchestrationResult(
            status="ok",
            route=decision,
            response=response,
            error=None,
        )
