"""Authentication tools for Bedrock agents."""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AuthTools:
    """Custom authentication tools for Bedrock agents."""

    def __init__(self, oauth2_manager: Any, session_handler: Any):
        """Initialize with OAuth2Manager and SessionHandler instances.

        Args:
            oauth2_manager: OAuth2Manager instance for token operations
            session_handler: SessionHandler instance for session management
        """
        self.oauth2_manager = oauth2_manager
        self.session_handler = session_handler

    async def validate_token(self, token: str) -> Dict[str, Any]:
        """Validate OAuth2 token and return claims.

        This tool validates an ID token and returns the decoded claims.
        Useful for verifying token authenticity and extracting user information.

        Args:
            token: JWT ID token from Cognito

        Returns:
            Dictionary containing:
                - valid (bool): Whether token is valid
                - claims (dict): Decoded JWT claims including sub, email, etc.
                - expires_at (int): Token expiration timestamp

        Raises:
            ValueError: If token is invalid or expired
        """
        try:
            logger.info("🔐 Validating OAuth2 token")
            claims = await self.oauth2_manager.validate_id_token(token)

            logger.info(f"✓ Token valid for user {claims.get('sub')}")
            return {
                "valid": True,
                "claims": claims,
                "user_id": claims.get("sub"),
                "email": claims.get("email"),
            }
        except Exception as e:
            logger.error(f"✗ Token validation failed: {e}")
            raise ValueError(f"Invalid token: {str(e)}")

    async def refresh_session(self, session_id: str) -> Dict[str, Any]:
        """Refresh user session with new access token.

        This tool refreshes an existing session by using the stored refresh token
        to obtain a new access token from Cognito.

        Args:
            session_id: UUID of the session to refresh

        Returns:
            Dictionary containing:
                - status (str): "refreshed" on success
                - access_token (str): New access token
                - expires_in (int): Token expiration time in seconds
                - refresh_token (str): New refresh token if provided by Cognito

        Raises:
            ValueError: If session not found, no refresh token available, or refresh fails
        """
        try:
            logger.info(f"🔄 Refreshing session: {session_id}")

            # Get current session
            session = await self.session_handler.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            if not session.refresh_token:
                raise ValueError("No refresh token available for session")

            # Exchange refresh token for new access token
            new_tokens = await self.oauth2_manager.refresh_access_token(
                session.refresh_token
            )

            # Update session with new tokens
            update_data = {
                "access_token": new_tokens.access_token,
                "updated_at": int(__import__("time").time()),
            }

            if new_tokens.refresh_token:
                update_data["refresh_token"] = new_tokens.refresh_token

            await self.session_handler.update_session(session_id, **update_data)

            logger.info(f"✓ Session refreshed: {session_id}")
            return {
                "status": "refreshed",
                "access_token": new_tokens.access_token,
                "expires_in": new_tokens.expires_in,
                "session_id": session_id,
            }
        except Exception as e:
            logger.error(f"✗ Session refresh failed: {e}")
            raise ValueError(f"Failed to refresh session: {str(e)}")

    async def get_token_info(self, session_id: str) -> Dict[str, Any]:
        """Get token information from an active session.

        Returns details about the current tokens in a session including
        expiration times and scope information.

        Args:
            session_id: UUID of the session

        Returns:
            Dictionary containing:
                - access_token (str): Current access token
                - token_type (str): Bearer
                - expires_at (int): Absolute expiration timestamp
                - scopes (list): List of scopes granted in this session
                - user_id (str): Cognito subject (user ID)

        Raises:
            ValueError: If session not found or expired
        """
        try:
            logger.info(f"📋 Getting token info for session: {session_id}")

            session = await self.session_handler.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            return {
                "access_token": session.access_token[:20] + "...",  # Masked
                "token_type": "Bearer",
                "expires_at": session.expires_at,
                "scopes": session.scopes,
                "user_id": session.user_id,
                "session_id": session_id,
            }
        except Exception as e:
            logger.error(f"✗ Failed to get token info: {e}")
            raise ValueError(f"Failed to get token info: {str(e)}")

    async def revoke_session(self, session_id: str) -> Dict[str, Any]:
        """Revoke a user session.

        Marks the session as inactive, effectively logging out the user
        and preventing further use of tokens from this session.

        Args:
            session_id: UUID of the session to revoke

        Returns:
            Dictionary containing:
                - status (str): "revoked"
                - session_id (str): The revoked session ID
                - message (str): Confirmation message

        Raises:
            ValueError: If session not found or revocation fails
        """
        try:
            logger.warning(f"🔒 Revoking session: {session_id}")

            session = await self.session_handler.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            await self.session_handler.revoke_session(session_id)

            logger.info(f"✓ Session revoked: {session_id}")
            return {
                "status": "revoked",
                "session_id": session_id,
                "message": f"Session {session_id} has been revoked",
            }
        except Exception as e:
            logger.error(f"✗ Session revocation failed: {e}")
            raise ValueError(f"Failed to revoke session: {str(e)}")

    def get_tool_definitions(self) -> list:
        """Get list of tool definitions for Strands SDK.

        Returns:
            List of tool definitions with name, description, and schema
        """
        return [
            {
                "name": "validate_token",
                "description": "Validate an OAuth2 token and return decoded claims",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "token": {
                            "type": "string",
                            "description": "JWT ID token to validate",
                        }
                    },
                    "required": ["token"],
                },
            },
            {
                "name": "refresh_session",
                "description": "Refresh a user session with a new access token",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "UUID of the session to refresh",
                        }
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "get_token_info",
                "description": "Get token information from an active session",
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
                "name": "revoke_session",
                "description": "Revoke a user session (logout)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "UUID of the session to revoke",
                        }
                    },
                    "required": ["session_id"],
                },
            },
        ]
