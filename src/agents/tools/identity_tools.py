"""Identity and profile tools for Bedrock agents."""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class IdentityTools:
    """Custom identity and profile tools for Bedrock agents."""

    def __init__(self, session_handler: Any, oauth2_manager: Any):
        """Initialize with SessionHandler and OAuth2Manager instances.

        Args:
            session_handler: SessionHandler instance for session management
            oauth2_manager: OAuth2Manager instance for user operations
        """
        self.session_handler = session_handler
        self.oauth2_manager = oauth2_manager

    async def get_user_profile(self, session_id: str) -> Dict[str, Any]:
        """Get user profile information from an active session.

        Retrieves user identity information including email, name, and other
        profile details associated with the current session.

        Args:
            session_id: UUID of the session

        Returns:
            Dictionary containing:
                - user_id (str): Cognito subject (unique user ID)
                - username (str): Email or username
                - email (str): User email address
                - session_id (str): Current session ID
                - created_at (int): Session creation timestamp
                - scopes (list): List of scopes granted to user

        Raises:
            ValueError: If session not found or expired
        """
        try:
            logger.info(f"👤 Getting user profile for session: {session_id}")

            session = await self.session_handler.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            # Get additional user info from Cognito
            try:
                user_info = await self.oauth2_manager.get_user_info(
                    session.access_token
                )
            except Exception as e:
                logger.warning(f"Could not fetch extended user info: {e}")
                user_info = {}

            logger.info(f"✓ User profile retrieved: {session.user_id}")
            return {
                "user_id": session.user_id,
                "username": session.username,
                "email": session.email or user_info.get("email"),
                "name": user_info.get("name", ""),
                "email_verified": user_info.get("email_verified", False),
                "session_id": session_id,
                "created_at": session.created_at,
                "scopes": session.scopes,
            }
        except Exception as e:
            logger.error(f"✗ Failed to get user profile: {e}")
            raise ValueError(f"Failed to get user profile: {str(e)}")

    async def list_user_sessions(self, session_id: str) -> Dict[str, Any]:
        """List all active sessions for the current user.

        Returns a list of all active sessions for the user associated
        with the provided session_id. Useful for session management
        and multi-device login scenarios.

        Args:
            session_id: UUID of any session for the user

        Returns:
            Dictionary containing:
                - user_id (str): User ID
                - session_count (int): Number of active sessions
                - sessions (list): List of session details:
                    - session_id (str): Session UUID
                    - created_at (int): Creation timestamp
                    - expires_at (int): Expiration timestamp
                    - ip_address (str): Client IP
                    - user_agent (str): Client user agent
                    - active (bool): Whether session is active

        Raises:
            ValueError: If session not found
        """
        try:
            logger.info(f"📱 Listing sessions for user in session: {session_id}")

            current_session = await self.session_handler.get_session(session_id)
            if not current_session:
                raise ValueError(f"Session {session_id} not found")

            user_id = current_session.user_id

            # Get all sessions for this user
            user_sessions = await self.session_handler.get_user_sessions(user_id)

            # Filter to only active sessions
            active_sessions = [s for s in user_sessions if s.get("active", True)]

            logger.info(
                f"✓ Found {len(active_sessions)} active sessions for user {user_id}"
            )

            return {
                "user_id": user_id,
                "session_count": len(active_sessions),
                "sessions": [
                    {
                        "session_id": s.get("session_id"),
                        "created_at": s.get("created_at"),
                        "expires_at": s.get("expires_at"),
                        "ip_address": s.get("ip_address", "unknown"),
                        "user_agent": s.get("user_agent", "unknown")[:50],  # Truncate
                        "active": s.get("active", True),
                    }
                    for s in active_sessions
                ],
            }
        except Exception as e:
            logger.error(f"✗ Failed to list user sessions: {e}")
            raise ValueError(f"Failed to list user sessions: {str(e)}")

    async def get_session_details(self, session_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific session.

        Returns comprehensive details about a session including creation time,
        expiration, IP address, user agent, and scope information.

        Args:
            session_id: UUID of the session

        Returns:
            Dictionary containing:
                - session_id (str): Session UUID
                - user_id (str): User ID
                - username (str): Email or username
                - created_at (int): Creation timestamp
                - expires_at (int): Expiration timestamp
                - is_expired (bool): Whether session has expired
                - ip_address (str): Client IP address
                - user_agent (str): Client user agent
                - scopes (list): Scopes granted in this session
                - active (bool): Whether session is marked active

        Raises:
            ValueError: If session not found
        """
        try:
            logger.info(f"📊 Getting session details: {session_id}")

            session = await self.session_handler.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            import time

            now = int(time.time())
            is_expired = session.expires_at < now

            logger.info(f"✓ Session details retrieved: {session_id}")

            return {
                "session_id": session_id,
                "user_id": session.user_id,
                "username": session.username,
                "email": session.email,
                "created_at": session.created_at,
                "expires_at": session.expires_at,
                "is_expired": is_expired,
                "time_remaining": max(0, session.expires_at - now),
                "ip_address": session.ip_address or "unknown",
                "user_agent": session.user_agent or "unknown",
                "scopes": session.scopes,
                "active": session.active,
            }
        except Exception as e:
            logger.error(f"✗ Failed to get session details: {e}")
            raise ValueError(f"Failed to get session details: {str(e)}")

    async def check_scope(self, session_id: str, required_scope: str) -> Dict[str, bool]:
        """Check if the user session has a specific scope.

        Useful for agents to verify they have permission to perform
        a specific action before attempting it.

        Args:
            session_id: UUID of the session
            required_scope: Scope to check (e.g., "bedrock:agents:invoke")

        Returns:
            Dictionary containing:
                - has_scope (bool): Whether user has the scope
                - scope (str): The scope that was checked
                - user_scopes (list): All scopes available to user
        """
        try:
            logger.info(
                f"🔍 Checking scope '{required_scope}' for session {session_id}"
            )

            session = await self.session_handler.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            has_scope = required_scope in session.scopes

            logger.info(f"✓ Scope check: {required_scope} = {has_scope}")

            return {
                "has_scope": has_scope,
                "scope": required_scope,
                "user_scopes": session.scopes,
            }
        except Exception as e:
            logger.error(f"✗ Scope check failed: {e}")
            raise ValueError(f"Failed to check scope: {str(e)}")

    def get_tool_definitions(self) -> list:
        """Get list of tool definitions for Strands SDK.

        Returns:
            List of tool definitions with name, description, and schema
        """
        return [
            {
                "name": "get_user_profile",
                "description": "Get user profile information from the current session",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "UUID of the session",
                        }
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "list_user_sessions",
                "description": "List all active sessions for the current user",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "UUID of any session for the user",
                        }
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "get_session_details",
                "description": "Get detailed information about a specific session",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "UUID of the session",
                        }
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "check_scope",
                "description": "Check if the user session has a specific OAuth2 scope",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "UUID of the session",
                        },
                        "required_scope": {
                            "type": "string",
                            "description": "Scope to check (e.g., 'bedrock:agents:invoke')",
                        },
                    },
                    "required": ["session_id", "required_scope"],
                },
            },
        ]
