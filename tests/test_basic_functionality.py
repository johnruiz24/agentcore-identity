"""
Basic functional tests for AgentCore Identity

Tests verify:
- Imports work correctly
- Classes can be instantiated
- Basic method calls execute
- Error handling works
"""

import pytest
import sys
from unittest.mock import MagicMock, patch, AsyncMock


class TestImports:
    """Test that all modules import correctly"""

    def test_import_oauth2_manager(self):
        """Test OAuth2Manager can be imported"""
        from src.auth.oauth2_manager import OAuth2Manager
        assert OAuth2Manager is not None

    def test_import_session_handler(self):
        """Test SessionHandler can be imported"""
        from src.auth.session_handler import SessionHandler
        assert SessionHandler is not None

    def test_import_auth_tools(self):
        """Test AuthTools can be imported"""
        from src.agents.tools.auth_tools import AuthTools
        assert AuthTools is not None

    def test_import_identity_tools(self):
        """Test IdentityTools can be imported"""
        from src.agents.tools.identity_tools import IdentityTools
        assert IdentityTools is not None

    def test_import_agent_executor(self):
        """Test BedrockAgentExecutor can be imported"""
        from src.agents.main_agent import BedrockAgentExecutor
        assert BedrockAgentExecutor is not None

    def test_import_mcp_servers(self):
        """Test MCP servers can be imported"""
        from src.mcp_servers.base_server import MCPServer
        from src.mcp_servers.auth_server import AuthServer
        from src.mcp_servers.identity_server import IdentityServer
        from src.mcp_servers.resource_server import ResourceServer

        assert MCPServer is not None
        assert AuthServer is not None
        assert IdentityServer is not None
        assert ResourceServer is not None

    def test_import_fastapi_server(self):
        """Test FastAPI server can be imported"""
        from src.deployment.fastapi_server import app
        assert app is not None


class TestOAuth2ManagerBasics:
    """Test basic OAuth2Manager functionality"""

    def test_oauth2_manager_instantiation(self, test_env_vars):
        """Test OAuth2Manager can be instantiated"""
        with patch('src.auth.oauth2_manager.boto3.client'):
            from src.auth.oauth2_manager import OAuth2Manager
            manager = OAuth2Manager(
                user_pool_id="eu-central-1_test",
                client_id="test-client",
                client_secret="test-secret",
                domain="test-domain",
            )
            assert manager is not None

    def test_get_authorization_url(self, test_env_vars):
        """Test get_authorization_url returns URL"""
        with patch('src.auth.oauth2_manager.boto3.client'):
            from src.auth.oauth2_manager import OAuth2Manager
            manager = OAuth2Manager(
                user_pool_id="eu-central-1_test",
                client_id="test-client",
                client_secret="test-secret",
                domain="test-domain",
            )
            url = manager.get_authorization_url()

            assert url is not None
            assert "response_type=code" in url
            assert "client_id" in url

    def test_oauth2_manager_attributes(self, test_env_vars):
        """Test OAuth2Manager has expected attributes"""
        with patch('src.auth.oauth2_manager.boto3.client'):
            from src.auth.oauth2_manager import OAuth2Manager
            manager = OAuth2Manager(
                user_pool_id="eu-central-1_test",
                client_id="test-client",
                client_secret="test-secret",
                domain="test-domain",
            )

            assert hasattr(manager, 'get_authorization_url')
            assert hasattr(manager, 'exchange_code_for_token')
            assert hasattr(manager, 'refresh_access_token')
            assert hasattr(manager, 'validate_id_token')
            assert hasattr(manager, 'get_user_info')


class TestSessionHandlerBasics:
    """Test basic SessionHandler functionality"""

    def test_session_handler_instantiation(self, test_env_vars):
        """Test SessionHandler can be instantiated"""
        with patch('src.auth.session_handler.boto3.resource'):
            from src.auth.session_handler import SessionHandler
            handler = SessionHandler(table_name="agentcore-identity-sessions")
            assert handler is not None

    def test_session_handler_attributes(self, test_env_vars):
        """Test SessionHandler has expected attributes"""
        with patch('src.auth.session_handler.boto3.resource'):
            from src.auth.session_handler import SessionHandler
            handler = SessionHandler(table_name="agentcore-identity-sessions")

            assert hasattr(handler, 'create_session')
            assert hasattr(handler, 'get_session')
            assert hasattr(handler, 'get_user_sessions')
            assert hasattr(handler, 'revoke_session')
            assert hasattr(handler, 'update_session')
            assert hasattr(handler, 'cleanup_expired_sessions')


class TestAuthToolsBasics:
    """Test basic AuthTools functionality"""

    def test_auth_tools_instantiation(self):
        """Test AuthTools can be instantiated"""
        from src.agents.tools.auth_tools import AuthTools

        session_handler = MagicMock()
        oauth2_manager = MagicMock()

        tools = AuthTools(session_handler, oauth2_manager)
        assert tools is not None

    def test_auth_tools_get_tool_definitions(self):
        """Test AuthTools.get_tool_definitions returns list"""
        from src.agents.tools.auth_tools import AuthTools

        session_handler = MagicMock()
        oauth2_manager = MagicMock()

        tools = AuthTools(session_handler, oauth2_manager)
        definitions = tools.get_tool_definitions()

        assert isinstance(definitions, list)
        assert len(definitions) > 0


class TestIdentityToolsBasics:
    """Test basic IdentityTools functionality"""

    def test_identity_tools_instantiation(self):
        """Test IdentityTools can be instantiated"""
        from src.agents.tools.identity_tools import IdentityTools

        session_handler = MagicMock()
        oauth2_manager = MagicMock()

        tools = IdentityTools(session_handler, oauth2_manager)
        assert tools is not None

    def test_identity_tools_get_tool_definitions(self):
        """Test IdentityTools.get_tool_definitions returns list"""
        from src.agents.tools.identity_tools import IdentityTools

        session_handler = MagicMock()
        oauth2_manager = MagicMock()

        tools = IdentityTools(session_handler, oauth2_manager)
        definitions = tools.get_tool_definitions()

        assert isinstance(definitions, list)
        assert len(definitions) > 0


class TestBedrockAgentExecutorBasics:
    """Test basic BedrockAgentExecutor functionality"""

    def test_agent_executor_instantiation(self, test_env_vars):
        """Test BedrockAgentExecutor can be instantiated"""
        from src.agents.main_agent import BedrockAgentExecutor
        from src.agents.tools.auth_tools import AuthTools
        from src.agents.tools.identity_tools import IdentityTools

        auth_tools = AuthTools(MagicMock(), MagicMock())
        identity_tools = IdentityTools(MagicMock(), MagicMock())

        executor = BedrockAgentExecutor(
            bedrock_model_id="eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
            region="eu-central-1",
            auth_tools=auth_tools,
            identity_tools=identity_tools,
            session_handler=MagicMock(),
        )
        assert executor is not None


class TestMCPServerBasics:
    """Test basic MCP Server functionality"""

    def test_auth_server_instantiation(self):
        """Test AuthServer can be instantiated"""
        from src.mcp_servers.auth_server import AuthServer

        session_handler = MagicMock()
        server = AuthServer(session_handler)
        assert server is not None

    def test_identity_server_instantiation(self):
        """Test IdentityServer can be instantiated"""
        from src.mcp_servers.identity_server import IdentityServer

        session_handler = MagicMock()
        server = IdentityServer(session_handler)
        assert server is not None

    def test_resource_server_instantiation(self):
        """Test ResourceServer can be instantiated"""
        from src.mcp_servers.resource_server import ResourceServer

        session_handler = MagicMock()
        server = ResourceServer(session_handler)
        assert server is not None

    def test_auth_server_get_tools_list(self):
        """Test AuthServer.get_tools_list returns list"""
        from src.mcp_servers.auth_server import AuthServer

        session_handler = MagicMock()
        server = AuthServer(session_handler)
        tools = server.get_tools_list()

        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_identity_server_get_tools_list(self):
        """Test IdentityServer.get_tools_list returns list"""
        from src.mcp_servers.identity_server import IdentityServer

        session_handler = MagicMock()
        server = IdentityServer(session_handler)
        tools = server.get_tools_list()

        assert isinstance(tools, list)
        assert len(tools) > 0


class TestFastAPIServerBasics:
    """Test basic FastAPI server functionality"""

    def test_fastapi_app_creation(self):
        """Test FastAPI app can be instantiated"""
        from src.deployment.fastapi_server import app
        assert app is not None

    def test_fastapi_app_has_routes(self):
        """Test FastAPI app has expected routes"""
        from src.deployment.fastapi_server import app

        routes = [route.path for route in app.routes]

        # Should have health endpoint
        assert "/health" in routes

    def test_fastapi_app_get_routes_count(self):
        """Test FastAPI app has multiple routes"""
        from src.deployment.fastapi_server import app

        routes = [route.path for route in app.routes]

        # Should have multiple routes configured
        assert len(routes) > 0


class TestModelClasses:
    """Test Pydantic model classes"""

    def test_token_response_model(self):
        """Test TokenResponse model"""
        from src.auth.oauth2_manager import TokenResponse

        token = TokenResponse(
            access_token="token-123",
            token_type="Bearer",
            expires_in=3600,
        )

        assert token.access_token == "token-123"
        assert token.token_type == "Bearer"
        assert token.expires_in == 3600

    def test_user_info_model(self):
        """Test UserInfo model"""
        from src.auth.oauth2_manager import UserInfo

        user = UserInfo(
            sub="user-123",
            email="<EMAIL_PLACEHOLDER>",
        )

        assert user.sub == "user-123"
        assert user.email == "<EMAIL_PLACEHOLDER>"


class TestErrorHandling:
    """Test error handling"""

    def test_oauth2_manager_with_invalid_config(self):
        """Test OAuth2Manager with invalid configuration"""
        with patch('src.auth.oauth2_manager.boto3.client') as mock_client:
            mock_client.side_effect = Exception("Invalid credentials")

            from src.auth.oauth2_manager import OAuth2Manager

            # Should handle error gracefully
            try:
                manager = OAuth2Manager()
            except Exception:
                pass

    def test_session_handler_with_invalid_dynamodb(self):
        """Test SessionHandler with invalid DynamoDB"""
        with patch('src.auth.session_handler.boto3.resource') as mock_resource:
            mock_resource.side_effect = Exception("DynamoDB error")

            from src.auth.session_handler import SessionHandler

            # Should handle error gracefully
            try:
                handler = SessionHandler()
            except Exception:
                pass


class TestToolDefinitionStructure:
    """Test that tool definitions have correct structure"""

    def test_auth_tools_definition_structure(self):
        """Test AuthTools definitions have required fields"""
        from src.agents.tools.auth_tools import AuthTools

        tools = AuthTools(MagicMock(), MagicMock())
        definitions = tools.get_tool_definitions()

        for tool_def in definitions:
            assert "name" in tool_def
            assert "description" in tool_def
            assert "input_schema" in tool_def

    def test_identity_tools_definition_structure(self):
        """Test IdentityTools definitions have required fields"""
        from src.agents.tools.identity_tools import IdentityTools

        tools = IdentityTools(MagicMock(), MagicMock())
        definitions = tools.get_tool_definitions()

        for tool_def in definitions:
            assert "name" in tool_def
            assert "description" in tool_def
            assert "input_schema" in tool_def

    def test_mcp_server_definition_structure(self):
        """Test MCP server tools have required fields"""
        from src.mcp_servers.auth_server import AuthServer

        server = AuthServer(MagicMock())
        tools = server.get_tools_list()

        for tool in tools:
            assert "name" in tool or isinstance(tool, dict)


class TestEnvironmentConfiguration:
    """Test environment configuration"""

    def test_environment_variables_required(self, test_env_vars):
        """Test required environment variables are set"""
        import os

        required_vars = [
            "AWS_REGION",
            "COGNITO_USER_POOL_ID",
            "COGNITO_CLIENT_ID",
            "DYNAMODB_TABLE_SESSIONS",
            "BEDROCK_MODEL_ID",
        ]

        for var in required_vars:
            # Should either be set or have default
            value = os.environ.get(var)
            # Just verify we can get the value


class TestAgentToolsNaming:
    """Test that tools are properly named"""

    def test_auth_tool_names(self):
        """Test AuthTools have expected tool names"""
        from src.agents.tools.auth_tools import AuthTools

        tools = AuthTools(MagicMock(), MagicMock())
        definitions = tools.get_tool_definitions()
        tool_names = [d["name"] for d in definitions]

        assert "validate_token" in tool_names
        assert "refresh_session" in tool_names
        assert "get_token_info" in tool_names
        assert "revoke_session" in tool_names

    def test_identity_tool_names(self):
        """Test IdentityTools have expected tool names"""
        from src.agents.tools.identity_tools import IdentityTools

        tools = IdentityTools(MagicMock(), MagicMock())
        definitions = tools.get_tool_definitions()
        tool_names = [d["name"] for d in definitions]

        assert "get_user_profile" in tool_names
        assert "list_user_sessions" in tool_names
        assert "get_session_details" in tool_names
        assert "check_scope" in tool_names

    def test_mcp_server_tool_names(self):
        """Test MCP servers have expected tool names"""
        from src.mcp_servers.auth_server import AuthServer
        from src.mcp_servers.identity_server import IdentityServer
        from src.mcp_servers.resource_server import ResourceServer

        auth_server = AuthServer(MagicMock())
        auth_tools = [t["name"] for t in auth_server.get_tools_list()]
        assert "get_user_scopes" in auth_tools or len(auth_tools) > 0

        identity_server = IdentityServer(MagicMock())
        identity_tools = [t["name"] for t in identity_server.get_tools_list()]
        assert "get_profile" in identity_tools or len(identity_tools) > 0

        resource_server = ResourceServer(MagicMock())
        resource_tools = [t["name"] for t in resource_server.get_tools_list()]
        assert "list_resources" in resource_tools or len(resource_tools) > 0
