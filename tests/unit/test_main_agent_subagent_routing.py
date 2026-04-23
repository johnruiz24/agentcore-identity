from __future__ import annotations

from dataclasses import dataclass

from src.agents.main_agent import BedrockAgentExecutor
from src.agents.subagent_tool_router import SubagentSpec


@dataclass
class FakeCaller:
    calls: list[dict]

    def call_tool(self, *, subagent_name: str, tool_name: str, arguments: dict):
        payload = {
            "subagent_name": subagent_name,
            "tool_name": tool_name,
            "arguments": arguments,
        }
        self.calls.append(payload)
        return {"ok": True, "payload": payload}


def build_executor() -> BedrockAgentExecutor:
    return BedrockAgentExecutor(
        bedrock_model_id="test-model",
        region="eu-central-1",
        auth_tools=None,
        identity_tools=None,
        session_handler=None,
    )


def test_main_agent_routes_and_executes_via_subagent_orchestrator() -> None:
    executor = build_executor()
    caller = FakeCaller(calls=[])

    result = executor.route_subagent_tool(
        requested_logical_tool="atlassian.search_issues",
        arguments={"cloudId": "abc", "jql": "statusCategory != Done"},
        preferred_subagent="jira_subagent",
        subagents=[
            SubagentSpec("jira_subagent", ("atlassian-openapi-dev3___searchJiraIssues",)),
            SubagentSpec("calendar_subagent", ("google-calendar-openapi-dev3___createCalendarEvent",)),
        ],
        caller=caller,
    )

    assert result.status == "ok"
    assert result.error is None
    assert len(caller.calls) == 1
    assert caller.calls[0]["subagent_name"] == "jira_subagent"


def test_main_agent_returns_tool_not_available_without_call() -> None:
    executor = build_executor()
    caller = FakeCaller(calls=[])

    result = executor.route_subagent_tool(
        requested_logical_tool="slack.post_message",
        arguments={"text": "hello"},
        preferred_subagent="jira_subagent",
        subagents=[SubagentSpec("jira_subagent", ("atlassian-openapi-dev3___searchJiraIssues",))],
        caller=caller,
    )

    assert result.status == "tool_not_available"
    assert result.error is not None
    assert result.error["error_code"] == "TOOL_NOT_AVAILABLE"
    assert len(caller.calls) == 0
