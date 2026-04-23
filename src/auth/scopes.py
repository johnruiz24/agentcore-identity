"""
OAuth2 Scopes definition for Bedrock AgentCore Identity

Defines all available OAuth2 scopes for authentication and authorization
in the AgentCore Identity system.
"""

from enum import Enum
from typing import Dict, List, Set


class Scope(str, Enum):
    """OAuth2 scopes for AgentCore Identity"""

    # Standard OIDC scopes
    OPENID = "openid"
    PROFILE = "profile"
    EMAIL = "email"

    # Bedrock Agent scopes
    BEDROCK_AGENTS_INVOKE = "bedrock:agents:invoke"
    BEDROCK_AGENTS_READ = "bedrock:agents:read"
    BEDROCK_AGENTS_CREATE = "bedrock:agents:create"
    BEDROCK_AGENTS_UPDATE = "bedrock:agents:update"
    BEDROCK_AGENTS_DELETE = "bedrock:agents:delete"

    # MCP scopes
    MCP_RESOURCES_READ = "mcp:resources:read"
    MCP_RESOURCES_CREATE = "mcp:resources:create"
    MCP_TOOLS_EXECUTE = "mcp:tools:execute"

    # Identity scopes
    IDENTITY_READ = "identity:read"
    IDENTITY_WRITE = "identity:write"

    # Session scopes
    SESSION_MANAGE = "session:manage"
    SESSION_REVOKE = "session:revoke"

    def __str__(self) -> str:
        return self.value


# Scope hierarchies - related scopes
SCOPE_GROUPS: Dict[str, Set[str]] = {
    "admin": {
        Scope.BEDROCK_AGENTS_CREATE,
        Scope.BEDROCK_AGENTS_UPDATE,
        Scope.BEDROCK_AGENTS_DELETE,
        Scope.IDENTITY_WRITE,
        Scope.SESSION_REVOKE,
    },
    "user": {
        Scope.BEDROCK_AGENTS_INVOKE,
        Scope.BEDROCK_AGENTS_READ,
        Scope.MCP_RESOURCES_READ,
        Scope.IDENTITY_READ,
        Scope.SESSION_MANAGE,
    },
    "agent": {
        Scope.BEDROCK_AGENTS_INVOKE,
        Scope.MCP_RESOURCES_READ,
        Scope.MCP_TOOLS_EXECUTE,
        Scope.IDENTITY_READ,
    },
    "developer": {
        Scope.BEDROCK_AGENTS_CREATE,
        Scope.BEDROCK_AGENTS_READ,
        Scope.BEDROCK_AGENTS_INVOKE,
        Scope.MCP_RESOURCES_READ,
        Scope.MCP_RESOURCES_CREATE,
        Scope.MCP_TOOLS_EXECUTE,
        Scope.IDENTITY_READ,
    },
}

# Default scopes for different user types
DEFAULT_SCOPES: Dict[str, List[str]] = {
    "human_user": [
        Scope.OPENID,
        Scope.PROFILE,
        Scope.EMAIL,
        Scope.BEDROCK_AGENTS_INVOKE,
        Scope.BEDROCK_AGENTS_READ,
        Scope.MCP_RESOURCES_READ,
        Scope.IDENTITY_READ,
        Scope.SESSION_MANAGE,
    ],
    "agent_user": [
        Scope.BEDROCK_AGENTS_INVOKE,
        Scope.MCP_RESOURCES_READ,
        Scope.MCP_TOOLS_EXECUTE,
        Scope.IDENTITY_READ,
    ],
    "developer": [
        Scope.OPENID,
        Scope.PROFILE,
        Scope.EMAIL,
    ],
}

# Scope descriptions for documentation
SCOPE_DESCRIPTIONS: Dict[str, str] = {
    Scope.OPENID: "OpenID Connect scope",
    Scope.PROFILE: "Access to user profile information",
    Scope.EMAIL: "Access to user email address",
    Scope.BEDROCK_AGENTS_INVOKE: "Permission to invoke Bedrock agents",
    Scope.BEDROCK_AGENTS_READ: "Permission to read agent information",
    Scope.BEDROCK_AGENTS_CREATE: "Permission to create new agents",
    Scope.BEDROCK_AGENTS_UPDATE: "Permission to update agent configuration",
    Scope.BEDROCK_AGENTS_DELETE: "Permission to delete agents",
    Scope.MCP_RESOURCES_READ: "Permission to read MCP resources",
    Scope.MCP_RESOURCES_CREATE: "Permission to create MCP resources",
    Scope.MCP_TOOLS_EXECUTE: "Permission to execute MCP tools",
    Scope.IDENTITY_READ: "Permission to read identity information",
    Scope.IDENTITY_WRITE: "Permission to write identity information",
    Scope.SESSION_MANAGE: "Permission to manage user sessions",
    Scope.SESSION_REVOKE: "Permission to revoke sessions",
}


def get_scope_description(scope: str) -> str:
    """Get description for a scope"""
    return SCOPE_DESCRIPTIONS.get(scope, "Unknown scope")


def get_scopes_for_group(group: str) -> Set[str]:
    """Get all scopes for a user group"""
    return SCOPE_GROUPS.get(group, set())


def validate_scopes(requested_scopes: List[str]) -> bool:
    """Validate that all requested scopes are valid"""
    valid_scopes = {scope.value for scope in Scope}
    return all(scope in valid_scopes for scope in requested_scopes)


def filter_scopes(requested_scopes: List[str], available_scopes: List[str]) -> List[str]:
    """Filter requested scopes to only include available ones"""
    available_set = set(available_scopes)
    return [scope for scope in requested_scopes if scope in available_set]
