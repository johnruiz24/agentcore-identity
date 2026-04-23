"""User identity and profile provider MCP server."""

import logging
from typing import Any, Dict

from .base_server import MCPServer, Tool

logger = logging.getLogger(__name__)


class IdentityServer(MCPServer):
    """MCP server providing user identity and profile information.

    Exposes tools for:
    - Retrieving user profiles
    - Listing user sessions
    - Checking user permissions
    """

    def __init__(self, session_handler: Any):
        """Initialize identity server.

        Args:
            session_handler: SessionHandler instance
        """
        super().__init__("identity_server", session_handler)

        # Register tools
        self.register_tool(
            Tool(
                name="get_profile",
                description="Get user profile information",
                params_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                required_scopes=["identity:read"],
                handler=self._get_profile,
            )
        )

        self.register_tool(
            Tool(
                name="list_sessions",
                description="List all active sessions for the user",
                params_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                required_scopes=["session:manage"],
                handler=self._list_sessions,
            )
        )

        self.register_tool(
            Tool(
                name="get_session_details",
                description="Get detailed information about a specific session",
                params_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID (current session if not specified)",
                        }
                    },
                    "required": [],
                },
                required_scopes=["identity:read"],
                handler=self._get_session_details,
            )
        )

        self.register_tool(
            Tool(
                name="check_permission",
                description="Check if user has a specific permission",
                params_schema={
                    "type": "object",
                    "properties": {
                        "scope": {
                            "type": "string",
                            "description": "Scope to check (e.g., 'bedrock:agents:invoke')",
                        }
                    },
                    "required": ["scope"],
                },
                required_scopes=["identity:read"],
                handler=self._check_permission,
            )
        )

    async def _get_profile(
        self, params: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get user profile.

        Args:
            params: Parameters (empty)
            context: Execution context with session

        Returns:
            User profile information
        """
        session = context.get("session", {})

        logger.info(f"👤 Getting profile for user: {session.get('user_id')}")

        return {
            "user_id": session.get("user_id"),
            "email": session.get("email"),
            "created_at": session.get("created_at"),
            "updated_at": session.get("created_at"),  # Same as created for now
        }

    async def _list_sessions(
        self, params: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """List user sessions.

        Args:
            params: Parameters (empty)
            context: Execution context with session

        Returns:
            List of user sessions
        """
        session = context.get("session", {})
        user_id = session.get("user_id")
        session_id = session.get("session_id")

        logger.info(f"📱 Listing sessions for user: {user_id}")

        try:
            # Get all sessions for this user
            user_sessions = await self.session_handler.get_user_sessions(user_id)

            # Format session list
            sessions_list = [
                {
                    "session_id": s.get("session_id"),
                    "created_at": s.get("created_at"),
                    "expires_at": s.get("expires_at"),
                    "active": s.get("active", True),
                    "is_current": s.get("session_id") == session_id,
                }
                for s in (user_sessions or [])
            ]

            return {
                "user_id": user_id,
                "session_count": len(sessions_list),
                "sessions": sessions_list,
            }
        except Exception as e:
            logger.error(f"✗ Failed to list sessions: {e}")
            raise

    async def _get_session_details(
        self, params: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get session details.

        Args:
            params: Parameters (optional session_id)
            context: Execution context with session

        Returns:
            Session details
        """
        session = context.get("session", {})
        session_id = params.get("session_id") or session.get("session_id")

        logger.info(f"📊 Getting session details: {session_id}")

        try:
            sess = await self.session_handler.get_session(session_id)
            if not sess:
                raise ValueError(f"Session {session_id} not found")

            import time

            now = int(time.time())

            return {
                "session_id": session_id,
                "user_id": sess.user_id,
                "email": sess.email,
                "created_at": sess.created_at,
                "expires_at": sess.expires_at,
                "active": sess.active,
                "time_remaining": max(0, sess.expires_at - now),
            }
        except Exception as e:
            logger.error(f"✗ Failed to get session details: {e}")
            raise

    async def _check_permission(
        self, params: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check if user has permission.

        Args:
            params: Parameters with scope to check
            context: Execution context with session

        Returns:
            Permission check result
        """
        session = context.get("session", {})
        scope = params.get("scope")

        if not scope:
            raise ValueError("scope parameter is required")

        user_scopes = session.get("scopes", [])
        has_permission = scope in user_scopes

        logger.info(f"🔍 Permission check: {scope} = {has_permission}")

        return {
            "scope": scope,
            "has_permission": has_permission,
            "user_scopes": user_scopes,
        }
