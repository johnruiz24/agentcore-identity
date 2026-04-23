#!/usr/bin/env python3
"""Atlassian 20Q via AgentCore Gateway with explicit session binding.

Flow:
1) start  -> initialize + first tools/call (may emit consent URL), persist state
2) finish -> call CompleteResourceTokenAuth(sessionUri, userIdentifier), verify access,
             run 20Q evidence runner
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import boto3
import requests

STATE_FILE_DEFAULT = "/tmp/atlassian_20q_session_binding_state.json"


def discover_gateway_auth(profile: str, region: str, gateway_id: str) -> tuple[str, str, str, str]:
    cloudcontrol = boto3.Session(profile_name=profile, region_name=region).client("cloudcontrol")
    res = cloudcontrol.get_resource(TypeName="AWS::BedrockAgentCore::Gateway", Identifier=gateway_id)
    props_raw = res["ResourceDescription"]["Properties"]
    props = json.loads(props_raw) if isinstance(props_raw, str) else props_raw
    custom = props["AuthorizerConfiguration"]["CustomJWTAuthorizer"]
    discovery_url = custom["DiscoveryUrl"].rstrip("/")
    parts = discovery_url.split("/")
    if len(parts) >= 3 and parts[-1] == "openid-configuration" and parts[-2] == ".well-known":
        pool_id = parts[-3]
    else:
        pool_id = parts[-1]
    return props["GatewayUrl"], pool_id, custom["AllowedClients"][0], custom["AllowedScopes"][0]


def get_client_secret(profile: str, region: str, pool_id: str, client_id: str) -> str:
    cognito = boto3.Session(profile_name=profile, region_name=region).client("cognito-idp")
    out = cognito.describe_user_pool_client(UserPoolId=pool_id, ClientId=client_id)
    return out["UserPoolClient"]["ClientSecret"]


def get_cc_token(region: str, pool_id: str, client_id: str, client_secret: str, scope: str) -> str:
    oidc_config_url = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/openid-configuration"
    with urllib.request.urlopen(oidc_config_url, timeout=20) as r:
        oidc = json.loads(r.read().decode("utf-8"))
    token_endpoint = oidc["token_endpoint"]
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": scope}).encode("utf-8")
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
        raise RuntimeError(f"No access_token in response: {payload}")
    return token


def jsonrpc(gateway_url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-11-25",
    }
    r = requests.post(gateway_url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()


def initialize(gateway_url: str, token: str) -> dict[str, Any]:
    return jsonrpc(
        gateway_url,
        token,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "atlassian-20q-session-binding", "version": "1.0"},
            },
        },
    )


def call_accessible_resources(gateway_url: str, token: str) -> dict[str, Any]:
    return jsonrpc(
        gateway_url,
        token,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "atlassian-openapi-dev3___listAtlassianAccessibleResources",
                "arguments": {},
            },
        },
    )


def extract_consent_url(resp: dict[str, Any]) -> str | None:
    try:
        return resp["error"]["data"]["elicitations"][0]["url"]
    except Exception:
        return None


def parse_session_uri_from_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    vals = qs.get("session_id")
    if not vals:
        return None
    return vals[0]


def parse_request_uri_from_consent_url(consent_url: str) -> str | None:
    parsed = urllib.parse.urlparse(consent_url)
    qs = urllib.parse.parse_qs(parsed.query)
    vals = qs.get("request_uri")
    if not vals:
        return None
    return urllib.parse.unquote(vals[0])


def cmd_start(args: argparse.Namespace) -> int:
    gateway_url, pool_id, client_id, scope = discover_gateway_auth(args.profile, args.region, args.gateway_id)
    client_secret = get_client_secret(args.profile, args.region, pool_id, client_id)
    token = get_cc_token(args.region, pool_id, client_id, client_secret, scope)

    initialize(gateway_url, token)
    resp = call_accessible_resources(gateway_url, token)

    state = {
        "gateway_url": gateway_url,
        "token": token,
        "profile": args.profile,
        "region": args.region,
        "gateway_id": args.gateway_id,
        "first_response": resp,
    }

    if "result" in resp and not resp["result"].get("isError"):
        state["status"] = "already_authorized"
        Path(args.state_file).write_text(json.dumps(state, indent=2))
        print("STATUS=already_authorized")
        print(f"STATE_FILE={args.state_file}")
        return 0

    consent_url = extract_consent_url(resp)
    if not consent_url:
        print(json.dumps(resp, indent=2))
        raise RuntimeError("Expected consent URL but none returned")

    session_uri = parse_request_uri_from_consent_url(consent_url)
    state["status"] = "consent_required"
    state["consent_url"] = consent_url
    state["session_uri"] = session_uri
    Path(args.state_file).write_text(json.dumps(state, indent=2))
    print("STATUS=consent_required")
    print(f"CONSENT_URL={consent_url}")
    print(f"SESSION_URI={session_uri}")
    print(f"STATE_FILE={args.state_file}")
    return 10


def cmd_finish(args: argparse.Namespace) -> int:
    st = json.loads(Path(args.state_file).read_text())
    gateway_url = st["gateway_url"]
    token = st["token"]
    region = st["region"]

    callback_session_uri = parse_session_uri_from_url(args.callback_url)
    session_uri = callback_session_uri or st.get("session_uri")
    if not session_uri:
        raise RuntimeError("No session URI found from callback URL or state file")

    data_plane = boto3.Session(profile_name=args.profile, region_name=region).client("bedrock-agentcore")
    complete_resp = data_plane.complete_resource_token_auth(
        sessionUri=session_uri,
        userIdentifier={"userToken": token},
    )

    initialize(gateway_url, token)
    check = call_accessible_resources(gateway_url, token)
    if "result" not in check or check["result"].get("isError"):
        raise RuntimeError(f"Post-complete call still failing: {json.dumps(check)}")

    out_json = args.output_json
    out_html = args.output_html
    cmd = [
        sys.executable,
        "scripts/run_atlassian_20q_rag_probe.py",
        "--state-file",
        args.state_file,
        "--output-json",
        out_json,
        "--output-html",
        out_html,
        "--max-results",
        str(args.max_results),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    print("COMPLETE_RESOURCE_TOKEN_AUTH_RESPONSE=" + json.dumps(complete_resp))
    print("POST_COMPLETE_ACCESS_CHECK=OK")
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr.rstrip(), file=sys.stderr)
        return proc.returncode

    st["status"] = "completed"
    st["callback_session_uri"] = callback_session_uri
    st["final_session_uri_used"] = session_uri
    st["complete_resource_token_auth_response"] = complete_resp
    st["output_json"] = out_json
    st["output_html"] = out_html
    Path(args.state_file).write_text(json.dumps(st, indent=2))
    print(f"OUTPUT_JSON={out_json}")
    print(f"OUTPUT_HTML={out_html}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Atlassian 20Q with explicit CompleteResourceTokenAuth flow")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", default=os.getenv("AWS_PROFILE", "<AWS_PROFILE>"))
    common.add_argument("--region", default=os.getenv("AWS_REGION", "eu-central-1"))
    common.add_argument("--gateway-id", default="<GATEWAY_ID>")
    common.add_argument("--state-file", default=STATE_FILE_DEFAULT)

    p_start = sub.add_parser("start", parents=[common], help="Start flow and emit single consent URL")
    p_start.set_defaults(func=cmd_start)

    p_finish = sub.add_parser("finish", parents=[common], help="Complete session binding and run 20Q")
    p_finish.add_argument("--callback-url", required=True, help="Final browser URL after consent (contains session_id)")
    p_finish.add_argument(
        "--output-json",
        default="/tmp/atlassian-20q-runtime-evidence.json",
    )
    p_finish.add_argument(
        "--output-html",
        default="/tmp/atlassian-20q-runtime-evidence.html",
    )
    p_finish.add_argument("--max-results", type=int, default=10)
    p_finish.set_defaults(func=cmd_finish)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
