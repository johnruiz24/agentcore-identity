"""Pytest configuration and fixtures for AgentCore Identity tests."""

import os
import json
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta, timezone

# Test fixtures for OAuth2Manager
@pytest.fixture
def mock_cognito_client():
    """Mock Cognito client"""
    client = MagicMock()
    client.initiate_auth = AsyncMock()
    client.admin_get_user = AsyncMock()
    client.admin_create_user = AsyncMock()
    client.admin_delete_user = AsyncMock()
    return client


@pytest.fixture
def mock_session_data():
    """Sample session data"""
    now = int(datetime.now(timezone.utc).timestamp())
    return {
        "session_id": "test-session-123",
        "user_id": "cognito-sub-123",
        "username": "<EMAIL_PLACEHOLDER>",
        "email": "<EMAIL_PLACEHOLDER>",
        "access_token": "test-access-token-abc123",
        "refresh_token": "test-refresh-token-xyz789",
        "scopes": ["openid", "profile", "email", "bedrock:agents:invoke"],
        "created_at": now,
        "expires_at": now + 3600,
        "ip_address": "127.0.0.1",
        "user_agent": "Mozilla/5.0",
        "active": True,
    }


@pytest.fixture
def mock_token_response():
    """Sample token response from Cognito"""
    return {
        "AuthenticationResult": {
            "AccessToken": "test-access-token",
            "IdToken": "test-id-token",
            "RefreshToken": "test-refresh-token",
            "ExpiresIn": 3600,
            "TokenType": "Bearer",
        }
    }


@pytest.fixture
def mock_jwt_claims():
    """Sample JWT claims"""
    return {
        "sub": "cognito-sub-123",
        "aud": "test-client-id",
        "iss": "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_d3VRWMX7h",
        "email": "<EMAIL_PLACEHOLDER>",
        "email_verified": True,
        "cognito:username": "<EMAIL_PLACEHOLDER>",
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }


# Mock boto3 resources
@pytest.fixture
def mock_dynamodb_table():
    """Mock DynamoDB table"""
    table = MagicMock()
    table.query = MagicMock(return_value={"Items": []})
    table.get_item = MagicMock(return_value={"Item": {}})
    table.put_item = MagicMock()
    table.update_item = MagicMock()
    table.delete_item = MagicMock()
    table.scan = MagicMock(return_value={"Items": []})
    return table


# Async test support
@pytest.fixture
def event_loop():
    """Provide event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Pytest settings
def pytest_collection_modifyitems(config, items):
    """Automatically add asyncio marker to async tests"""
    for item in items:
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)


# Test database configuration
@pytest.fixture
def test_env_vars(monkeypatch):
    """Set test environment variables"""
    test_vars = {
        "AWS_REGION": "eu-central-1",
        "AWS_ACCOUNT_ID": "123456789",
        "AWS_PROFILE": "test",
        "COGNITO_USER_POOL_ID": "eu-central-1_d3VRWMX7h",
        "COGNITO_CLIENT_ID": "test-client-id",
        "COGNITO_CLIENT_SECRET": "test-client-secret",
        "COGNITO_DOMAIN": "agentcore-identity",
        "OAUTH2_REDIRECT_URI": "http://localhost:8000/auth/callback",
        "DYNAMODB_TABLE_SESSIONS": "test-sessions",
        "DYNAMODB_TABLE_USERS": "test-users",
        "BEDROCK_MODEL_ID": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "LOG_LEVEL": "DEBUG",
    }

    for key, value in test_vars.items():
        monkeypatch.setenv(key, value)

    return test_vars
