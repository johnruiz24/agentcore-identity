"""Base abstract class for OAuth 2.0 credential providers."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class TokenResponse:
    """Response from token exchange or refresh."""

    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    scope: Optional[str] = None
    token_type: str = "Bearer"
    extra_data: Optional[Dict[str, Any]] = None


class CredentialProvider(ABC):
    """Abstract base class for OAuth 2.0 credential providers.

    Implements the provider abstraction pattern to support multiple OAuth providers
    (Google, GitHub, etc.) with consistent interface.
    """

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        """Initialize provider with OAuth credentials.

        Args:
            client_id: OAuth 2.0 client ID
            client_secret: OAuth 2.0 client secret
            redirect_uri: Callback URL after user authorization
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.logger = logger

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier (e.g., 'google_calendar', 'github')."""
        pass

    @property
    @abstractmethod
    def authorize_url(self) -> str:
        """OAuth 2.0 authorization endpoint URL."""
        pass

    @property
    @abstractmethod
    def token_url(self) -> str:
        """OAuth 2.0 token endpoint URL."""
        pass

    @property
    @abstractmethod
    def default_scopes(self) -> List[str]:
        """Default scopes for this provider."""
        pass

    @abstractmethod
    async def get_authorization_url(
        self, scopes: List[str], state: str, **kwargs
    ) -> str:
        """Get authorization URL for 3-legged OAuth flow.

        Args:
            scopes: OAuth scopes to request
            state: CSRF protection state token
            **kwargs: Provider-specific parameters

        Returns:
            Authorization URL for user to visit
        """
        pass

    @abstractmethod
    async def exchange_code_for_token(self, code: str) -> TokenResponse:
        """Exchange authorization code for access token.

        Called after user authorizes on provider's login page.

        Args:
            code: Authorization code from provider callback

        Returns:
            Token response with access_token and optional refresh_token

        Raises:
            ValueError: If code exchange fails
        """
        pass

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """Refresh expired access token using refresh token.

        Args:
            refresh_token: Refresh token from previous authentication

        Returns:
            New token response

        Raises:
            ValueError: If refresh fails or refresh_token invalid
        """
        pass

    @abstractmethod
    async def validate_token(self, token: str) -> bool:
        """Check if access token is still valid.

        Args:
            token: Access token to validate

        Returns:
            True if token is valid, False if expired or invalid
        """
        pass

    @abstractmethod
    async def get_user_info(self, token: str) -> Dict[str, Any]:
        """Get user information using access token.

        Args:
            token: Access token

        Returns:
            Dictionary with user info (at minimum: id, email, name)

        Raises:
            ValueError: If token invalid or API fails
        """
        pass

    async def revoke_token(self, token: str) -> bool:
        """Revoke an access token (optional, provider-dependent).

        Args:
            token: Token to revoke

        Returns:
            True if revocation successful
        """
        self.logger.info(f"Token revocation not implemented for {self.provider_name}")
        return False

    def _build_authorization_params(
        self, scopes: List[str], state: str, **kwargs
    ) -> Dict[str, str]:
        """Build authorization request parameters.

        Args:
            scopes: OAuth scopes
            state: CSRF state token
            **kwargs: Additional parameters

        Returns:
            Dictionary of authorization parameters
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
        }
        params.update(kwargs)
        return params

    def _build_token_request_params(self, code: str) -> Dict[str, str]:
        """Build token request parameters for code exchange.

        Args:
            code: Authorization code from provider

        Returns:
            Dictionary of token request parameters
        """
        return {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
        }

    def _build_refresh_request_params(self, refresh_token: str) -> Dict[str, str]:
        """Build token refresh request parameters.

        Args:
            refresh_token: Refresh token

        Returns:
            Dictionary of refresh request parameters
        """
        return {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
