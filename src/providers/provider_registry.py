"""Registry for managing OAuth provider implementations."""

from typing import Dict, Type, Optional
import logging

from .base_provider import CredentialProvider
from .google_provider import GoogleCalendarProvider
from .github_provider import GitHubProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry for managing OAuth credential providers.

    Provides centralized provider discovery and instantiation.
    """

    # Built-in providers
    _builtin_providers: Dict[str, Type[CredentialProvider]] = {
        "google_calendar": GoogleCalendarProvider,
        "github": GitHubProvider,
    }

    def __init__(self):
        """Initialize provider registry."""
        self._providers: Dict[str, Type[CredentialProvider]] = (
            self._builtin_providers.copy()
        )
        self._instances: Dict[str, CredentialProvider] = {}

    def register_provider(
        self, name: str, provider_class: Type[CredentialProvider]
    ) -> None:
        """Register a new OAuth provider.

        Args:
            name: Provider identifier
            provider_class: CredentialProvider subclass

        Raises:
            ValueError: If provider already registered
        """
        if name in self._providers:
            logger.warning(f"Provider '{name}' already registered, overwriting")

        if not issubclass(provider_class, CredentialProvider):
            raise ValueError(
                f"Provider class must be subclass of CredentialProvider"
            )

        self._providers[name] = provider_class
        logger.info(f"Registered provider: {name}")

    def unregister_provider(self, name: str) -> None:
        """Unregister an OAuth provider.

        Args:
            name: Provider identifier

        Raises:
            KeyError: If provider not found
        """
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' not found")

        # Don't allow unregistering built-in providers
        if name in self._builtin_providers:
            logger.warning(f"Cannot unregister built-in provider: {name}")
            return

        del self._providers[name]
        if name in self._instances:
            del self._instances[name]

        logger.info(f"Unregistered provider: {name}")

    def get_provider_class(self, name: str) -> Type[CredentialProvider]:
        """Get provider class by name.

        Args:
            name: Provider identifier

        Returns:
            CredentialProvider subclass

        Raises:
            KeyError: If provider not found
        """
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' not found")

        return self._providers[name]

    def create_provider(
        self, name: str, client_id: str, client_secret: str, redirect_uri: str
    ) -> CredentialProvider:
        """Create a provider instance.

        Args:
            name: Provider identifier
            client_id: OAuth client ID
            client_secret: OAuth client secret
            redirect_uri: OAuth callback URL

        Returns:
            Instantiated provider

        Raises:
            KeyError: If provider not found
        """
        provider_class = self.get_provider_class(name)
        instance = provider_class(client_id, client_secret, redirect_uri)
        logger.info(f"Created provider instance: {name}")
        return instance

    def list_providers(self) -> Dict[str, Dict[str, any]]:
        """List all registered providers with metadata.

        Returns:
            Dictionary of provider names to metadata
        """
        result = {}
        for name, provider_class in self._providers.items():
            # Create temporary instance to get metadata
            try:
                # Use dummy credentials for metadata extraction
                instance = provider_class("", "", "")
                result[name] = {
                    "name": instance.provider_name,
                    "authorize_url": instance.authorize_url,
                    "default_scopes": instance.default_scopes,
                }
            except Exception as e:
                logger.error(f"Error getting metadata for provider {name}: {e}")
                result[name] = {"error": str(e)}

        return result

    def is_registered(self, name: str) -> bool:
        """Check if provider is registered.

        Args:
            name: Provider identifier

        Returns:
            True if registered
        """
        return name in self._providers


# Global registry instance
_registry = ProviderRegistry()


def get_registry() -> ProviderRegistry:
    """Get global provider registry instance.

    Returns:
        Global ProviderRegistry instance
    """
    return _registry
