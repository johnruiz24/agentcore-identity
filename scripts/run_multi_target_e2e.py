#!/usr/bin/env python3
"""Run complex multi-target MCP scenarios (Atlassian + Google Calendar)."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import http.client
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
import urllib.error

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agents.mcp_subagent_orchestrator import MCPSubagentOrchestrator
from src.agents.subagent_tool_router import SubagentSpec, SubagentToolRouter


@dataclass
class GatewayAuthConfig:
    gateway_url: str
    pool_id: str
    client_id: str
    scope: str


LOGICAL_TO_SUFFIX = {
    "atlassian.list_accessible_resources": "___listAtlassianAccessibleResources",
    "atlassian.search_projects": "___searchJiraProjects",
    "atlassian.search_issues": "___searchJiraIssues",
    "google.create_calendar_event": "___createCalendarEvent",
}


def discover_gateway_auth(profile: str, region: str, gateway_id: str) -> GatewayAuthConfig:
    cloudcontrol = boto3.Session(profile_name=profile, region_name=region).client("cloudcontrol")
    res = cloudcontrol.get_resource(
        TypeName="AWS::BedrockAgentCore::Gateway",
        Identifier=gateway_id,
    )
    props_raw = res["ResourceDescription"]["Properties"]
    props = json.loads(props_raw) if isinstance(props_raw, str) else props_raw
    custom = props["AuthorizerConfiguration"]["CustomJWTAuthorizer"]
    discovery_url = custom["DiscoveryUrl"].rstrip("/")
    parts = discovery_url.split("/")
    if len(parts) >= 2 and parts[-1] == ".well-known":
        pool_id = parts[-2]
    elif len(parts) >= 3 and parts[-1] == "openid-configuration" and parts[-2] == ".well-known":
        pool_id = parts[-3]
    else:
        pool_id = parts[-1]

    return GatewayAuthConfig(
        gateway_url=props["GatewayUrl"],
        pool_id=pool_id,
        client_id=custom["AllowedClients"][0],
        scope=custom["AllowedScopes"][0],
    )


def get_cognito_client_secret(profile: str, region: str, pool_id: str, client_id: str) -> str:
    cognito = boto3.Session(profile_name=profile, region_name=region).client("cognito-idp")
    out = cognito.describe_user_pool_client(UserPoolId=pool_id, ClientId=client_id)
    return out["UserPoolClient"]["ClientSecret"]


def get_cognito_access_token(
    *,
    region: str,
    pool_id: str,
    client_id: str,
    client_secret: str,
    scope: str,
) -> str:
    oidc_config_url = (
        f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/openid-configuration"
    )
    with urllib.request.urlopen(oidc_config_url, timeout=20) as r:
        oidc = json.loads(r.read().decode("utf-8"))
    token_endpoint = oidc["token_endpoint"]

    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "scope": scope,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        token_endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        payload = json.loads(r.read().decode("utf-8"))
    token = payload.get("access_token")
    if not token:
        raise RuntimeError(f"Could not obtain access token: {payload}")
    return token


def mcp_jsonrpc(url: str, token: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-11-25",
        },
    )

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=75) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
            return {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {
                    "code": -32097,
                    "message": f"HTTP {e.code}: {raw[:500]}",
                },
            }
        except (TimeoutError, urllib.error.URLError, http.client.RemoteDisconnected) as e:
            last_error = e
            if attempt < 2:
                time.sleep(1.0 + attempt)
                continue
            return {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {
                    "code": -32098,
                    "message": f"Transport failure after retries: {type(e).__name__}: {e}",
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": body.get("id"),
        "error": {
            "code": -32099,
            "message": f"Unknown transport failure: {last_error}",
        },
    }


def discover_tools(url: str, token: str) -> list[dict[str, Any]]:
    init_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "multi-target-e2e", "version": "1.0"},
        },
    }
    tools_body = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    _ = mcp_jsonrpc(url, token, init_body)
    tools_res = mcp_jsonrpc(url, token, tools_body)
    return tools_res.get("result", {}).get("tools", [])


def build_subagent_specs(tools: list[dict[str, Any]]) -> list[SubagentSpec]:
    names = [t.get("name", "") for t in tools]
    atl = tuple(sorted(n for n in names if n.startswith("atlassian-openapi-")))
    gcal = tuple(sorted(n for n in names if n.startswith("google-calendar-openapi-")))
    specs: list[SubagentSpec] = []
    if atl:
        specs.append(SubagentSpec(name="jira_subagent", tools=atl))
    if gcal:
        specs.append(SubagentSpec(name="calendar_subagent", tools=gcal))
    if not specs:
        specs.append(SubagentSpec(name="default_subagent", tools=tuple(sorted(names))))
    return specs


def preferred_subagent_for(logical_tool: str) -> str | None:
    if logical_tool.startswith("atlassian."):
        return "jira_subagent"
    if logical_tool.startswith("google."):
        return "calendar_subagent"
    return None


def substitute_templates(obj: Any, context: dict[str, str]) -> Any:
    if isinstance(obj, dict):
        return {k: substitute_templates(v, context) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute_templates(v, context) for v in obj]
    if isinstance(obj, str):
        out = obj
        for key, value in context.items():
            out = out.replace(f"{{{{{key}}}}}", value)
        return out
    return obj


def extract_cloud_id(call_result: dict[str, Any]) -> str | None:
    result = call_result.get("result", {})
    content = result.get("content", [])
    if not content:
        return None

    first = content[0]
    if isinstance(first, dict):
        payload = first.get("json")
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            value = payload[0].get("id")
            if value:
                return str(value)

        text = first.get("text")
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                    value = parsed[0].get("id")
                    if value:
                        return str(value)
            except json.JSONDecodeError:
                return None
    return None


def build_default_context() -> dict[str, str]:
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    start = dt.datetime.combine(tomorrow, dt.time(9, 0))
    end = dt.datetime.combine(tomorrow, dt.time(9, 30))
    context = {
        "tomorrow_date": tomorrow.isoformat(),
        "tomorrow_start_iso": start.isoformat(),
        "tomorrow_end_iso": end.isoformat(),
    }
    for idx in range(1, 11):
        slot_start = start + dt.timedelta(minutes=(idx - 1) * 45)
        slot_end = slot_start + dt.timedelta(minutes=30)
        context[f"slot{idx}_start_iso"] = slot_start.isoformat()
        context[f"slot{idx}_end_iso"] = slot_end.isoformat()
    return context


class ScenarioMCPCaller:
    def __init__(self, *, gateway_url: str, token: str, live: bool):
        self.gateway_url = gateway_url
        self.token = token
        self.live = live

    def call_tool(self, *, subagent_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.live:
            return {
                "planned": True,
                "subagent_name": subagent_name,
                "tool_name": tool_name,
                "arguments": arguments,
            }

        payload = {
            "jsonrpc": "2.0",
            "id": 1001,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        return mcp_jsonrpc(self.gateway_url, self.token, payload)


def run_scenarios(
    *,
    gateway_url: str,
    token: str,
    tools: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    live: bool,
) -> dict[str, Any]:
    subagents = build_subagent_specs(tools)
    orchestrator = MCPSubagentOrchestrator(
        router=SubagentToolRouter(LOGICAL_TO_SUFFIX),
        caller=ScenarioMCPCaller(gateway_url=gateway_url, token=token, live=live),
    )

    report: dict[str, Any] = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "gateway_url": gateway_url,
        "live": live,
        "tools": [t.get("name", "") for t in tools],
        "subagents": [{"name": s.name, "tools": list(s.tools)} for s in subagents],
        "scenarios": [],
    }

    for scenario in scenarios:
        scenario_started = time.perf_counter()
        context = build_default_context()
        scenario_out: dict[str, Any] = {
            "id": scenario["id"],
            "question": scenario["question"],
            "steps": [],
        }

        for idx, step in enumerate(scenario.get("steps", []), start=1):
            step_started = time.perf_counter()
            logical = step["logical_tool"]
            args = substitute_templates(step.get("arguments", {}), context)
            orchestration = orchestrator.execute(
                requested_logical_tool=logical,
                arguments=args,
                subagents=subagents,
                preferred_subagent=preferred_subagent_for(logical),
            )

            step_out: dict[str, Any] = {
                "index": idx,
                "logical_tool": logical,
                "tool_name": orchestration.route.selected_tool_name,
                "selected_subagent": orchestration.route.selected_subagent,
                "arguments": args,
            }

            if orchestration.status != "ok":
                step_out["status"] = "tool_not_available"
                step_out["error"] = orchestration.error
                step_out["duration_ms"] = round((time.perf_counter() - step_started) * 1000, 2)
                scenario_out["steps"].append(step_out)
                break

            res = orchestration.response or {}
            step_out["response"] = res
            step_out["status"] = "ok" if live else "planned"

            if live:
                error = res.get("error")
                if error:
                    step_out["status"] = "error"
                    if error.get("code") == -32042:
                        step_out["consent_url"] = (
                            error.get("data", {}).get("elicitations", [{}])[0].get("url")
                        )
                    step_out["duration_ms"] = round((time.perf_counter() - step_started) * 1000, 2)
                    scenario_out["steps"].append(step_out)
                    break
                result_is_error = bool(res.get("result", {}).get("isError"))
                if result_is_error:
                    step_out["status"] = "error_result"
                    step_out["duration_ms"] = round((time.perf_counter() - step_started) * 1000, 2)
                    scenario_out["steps"].append(step_out)
                    break

            if logical == "atlassian.list_accessible_resources":
                cloud_id = extract_cloud_id(res)
                if cloud_id:
                    context["cloudId"] = cloud_id
                    step_out["cloudId"] = cloud_id

            step_out["duration_ms"] = round((time.perf_counter() - step_started) * 1000, 2)
            scenario_out["steps"].append(step_out)

        scenario_out["duration_ms"] = round((time.perf_counter() - scenario_started) * 1000, 2)
        report["scenarios"].append(scenario_out)

    return report


def print_human_summary(report: dict[str, Any]) -> None:
    print(f"GATEWAY_URL={report['gateway_url']}")
    print(f"LIVE_MODE={report['live']}")
    print(f"TOOLS_DISCOVERED={len(report['tools'])}")
    for name in report["tools"]:
        print(f"- {name}")
    print("")

    for scenario in report["scenarios"]:
        print(f"SCENARIO={scenario['id']}")
        print(f"QUESTION={scenario['question']}")
        for step in scenario["steps"]:
            print(
                "STEP="
                f"{step['index']} "
                f"logical={step['logical_tool']} "
                f"tool={step['tool_name']} "
                f"subagent={step.get('selected_subagent')} "
                f"status={step['status']}"
            )
            if "consent_url" in step:
                print(f"CONSENT_URL={step['consent_url']}")
            if step.get("status") == "tool_not_available":
                print(f"ROUTE_ERROR={json.dumps(step.get('error', {}), ensure_ascii=True)}")
        print("")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run multi-target MCP E2E scenarios")
    parser.add_argument("--profile", default=os.getenv("AWS_PROFILE", "<AWS_PROFILE>"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "eu-central-1"))
    parser.add_argument("--gateway-id", required=True)
    parser.add_argument(
        "--scenario-file",
        default="tests/e2e/data/multi_target_complex_questions.json",
        help="Path to scenario JSON file",
    )
    parser.add_argument(
        "--mode",
        choices=["live", "dry-run"],
        default="dry-run",
        help="live executes tools/call; dry-run only prints planned invocations",
    )
    parser.add_argument(
        "--output",
        default="/tmp/multi_target_e2e_report.json",
        help="Where to write JSON report",
    )
    parser.add_argument(
        "--agent-identity-token",
        default=None,
        help="User JWT access token for USER_FEDERATION-aligned execution",
    )
    args = parser.parse_args()

    scenario_path = Path(args.scenario_file)
    scenarios = json.loads(scenario_path.read_text())

    cfg = discover_gateway_auth(args.profile, args.region, args.gateway_id)
    if args.agent_identity_token:
        token = args.agent_identity_token
    else:
        if args.mode == "live":
            raise RuntimeError(
                "Live USER_FEDERATION execution requires --agent-identity-token (user JWT). "
                "Refusing client_credentials fallback to prevent consent loops."
            )
        client_secret = get_cognito_client_secret(args.profile, args.region, cfg.pool_id, cfg.client_id)
        token = get_cognito_access_token(
            region=args.region,
            pool_id=cfg.pool_id,
            client_id=cfg.client_id,
            client_secret=client_secret,
            scope=cfg.scope,
        )

    tools = discover_tools(cfg.gateway_url, token)
    report = run_scenarios(
        gateway_url=cfg.gateway_url,
        token=token,
        tools=tools,
        scenarios=scenarios,
        live=(args.mode == "live"),
    )

    out_path = Path(args.output)
    out_path.write_text(json.dumps(report, indent=2))
    print_human_summary(report)
    print(f"REPORT_FILE={out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
