"""Token exchange service for converting user OAuth tokens to resource access tokens."""

import uuid
import time
import logging
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
from enum import Enum

from src.providers.provider_registry import get_registry

logger = logging.getLogger(__name__)


class ExchangeStatus(str, Enum):
    """Token exchange status."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REVOKED = "revoked"


@dataclass
class TokenExchange:
    """Token exchange record."""

    exchange_id: str
    session_id: str
    provider_name: str
    user_token: str
    resource_token: Optional[str] = None
    scopes: List[str] = field(default_factory=list)
    created_at: int = field(default_factory=lambda: int(time.time()))
    expires_at: Optional[int] = None
    refresh_token: Optional[str] = None
    status: ExchangeStatus = ExchangeStatus.PENDING
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "exchange_id": self.exchange_id,
            "session_id": self.session_id,
            "provider_name": self.provider_name,
            "resource_token": self.resource_token,
            "scopes": self.scopes,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status.value,
            "error": self.error,
        }


class TokenExchangeService:
    """Service for exchanging user OAuth tokens for resource-specific tokens.

    Orchestrates token exchange between OAuth providers, implementing the
    delegation-based authentication pattern for AgentCore Identity.
    """

    def __init__(self):
        """Initialize token exchange service."""
        self.registry = get_registry()
        # In-memory storage for exchanges (replace with DynamoDB in production)
        self._exchanges: Dict[str, TokenExchange] = {}
        logger.info("TokenExchangeService initialized")

    async def initiate_exchange(
        self,
        session_id: str,
        provider_name: str,
        user_token: str,
        scopes: Optional[List[str]] = None,
    ) -> TokenExchange:
        """Initiate a new token exchange.

        Args:
            session_id: User session ID
            provider_name: OAuth provider name (e.g., 'google_calendar')
            user_token: User's OAuth token
            scopes: Specific scopes to request (optional)

        Returns:
            TokenExchange with exchange_id and status

        Raises:
            ValueError: If provider not found or exchange fails
        """
        exchange_id = str(uuid.uuid4())

        try:
            # Validate provider exists
            provider_class = self.registry.get_provider_class(provider_name)
            logger.info(
                f"Initiating token exchange: session={session_id}, provider={provider_name}"
            )

            # Use provider's default scopes if not specified
            if scopes is None:
                # Create temporary instance to get default scopes
                temp_provider = provider_class("", "", "")
                scopes = temp_provider.default_scopes

            # Create exchange record
            exchange = TokenExchange(
                exchange_id=exchange_id,
                session_id=session_id,
                provider_name=provider_name,
                user_token=user_token,
                scopes=scopes,
                status=ExchangeStatus.PENDING,
            )

            self._exchanges[exchange_id] = exchange
            logger.info(f"Exchange initiated: {exchange_id}")

            return exchange

        except KeyError as e:
            logger.error(f"Provider not found: {provider_name}")
            raise ValueError(f"Provider '{provider_name}' not found: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to initiate exchange: {e}")
            raise ValueError(f"Exchange initiation failed: {str(e)}")

    async def complete_exchange(
        self,
        exchange_id: str,
        resource_token: str,
        refresh_token: Optional[str] = None,
        expires_at: Optional[int] = None,
    ) -> TokenExchange:
        """Complete a token exchange with the obtained resource token.

        Args:
            exchange_id: Exchange ID from initiate_exchange
            resource_token: Token for accessing resource
            refresh_token: Optional refresh token
            expires_at: Token expiration timestamp

        Returns:
            Completed TokenExchange

        Raises:
            ValueError: If exchange not found
        """
        if exchange_id not in self._exchanges:
            raise ValueError(f"Exchange '{exchange_id}' not found")

        exchange = self._exchanges[exchange_id]
        exchange.resource_token = resource_token
        exchange.refresh_token = refresh_token
        exchange.expires_at = expires_at
        exchange.status = ExchangeStatus.COMPLETED

        logger.info(
            f"Exchange completed: {exchange_id} (provider={exchange.provider_name})"
        )

        return exchange

    async def fail_exchange(self, exchange_id: str, error: str) -> TokenExchange:
        """Mark exchange as failed.

        Args:
            exchange_id: Exchange ID
            error: Error message

        Returns:
            Failed TokenExchange

        Raises:
            ValueError: If exchange not found
        """
        if exchange_id not in self._exchanges:
            raise ValueError(f"Exchange '{exchange_id}' not found")

        exchange = self._exchanges[exchange_id]
        exchange.status = ExchangeStatus.FAILED
        exchange.error = error

        logger.error(f"Exchange failed: {exchange_id} - {error}")

        return exchange

    async def get_exchange_status(self, exchange_id: str) -> TokenExchange:
        """Get current status of token exchange.

        Args:
            exchange_id: Exchange ID

        Returns:
            TokenExchange record

        Raises:
            ValueError: If exchange not found
        """
        if exchange_id not in self._exchanges:
            raise ValueError(f"Exchange '{exchange_id}' not found")

        return self._exchanges[exchange_id]

    async def revoke_resource_token(self, exchange_id: str) -> None:
        """Revoke a resource token.

        Args:
            exchange_id: Exchange ID

        Raises:
            ValueError: If exchange not found
        """
        if exchange_id not in self._exchanges:
            raise ValueError(f"Exchange '{exchange_id}' not found")

        exchange = self._exchanges[exchange_id]
        exchange.status = ExchangeStatus.REVOKED

        logger.info(
            f"Token revoked: {exchange_id} (provider={exchange.provider_name})"
        )

    async def list_exchanges_for_session(
        self, session_id: str
    ) -> List[TokenExchange]:
        """List all exchanges for a session.

        Args:
            session_id: Session ID

        Returns:
            List of TokenExchange records
        """
        exchanges = [e for e in self._exchanges.values() if e.session_id == session_id]
        logger.debug(f"Found {len(exchanges)} exchanges for session {session_id}")
        return exchanges

    async def validate_exchange_state(
        self, exchange_id: str, session_id: str
    ) -> bool:
        """Validate that exchange belongs to session and is valid.

        Args:
            exchange_id: Exchange ID
            session_id: Expected session ID

        Returns:
            True if valid

        Raises:
            ValueError: If validation fails
        """
        if exchange_id not in self._exchanges:
            raise ValueError(f"Exchange '{exchange_id}' not found")

        exchange = self._exchanges[exchange_id]

        if exchange.session_id != session_id:
            raise ValueError(f"Exchange session mismatch")

        if exchange.status != ExchangeStatus.PENDING:
            raise ValueError(
                f"Exchange not in pending state: {exchange.status.value}"
            )

        return True

    def cleanup_expired_exchanges(self, max_age_seconds: int = 3600) -> int:
        """Clean up expired exchange records.

        Args:
            max_age_seconds: Remove exchanges older than this (default: 1 hour)

        Returns:
            Number of exchanges removed
        """
        current_time = int(time.time())
        cutoff_time = current_time - max_age_seconds

        expired_ids = [
            eid
            for eid, exchange in self._exchanges.items()
            if exchange.created_at < cutoff_time
            and exchange.status == ExchangeStatus.PENDING
        ]

        for eid in expired_ids:
            del self._exchanges[eid]

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired exchanges")

        return len(expired_ids)


# Global instance
_service = TokenExchangeService()


def get_token_exchange_service() -> TokenExchangeService:
    """Get global token exchange service instance.

    Returns:
        Global TokenExchangeService instance
    """
    return _service
