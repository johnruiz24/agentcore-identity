#!/usr/bin/env python3
"""
Discover MCP tools currently exposed by AgentCore Gateway and highlight Atlassian tools.

Flow:
1) Discover gateway URL + Cognito authorizer contract via CloudControl
2) Mint Cognito client-credentials token
3) Call MCP initialize + tools/list
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass

import boto3


@dataclass
class GatewayAuthConfig:
    gateway_url: str
    pool_id: str
    client_id: str
    scope: str


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


def mcp_jsonrpc(url: str, token: str, body: dict) -> dict:
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
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover tools exposed by AgentCore Gateway")
    parser.add_argument("--profile", default=os.getenv("AWS_PROFILE", "<AWS_PROFILE>"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "eu-central-1"))
    parser.add_argument("--gateway-id", required=True)
    args = parser.parse_args()

    cfg = discover_gateway_auth(args.profile, args.region, args.gateway_id)
    client_secret = get_cognito_client_secret(args.profile, args.region, cfg.pool_id, cfg.client_id)
    token = get_cognito_access_token(
        region=args.region,
        pool_id=cfg.pool_id,
        client_id=cfg.client_id,
        client_secret=client_secret,
        scope=cfg.scope,
    )

    init_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "tool-discovery", "version": "1.0"},
        },
    }
    tools_body = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

    init_res = mcp_jsonrpc(cfg.gateway_url, token, init_body)
    tools_res = mcp_jsonrpc(cfg.gateway_url, token, tools_body)
    tools = tools_res.get("result", {}).get("tools", [])
    names = [t.get("name", "") for t in tools]
    atl = [n for n in names if n.startswith("atlassian-openapi-")]

    print(f"GATEWAY_URL={cfg.gateway_url}")
    print(f"TOTAL_TOOLS={len(names)}")
    print("TOOL_NAMES=")
    for name in names:
        print(f"- {name}")
    print("")
    print(f"ATLASSIAN_TOOLS={len(atl)}")
    for name in atl:
        print(f"- {name}")
    print("")
    print("INITIALIZE_RESULT=")
    print(json.dumps(init_res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

