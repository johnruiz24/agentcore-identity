"""Google Calendar OAuth 2.0 provider implementation."""

from typing import Dict, List, Optional, Any
import httpx
import logging

from .base_provider import CredentialProvider, TokenResponse

logger = logging.getLogger(__name__)


class GoogleCalendarProvider(CredentialProvider):
    """Google Calendar OAuth 2.0 provider.

    Implements 3-legged OAuth flow for accessing user's Google Calendar.
    """

    @property
    def provider_name(self) -> str:
        """Provider identifier."""
        return "google_calendar"

    @property
    def authorize_url(self) -> str:
        """Google OAuth 2.0 authorization endpoint."""
        return "https://accounts.google.com/o/oauth2/v2/auth"

    @property
    def token_url(self) -> str:
        """Google OAuth 2.0 token endpoint."""
        return "https://oauth2.googleapis.com/token"

    @property
    def default_scopes(self) -> List[str]:
        """Default scopes for Google Calendar API."""
        return ["https://www.googleapis.com/auth/calendar"]

    async def get_authorization_url(
        self, scopes: List[str], state: str, **kwargs
    ) -> str:
        """Get Google authorization URL.

        Args:
            scopes: OAuth scopes to request
            state: CSRF protection state token
            **kwargs: Additional parameters (access_type, prompt, etc.)

        Returns:
            Authorization URL user should visit
        """
        params = self._build_authorization_params(scopes, state)

        # Google-specific parameters
        params.update(
            {
                "access_type": kwargs.get("access_type", "offline"),
                "prompt": kwargs.get("prompt", "consent"),
            }
        )

        # Build URL
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.authorize_url}?{query_string}"

    async def exchange_code_for_token(self, code: str) -> TokenResponse:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code from Google callback

        Returns:
            Token response with access_token and refresh_token

        Raises:
            ValueError: If code exchange fails
        """
        params = self._build_token_request_params(code)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.token_url, data=params)
                response.raise_for_status()

                data = response.json()
                logger.info(f"Successfully exchanged code for Google token")

                return TokenResponse(
                    access_token=data["access_token"],
                    refresh_token=data.get("refresh_token"),
                    expires_in=data.get("expires_in"),
                    scope=data.get("scope"),
                    extra_data=data,
                )

            except httpx.HTTPError as e:
                logger.error(f"Failed to exchange code for Google token: {e}")
                raise ValueError(f"Code exchange failed: {str(e)}")
            except KeyError as e:
                logger.error(f"Invalid response from Google token endpoint: {e}")
                raise ValueError(f"Invalid token response: {str(e)}")

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """Refresh expired access token.

        Args:
            refresh_token: Refresh token from previous authentication

        Returns:
            New token response

        Raises:
            ValueError: If refresh fails
        """
        params = self._build_refresh_request_params(refresh_token)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.token_url, data=params)
                response.raise_for_status()

                data = response.json()
                logger.info("Successfully refreshed Google access token")

                return TokenResponse(
                    access_token=data["access_token"],
                    refresh_token=data.get("refresh_token", refresh_token),
                    expires_in=data.get("expires_in"),
                    scope=data.get("scope"),
                    extra_data=data,
                )

            except httpx.HTTPError as e:
                logger.error(f"Failed to refresh Google token: {e}")
                raise ValueError(f"Token refresh failed: {str(e)}")

    async def validate_token(self, token: str) -> bool:
        """Check if access token is still valid.

        Args:
            token: Access token to validate

        Returns:
            True if token is valid, False otherwise
        """
        url = f"https://www.googleapis.com/oauth2/v1/tokeninfo?access_token={token}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    logger.debug("Google token is valid")
                    return True
                else:
                    logger.debug(f"Google token is invalid: {response.status_code}")
                    return False
            except httpx.HTTPError as e:
                logger.error(f"Error validating Google token: {e}")
                return False

    async def get_user_info(self, token: str) -> Dict[str, Any]:
        """Get user information from Google.

        Args:
            token: Access token

        Returns:
            Dictionary with user info

        Raises:
            ValueError: If token invalid or API fails
        """
        url = "https://www.googleapis.com/oauth2/v1/userinfo"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

                data = response.json()
                logger.info(f"Retrieved user info for: {data.get('email')}")

                return {
                    "id": data.get("id"),
                    "email": data.get("email"),
                    "name": data.get("name"),
                    "picture": data.get("picture"),
                }

            except httpx.HTTPError as e:
                logger.error(f"Failed to get Google user info: {e}")
                raise ValueError(f"Failed to get user info: {str(e)}")

    async def revoke_token(self, token: str) -> bool:
        """Revoke an access token.

        Args:
            token: Token to revoke

        Returns:
            True if revocation successful
        """
        url = f"https://oauth2.googleapis.com/revoke?token={token}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url)
                if response.status_code == 200:
                    logger.info("Successfully revoked Google token")
                    return True
                else:
                    logger.warning(
                        f"Failed to revoke Google token: {response.status_code}"
                    )
                    return False
            except httpx.HTTPError as e:
                logger.error(f"Error revoking Google token: {e}")
                return False
