"""
Session Handler for managing user sessions

Handles session creation, validation, and revocation using DynamoDB.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import boto3
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SessionData(BaseModel):
    """Session data model"""

    session_id: str
    user_id: str
    username: str
    email: Optional[str] = None
    scopes: list[str]
    access_token: str
    refresh_token: Optional[str] = None
    created_at: int  # Unix timestamp
    expires_at: int  # Unix timestamp for DynamoDB TTL
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    active: bool = True


class SessionHandler:
    """Manages user sessions in DynamoDB"""

    def __init__(
        self,
        table_name: str,
        region: str = "eu-central-1",
        session_ttl_hours: int = 24,
    ):
        """
        Initialize SessionHandler

        Args:
            table_name: DynamoDB table name for sessions
            region: AWS Region
            session_ttl_hours: Session time-to-live in hours
        """
        self.table_name = table_name
        self.region = region
        self.session_ttl_hours = session_ttl_hours

        # DynamoDB client
        self.dynamodb = boto3.resource("dynamodb", region_name=region)
        self.table = self.dynamodb.Table(table_name)

    def create_session(
        self,
        user_id: str,
        username: str,
        access_token: str,
        scopes: list[str],
        email: Optional[str] = None,
        refresh_token: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> SessionData:
        """
        Create a new session

        Args:
            user_id: User's sub from Cognito
            username: Username
            access_token: OAuth2 access token
            scopes: List of scopes
            email: User email
            refresh_token: OAuth2 refresh token
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            SessionData
        """
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        created_at = int(now.timestamp())
        expires_at = int((now + timedelta(hours=self.session_ttl_hours)).timestamp())

        session = SessionData(
            session_id=session_id,
            user_id=user_id,
            username=username,
            email=email,
            scopes=scopes,
            access_token=access_token,
            refresh_token=refresh_token,
            created_at=created_at,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            active=True,
        )

        # Store in DynamoDB
        try:
            self.table.put_item(Item=session.model_dump())
            logger.info(f"✓ Session created: {session_id} for user {user_id}")
            return session

        except Exception as e:
            logger.error(f"✗ Failed to create session: {e}")
            raise

    def get_session(self, session_id: str) -> Optional[SessionData]:
        """
        Retrieve a session by ID

        Args:
            session_id: Session ID

        Returns:
            SessionData or None if not found
        """
        try:
            # DynamoDB query requires both hash and range key in get_item
            # We need to query by session_id
            response = self.table.query(
                KeyConditionExpression="session_id = :sid",
                ExpressionAttributeValues={":sid": session_id},
                Limit=1,
            )

            items = response.get("Items", [])
            if not items:
                logger.warning(f"⚠ Session not found: {session_id}")
                return None

            session_data = items[0]

            # Check if session is still active
            now = int(datetime.now(timezone.utc).timestamp())
            if session_data.get("expires_at", 0) < now:
                logger.warning(f"⚠ Session expired: {session_id}")
                return None

            if not session_data.get("active", True):
                logger.warning(f"⚠ Session inactive: {session_id}")
                return None

            return SessionData(**session_data)

        except Exception as e:
            logger.error(f"✗ Failed to get session: {e}")
            return None

    def get_user_sessions(self, user_id: str) -> list[SessionData]:
        """
        Get all active sessions for a user

        Args:
            user_id: User ID

        Returns:
            List of SessionData
        """
        try:
            response = self.table.query(
                IndexName="user_id-created_at-index",
                KeyConditionExpression="user_id = :uid",
                ExpressionAttributeValues={":uid": user_id},
            )

            sessions = []
            now = int(datetime.now(timezone.utc).timestamp())

            for item in response.get("Items", []):
                # Filter active sessions only
                if item.get("active", True) and item.get("expires_at", 0) > now:
                    sessions.append(SessionData(**item))

            logger.info(f"✓ Retrieved {len(sessions)} active sessions for user {user_id}")
            return sessions

        except Exception as e:
            logger.error(f"✗ Failed to get user sessions: {e}")
            return []

    def update_session(self, session_id: str, **updates) -> Optional[SessionData]:
        """
        Update session attributes

        Args:
            session_id: Session ID
            **updates: Attributes to update

        Returns:
            Updated SessionData or None if failed
        """
        try:
            # Build update expression
            update_parts = []
            expression_values = {}

            for key, value in updates.items():
                if key not in ["session_id", "user_id", "created_at"]:  # Don't update keys
                    update_parts.append(f"{key} = :{key}")
                    expression_values[f":{key}"] = value

            if not update_parts:
                return self.get_session(session_id)

            update_expr = "SET " + ", ".join(update_parts)

            # Get the user_id first (needed for the key)
            session = self.get_session(session_id)
            if not session:
                return None

            self.table.update_item(
                Key={"session_id": session_id, "user_id": session.user_id},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expression_values,
            )

            logger.info(f"✓ Session updated: {session_id}")
            return self.get_session(session_id)

        except Exception as e:
            logger.error(f"✗ Failed to update session: {e}")
            return None

    def revoke_session(self, session_id: str) -> bool:
        """
        Revoke a session (mark as inactive)

        Args:
            session_id: Session ID

        Returns:
            True if revoked, False otherwise
        """
        session = self.get_session(session_id)
        if not session:
            return False

        return self.update_session(session_id, active=False) is not None

    def revoke_all_user_sessions(self, user_id: str, exclude_session_id: Optional[str] = None) -> int:
        """
        Revoke all sessions for a user

        Args:
            user_id: User ID
            exclude_session_id: Session to exclude from revocation

        Returns:
            Number of sessions revoked
        """
        sessions = self.get_user_sessions(user_id)
        revoked_count = 0

        for session in sessions:
            if exclude_session_id and session.session_id == exclude_session_id:
                continue

            if self.revoke_session(session.session_id):
                revoked_count += 1

        logger.info(f"✓ Revoked {revoked_count} sessions for user {user_id}")
        return revoked_count

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session from DynamoDB

        Args:
            session_id: Session ID

        Returns:
            True if deleted, False otherwise
        """
        try:
            session = self.get_session(session_id)
            if not session:
                return False

            self.table.delete_item(
                Key={"session_id": session_id, "user_id": session.user_id}
            )

            logger.info(f"✓ Session deleted: {session_id}")
            return True

        except Exception as e:
            logger.error(f"✗ Failed to delete session: {e}")
            return False

    def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions (manual cleanup, DynamoDB TTL handles auto-cleanup)

        Returns:
            Number of sessions cleaned up
        """
        try:
            # Scan all sessions and delete expired ones
            # Note: This is a manual cleanup - DynamoDB TTL handles auto-deletion
            cleaned = 0
            now = int(datetime.now(timezone.utc).timestamp())

            # This is just for demonstration; in production, DynamoDB TTL handles this
            logger.info(f"✓ Cleaned up {cleaned} expired sessions")
            return cleaned

        except Exception as e:
            logger.error(f"✗ Failed to cleanup sessions: {e}")
            return 0
