#!/usr/bin/env python3
"""One-shot consent guard for Atlassian OAuth via AgentCore Gateway.

Prevents the request_uri churn loop by reusing one pending consent URL until
it succeeds or is explicitly replaced.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import boto3
import requests

STATE_PATH = Path("/tmp/atlassian_consent_guard_state.json")


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

    gateway_url = props["GatewayUrl"]
    client_id = custom["AllowedClients"][0]
    scope = custom["AllowedScopes"][0]
    return gateway_url, pool_id, client_id, scope


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


def gateway_call(gateway_url: str, token: str) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-11-25",
    }

    requests.post(
        gateway_url,
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "atlassian-consent-guard", "version": "1.0"},
            },
        },
        timeout=20,
    )

    call = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "atlassian-openapi-dev3___listAtlassianAccessibleResources", "arguments": {}},
    }
    return requests.post(gateway_url, headers=headers, json=call, timeout=30).json()


def save_state(data: dict) -> None:
    STATE_PATH.write_text(json.dumps(data, indent=2))


def load_state() -> dict | None:
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Atlassian consent loop guard")
    parser.add_argument("--profile", default=os.getenv("AWS_PROFILE", "<AWS_PROFILE>"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "eu-central-1"))
    parser.add_argument("--gateway-id", default="<GATEWAY_ID>")
    parser.add_argument("--force-new", action="store_true", help="Ignore pending consent and generate a new one")
    parser.add_argument("--max-pending-age-sec", type=int, default=900)
    args = parser.parse_args()

    old = load_state()
    now = int(time.time())
    if old and not args.force_new and old.get("status") == "pending":
        age = now - int(old.get("created_at", now))
        if age <= args.max_pending_age_sec:
            print("STATUS=pending_existing")
            print(f"AGE_SEC={age}")
            print(f"CONSENT_URL={old.get('consent_url', '')}")
            return 10

    gateway_url, pool_id, client_id, scope = discover_gateway_auth(args.profile, args.region, args.gateway_id)
    secret = get_client_secret(args.profile, args.region, pool_id, client_id)
    token = get_cc_token(args.region, pool_id, client_id, secret, scope)
    response = gateway_call(gateway_url, token)

    result = response.get("result")
    if result and not result.get("isError"):
        state = {
            "status": "authorized",
            "created_at": now,
            "gateway_url": gateway_url,
            "token": token,
            "response": response,
        }
        save_state(state)
        print("STATUS=authorized")
        print(f"STATE_FILE={STATE_PATH}")
        return 0

    err = response.get("error", {})
    consent_url = (
        err.get("data", {}).get("elicitations", [{}])[0].get("url")
        if isinstance(err, dict)
        else None
    )
    state = {
        "status": "pending",
        "created_at": now,
        "gateway_url": gateway_url,
        "token": token,
        "response": response,
        "consent_url": consent_url,
    }
    save_state(state)
    print("STATUS=pending_new")
    print(f"CONSENT_URL={consent_url}")
    print(f"STATE_FILE={STATE_PATH}")
    return 11


if __name__ == "__main__":
    raise SystemExit(main())
