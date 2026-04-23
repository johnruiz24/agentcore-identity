"""GitHub OAuth 2.0 provider implementation."""

from typing import Dict, List, Optional, Any
import httpx
import logging

from .base_provider import CredentialProvider, TokenResponse

logger = logging.getLogger(__name__)


class GitHubProvider(CredentialProvider):
    """GitHub OAuth 2.0 provider.

    Implements 3-legged OAuth flow for accessing user's GitHub resources.
    """

    @property
    def provider_name(self) -> str:
        """Provider identifier."""
        return "github"

    @property
    def authorize_url(self) -> str:
        """GitHub OAuth 2.0 authorization endpoint."""
        return "https://github.com/login/oauth/authorize"

    @property
    def token_url(self) -> str:
        """GitHub OAuth 2.0 token endpoint."""
        return "https://github.com/login/oauth/access_token"

    @property
    def default_scopes(self) -> List[str]:
        """Default scopes for GitHub API."""
        return ["repo", "gist", "user"]

    async def get_authorization_url(
        self, scopes: List[str], state: str, **kwargs
    ) -> str:
        """Get GitHub authorization URL.

        Args:
            scopes: OAuth scopes to request
            state: CSRF protection state token
            **kwargs: Additional parameters

        Returns:
            Authorization URL user should visit
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": ",".join(scopes),
            "state": state,
            "allow_signup": kwargs.get("allow_signup", "true"),
        }

        # Build URL
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.authorize_url}?{query_string}"

    async def exchange_code_for_token(self, code: str) -> TokenResponse:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code from GitHub callback

        Returns:
            Token response with access_token

        Raises:
            ValueError: If code exchange fails
        """
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        headers = {"Accept": "application/json"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.token_url, data=data, headers=headers)
                response.raise_for_status()

                token_data = response.json()
                logger.info("Successfully exchanged code for GitHub token")

                return TokenResponse(
                    access_token=token_data["access_token"],
                    refresh_token=token_data.get("refresh_token"),
                    expires_in=token_data.get("expires_in"),
                    scope=token_data.get("scope"),
                    extra_data=token_data,
                )

            except httpx.HTTPError as e:
                logger.error(f"Failed to exchange code for GitHub token: {e}")
                raise ValueError(f"Code exchange failed: {str(e)}")
            except KeyError as e:
                logger.error(f"Invalid response from GitHub token endpoint: {e}")
                raise ValueError(f"Invalid token response: {str(e)}")

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """Refresh expired access token.

        GitHub supports refresh tokens (as of 2024).

        Args:
            refresh_token: Refresh token from previous authentication

        Returns:
            New token response

        Raises:
            ValueError: If refresh fails
        """
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        headers = {"Accept": "application/json"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.token_url, data=data, headers=headers)
                response.raise_for_status()

                token_data = response.json()
                logger.info("Successfully refreshed GitHub access token")

                return TokenResponse(
                    access_token=token_data["access_token"],
                    refresh_token=token_data.get("refresh_token", refresh_token),
                    expires_in=token_data.get("expires_in"),
                    scope=token_data.get("scope"),
                    extra_data=token_data,
                )

            except httpx.HTTPError as e:
                logger.error(f"Failed to refresh GitHub token: {e}")
                raise ValueError(f"Token refresh failed: {str(e)}")

    async def validate_token(self, token: str) -> bool:
        """Check if access token is still valid.

        Args:
            token: Access token to validate

        Returns:
            True if token is valid, False otherwise
        """
        url = "https://api.github.com/user"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    logger.debug("GitHub token is valid")
                    return True
                else:
                    logger.debug(f"GitHub token is invalid: {response.status_code}")
                    return False
            except httpx.HTTPError as e:
                logger.error(f"Error validating GitHub token: {e}")
                return False

    async def get_user_info(self, token: str) -> Dict[str, Any]:
        """Get user information from GitHub.

        Args:
            token: Access token

        Returns:
            Dictionary with user info

        Raises:
            ValueError: If token invalid or API fails
        """
        url = "https://api.github.com/user"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

                data = response.json()
                logger.info(f"Retrieved user info for: {data.get('login')}")

                return {
                    "id": data.get("id"),
                    "login": data.get("login"),
                    "email": data.get("email"),
                    "name": data.get("name"),
                    "avatar_url": data.get("avatar_url"),
                }

            except httpx.HTTPError as e:
                logger.error(f"Failed to get GitHub user info: {e}")
                raise ValueError(f"Failed to get user info: {str(e)}")

    async def revoke_token(self, token: str) -> bool:
        """Revoke an access token.

        GitHub doesn't have a standard revocation endpoint, so this
        would typically be done through the user's GitHub settings.

        Args:
            token: Token to revoke

        Returns:
            False (not implemented for GitHub)
        """
        logger.info(
            "Token revocation for GitHub should be done via GitHub OAuth app settings"
        )
        return False
