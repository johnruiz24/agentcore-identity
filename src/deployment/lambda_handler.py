"""
Lambda handler for Bedrock Agent tool invocations

Handles all tool calls from the Bedrock Agent and routes them to the appropriate
AuthTools or IdentityTools handlers.
"""

import json
import logging
import os
from typing import Any, Dict

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Import tool handlers
from src.agents.tools.auth_tools import AuthTools
from src.agents.tools.identity_tools import IdentityTools
from src.auth.oauth2_manager import OAuth2Manager
from src.auth.session_handler import SessionHandler


def get_oauth2_manager() -> OAuth2Manager:
    """Initialize OAuth2Manager from environment"""
    return OAuth2Manager(
        user_pool_id=os.environ.get("COGNITO_USER_POOL_ID", ""),
        client_id=os.environ.get("COGNITO_CLIENT_ID", ""),
        client_secret=os.environ.get("COGNITO_CLIENT_SECRET", ""),
        domain=os.environ.get("COGNITO_DOMAIN", ""),
    )


def get_session_handler() -> SessionHandler:
    """Initialize SessionHandler from environment"""
    return SessionHandler(
        table_name=os.environ.get(
            "DYNAMODB_TABLE_SESSIONS", "agentcore-identity-sessions-sandbox"
        )
    )


async def handle_auth_tool(
    tool_name: str, parameters: Dict[str, Any], auth_tools: AuthTools
) -> Dict[str, Any]:
    """Handle AuthTools invocations"""
    logger.info(f"Handling auth tool: {tool_name}")

    if tool_name == "validate_token":
        result = await auth_tools.validate_token(parameters["token"])
        return result
    elif tool_name == "refresh_session":
        result = await auth_tools.refresh_session(parameters["session_id"])
        return result
    elif tool_name == "get_token_info":
        result = await auth_tools.get_token_info(parameters["session_id"])
        return result
    elif tool_name == "revoke_session":
        result = await auth_tools.revoke_session(parameters["session_id"])
        return result
    else:
        raise ValueError(f"Unknown auth tool: {tool_name}")


async def handle_identity_tool(
    tool_name: str, parameters: Dict[str, Any], identity_tools: IdentityTools
) -> Dict[str, Any]:
    """Handle IdentityTools invocations"""
    logger.info(f"Handling identity tool: {tool_name}")

    if tool_name == "get_user_profile":
        result = await identity_tools.get_user_profile(parameters["session_id"])
        return result
    elif tool_name == "list_user_sessions":
        result = await identity_tools.list_user_sessions(parameters["session_id"])
        return result
    elif tool_name == "get_session_details":
        result = await identity_tools.get_session_details(parameters["session_id"])
        return result
    elif tool_name == "check_scope":
        result = await identity_tools.check_scope(
            parameters["session_id"], parameters["required_scope"]
        )
        return result
    else:
        raise ValueError(f"Unknown identity tool: {tool_name}")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for Bedrock Agent tool invocations

    Event format from Bedrock Agent:
    {
        "toolName": "validate_token" | "get_user_profile" | etc.,
        "parameters": {
            "token": "...",
            "session_id": "...",
            ...
        }
    }
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        tool_name = event.get("toolName", "")
        parameters = event.get("parameters", {})

        # Initialize managers
        oauth2_manager = get_oauth2_manager()
        session_handler = get_session_handler()

        # Initialize tool handlers
        auth_tools = AuthTools(session_handler, oauth2_manager)
        identity_tools = IdentityTools(session_handler, oauth2_manager)

        # Determine which tool to call
        if tool_name in [
            "validate_token",
            "refresh_session",
            "get_token_info",
            "revoke_session",
        ]:
            # Use sync wrapper for auth tools
            import asyncio

            result = asyncio.run(
                handle_auth_tool(tool_name, parameters, auth_tools)
            )
        elif tool_name in [
            "get_user_profile",
            "list_user_sessions",
            "get_session_details",
            "check_scope",
        ]:
            # Use sync wrapper for identity tools
            import asyncio

            result = asyncio.run(
                handle_identity_tool(tool_name, parameters, identity_tools)
            )
        else:
            logger.error(f"Unknown tool: {tool_name}")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"Unknown tool: {tool_name}"}),
            }

        logger.info(f"Tool execution successful: {tool_name}")

        return {
            "statusCode": 200,
            "body": json.dumps({"result": result, "tool": tool_name}),
        }

    except Exception as e:
        logger.error(f"Error handling tool invocation: {str(e)}", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


# For local testing
if __name__ == "__main__":
    test_event = {
        "toolName": "validate_token",
        "parameters": {"token": "test-token-123"},
    }

    class Context:
        pass

    result = handler(test_event, Context())
    print(json.dumps(result, indent=2))
