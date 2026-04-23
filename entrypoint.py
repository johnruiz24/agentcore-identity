#!/usr/bin/env python3
"""
Bedrock AgentCore Identity Service - FastAPI runtime entrypoint.
"""

import os
import re
import sys
from datetime import datetime, timedelta
import json
from typing import Any, Dict
from zoneinfo import ZoneInfo

import boto3
from dotenv import load_dotenv
from fastapi import FastAPI, Request
import requests
import uvicorn

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

# Load environment
load_dotenv()

# Import service logic
from src.auth.session_handler import SessionHandler
from src.storage.dynamodb_vault import DynamoDBCredentialVault
from src.storage.dynamodb_audit import DynamoDBauditStore


app = FastAPI(title="bedrock-agentcore-identity", version="1.0.0")

# Lazy-initialized services to keep /health up even when AWS deps are unavailable.
session_handler = None
credential_vault = None
audit_store = None

AGENT_SYSTEM_PROMPT = (
    "You are a calendar orchestration agent. "
    "Your task is to transform user intent into a Google Calendar tool call "
    "and return the tool execution result."
)

DEFAULT_GATEWAY_URL = os.getenv(
    "GATEWAY_MCP_URL",
    "<GATEWAY_URL>",
)
DEFAULT_TOOL_NAME = os.getenv(
    "CALENDAR_TOOL_NAME",
    "google-calendar-openapi-dev3___createCalendarEvent",
)
MCP_VERSION = "2025-11-25"
RESOURCE_PROVIDER_NAME = os.getenv("RESOURCE_PROVIDER_NAME", "google-oauth-client-q7jdi")
RESOURCE_PROVIDER_SCOPE = os.getenv(
    "RESOURCE_PROVIDER_SCOPE", "https://www.googleapis.com/auth/calendar.events"
)
RESOURCE_OAUTH_RETURN_URL = os.getenv(
    "RESOURCE_OAUTH_RETURN_URL",
    "http://localhost:8765/callback",
)
ENABLE_RESOURCE_OAUTH_CHECK = os.getenv("ENABLE_RESOURCE_OAUTH_CHECK", "false").lower() == "true"
PLANNER_MODEL_ID = os.getenv(
    "PLANNER_MODEL_ID",
    "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
)

def _ensure_services() -> None:
    global session_handler, credential_vault, audit_store
    if session_handler is None:
        session_handler = SessionHandler(
            table_name=os.getenv("DYNAMODB_TABLE_SESSIONS", "agentcore-identity-sessions")
        )
    if credential_vault is None:
        credential_vault = DynamoDBCredentialVault(region=os.getenv("AWS_REGION", "eu-central-1"))
    if audit_store is None:
        audit_store = DynamoDBauditStore(region=os.getenv("AWS_REGION", "eu-central-1"))


def _plan_calendar_tool_args_llm(prompt: str, timezone: str) -> Dict[str, Any] | None:
    now = datetime.now(ZoneInfo(timezone)).isoformat()
    system = (
        "Convert user calendar requests to JSON for Google Calendar tool. "
        "Return ONLY valid JSON with keys exactly: calendarId, summary, description, start, end. "
        "Use ISO-8601 dateTime with timezone. If duration is omitted, use 60 minutes."
    )
    user = (
        f"Timezone: {timezone}\n"
        f"Current datetime: {now}\n"
        f"User request: {prompt}\n"
        "Output format:\n"
        "{\"calendarId\":\"primary\",\"summary\":\"...\",\"description\":\"...\","
        "\"start\":{\"dateTime\":\"...\",\"timeZone\":\"...\"},"
        "\"end\":{\"dateTime\":\"...\",\"timeZone\":\"...\"}}"
    )
    try:
        brt = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "eu-central-1"))
        resp = brt.converse(
            modelId=PLANNER_MODEL_ID,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": 400, "temperature": 0},
        )
        text = ""
        for block in resp.get("output", {}).get("message", {}).get("content", []):
            if "text" in block:
                text += block["text"]
        text = text.strip()
        if not text:
            return None
        if text.startswith("```"):
            text = text.strip("`")
            text = text.replace("json", "", 1).strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        required = {"calendarId", "summary", "description", "start", "end"}
        if not required.issubset(data.keys()):
            return None
        if not isinstance(data.get("start"), dict) or not isinstance(data.get("end"), dict):
            return None
        if "dateTime" not in data["start"] or "dateTime" not in data["end"]:
            return None
        data["start"]["timeZone"] = timezone
        data["end"]["timeZone"] = timezone
        return data
    except Exception:
        return None


def _plan_calendar_tool_args(prompt: str, timezone: str) -> Dict[str, Any]:
    llm_plan = _plan_calendar_tool_args_llm(prompt, timezone)
    if llm_plan is not None:
        return llm_plan

    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    base_date = now.date()
    if "tomorrow" in prompt.lower():
        base_date = (now + timedelta(days=1)).date()

    # Minimal parser for patterns like "2-3pm", fallback 14:00-15:00.
    m = re.search(r"\b(\d{1,2})\s*-\s*(\d{1,2})\s*(am|pm)\b", prompt.lower())
    if m:
        start_hour = int(m.group(1)) % 12
        end_hour = int(m.group(2)) % 12
        if m.group(3) == "pm":
            start_hour += 12
            end_hour += 12
    else:
        start_hour, end_hour = 14, 15

    start_dt = datetime(base_date.year, base_date.month, base_date.day, start_hour, 0, tzinfo=tz)
    end_dt = datetime(base_date.year, base_date.month, base_date.day, end_hour, 0, tzinfo=tz)
    summary = prompt.strip()[:80] or "AgentCore Calendar Event"

    return {
        "calendarId": "primary",
        "summary": summary,
        "description": "Created by AgentCore runtime orchestration",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": timezone},
    }


def _mcp_jsonrpc_call(
    gateway_url: str,
    bearer_token: str,
    rpc_id: int,
    method: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    response = requests.post(
        gateway_url,
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": MCP_VERSION,
        },
        json={"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params},
        timeout=30,
    )
    try:
        return response.json()
    except Exception:
        return {"error": {"code": response.status_code, "message": response.text}}


def _ensure_resource_oauth(
    workload_identity_token: str,
    *,
    force_authentication: bool = False,
) -> Dict[str, Any]:
    client = boto3.client("bedrock-agentcore", region_name=os.getenv("AWS_REGION", "eu-central-1"))
    return client.get_resource_oauth2_token(
        workloadIdentityToken=workload_identity_token,
        resourceCredentialProviderName=RESOURCE_PROVIDER_NAME,
        scopes=[RESOURCE_PROVIDER_SCOPE],
        oauth2Flow="USER_FEDERATION",
        resourceOauth2ReturnUrl=RESOURCE_OAUTH_RETURN_URL,
        forceAuthentication=force_authentication,
    )


def _run_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        return {"status": "error", "message": "Missing prompt"}

    gateway_token = (
        payload.get("gateway_bearer_token")
        or payload.get("user_token")
        or payload.get("access_token")
    )
    if not gateway_token:
        return {"status": "error", "message": "Missing gateway_bearer_token/user_token/access_token"}

    gateway_url = payload.get("gateway_url", DEFAULT_GATEWAY_URL)
    tool_name = payload.get("tool_name", DEFAULT_TOOL_NAME)
    timezone = payload.get("time_zone", "Europe/Berlin")
    tool_args = payload.get("tool_arguments") or _plan_calendar_tool_args(prompt, timezone)

    if ENABLE_RESOURCE_OAUTH_CHECK:
        try:
            token_state = _ensure_resource_oauth(gateway_token, force_authentication=False)
            if token_state.get("authorizationUrl"):
                return {
                    "status": "needs_consent",
                    "system_prompt": AGENT_SYSTEM_PROMPT,
                    "elicitations": [{"url": token_state["authorizationUrl"]}],
                    "session_uri": token_state.get("sessionUri"),
                    "session_status": token_state.get("sessionStatus"),
                    "tool_name": tool_name,
                    "tool_arguments": tool_args,
                }
        except Exception as exc:
            return {"status": "error", "stage": "resource_oauth_check", "message": str(exc)}

    init_resp = _mcp_jsonrpc_call(
        gateway_url,
        gateway_token,
        1,
        "initialize",
        {
            "protocolVersion": MCP_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "agentcore-runtime-agent", "version": "1.0"},
        },
    )
    if "error" in init_resp:
        return {"status": "error", "stage": "initialize", "system_prompt": AGENT_SYSTEM_PROMPT, "response": init_resp}

    call_resp = _mcp_jsonrpc_call(
        gateway_url,
        gateway_token,
        2,
        "tools/call",
        {"name": tool_name, "arguments": tool_args},
    )

    if (
        "result" in call_resp
        and isinstance(call_resp["result"], dict)
        and call_resp["result"].get("isError")
        and ENABLE_RESOURCE_OAUTH_CHECK
    ):
        content = call_resp["result"].get("content", [])
        text = ""
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text += str(item.get("text", ""))
        if "401" in text or "Invalid Credentials" in text or "UNAUTHENTICATED" in text:
            try:
                token_state = _ensure_resource_oauth(gateway_token, force_authentication=True)
                if token_state.get("authorizationUrl"):
                    return {
                        "status": "needs_consent",
                        "system_prompt": AGENT_SYSTEM_PROMPT,
                        "elicitations": [{"url": token_state["authorizationUrl"]}],
                        "session_uri": token_state.get("sessionUri"),
                        "session_status": token_state.get("sessionStatus"),
                        "tool_name": tool_name,
                        "tool_arguments": tool_args,
                    }
            except Exception as exc:
                return {"status": "error", "stage": "resource_oauth_refresh", "message": str(exc)}

    if "error" in call_resp and call_resp["error"].get("code") == -32042:
        elicitations = call_resp["error"].get("data", {}).get("elicitations", [])
        return {
            "status": "needs_consent",
            "system_prompt": AGENT_SYSTEM_PROMPT,
            "elicitations": elicitations,
            "tool_name": tool_name,
            "tool_arguments": tool_args,
        }

    return {
        "status": "success",
        "system_prompt": AGENT_SYSTEM_PROMPT,
        "tool_name": tool_name,
        "tool_arguments": tool_args,
        "response": call_resp,
    }


@app.get("/health")
async def health() -> Dict[str, str]:
    return {
        "status": "healthy",
        "service": "bedrock-agentcore-identity",
        "version": "1.0.0",
    }


@app.get("/info")
async def info() -> Dict[str, str]:
    return {
        "service": "bedrock-agentcore-identity",
        "version": "1.0.0",
        "description": "OAuth2 Credential Management for Bedrock Agents",
    }


def _handle_action_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Execute action payload and return normalized response."""
    try:
        _ensure_services()
        action = payload.get("action")

        if action in {"agent_run", "agent_orchestrate_calendar"} or "prompt" in payload:
            return _run_agent(payload)

        if action == "validate_token":
            session_id = payload.get("session_id")
            credentials = credential_vault.retrieve_credential(session_id)
            return {"status": "success", "valid": credentials is not None, "credentials": credentials}

        if action == "get_credentials":
            session_id = payload.get("session_id")
            credentials = credential_vault.retrieve_credential(session_id)
            return {"status": "success", "credentials": credentials}

        if action == "store_credentials":
            session_id = payload.get("session_id")
            credentials = payload.get("credentials")
            credential_vault.store_credential(session_id, credentials)
            return {"status": "success", "message": "Credentials stored"}

        if action == "audit_log":
            audit_store.log_entry(
                session_id=payload.get("session_id"),
                user_id=payload.get("user_id"),
                action=payload.get("action_type"),
                resource=payload.get("resource"),
                result=payload.get("result"),
                details=payload.get("details"),
            )
            return {"status": "success", "message": "Audit logged"}

        return {"status": "error", "message": f"Unknown action: {action}"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _normalize_payload(payload: Any) -> Dict[str, Any]:
    """
    AgentCore can deliver payload as object, JSON string, or wrapped dict.
    Normalize all known shapes to a dict so runtime never fails with 422.
    """
    if isinstance(payload, dict):
        if isinstance(payload.get("payload"), str):
            try:
                parsed = json.loads(payload["payload"])
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        if isinstance(payload.get("body"), str):
            try:
                parsed = json.loads(payload["body"])
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return payload
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {"prompt": payload}
    return {"raw_payload": payload}


async def _normalize_request_payload(request: Request) -> Dict[str, Any]:
    raw = await request.body()
    if not raw:
        return {}
    text = raw.decode("utf-8", errors="ignore").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {"prompt": text}
    return _normalize_payload(parsed)


@app.post("/invoke")
async def invoke(request: Request) -> Dict[str, Any]:
    """Compatibility endpoint used by local tooling."""
    return _handle_action_payload(await _normalize_request_payload(request))


@app.post("/")
async def invoke_root(request: Request) -> Dict[str, Any]:
    """AgentCore runtime compatibility endpoint."""
    return _handle_action_payload(await _normalize_request_payload(request))


@app.post("/invocations")
async def invoke_agentcore(request: Request) -> Dict[str, Any]:
    """AgentCore runtime compatibility endpoint."""
    return _handle_action_payload(await _normalize_request_payload(request))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
