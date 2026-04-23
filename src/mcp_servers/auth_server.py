"""OAuth2 Scope provider MCP server."""

import logging
from typing import Any, Dict, List

from .base_server import MCPServer, Tool

logger = logging.getLogger(__name__)


class AuthServer(MCPServer):
    """MCP server providing OAuth2 scope information and utilities.

    Exposes tools for:
    - Retrieving user scopes
    - Listing available scopes
    - Validating scope combinations
    """

    def __init__(self, session_handler: Any):
        """Initialize auth server.

        Args:
            session_handler: SessionHandler instance
        """
        super().__init__("auth_server", session_handler)

        # Register tools
        self.register_tool(
            Tool(
                name="get_user_scopes",
                description="Get OAuth2 scopes for the current user",
                params_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                required_scopes=["openid"],
                handler=self._get_user_scopes,
            )
        )

        self.register_tool(
            Tool(
                name="list_available_scopes",
                description="List all available OAuth2 scopes in the system",
                params_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                required_scopes=["openid"],
                handler=self._list_available_scopes,
            )
        )

        self.register_tool(
            Tool(
                name="validate_scopes",
                description="Validate if a set of scopes is valid",
                params_schema={
                    "type": "object",
                    "properties": {
                        "scopes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of scopes to validate",
                        }
                    },
                    "required": ["scopes"],
                },
                required_scopes=["openid"],
                handler=self._validate_scopes,
            )
        )

    async def _get_user_scopes(
        self, params: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get scopes for the current user.

        Args:
            params: Parameters (empty)
            context: Execution context with session

        Returns:
            Dictionary with user scopes
        """
        session = context.get("session", {})

        logger.info(f"👤 Getting scopes for user: {session.get('user_id')}")

        return {
            "user_id": session.get("user_id"),
            "email": session.get("email"),
            "scopes": session.get("scopes", []),
            "scope_count": len(session.get("scopes", [])),
        }

    async def _list_available_scopes(
        self, params: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """List all available scopes.

        Args:
            params: Parameters (empty)
            context: Execution context

        Returns:
            Dictionary with available scopes
        """
        logger.info("📋 Listing available scopes")

        available_scopes = {
            "oidc": [
                {"name": "openid", "description": "OpenID Connect scope"},
                {"name": "profile", "description": "User profile information"},
                {"name": "email", "description": "User email address"},
            ],
            "bedrock": [
                {"name": "bedrock:agents:invoke", "description": "Invoke Bedrock agents"},
                {"name": "bedrock:agents:read", "description": "Read agent information"},
                {"name": "bedrock:agents:create", "description": "Create new agents"},
                {"name": "bedrock:agents:update", "description": "Update agent configuration"},
                {"name": "bedrock:agents:delete", "description": "Delete agents"},
            ],
            "mcp": [
                {"name": "mcp:resources:read", "description": "Read MCP resources"},
                {"name": "mcp:resources:create", "description": "Create MCP resources"},
                {"name": "mcp:tools:execute", "description": "Execute MCP tools"},
            ],
            "identity": [
                {"name": "identity:read", "description": "Read identity information"},
                {"name": "identity:write", "description": "Write identity information"},
            ],
            "session": [
                {"name": "session:manage", "description": "Manage user sessions"},
                {"name": "session:revoke", "description": "Revoke sessions"},
            ],
        }

        # Flatten to list
        all_scopes = []
        for category, scopes in available_scopes.items():
            for scope in scopes:
                all_scopes.append({**scope, "category": category})

        return {
            "total_scopes": len(all_scopes),
            "by_category": {
                cat: len(scopes) for cat, scopes in available_scopes.items()
            },
            "scopes": all_scopes,
        }

    async def _validate_scopes(
        self, params: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate if scopes are valid.

        Args:
            params: Parameters with scopes list
            context: Execution context

        Returns:
            Validation result
        """
        requested_scopes = params.get("scopes", [])

        logger.info(f"✓ Validating {len(requested_scopes)} scopes")

        # Define all valid scopes
        valid_scopes = {
            # OIDC
            "openid",
            "profile",
            "email",
            # Bedrock
            "bedrock:agents:invoke",
            "bedrock:agents:read",
            "bedrock:agents:create",
            "bedrock:agents:update",
            "bedrock:agents:delete",
            # MCP
            "mcp:resources:read",
            "mcp:resources:create",
            "mcp:tools:execute",
            # Identity
            "identity:read",
            "identity:write",
            # Session
            "session:manage",
            "session:revoke",
        }

        invalid_scopes = [s for s in requested_scopes if s not in valid_scopes]
        valid_requested = [s for s in requested_scopes if s in valid_scopes]

        return {
            "valid": len(invalid_scopes) == 0,
            "valid_scopes": valid_requested,
            "invalid_scopes": invalid_scopes,
            "total_requested": len(requested_scopes),
            "total_valid": len(valid_requested),
        }
