from __future__ import annotations

import json
from pathlib import Path

import pytest


SCENARIO_FILE = Path("tests/e2e/data/multi_target_complex_questions.json")

LOGICAL_TO_SUFFIX = {
    "atlassian.list_accessible_resources": "___listAtlassianAccessibleResources",
    "atlassian.search_projects": "___searchJiraProjects",
    "atlassian.search_issues": "___searchJiraIssues",
    "google.create_calendar_event": "___createCalendarEvent",
}


@pytest.fixture(scope="module")
def scenarios() -> list[dict]:
    return json.loads(SCENARIO_FILE.read_text())


def test_scenario_file_exists() -> None:
    assert SCENARIO_FILE.exists(), "Scenario file must exist"


def test_scenarios_have_required_fields(scenarios: list[dict]) -> None:
    assert scenarios, "Scenario list must not be empty"

    for scenario in scenarios:
        assert "id" in scenario and scenario["id"]
        assert "question" in scenario and scenario["question"]
        assert "steps" in scenario and isinstance(scenario["steps"], list)
        assert scenario["steps"], f"Scenario {scenario['id']} must have at least one step"


def test_all_logical_tools_are_supported(scenarios: list[dict]) -> None:
    for scenario in scenarios:
        for step in scenario["steps"]:
            logical_tool = step.get("logical_tool")
            assert logical_tool in LOGICAL_TO_SUFFIX, (
                f"Unsupported logical tool in {scenario['id']}: {logical_tool}"
            )


def test_cross_tool_scenarios_include_both_targets(scenarios: list[dict]) -> None:
    cross_ids = {"cross_release_readout", "cross_incident_followup"}
    id_to_scenario = {s["id"]: s for s in scenarios}

    for scenario_id in cross_ids:
        scenario = id_to_scenario[scenario_id]
        logical_tools = [s["logical_tool"] for s in scenario["steps"]]
        assert any(t.startswith("atlassian.") for t in logical_tools)
        assert any(t.startswith("google.") for t in logical_tools)


def test_template_arguments_present_for_cloud_id_chained_steps(scenarios: list[dict]) -> None:
    for scenario in scenarios:
        saw_resource_discovery = False
        for step in scenario["steps"]:
            logical = step["logical_tool"]
            if logical == "atlassian.list_accessible_resources":
                saw_resource_discovery = True
            if logical in {"atlassian.search_projects", "atlassian.search_issues"}:
                assert saw_resource_discovery, (
                    f"{scenario['id']} uses Atlassian search before resource discovery"
                )
                cloud_id = step.get("arguments", {}).get("cloudId")
                assert cloud_id == "{{cloudId}}", (
                    f"{scenario['id']} Atlassian search step must template cloudId"
                )
