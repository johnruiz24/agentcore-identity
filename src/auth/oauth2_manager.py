"""
OAuth2 Manager for AWS Cognito integration

Handles OAuth2 authentication flow with AWS Cognito, including:
- Authorization code exchange
- Token validation and refresh
- User information retrieval
- Scope management
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlparse, parse_qs

import boto3
from jose import JWTError, jwt
from pydantic import BaseModel

try:
    import requests
except ModuleNotFoundError:
    requests = None

logger = logging.getLogger(__name__)


def _require_requests():
    if requests is None:
        raise RuntimeError(
            "requests is not installed in this runtime image; OAuth HTTP calls are unavailable"
        )
    return requests


class TokenResponse(BaseModel):
    """OAuth2 token response"""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    scope: Optional[str] = None


class UserInfo(BaseModel):
    """User information from Cognito"""

    sub: str
    email: Optional[str] = None
    email_verified: Optional[bool] = None
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    picture: Optional[str] = None
    updated_at: Optional[int] = None
    phone_number: Optional[str] = None
    custom_department: Optional[str] = None


class OAuth2Manager:
    """Manages OAuth2 authentication with AWS Cognito"""

    def __init__(
        self,
        user_pool_id: str,
        client_id: str,
        client_secret: str,
        domain: str,
        region: str = "eu-central-1",
        redirect_uri: str = "http://localhost:8000/auth/callback",
    ):
        """
        Initialize OAuth2Manager

        Args:
            user_pool_id: Cognito User Pool ID
            client_id: Cognito App Client ID
            client_secret: Cognito App Client Secret
            domain: Cognito Domain
            region: AWS Region
            redirect_uri: OAuth2 Redirect URI
        """
        self.user_pool_id = user_pool_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.domain = domain
        self.region = region
        self.redirect_uri = redirect_uri

        # Construct URLs
        self.cognito_domain_url = f"https://{domain}.auth.{region}.amazoncognito.com"
        self.token_url = f"{self.cognito_domain_url}/oauth2/token"
        self.authorize_url = f"{self.cognito_domain_url}/oauth2/authorize"
        self.userinfo_url = f"{self.cognito_domain_url}/oauth2/userInfo"
        self.jwks_url = f"{self.cognito_domain_url}/.well-known/jwks.json"

        # Cognito IDP client
        self.cognito_client = boto3.client("cognito-idp", region_name=region)

        # JWT configuration
        self.algorithm = "RS256"
        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._jwks_cache_time: Optional[datetime] = None
        self._jwks_cache_ttl = timedelta(hours=24)

    def get_authorization_url(
        self, scopes: Optional[List[str]] = None, state: Optional[str] = None
    ) -> str:
        """
        Generate OAuth2 authorization URL

        Args:
            scopes: List of requested scopes
            state: State parameter for CSRF protection

        Returns:
            Authorization URL
        """
        if scopes is None:
            scopes = ["openid", "profile", "email"]

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": " ".join(scopes),
            "redirect_uri": self.redirect_uri,
            "response_mode": "form_post",
        }

        if state:
            params["state"] = state

        return f"{self.authorize_url}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> TokenResponse:
        """
        Exchange authorization code for tokens

        Args:
            code: Authorization code from Cognito

        Returns:
            TokenResponse with access_token, refresh_token, etc.

        Raises:
            requests.RequestException: If token exchange fails
        """
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        response = _require_requests().post(self.token_url, data=data)
        response.raise_for_status()

        token_data = response.json()
        logger.info(f"✓ Token exchanged successfully for user")

        return TokenResponse(**token_data)

    def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """
        Refresh access token using refresh token

        Args:
            refresh_token: Refresh token

        Returns:
            TokenResponse with new access_token

        Raises:
            requests.RequestException: If refresh fails
        """
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }

        response = _require_requests().post(self.token_url, data=data)
        response.raise_for_status()

        token_data = response.json()
        logger.info(f"✓ Token refreshed successfully")

        return TokenResponse(**token_data)

    def _get_jwks(self) -> Dict[str, Any]:
        """
        Fetch JWKS from Cognito (with caching)

        Returns:
            JWKS dictionary
        """
        # Check cache
        if self._jwks_cache and self._jwks_cache_time:
            if datetime.now(timezone.utc) - self._jwks_cache_time < self._jwks_cache_ttl:
                return self._jwks_cache

        # Fetch from Cognito
        response = _require_requests().get(self.jwks_url)
        response.raise_for_status()

        self._jwks_cache = response.json()
        self._jwks_cache_time = datetime.now(timezone.utc)

        return self._jwks_cache

    def _get_public_key(self, token: str) -> Dict[str, Any]:
        """
        Get public key for verifying JWT

        Args:
            token: JWT token

        Returns:
            Public key from JWKS

        Raises:
            JWTError: If key not found
        """
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")

        if not kid:
            raise JWTError("Token missing kid header")

        jwks = self._get_jwks()

        key = None
        for k in jwks.get("keys", []):
            if k.get("kid") == kid:
                key = k
                break

        if not key:
            raise JWTError(f"Key {kid} not found in JWKS")

        return key

    def validate_id_token(self, token: str) -> Dict[str, Any]:
        """
        Validate and decode ID token

        Args:
            token: JWT ID token

        Returns:
            Decoded token claims

        Raises:
            JWTError: If token validation fails
        """
        try:
            # Get the key
            key = self._get_public_key(token)

            # Decode and verify
            decoded = jwt.decode(
                token,
                key,
                algorithms=[self.algorithm],
                audience=self.client_id,
                issuer=f"{self.cognito_domain_url}",
            )

            logger.debug(f"✓ ID token validated for user {decoded.get('sub')}")
            return decoded

        except JWTError as e:
            logger.error(f"✗ ID token validation failed: {e}")
            raise

    def get_user_info(self, access_token: str) -> UserInfo:
        """
        Get user information from Cognito

        Args:
            access_token: OAuth2 access token

        Returns:
            UserInfo with user details

        Raises:
            requests.RequestException: If request fails
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        response = _require_requests().get(self.userinfo_url, headers=headers)
        response.raise_for_status()

        user_data = response.json()
        user_info = UserInfo(**user_data)

        logger.info(f"✓ User info retrieved for {user_info.sub}")

        return user_info

    def revoke_token(self, token: str, token_type: str = "access_token") -> None:
        """
        Revoke a token

        Args:
            token: Token to revoke
            token_type: Type of token ('access_token' or 'refresh_token')

        Raises:
            requests.RequestException: If revocation fails
        """
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "token": token,
            "token_type_hint": token_type,
        }

        revoke_url = f"{self.cognito_domain_url}/oauth2/revoke"
        response = _require_requests().post(revoke_url, data=data)
        response.raise_for_status()

        logger.info(f"✓ {token_type} revoked successfully")

    def create_user(
        self, username: str, email: str, temporary_password: str, name: Optional[str] = None
    ) -> str:
        """
        Create a new user in Cognito

        Args:
            username: Username
            email: Email address
            temporary_password: Temporary password
            name: User's full name

        Returns:
            User sub (unique identifier)

        Raises:
            Exception: If user creation fails
        """
        try:
            response = self.cognito_client.admin_create_user(
                UserPoolId=self.user_pool_id,
                Username=username,
                TemporaryPassword=temporary_password,
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "email_verified", "Value": "true"},
                ] + ([{"Name": "name", "Value": name}] if name else []),
                MessageAction="SUPPRESS",  # Don't send welcome email
            )

            user = response["User"]
            logger.info(f"✓ User created: {user['Username']} ({user['UserCreateDate']})")
            return user["Username"]

        except self.cognito_client.exceptions.UsernameExistsException:
            logger.warning(f"⚠ User {username} already exists")
            raise ValueError(f"User {username} already exists")

    def set_user_password(self, username: str, password: str, permanent: bool = True) -> None:
        """
        Set user password

        Args:
            username: Username
            password: New password
            permanent: If True, set as permanent password

        Raises:
            Exception: If operation fails
        """
        self.cognito_client.admin_set_user_password(
            UserPoolId=self.user_pool_id,
            Username=username,
            Password=password,
            Permanent=permanent,
        )

        logger.info(f"✓ Password set for user {username}")

    def get_user(self, username: str) -> Dict[str, Any]:
        """
        Get user details from Cognito

        Args:
            username: Username or email

        Returns:
            User details

        Raises:
            Exception: If user not found
        """
        try:
            response = self.cognito_client.admin_get_user(
                UserPoolId=self.user_pool_id,
                Username=username,
            )

            user = response["User"]
            attributes = {attr["Name"]: attr["Value"] for attr in user.get("UserAttributes", [])}

            return {
                "username": user["Username"],
                "status": user["UserStatus"],
                "created": user["UserCreateDate"],
                "updated": user.get("UserLastModifiedDate"),
                "attributes": attributes,
                "enabled": user.get("Enabled", True),
            }

        except self.cognito_client.exceptions.UserNotFoundException:
            logger.warning(f"⚠ User {username} not found")
            raise ValueError(f"User {username} not found")

    def delete_user(self, username: str) -> None:
        """
        Delete a user from Cognito

        Args:
            username: Username

        Raises:
            Exception: If deletion fails
        """
        self.cognito_client.admin_delete_user(
            UserPoolId=self.user_pool_id,
            Username=username,
        )

        logger.info(f"✓ User deleted: {username}")
