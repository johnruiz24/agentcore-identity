#!/usr/bin/env python3
"""
Start Atlassian USER_FEDERATION OAuth through Bedrock AgentCore Identity.

Equivalent to agentcore_google_user_federation_flow.py but with Atlassian defaults.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass

import boto3
from bedrock_agentcore.services.identity import IdentityClient


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


async def run_flow(
    *,
    profile: str,
    region: str,
    gateway_id: str,
    provider_name: str,
    callback_url: str,
    scope: str,
    agent_identity_token: str | None,
    force_authentication: bool,
) -> str:
    cfg = discover_gateway_auth(profile, region, gateway_id)
    if not agent_identity_token:
        raise RuntimeError(
            "USER_FEDERATION requires --agent-identity-token (real user JWT). "
            "Refusing to fallback to client_credentials to avoid consent loops."
        )
    identity_token = agent_identity_token

    print(f"GATEWAY_URL={cfg.gateway_url}")
    print(f"POOL_ID={cfg.pool_id}")
    print(f"CLIENT_ID={cfg.client_id}")
    print(f"SCOPE={cfg.scope}")
    print("")

    auth_urls: list[str] = []

    def on_auth_url(url: str) -> None:
        auth_urls.append(url)
        print("OPEN_THIS_URL_IN_BROWSER:")
        print(url)
        print("")
        print("After consent, wait here; script will poll for token.")
        print("")

    identity = IdentityClient(region=region)
    token = await identity.get_token(
        provider_name=provider_name,
        scopes=[scope],
        agent_identity_token=identity_token,
        on_auth_url=on_auth_url,
        auth_flow="USER_FEDERATION",
        callback_url=callback_url,
        force_authentication=force_authentication,
    )
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AgentCore USER_FEDERATION Atlassian OAuth flow")
    parser.add_argument("--profile", default=os.getenv("AWS_PROFILE", "<AWS_PROFILE>"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "eu-central-1"))
    parser.add_argument("--gateway-id", required=True)
    parser.add_argument(
        "--provider-name",
        default="atlassian-oauth-client-a48bd",
    )
    parser.add_argument(
        "--callback-url",
        default="https://bedrock-agentcore.eu-central-1.amazonaws.com/identities/oauth2/callback",
    )
    parser.add_argument(
        "--provider-scope",
        default="read:jira-work",
    )
    parser.add_argument(
        "--agent-identity-token",
        default=None,
        help="JWT access token for a real user session (required for USER_FEDERATION success)",
    )
    parser.add_argument(
        "--force-authentication",
        action="store_true",
        help="Force provider re-consent even if a cached token already exists.",
    )
    args = parser.parse_args()

    try:
        token = asyncio.run(
            run_flow(
                profile=args.profile,
                region=args.region,
                gateway_id=args.gateway_id,
                provider_name=args.provider_name,
                callback_url=args.callback_url,
                scope=args.provider_scope,
                agent_identity_token=args.agent_identity_token,
                force_authentication=args.force_authentication,
            )
        )
        print("AGENTCORE_PROVIDER_ACCESS_TOKEN_OBTAINED=YES")
        print(f"ACCESS_TOKEN_PREFIX={token[:24]}...")
        return 0
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130
    except Exception as exc:
        print(f"FLOW_FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
