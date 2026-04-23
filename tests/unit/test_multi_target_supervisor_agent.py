from __future__ import annotations

from dataclasses import dataclass

from src.agents.multi_target_supervisor_agent import MultiTargetSupervisorAgent, SupervisorStep
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


LOGICAL_TO_SUFFIX = {
    "atlassian.search_issues": "___searchJiraIssues",
    "google.create_calendar_event": "___createCalendarEvent",
}


def test_supervisor_executes_cross_target_plan() -> None:
    caller = FakeCaller(calls=[])
    agent = MultiTargetSupervisorAgent(logical_to_suffix=LOGICAL_TO_SUFFIX, caller=caller)

    result = agent.execute_plan(
        steps=[
            SupervisorStep(
                logical_tool="atlassian.search_issues",
                arguments={"cloudId": "abc", "jql": "statusCategory != Done"},
                preferred_subagent="jira_subagent",
            ),
            SupervisorStep(
                logical_tool="google.create_calendar_event",
                arguments={"summary": "Sync"},
                preferred_subagent="calendar_subagent",
            ),
        ],
        subagents=[
            SubagentSpec("jira_subagent", ("atlassian-openapi-dev3___searchJiraIssues",)),
            SubagentSpec("calendar_subagent", ("google-calendar-openapi-dev3___createCalendarEvent",)),
        ],
    )

    assert result["status"] == "ok"
    assert len(result["steps"]) == 2
    assert len(caller.calls) == 2


def test_supervisor_stops_on_required_unavailable_tool() -> None:
    caller = FakeCaller(calls=[])
    agent = MultiTargetSupervisorAgent(logical_to_suffix=LOGICAL_TO_SUFFIX, caller=caller)

    result = agent.execute_plan(
        steps=[
            SupervisorStep(
                logical_tool="atlassian.search_issues",
                arguments={"cloudId": "abc", "jql": "statusCategory != Done"},
                preferred_subagent="jira_subagent",
            ),
            SupervisorStep(
                logical_tool="slack.post_message",
                arguments={"text": "hello"},
                required=True,
            ),
            SupervisorStep(
                logical_tool="google.create_calendar_event",
                arguments={"summary": "Must not run"},
            ),
        ],
        subagents=[
            SubagentSpec("jira_subagent", ("atlassian-openapi-dev3___searchJiraIssues",)),
            SubagentSpec("calendar_subagent", ("google-calendar-openapi-dev3___createCalendarEvent",)),
        ],
    )

    assert result["status"] == "failed"
    assert result["failed_at_step"] == 2
    assert len(caller.calls) == 1
