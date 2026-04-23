# Implementation Guides

Complete guides for extending AgentCore Identity with new agents, MCP servers, and tools.

## Table of Contents
1. [Creating Custom Bedrock Agents](#creating-custom-bedrock-agents)
2. [Creating Custom MCP Servers](#creating-custom-mcp-servers)
3. [Adding Custom Tools](#adding-custom-tools)
4. [OAuth2 Integration](#oauth2-integration)
5. [Session Management](#session-management)

---

## Creating Custom Bedrock Agents

### Basic Agent Structure

```python
from src.agents.main_agent import BedrockAgentExecutor
from src.agents.tools import AuthTools, IdentityTools

# Initialize agent
agent = BedrockAgentExecutor(
    bedrock_model_id="eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    region="eu-central-1",
    auth_tools=auth_tools,
    identity_tools=identity_tools,
    session_handler=session_handler
)

# Invoke agent
result = await agent.invoke(
    prompt="What are my current permissions?",
    session_id="user-session-123"
)
```

### Custom Tool Implementation

```python
class CustomTools:
    def __init__(self, session_handler, oauth2_manager):
        self.session_handler = session_handler
        self.oauth2_manager = oauth2_manager

    async def custom_operation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Your custom tool implementation"""
        return {"status": "success", "data": params}

    def get_tool_definitions(self) -> list:
        """Return tool definitions for agent"""
        return [
            {
                "name": "custom_operation",
                "description": "Description of your tool",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "..."}
                    },
                    "required": ["param1"]
                }
            }
        ]
```

### Register Custom Tools

```python
# In FastAPI lifespan:
custom_tools = CustomTools(session_handler, oauth2_manager)

agent_executor = BedrockAgentExecutor(
    bedrock_model_id=model_id,
    region=region,
    auth_tools=auth_tools,
    identity_tools=identity_tools,
    custom_tools=custom_tools,  # Add your tools
    session_handler=session_handler
)
```

---

## Creating Custom MCP Servers

### Basic MCP Server

```python
from src.mcp_servers import MCPServer, Tool

class CustomMCPServer(MCPServer):
    def __init__(self, session_handler):
        super().__init__("custom_server", session_handler)

        # Register tools
        self.register_tool(
            Tool(
                name="custom_tool",
                description="Your custom tool",
                params_schema={
                    "type": "object",
                    "properties": {
                        "input": {"type": "string"}
                    },
                    "required": ["input"]
                },
                required_scopes=["custom:tool:execute"],
                handler=self._custom_tool
            )
        )

    async def _custom_tool(
        self,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Implement your tool logic"""
        session = context.get("session", {})
        input_param = params.get("input")

        return {
            "result": f"Processed: {input_param}",
            "user_id": session.get("user_id")
        }
```

### Register MCP Server

```python
# In FastAPI lifespan:
custom_server = CustomMCPServer(session_handler)
mcp_servers["custom_server"] = custom_server
```

### Invoke MCP Server

```bash
# POST /mcp/invoke
{
    "session_id": "user-session-123",
    "server": "custom_server",
    "tool": "custom_tool",
    "input": {
        "input": "value"
    }
}
```

---

## Adding Custom Tools

### Tool with Scope Enforcement

```python
from src.mcp_servers import Tool

tool = Tool(
    name="admin_operation",
    description="Admin-only operation",
    params_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "Action to perform"},
            "resource_id": {"type": "string", "description": "Resource ID"}
        },
        "required": ["action", "resource_id"]
    },
    required_scopes=["admin:operations"],
    handler=async_handler_func
)
```

### Tool with Error Handling

```python
async def safe_tool_handler(params, context):
    try:
        # Your tool logic
        result = perform_operation(params)
        return {"status": "success", "data": result}

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise ValueError(f"Invalid parameters: {e}")

    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        raise RuntimeError(f"Tool execution failed: {e}")
```

---

## OAuth2 Integration

### Check User Scopes

```python
# In your agent/tool:
session = await session_handler.get_session(session_id)

required_scopes = ["bedrock:agents:invoke"]
has_required_scopes = all(
    scope in session.scopes
    for scope in required_scopes
)

if not has_required_scopes:
    raise PermissionError("Insufficient scopes for this operation")
```

### Request Additional Scopes

```python
# Guide user to re-authenticate with additional scopes
additional_scopes = ["mcp:resources:create"]
auth_url = oauth2_manager.get_authorization_url(scopes=additional_scopes)

return {
    "status": "additional_scopes_required",
    "auth_url": auth_url,
    "scopes": additional_scopes
}
```

### Validate Token

```python
# In middleware or before tool execution:
from src.auth.oauth2_manager import OAuth2Manager

try:
    claims = await oauth2_manager.validate_id_token(token)
    logger.info(f"Token valid for user: {claims['sub']}")
except Exception as e:
    logger.error(f"Token validation failed: {e}")
    raise ValueError("Invalid or expired token")
```

---

## Session Management

### Create Session

```python
# After OAuth2 authentication:
session = await session_handler.create_session(
    user_id=user_claims["sub"],
    username=user_claims.get("cognito:username"),
    access_token=tokens.access_token,
    refresh_token=tokens.refresh_token,
    scopes=granted_scopes,
    ip_address=client_ip,
    user_agent=user_agent
)
```

### Refresh Session

```python
# When access token expires:
new_tokens = await oauth2_manager.refresh_access_token(
    session.refresh_token
)

await session_handler.update_session(
    session_id,
    access_token=new_tokens.access_token,
    refresh_token=new_tokens.refresh_token
)
```

### List User Sessions

```python
# Get all active sessions for a user:
user_sessions = await session_handler.get_user_sessions(user_id)

for session in user_sessions:
    print(f"Session: {session['session_id']}")
    print(f"  Created: {session['created_at']}")
    print(f"  IP: {session['ip_address']}")
    print(f"  Active: {session['active']}")
```

### Logout (Revoke Session)

```python
# Revoke single session:
await session_handler.revoke_session(session_id)

# Logout all sessions:
await session_handler.revoke_all_user_sessions(user_id)
```

---

## FastAPI Endpoint Examples

### Secure Endpoint with Session Validation

```python
from fastapi import HTTPException, Depends

async def require_session(session_id: str = None):
    """Dependency to validate session"""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    session = await session_handler.get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    return session

@app.get("/api/protected-resource")
async def get_protected_resource(session: dict = Depends(require_session)):
    """Protected endpoint"""
    return {
        "data": "sensitive information",
        "user": session.user_id,
        "scopes": session.scopes
    }
```

### Endpoint with Scope Validation

```python
async def require_scope(required_scope: str):
    """Dependency to check scope"""
    async def check_scope(session: dict = Depends(require_session)):
        if required_scope not in session.scopes:
            raise HTTPException(
                status_code=403,
                detail=f"Missing scope: {required_scope}"
            )
        return session

    return check_scope

@app.post("/api/admin-operation")
async def admin_operation(
    session: dict = Depends(require_scope("admin:operations"))
):
    """Admin-only endpoint"""
    return {"status": "operation_completed"}
```

---

## Troubleshooting

### Session Not Found

**Problem**: "Session {session_id} not found"

**Solutions**:
1. Verify session_id is correct
2. Check if session expired (DynamoDB TTL)
3. Re-authenticate to create new session

### Missing Scopes

**Problem**: "Missing bedrock:agents:invoke scope"

**Solutions**:
1. Request additional scopes during login
2. User re-authenticates with required scopes
3. Check scope configuration in Cognito

### Token Validation Failed

**Problem**: "Invalid or expired token"

**Solutions**:
1. Refresh token using refresh_token
2. If refresh fails, re-authenticate
3. Verify token hasn't been tampered with

### MCP Tool Not Found

**Problem**: "Tool {tool_name} not found on server {server_name}"

**Solutions**:
1. Verify tool name is correct
2. Check server is registered
3. Verify tool is registered with server

---

## Best Practices

1. **Always validate sessions** before executing operations
2. **Check scopes** before allowing sensitive operations
3. **Log all operations** for audit trail
4. **Handle errors gracefully** with meaningful error messages
5. **Cache JWKS** for better performance
6. **Use TTL** for session expiration
7. **Rotate refresh tokens** periodically
8. **Mask sensitive data** in logs

---

## Examples Repository

For complete working examples, see:
- `/examples/custom_agent.py` - Custom agent implementation
- `/examples/custom_mcp_server.py` - Custom MCP server
- `/examples/fastapi_integration.py` - FastAPI endpoints

---

## Support

- Check TESTING.md for testing patterns
- See DEPLOYMENT.md for deployment procedures
- Review README.md for API reference
