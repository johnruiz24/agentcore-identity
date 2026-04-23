#!/usr/bin/env python3
"""
BEDROCK AGENTCORE IDENTITY + RUNTIME + GATEWAY EXAMPLE
Complete working example showing how Identity, Runtime, and Gateway work together
with OAuth2 protocol to interact with MCPs and Agents.
"""

import os
import json
import asyncio
from typing import Dict, Any
from datetime import datetime, timedelta

# Bedrock AgentCore
from bedrock_agentcore import BedrockAgentCoreApp

# OAuth2 & JWT
from jose import jwt, JWTError
from pydantic import BaseModel

# ============================================================================
# 1. IDENTITY SERVICE - OAuth2 Credential Management
# ============================================================================

class IdentityService:
    """
    Manages OAuth2 credentials and tokens for agents and MCPs.
    This is what authenticates inbound requests and stores outbound credentials.
    """

    def __init__(self, secret_key: str = "bedrock-agentcore-secret-key-do-not-use-in-prod"):
        self.secret_key = secret_key
        self.credentials_store: Dict[str, Dict[str, Any]] = {}
        self.tokens_store: Dict[str, Dict[str, Any]] = {}

    def create_oauth_token(self, agent_id: str, scopes: list) -> str:
        """
        Create JWT token for an agent to access external services (MCPs).
        This is OUTBOUND auth - agent using credentials to access external services.
        """
        payload = {
            "agent_id": agent_id,
            "scopes": scopes,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=1),
            "type": "agent_access"
        }
        token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        self.tokens_store[agent_id] = {
            "token": token,
            "scopes": scopes,
            "created_at": datetime.utcnow().isoformat()
        }
        return token

    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate token from caller (INBOUND auth).
        Used by Gateway to verify requests are authorized.
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return {"valid": True, "payload": payload}
        except JWTError:
            return {"valid": False, "error": "Invalid token"}

    def store_mcp_credentials(self, agent_id: str, provider: str, credentials: Dict) -> None:
        """
        Store OAuth2 credentials for MCPs (e.g., GitHub token, Slack token).
        These are credentials the AGENT uses to call EXTERNAL services.
        """
        if agent_id not in self.credentials_store:
            self.credentials_store[agent_id] = {}

        self.credentials_store[agent_id][provider] = {
            "provider": provider,
            "credentials": credentials,
            "stored_at": datetime.utcnow().isoformat()
        }

    def get_mcp_credentials(self, agent_id: str, provider: str) -> Dict:
        """Retrieve stored credentials for an agent to use with an MCP."""
        if agent_id in self.credentials_store and provider in self.credentials_store[agent_id]:
            return self.credentials_store[agent_id][provider]
        return None


# ============================================================================
# 2. GATEWAY SERVICE - OAuth2 Validation & Request Routing
# ============================================================================

class GatewayService:
    """
    Routes requests to agents through OAuth2 validation.
    This is the entry point - validates all incoming requests have valid OAuth2 tokens.
    """

    def __init__(self, identity_service: IdentityService):
        self.identity_service = identity_service

    def validate_request(self, token: str, required_scopes: list) -> Dict[str, Any]:
        """
        Validate incoming request has valid OAuth2 token with required scopes.
        This enforces security at the gateway level.
        """
        validation = self.identity_service.validate_token(token)

        if not validation["valid"]:
            return {"authorized": False, "error": "Invalid token"}

        payload = validation["payload"]
        agent_scopes = payload.get("scopes", [])

        # Check if agent has all required scopes
        missing_scopes = [s for s in required_scopes if s not in agent_scopes]
        if missing_scopes:
            return {"authorized": False, "error": f"Missing scopes: {missing_scopes}"}

        return {
            "authorized": True,
            "agent_id": payload.get("agent_id"),
            "scopes": agent_scopes
        }


# ============================================================================
# 3. RUNTIME SERVICE - Agent Execution with Bedrock AgentCore
# ============================================================================

# Create the BedrockAgentCore app - this is the RUNTIME
app = BedrockAgentCoreApp()

# Initialize services
identity_service = IdentityService()
gateway_service = GatewayService(identity_service)


class InvokeAgentRequest(BaseModel):
    """Request to invoke an agent."""
    agent_id: str
    oauth_token: str  # Token validating who's calling us
    action: str
    parameters: Dict[str, Any]
    mcp_provider: str = None  # If agent needs to call an MCP


@app.entrypoint
def bedrock_agentcore_identity(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    MAIN ENTRYPOINT - This is what Bedrock AgentCore Runtime calls.
    It receives requests, validates OAuth2, and executes agent logic.
    """

    print(f"\n{'='*70}")
    print(f"BEDROCK AGENTCORE RUNTIME ENTRYPOINT CALLED")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print(f"{'='*70}\n")

    try:
        agent_id = payload.get("agent_id")
        oauth_token = payload.get("oauth_token")
        action = payload.get("action")
        parameters = payload.get("parameters", {})
        mcp_provider = payload.get("mcp_provider")

        # STEP 1: Gateway validates the OAuth2 token (INBOUND AUTH)
        print(f"[GATEWAY] Validating OAuth2 token for agent: {agent_id}")
        auth_result = gateway_service.validate_request(
            oauth_token,
            required_scopes=["agent:invoke", "mcp:access"]
        )

        if not auth_result["authorized"]:
            return {
                "status": "error",
                "error": auth_result.get("error"),
                "code": 401
            }

        print(f"[GATEWAY] ✓ Token valid. Agent scopes: {auth_result['scopes']}")

        # STEP 2: Execute agent logic
        print(f"\n[RUNTIME] Executing agent action: {action}")

        if action == "list_mcps":
            # List available MCPs that this agent can access
            result = {
                "status": "success",
                "agent_id": agent_id,
                "available_mcps": ["github_mcp", "slack_mcp", "notion_mcp"],
                "authorized_scopes": auth_result["scopes"]
            }

        elif action == "call_mcp":
            # Agent wants to call an external MCP
            print(f"[AGENT] Requesting to call MCP: {mcp_provider}")

            # STEP 3: Retrieve stored credentials for MCP (OUTBOUND AUTH)
            mcp_creds = identity_service.get_mcp_credentials(agent_id, mcp_provider)

            if not mcp_creds:
                return {
                    "status": "error",
                    "error": f"No credentials stored for MCP: {mcp_provider}",
                    "code": 404
                }

            print(f"[IDENTITY] ✓ Retrieved credentials for {mcp_provider}")

            # Simulate calling the MCP with the agent's credentials
            mcp_result = {
                "mcp": mcp_provider,
                "authenticated_as": agent_id,
                "credentials_used": "stored_oauth_token",
                "mcp_response": f"Hello from {mcp_provider}! Agent {agent_id} is authenticated."
            }

            result = {
                "status": "success",
                "agent_id": agent_id,
                "action": "call_mcp",
                "mcp_provider": mcp_provider,
                "mcp_result": mcp_result
            }

        elif action == "store_credentials":
            # Store new credentials for an MCP
            print(f"[AGENT] Storing credentials for MCP: {mcp_provider}")

            credentials = parameters.get("credentials", {})
            identity_service.store_mcp_credentials(agent_id, mcp_provider, credentials)

            result = {
                "status": "success",
                "message": f"Credentials stored for {mcp_provider}",
                "agent_id": agent_id
            }

        else:
            result = {
                "status": "error",
                "error": f"Unknown action: {action}"
            }

        print(f"\n[RUNTIME] ✓ Agent execution complete")
        return result

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "code": 500
        }


# ============================================================================
# 4. HEALTH CHECK & INFO ENDPOINTS
# ============================================================================

@app.route("/ping")
async def ping():
    """Health check for Bedrock AgentCore Runtime."""
    return {
        "status": "healthy",
        "service": "bedrock-agentcore-identity-runtime",
        "version": "1.0.0"
    }


@app.route("/info")
async def info():
    """Service information."""
    return {
        "service": "Bedrock AgentCore Identity + Runtime + Gateway",
        "components": {
            "identity": "OAuth2 credential management",
            "gateway": "Request authorization & routing",
            "runtime": "Agent execution via Bedrock AgentCore"
        },
        "auth_protocol": "OAuth2 with JWT",
        "version": "1.0.0"
    }


# ============================================================================
# 5. EXAMPLE USAGE - How to interact with the system
# ============================================================================

def example_usage():
    """
    Demonstrates how to use Bedrock AgentCore Identity + Runtime + Gateway
    to invoke agents and access MCPs via OAuth2.
    """

    print("\n" + "="*70)
    print("BEDROCK AGENTCORE IDENTITY EXAMPLE - Complete Workflow")
    print("="*70 + "\n")

    # STEP 1: Identity Service creates a token for an agent
    print("STEP 1: Create OAuth2 token for agent")
    print("-" * 70)
    agent_token = identity_service.create_oauth_token(
        agent_id="my-agent-001",
        scopes=["agent:invoke", "mcp:access", "mcp:github", "mcp:slack"]
    )
    print(f"✓ Token created: {agent_token[:50]}...\n")

    # STEP 2: Agent stores credentials for MCPs it will access
    print("STEP 2: Store MCP credentials in Identity Service")
    print("-" * 70)
    identity_service.store_mcp_credentials(
        agent_id="my-agent-001",
        provider="github_mcp",
        credentials={"token": "ghp_xxxxxxxxxxxx", "username": "agent-user"}
    )
    print("✓ GitHub credentials stored\n")

    identity_service.store_mcp_credentials(
        agent_id="my-agent-001",
        provider="slack_mcp",
        credentials={"token": "xoxb-xxxxxxxxxxxx", "workspace": "my-workspace"}
    )
    print("✓ Slack credentials stored\n")

    # STEP 3: Invoke agent through Gateway + Runtime
    print("STEP 3: Invoke agent through Gateway (OAuth2 validation)")
    print("-" * 70)

    # Gateway validates token
    print("Gateway validating request...")
    validation = gateway_service.validate_request(agent_token, ["agent:invoke", "mcp:access"])
    print(f"✓ Gateway authorized: {validation['authorized']}\n")

    # STEP 4: Runtime executes the agent
    print("STEP 4: Runtime executes agent action")
    print("-" * 70)

    # List available MCPs
    list_mcps_payload = {
        "agent_id": "my-agent-001",
        "oauth_token": agent_token,
        "action": "list_mcps",
        "parameters": {}
    }
    result = bedrock_agentcore_identity(list_mcps_payload)
    print(f"✓ Result: {json.dumps(result, indent=2)}\n")

    # STEP 5: Agent calls an MCP
    print("STEP 5: Agent calls MCP via Runtime (using stored credentials)")
    print("-" * 70)

    call_mcp_payload = {
        "agent_id": "my-agent-001",
        "oauth_token": agent_token,
        "action": "call_mcp",
        "mcp_provider": "github_mcp",
        "parameters": {"repo": "myrepo"}
    }
    result = bedrock_agentcore_identity(call_mcp_payload)
    print(f"✓ Result: {json.dumps(result, indent=2)}\n")

    print("="*70)
    print("EXAMPLE COMPLETE")
    print("="*70)
    print("\nKEY POINTS:")
    print("1. Identity Service manages OAuth2 tokens and MCP credentials")
    print("2. Gateway validates all inbound requests (INBOUND AUTH)")
    print("3. Runtime executes agents within Bedrock AgentCore")
    print("4. Agents access MCPs using stored credentials (OUTBOUND AUTH)")
    print("5. Everything flows through OAuth2 protocol\n")


if __name__ == "__main__":
    # Run example
    example_usage()

    # Uncomment to start the Bedrock AgentCore runtime server
    # print("\nStarting Bedrock AgentCore Runtime on port 8080...")
    # app.run(port=8080, host="0.0.0.0")
