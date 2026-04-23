"""Orchestrator for 3-legged OAuth flows with resource providers."""

import uuid
import time
import logging
import secrets
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlencode

from src.providers.provider_registry import get_registry
from src.auth.token_exchange_service import (
    get_token_exchange_service,
    ExchangeStatus,
)

logger = logging.getLogger(__name__)


class FlowStatus(str, Enum):
    """OAuth flow status."""

    INITIATED = "initiated"
    AUTHORIZED = "authorized"
    TOKEN_EXCHANGED = "token_exchanged"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class OAuthFlow:
    """OAuth flow record."""

    flow_id: str
    session_id: str
    provider_name: str
    scopes: List[str]
    state: str  # CSRF token
    authorization_url: str
    status: FlowStatus = FlowStatus.INITIATED
    created_at: int = field(default_factory=lambda: int(time.time()))
    expires_at: int = field(default_factory=lambda: int(time.time() + 1800))  # 30 min
    completed_at: Optional[int] = None
    error: Optional[str] = None
    credential_id: Optional[str] = None
    redirect_uri: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "flow_id": self.flow_id,
            "session_id": self.session_id,
            "provider_name": self.provider_name,
            "authorization_url": self.authorization_url,
            "status": self.status.value,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "error": self.error,
        }

    @property
    def is_expired(self) -> bool:
        """Check if flow has expired."""
        return int(time.time()) > self.expires_at


@dataclass
class OAuthFlowInitiation:
    """Response from initiating an OAuth flow."""

    flow_id: str
    authorization_url: str
    expires_at: int
    provider_name: str


@dataclass
class OAuthFlowCompletion:
    """Response from completing an OAuth flow."""

    flow_id: str
    status: str
    provider_name: str
    credential_id: str
    error: Optional[str] = None


class OAuth3LeggedOrchestrator:
    """Orchestrator for 3-legged OAuth flows.

    Manages complete OAuth 2.0 3-legged flow lifecycle including:
    - Flow initiation with authorization URL generation
    - Provider callback handling
    - Token exchange
    - Credential storage
    """

    def __init__(self, redirect_base_url: str = "http://localhost:8080"):
        """Initialize orchestrator.

        Args:
            redirect_base_url: Base URL for OAuth callbacks
        """
        self.redirect_base_url = redirect_base_url
        self.registry = get_registry()
        self.token_exchange_service = get_token_exchange_service()
        # In-memory storage for flows (replace with DynamoDB in production)
        self._flows: Dict[str, OAuthFlow] = {}
        logger.info("OAuth3LeggedOrchestrator initialized")

    async def initiate_flow(
        self,
        session_id: str,
        provider_name: str,
        scopes: Optional[List[str]] = None,
        **provider_kwargs,
    ) -> OAuthFlowInitiation:
        """Initiate a new 3-legged OAuth flow.

        Args:
            session_id: User session ID
            provider_name: OAuth provider (e.g., 'google_calendar')
            scopes: Specific scopes to request (optional)
            **provider_kwargs: Provider-specific parameters

        Returns:
            OAuthFlowInitiation with flow_id and authorization_url

        Raises:
            ValueError: If provider not found or setup fails
        """
        flow_id = str(uuid.uuid4())
        state = secrets.token_urlsafe(32)  # CSRF token

        try:
            # Get provider and create instance
            provider_class = self.registry.get_provider_class(provider_name)
            redirect_uri = f"{self.redirect_base_url}/oauth/callback/{flow_id}"
            provider = provider_class("", "", redirect_uri)

            logger.info(
                f"Initiating OAuth flow: session={session_id}, provider={provider_name}, flow={flow_id}"
            )

            # Use provider's default scopes if not specified
            if scopes is None:
                scopes = provider.default_scopes

            # Get authorization URL from provider
            authorization_url = await provider.get_authorization_url(
                scopes, state, **provider_kwargs
            )

            # Create flow record
            flow = OAuthFlow(
                flow_id=flow_id,
                session_id=session_id,
                provider_name=provider_name,
                scopes=scopes,
                state=state,
                authorization_url=authorization_url,
                redirect_uri=redirect_uri,
                status=FlowStatus.INITIATED,
            )

            self._flows[flow_id] = flow
            logger.info(f"OAuth flow initiated: {flow_id}")

            return OAuthFlowInitiation(
                flow_id=flow_id,
                authorization_url=authorization_url,
                expires_at=flow.expires_at,
                provider_name=provider_name,
            )

        except KeyError as e:
            logger.error(f"Provider not found: {provider_name}")
            raise ValueError(f"Provider '{provider_name}' not found: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to initiate OAuth flow: {e}")
            raise ValueError(f"Flow initiation failed: {str(e)}")

    async def handle_callback(
        self, flow_id: str, code: str, state: str
    ) -> OAuthFlowCompletion:
        """Process provider callback after user authorizes.

        Args:
            flow_id: Flow ID from initiate_flow
            code: Authorization code from provider
            state: CSRF state token from provider

        Returns:
            OAuthFlowCompletion with credential_id

        Raises:
            ValueError: If flow invalid or token exchange fails
        """
        if flow_id not in self._flows:
            logger.error(f"Flow not found: {flow_id}")
            raise ValueError(f"Flow '{flow_id}' not found")

        flow = self._flows[flow_id]

        # Validate state token (CSRF protection)
        if flow.state != state:
            logger.error(f"CSRF state mismatch for flow {flow_id}")
            raise ValueError("CSRF state mismatch")

        # Check if flow expired
        if flow.is_expired:
            logger.error(f"Flow expired: {flow_id}")
            flow.status = FlowStatus.FAILED
            flow.error = "Flow expired"
            raise ValueError("Flow has expired")

        try:
            logger.info(f"Processing callback for flow: {flow_id}")

            # Get provider and exchange code for token
            provider_class = self.registry.get_provider_class(flow.provider_name)
            provider = provider_class("", "", flow.redirect_uri)

            # Exchange authorization code for access token
            token_response = await provider.exchange_code_for_token(code)

            logger.info(f"Successfully exchanged code for token: {flow_id}")

            # Complete the token exchange service exchange
            credential_id = str(uuid.uuid4())
            exchange = await self.token_exchange_service.complete_exchange(
                exchange_id=credential_id,
                resource_token=token_response.access_token,
                refresh_token=token_response.refresh_token,
                expires_at=(
                    int(time.time()) + token_response.expires_in
                    if token_response.expires_in
                    else None
                ),
            )

            # Update flow record
            flow.status = FlowStatus.COMPLETED
            flow.completed_at = int(time.time())
            flow.credential_id = credential_id

            logger.info(f"OAuth flow completed: {flow_id}")

            return OAuthFlowCompletion(
                flow_id=flow_id,
                status=FlowStatus.COMPLETED.value,
                provider_name=flow.provider_name,
                credential_id=credential_id,
            )

        except Exception as e:
            logger.error(f"Failed to handle callback: {e}")
            flow.status = FlowStatus.FAILED
            flow.error = str(e)

            return OAuthFlowCompletion(
                flow_id=flow_id,
                status=FlowStatus.FAILED.value,
                provider_name=flow.provider_name,
                credential_id="",
                error=str(e),
            )

    async def get_flow_status(self, flow_id: str) -> OAuthFlow:
        """Get current status of OAuth flow.

        Args:
            flow_id: Flow ID

        Returns:
            OAuthFlow record

        Raises:
            ValueError: If flow not found
        """
        if flow_id not in self._flows:
            raise ValueError(f"Flow '{flow_id}' not found")

        flow = self._flows[flow_id]

        # Mark as expired if past expiration
        if flow.is_expired and flow.status == FlowStatus.INITIATED:
            flow.status = FlowStatus.FAILED
            flow.error = "Flow expired"

        return flow

    async def cancel_flow(self, flow_id: str) -> None:
        """Cancel an incomplete OAuth flow.

        Args:
            flow_id: Flow ID

        Raises:
            ValueError: If flow not found
        """
        if flow_id not in self._flows:
            raise ValueError(f"Flow '{flow_id}' not found")

        flow = self._flows[flow_id]
        flow.status = FlowStatus.CANCELLED
        flow.completed_at = int(time.time())

        logger.info(f"OAuth flow cancelled: {flow_id}")

    async def validate_flow_for_session(
        self, flow_id: str, session_id: str
    ) -> bool:
        """Validate that flow belongs to session and is valid.

        Args:
            flow_id: Flow ID
            session_id: Expected session ID

        Returns:
            True if valid

        Raises:
            ValueError: If validation fails
        """
        flow = await self.get_flow_status(flow_id)

        if flow.session_id != session_id:
            raise ValueError(f"Flow session mismatch")

        if flow.status != FlowStatus.INITIATED:
            raise ValueError(
                f"Flow not in initiated state: {flow.status.value}"
            )

        if flow.is_expired:
            raise ValueError("Flow has expired")

        return True

    def cleanup_expired_flows(self, max_age_seconds: int = 3600) -> int:
        """Clean up expired flow records.

        Args:
            max_age_seconds: Remove flows older than this (default: 1 hour)

        Returns:
            Number of flows removed
        """
        current_time = int(time.time())
        cutoff_time = current_time - max_age_seconds

        expired_ids = [
            fid
            for fid, flow in self._flows.items()
            if flow.created_at < cutoff_time
            and flow.status in [FlowStatus.CANCELLED, FlowStatus.FAILED]
        ]

        for fid in expired_ids:
            del self._flows[fid]

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired flows")

        return len(expired_ids)


# Global instance
_orchestrator = OAuth3LeggedOrchestrator()


def get_oauth_flow_orchestrator() -> OAuth3LeggedOrchestrator:
    """Get global OAuth flow orchestrator instance.

    Returns:
        Global OAuth3LeggedOrchestrator instance
    """
    return _orchestrator
