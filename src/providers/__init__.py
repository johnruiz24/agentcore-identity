"""Credential provider implementations for OAuth 2.0 resources."""

from .base_provider import CredentialProvider, TokenResponse
from .google_provider import GoogleCalendarProvider
from .github_provider import GitHubProvider
from .provider_registry import ProviderRegistry

__all__ = [
    "CredentialProvider",
    "TokenResponse",
    "GoogleCalendarProvider",
    "GitHubProvider",
    "ProviderRegistry",
]
