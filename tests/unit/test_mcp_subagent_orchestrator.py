from __future__ import annotations

from dataclasses import dataclass

from src.agents.mcp_subagent_orchestrator import MCPSubagentOrchestrator
from src.agents.subagent_tool_router import SubagentSpec, SubagentToolRouter


LOGICAL_TO_SUFFIX = {
    "atlassian.search_issues": "___searchJiraIssues",
    "google.create_calendar_event": "___createCalendarEvent",
}


@dataclass
class FakeCaller:
    calls: list[dict]

    def call_tool(self, *, subagent_name: str, tool_name: str, arguments: dict) -> dict:
        payload = {
            "subagent_name": subagent_name,
            "tool_name": tool_name,
            "arguments": arguments,
        }
        self.calls.append(payload)
        return {"ok": True, "echo": payload}


def test_execute_calls_selected_tool_on_preferred_subagent() -> None:
    caller = FakeCaller(calls=[])
    orchestrator = MCPSubagentOrchestrator(
        router=SubagentToolRouter(LOGICAL_TO_SUFFIX),
        caller=caller,
    )

    result = orchestrator.execute(
        requested_logical_tool="atlassian.search_issues",
        arguments={"cloudId": "abc", "jql": "statusCategory != Done"},
        preferred_subagent="jira_subagent",
        subagents=[
            SubagentSpec("jira_subagent", ("atlassian-openapi-dev3___searchJiraIssues",)),
            SubagentSpec("calendar_subagent", ("google-calendar-openapi-dev3___createCalendarEvent",)),
        ],
    )

    assert result.status == "ok"
    assert result.error is None
    assert len(caller.calls) == 1
    assert caller.calls[0]["subagent_name"] == "jira_subagent"


def test_execute_reroutes_to_other_subagent_when_needed() -> None:
    caller = FakeCaller(calls=[])
    orchestrator = MCPSubagentOrchestrator(
        router=SubagentToolRouter(LOGICAL_TO_SUFFIX),
        caller=caller,
    )

    result = orchestrator.execute(
        requested_logical_tool="google.create_calendar_event",
        arguments={"summary": "x"},
        preferred_subagent="jira_subagent",
        subagents=[
            SubagentSpec("jira_subagent", ("atlassian-openapi-dev3___searchJiraIssues",)),
            SubagentSpec("calendar_subagent", ("google-calendar-openapi-dev3___createCalendarEvent",)),
        ],
    )

    assert result.status == "ok"
    assert result.route.selected_subagent == "calendar_subagent"
    assert len(caller.calls) == 1
    assert caller.calls[0]["tool_name"] == "google-calendar-openapi-dev3___createCalendarEvent"


def test_execute_does_not_call_any_tool_when_unavailable() -> None:
    caller = FakeCaller(calls=[])
    orchestrator = MCPSubagentOrchestrator(
        router=SubagentToolRouter(LOGICAL_TO_SUFFIX),
        caller=caller,
    )

    result = orchestrator.execute(
        requested_logical_tool="slack.post_message",
        arguments={"text": "hello"},
        preferred_subagent="jira_subagent",
        subagents=[SubagentSpec("jira_subagent", ("atlassian-openapi-dev3___searchJiraIssues",))],
    )

    assert result.status == "tool_not_available"
    assert result.response is None
    assert result.error is not None
    assert result.error["error_code"] == "TOOL_NOT_AVAILABLE"
    assert len(caller.calls) == 0
