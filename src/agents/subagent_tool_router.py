"""Subagent tool routing with deterministic fallback for multi-target MCP setups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SubagentSpec:
    """Subagent capability snapshot from MCP tools/list results."""

    name: str
    tools: tuple[str, ...]


@dataclass(frozen=True)
class RouteDecision:
    """Routing outcome for a requested logical tool capability."""

    status: str
    requested_logical_tool: str
    selected_subagent: str | None
    selected_tool_name: str | None
    error_code: str | None
    available_tools: tuple[str, ...]
    suggested_route: tuple[str, ...]


class SubagentToolRouter:
    """Resolve logical actions to concrete MCP tools across subagents.

    Router is intentionally framework-agnostic so it can be used from plain Runtime
    orchestration or plugged into LangGraph/DeepAgents nodes.
    """

    def __init__(self, logical_to_suffix: dict[str, str]):
        if not logical_to_suffix:
            raise ValueError("logical_to_suffix cannot be empty")
        self.logical_to_suffix = logical_to_suffix

    @staticmethod
    def _find_tool(tools: Iterable[str], suffix: str) -> str | None:
        for tool in tools:
            if tool.endswith(suffix):
                return tool
        return None

    def route(
        self,
        *,
        requested_logical_tool: str,
        subagents: list[SubagentSpec],
        preferred_subagent: str | None = None,
    ) -> RouteDecision:
        if requested_logical_tool not in self.logical_to_suffix:
            all_tools = tuple(sorted({t for s in subagents for t in s.tools}))
            return RouteDecision(
                status="tool_not_available",
                requested_logical_tool=requested_logical_tool,
                selected_subagent=None,
                selected_tool_name=None,
                error_code="TOOL_NOT_AVAILABLE",
                available_tools=all_tools,
                suggested_route=tuple(),
            )

        suffix = self.logical_to_suffix[requested_logical_tool]
        by_name = {s.name: s for s in subagents}

        if preferred_subagent and preferred_subagent in by_name:
            tool = self._find_tool(by_name[preferred_subagent].tools, suffix)
            if tool:
                return RouteDecision(
                    status="ok",
                    requested_logical_tool=requested_logical_tool,
                    selected_subagent=preferred_subagent,
                    selected_tool_name=tool,
                    error_code=None,
                    available_tools=tuple(sorted(by_name[preferred_subagent].tools)),
                    suggested_route=(preferred_subagent,),
                )

        candidates: list[tuple[str, str]] = []
        for spec in subagents:
            tool = self._find_tool(spec.tools, suffix)
            if tool:
                candidates.append((spec.name, tool))

        if candidates:
            chosen_subagent, chosen_tool = candidates[0]
            return RouteDecision(
                status="ok",
                requested_logical_tool=requested_logical_tool,
                selected_subagent=chosen_subagent,
                selected_tool_name=chosen_tool,
                error_code=None,
                available_tools=tuple(sorted({t for _, t in candidates})),
                suggested_route=tuple(name for name, _ in candidates),
            )

        all_tools = tuple(sorted({t for s in subagents for t in s.tools}))
        suggested = tuple(
            sorted(
                {
                    s.name
                    for s in subagents
                    if any(t.startswith("atlassian-") for t in s.tools)
                    or any(t.startswith("google-calendar-") for t in s.tools)
                }
            )
        )
        return RouteDecision(
            status="tool_not_available",
            requested_logical_tool=requested_logical_tool,
            selected_subagent=None,
            selected_tool_name=None,
            error_code="TOOL_NOT_AVAILABLE",
            available_tools=all_tools,
            suggested_route=suggested,
        )

    @staticmethod
    def as_error_payload(decision: RouteDecision) -> dict:
        """Convert non-ok decision into a stable error contract for orchestrators."""
        return {
            "error_code": decision.error_code or "TOOL_NOT_AVAILABLE",
            "requested_tool": decision.requested_logical_tool,
            "available_tools": list(decision.available_tools),
            "suggested_route": list(decision.suggested_route),
        }
