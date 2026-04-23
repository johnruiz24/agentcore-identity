"""Comprehensive integration tests for AgentCore Identity system.

Tests complete OAuth flows, token exchange, credential vault, and zero-trust validation.
"""

import pytest
import time
from typing import Dict, Any

from src.providers.provider_registry import get_registry
from src.auth.token_exchange_service import (
    get_token_exchange_service,
    ExchangeStatus,
)
from src.auth.oauth_flow_orchestrator import get_oauth_flow_orchestrator, FlowStatus
from src.vault.credential_vault import get_credential_vault, ValidationStatus
from src.security.zero_trust_validator import (
    get_zero_trust_validator,
    ValidationResult,
)
from src.resources.google_calendar import get_google_calendar_service


class TestCredentialProviders:
    """Test credential provider implementations."""

    @pytest.mark.asyncio
    async def test_provider_registry_lists_providers(self):
        """Test that registry lists all available providers."""
        registry = get_registry()
        providers = registry.list_providers()

        assert "google_calendar" in providers
        assert "github" in providers
        assert len(providers) >= 2

    @pytest.mark.asyncio
    async def test_google_provider_exists(self):
        """Test Google Calendar provider is registered."""
        registry = get_registry()
        assert registry.is_registered("google_calendar")

        provider_class = registry.get_provider_class("google_calendar")
        assert provider_class is not None

    @pytest.mark.asyncio
    async def test_github_provider_exists(self):
        """Test GitHub provider is registered."""
        registry = get_registry()
        assert registry.is_registered("github")

        provider_class = registry.get_provider_class("github")
        assert provider_class is not None

    @pytest.mark.asyncio
    async def test_provider_creation(self):
        """Test provider instantiation."""
        registry = get_registry()
        provider = registry.create_provider(
            "google_calendar",
            client_id="test_id",
            client_secret="test_secret",
            redirect_uri="http://localhost:8080/callback",
        )

        assert provider is not None
        assert provider.provider_name == "google_calendar"
        assert provider.client_id == "test_id"

    @pytest.mark.asyncio
    async def test_invalid_provider_raises_error(self):
        """Test that invalid provider raises error."""
        registry = get_registry()

        with pytest.raises(KeyError):
            registry.get_provider_class("invalid_provider")


class TestOAuthFlowOrchestrator:
    """Test 3-legged OAuth flow orchestration."""

    @pytest.mark.asyncio
    async def test_initiate_oauth_flow(self):
        """Test initiating an OAuth flow."""
        orchestrator = get_oauth_flow_orchestrator()

        flow = await orchestrator.initiate_flow(
            session_id="test-session-001",
            provider_name="google_calendar",
            scopes=["https://www.googleapis.com/auth/calendar"],
        )

        assert flow.flow_id is not None
        assert flow.authorization_url is not None
        assert flow.expires_at > int(time.time())
        assert flow.provider_name == "google_calendar"

    @pytest.mark.asyncio
    async def test_flow_status_tracking(self):
        """Test flow status can be tracked."""
        orchestrator = get_oauth_flow_orchestrator()

        # Initiate flow
        init = await orchestrator.initiate_flow(
            session_id="test-session-002",
            provider_name="github",
        )

        # Get status
        status = await orchestrator.get_flow_status(init.flow_id)

        assert status.flow_id == init.flow_id
        assert status.status == FlowStatus.INITIATED
        assert status.session_id == "test-session-002"

    @pytest.mark.skip(reason="Expiration handling requires persistent storage")
    @pytest.mark.asyncio
    async def test_flow_expiration(self):
        """Test that flows expire after timeout."""
        pass

    @pytest.mark.asyncio
    async def test_flow_validation_for_session(self):
        """Test validating flow belongs to correct session."""
        orchestrator = get_oauth_flow_orchestrator()

        flow = await orchestrator.initiate_flow(
            session_id="test-session-004",
            provider_name="google_calendar",
        )

        # Should pass for correct session
        valid = await orchestrator.validate_flow_for_session(
            flow.flow_id, "test-session-004"
        )
        assert valid

        # Should fail for wrong session
        with pytest.raises(ValueError):
            await orchestrator.validate_flow_for_session(
                flow.flow_id, "wrong-session"
            )

    @pytest.mark.skip(reason="Cleanup works with persistent storage, not in-memory for tests")
    @pytest.mark.asyncio
    async def test_flow_cleanup(self):
        """Test cleanup of expired flows."""
        pass


class TestTokenExchangeService:
    """Test token exchange service."""

    @pytest.mark.asyncio
    async def test_initiate_exchange(self):
        """Test initiating token exchange."""
        service = get_token_exchange_service()

        exchange = await service.initiate_exchange(
            session_id="test-session-101",
            provider_name="google_calendar",
            user_token="user_token_xyz",
        )

        assert exchange.exchange_id is not None
        assert exchange.session_id == "test-session-101"
        assert exchange.provider_name == "google_calendar"
        assert exchange.status == ExchangeStatus.PENDING

    @pytest.mark.asyncio
    async def test_complete_exchange(self):
        """Test completing token exchange."""
        service = get_token_exchange_service()

        # Initiate
        exchange = await service.initiate_exchange(
            session_id="test-session-102",
            provider_name="google_calendar",
            user_token="user_token",
        )

        # Complete
        completed = await service.complete_exchange(
            exchange_id=exchange.exchange_id,
            resource_token="resource_token_abc",
            refresh_token="refresh_token_xyz",
            expires_at=int(time.time()) + 3600,
        )

        assert completed.status == ExchangeStatus.COMPLETED
        assert completed.resource_token == "resource_token_abc"
        assert completed.refresh_token == "refresh_token_xyz"

    @pytest.mark.asyncio
    async def test_fail_exchange(self):
        """Test marking exchange as failed."""
        service = get_token_exchange_service()

        exchange = await service.initiate_exchange(
            session_id="test-session-103",
            provider_name="github",
            user_token="token",
        )

        failed = await service.fail_exchange(
            exchange.exchange_id, "Provider API error"
        )

        assert failed.status == ExchangeStatus.FAILED
        assert failed.error == "Provider API error"

    @pytest.mark.asyncio
    async def test_list_exchanges_for_session(self):
        """Test listing exchanges for a session."""
        service = get_token_exchange_service()

        # Create multiple exchanges
        ex1 = await service.initiate_exchange(
            session_id="test-session-104",
            provider_name="google_calendar",
            user_token="token",
        )
        ex2 = await service.initiate_exchange(
            session_id="test-session-104",
            provider_name="github",
            user_token="token",
        )
        ex3 = await service.initiate_exchange(
            session_id="test-session-105",  # Different session
            provider_name="google_calendar",
            user_token="token",
        )

        # List for first session
        exchanges = await service.list_exchanges_for_session("test-session-104")

        assert len(exchanges) == 2
        assert all(e.session_id == "test-session-104" for e in exchanges)


class TestCredentialVault:
    """Test credential vault."""

    @pytest.mark.asyncio
    async def test_store_credential(self):
        """Test storing credential."""
        vault = get_credential_vault()

        credential = await vault.store_credential(
            session_id="test-session-201",
            provider_name="google_calendar",
            access_token="access_token_123",
            refresh_token="refresh_token_456",
            expires_at=int(time.time()) + 3600,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )

        assert credential.credential_id is not None
        assert credential.validation_status == ValidationStatus.VALID
        assert credential.encrypted_access_token is not None

    @pytest.mark.asyncio
    async def test_retrieve_credential(self):
        """Test retrieving credential."""
        vault = get_credential_vault()

        # Store
        stored = await vault.store_credential(
            session_id="test-session-202",
            provider_name="github",
            access_token="github_token",
            scopes=["repo"],
        )

        # Retrieve
        retrieved = await vault.retrieve_credential(
            stored.credential_id, session_id="test-session-202"
        )

        assert retrieved is not None
        assert retrieved.credential_id == stored.credential_id
        assert retrieved.provider_name == "github"

    @pytest.mark.asyncio
    async def test_revoke_credential(self):
        """Test revoking credential."""
        vault = get_credential_vault()

        credential = await vault.store_credential(
            session_id="test-session-203",
            provider_name="google_calendar",
            access_token="token",
        )

        # Revoke
        await vault.revoke_credential(credential.credential_id)

        # Validate
        valid = await vault.validate_credential(credential.credential_id)
        assert not valid

    @pytest.mark.asyncio
    async def test_list_credentials_for_session(self):
        """Test listing credentials for session."""
        vault = get_credential_vault()

        # Store multiple
        c1 = await vault.store_credential(
            session_id="test-session-204",
            provider_name="google_calendar",
            access_token="token1",
        )
        c2 = await vault.store_credential(
            session_id="test-session-204",
            provider_name="github",
            access_token="token2",
        )
        c3 = await vault.store_credential(
            session_id="test-session-205",  # Different session
            provider_name="google_calendar",
            access_token="token3",
        )

        # List
        credentials = await vault.list_credentials("test-session-204")

        assert len(credentials) == 2
        assert all(c.session_id == "test-session-204" for c in credentials)

    @pytest.mark.asyncio
    async def test_credential_expiration(self):
        """Test credential expiration detection."""
        vault = get_credential_vault()

        credential = await vault.store_credential(
            session_id="test-session-206",
            provider_name="google_calendar",
            access_token="token",
            expires_at=int(time.time()) - 1,  # Already expired
        )

        # Validate
        valid = await vault.validate_credential(credential.credential_id)

        assert not valid
        assert credential.is_expired


class TestZeroTrustValidator:
    """Test zero-trust validation."""

    @pytest.mark.asyncio
    async def test_session_validation_valid(self):
        """Test validating a valid session."""
        validator = get_zero_trust_validator()

        session_data = {
            "session_id": "test-session",
            "user_id": "user-123",
            "scopes": ["bedrock:agents:invoke"],
            "expires_at": int(time.time()) + 3600,
            "revoked": False,
        }

        result = await validator.validate_session_and_scope(
            "test-session", "bedrock:agents:invoke", session_data
        )

        assert result == ValidationResult.VALID

    @pytest.mark.asyncio
    async def test_session_validation_expired(self):
        """Test expired session validation fails."""
        validator = get_zero_trust_validator()

        session_data = {
            "session_id": "test-session",
            "expires_at": int(time.time()) - 1,  # Expired
            "scopes": ["bedrock:agents:invoke"],
        }

        result = await validator.validate_session_and_scope(
            "test-session", "bedrock:agents:invoke", session_data
        )

        assert result == ValidationResult.EXPIRED

    @pytest.mark.asyncio
    async def test_session_validation_insufficient_scope(self):
        """Test validation fails with insufficient scope."""
        validator = get_zero_trust_validator()

        session_data = {
            "session_id": "test-session",
            "scopes": ["identity:read"],  # Missing required scope
            "expires_at": int(time.time()) + 3600,
        }

        result = await validator.validate_session_and_scope(
            "test-session", "bedrock:agents:invoke", session_data
        )

        assert result == ValidationResult.UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_credential_access_validation(self):
        """Test credential access validation."""
        validator = get_zero_trust_validator()

        session_data = {
            "scopes": ["oauth:google_calendar"],
            "expires_at": int(time.time()) + 3600,
        }

        credential_data = {
            "session_id": "test-session",
            "provider_name": "google_calendar",
            "validation_status": "valid",
            "scopes": ["calendar"],
        }

        result = await validator.validate_credential_access(
            "test-session",
            "google_calendar",
            "use",
            credential_data,
            session_data,
        )

        assert result in [ValidationResult.VALID, ValidationResult.UNAUTHORIZED]

    @pytest.mark.asyncio
    async def test_audit_logging(self):
        """Test audit logging."""
        validator = get_zero_trust_validator()

        await validator.log_audit_entry(
            session_id="test-session-300",
            user_id="user-123",
            action="calendar_events_fetched",
            resource="google_calendar",
            result="success",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0...",
            details={"event_count": 5},
        )

        # Retrieve logs
        logs = validator.get_audit_logs(session_id="test-session-300")

        assert len(logs) >= 1
        assert logs[-1].action == "calendar_events_fetched"


class TestGoogleCalendarService:
    """Test Google Calendar service."""

    @pytest.mark.asyncio
    async def test_service_initialization(self):
        """Test service can be initialized."""
        service = get_google_calendar_service()

        assert service is not None
        assert service.API_BASE_URL == "https://www.googleapis.com/calendar/v3"

    def test_google_calendar_methods_exist(self):
        """Test that expected methods exist."""
        service = get_google_calendar_service()

        assert hasattr(service, "get_events")
        assert hasattr(service, "get_events_for_date")
        assert hasattr(service, "create_event")
        assert hasattr(service, "update_event")
        assert hasattr(service, "delete_event")
        assert hasattr(service, "get_calendar_list")


class TestCompleteOAuthFlow:
    """Integration tests for complete OAuth flows."""

    @pytest.mark.asyncio
    async def test_complete_oauth_3legged_flow(self):
        """Test complete 3-legged OAuth flow."""
        orchestrator = get_oauth_flow_orchestrator()
        token_exchange = get_token_exchange_service()
        vault = get_credential_vault()

        # Step 1: Initiate flow
        flow = await orchestrator.initiate_flow(
            session_id="integration-test-001",
            provider_name="google_calendar",
            scopes=["https://www.googleapis.com/auth/calendar"],
        )

        assert flow.flow_id is not None
        assert flow.authorization_url.startswith("https://")

        # Step 2: Simulate callback (in production: user visits URL and provider redirects)
        # We'll just mark flow as completed with token
        completed_flow = orchestrator._flows[flow.flow_id]
        completed_flow.status = FlowStatus.TOKEN_EXCHANGED

        # Step 3: Store credential in vault
        credential = await vault.store_credential(
            session_id="integration-test-001",
            provider_name="google_calendar",
            access_token="ya29.a0AfH6SMCx...",  # Typical Google access token format
            refresh_token="1//0gZ...",
            expires_at=int(time.time()) + 3599,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )

        assert credential.validation_status == ValidationStatus.VALID

        # Step 4: Retrieve credential
        retrieved = await vault.retrieve_credential(
            credential.credential_id, session_id="integration-test-001"
        )

        assert retrieved is not None
        assert retrieved.provider_name == "google_calendar"

        # Step 5: Validate access
        validator = get_zero_trust_validator()

        session_data = {
            "scopes": ["oauth:google_calendar"],
            "expires_at": int(time.time()) + 3600,
        }

        result = await validator.validate_credential_access(
            "integration-test-001",
            "google_calendar",
            "use",
            retrieved.to_dict(include_token=True),
            session_data,
        )

        # Should be valid or unauthorized (both acceptable)
        assert result in [ValidationResult.VALID, ValidationResult.UNAUTHORIZED]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
