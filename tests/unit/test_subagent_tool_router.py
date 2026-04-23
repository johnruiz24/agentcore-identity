from src.agents.subagent_tool_router import RouteDecision, SubagentSpec, SubagentToolRouter


LOGICAL_TO_SUFFIX = {
    "atlassian.search_issues": "___searchJiraIssues",
    "google.create_calendar_event": "___createCalendarEvent",
}


def test_routes_to_preferred_subagent_when_tool_exists() -> None:
    router = SubagentToolRouter(LOGICAL_TO_SUFFIX)
    decision = router.route(
        requested_logical_tool="atlassian.search_issues",
        preferred_subagent="jira_subagent",
        subagents=[
            SubagentSpec(
                name="jira_subagent",
                tools=("atlassian-openapi-dev3___searchJiraIssues",),
            ),
            SubagentSpec(
                name="calendar_subagent",
                tools=("google-calendar-openapi-dev3___createCalendarEvent",),
            ),
        ],
    )

    assert decision.status == "ok"
    assert decision.selected_subagent == "jira_subagent"
    assert decision.selected_tool_name == "atlassian-openapi-dev3___searchJiraIssues"


def test_reroutes_when_preferred_subagent_lacks_tool() -> None:
    router = SubagentToolRouter(LOGICAL_TO_SUFFIX)
    decision = router.route(
        requested_logical_tool="google.create_calendar_event",
        preferred_subagent="jira_subagent",
        subagents=[
            SubagentSpec(
                name="jira_subagent",
                tools=("atlassian-openapi-dev3___searchJiraIssues",),
            ),
            SubagentSpec(
                name="calendar_subagent",
                tools=("google-calendar-openapi-dev3___createCalendarEvent",),
            ),
        ],
    )

    assert decision.status == "ok"
    assert decision.selected_subagent == "calendar_subagent"
    assert decision.selected_tool_name == "google-calendar-openapi-dev3___createCalendarEvent"
    assert "calendar_subagent" in decision.suggested_route


def test_returns_tool_not_available_when_no_subagent_has_capability() -> None:
    router = SubagentToolRouter(LOGICAL_TO_SUFFIX)
    decision = router.route(
        requested_logical_tool="atlassian.search_issues",
        preferred_subagent="jira_subagent",
        subagents=[
            SubagentSpec(
                name="jira_subagent",
                tools=("atlassian-openapi-dev3___searchJiraProjects",),
            ),
            SubagentSpec(
                name="calendar_subagent",
                tools=("google-calendar-openapi-dev3___createCalendarEvent",),
            ),
        ],
    )

    assert decision.status == "tool_not_available"
    assert decision.error_code == "TOOL_NOT_AVAILABLE"
    payload = SubagentToolRouter.as_error_payload(decision)
    assert payload["error_code"] == "TOOL_NOT_AVAILABLE"
    assert payload["requested_tool"] == "atlassian.search_issues"
    assert "google-calendar-openapi-dev3___createCalendarEvent" in payload["available_tools"]


def test_unknown_logical_tool_returns_not_available_without_call_attempt() -> None:
    router = SubagentToolRouter(LOGICAL_TO_SUFFIX)
    decision = router.route(
        requested_logical_tool="slack.post_message",
        subagents=[
            SubagentSpec(
                name="jira_subagent",
                tools=("atlassian-openapi-dev3___searchJiraIssues",),
            )
        ],
    )

    assert isinstance(decision, RouteDecision)
    assert decision.status == "tool_not_available"
    assert decision.selected_tool_name is None
    assert decision.error_code == "TOOL_NOT_AVAILABLE"
