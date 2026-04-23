"""
FastAPI server for AgentCore Identity

Provides OAuth2 authentication endpoints and agent invocation endpoints
for local development and testing.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Load environment variables from .env
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Models
class LoginRequest(BaseModel):
    """Login request"""

    scopes: Optional[list[str]] = None
    state: Optional[str] = None


class AuthCallbackRequest(BaseModel):
    """Authorization callback from Cognito"""

    code: str
    state: Optional[str] = None


class TokenResponse(BaseModel):
    """Token response"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None


class UserResponse(BaseModel):
    """User response"""

    sub: str
    email: Optional[str] = None
    name: Optional[str] = None
    email_verified: Optional[bool] = None


class AgentInvokeRequest(BaseModel):
    """Agent invocation request"""

    prompt: str
    agent_id: str = "default"
    session_id: Optional[str] = None


class AgentInvokeResponse(BaseModel):
    """Agent invocation response"""

    response: str
    session_id: str
    user: str
    scopes: list[str]


class MCPMessage(BaseModel):
    """MCP message request"""

    method: str
    params: Optional[dict] = None


class MCPInvokeRequest(BaseModel):
    """MCP tool invocation request"""

    session_id: str
    server: str  # auth_server, identity_server, resource_server
    tool: str
    input: dict = {}


# Global instances (will be initialized in startup)
oauth2_manager = None
session_handler = None
bedrock_client = None
agent_executor = None
mcp_servers = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI app"""
    # Startup
    logger.info("🚀 Starting AgentCore Identity FastAPI server")

    global oauth2_manager, session_handler, bedrock_client, agent_executor, mcp_servers

    # Import managers
    from src.auth.oauth2_manager import OAuth2Manager
    from src.auth.session_handler import SessionHandler
    from src.agents import BedrockAgentExecutor, AuthTools, IdentityTools
    from src.mcp_servers import AuthServer, IdentityServer, ResourceServer

    # Initialize managers
    oauth2_manager = OAuth2Manager(
        user_pool_id=os.getenv("COGNITO_USER_POOL_ID"),
        client_id=os.getenv("COGNITO_CLIENT_ID"),
        client_secret=os.getenv("COGNITO_CLIENT_SECRET"),
        domain=os.getenv("COGNITO_DOMAIN"),
        region=os.getenv("AWS_REGION", "eu-central-1"),
        redirect_uri=os.getenv("OAUTH2_REDIRECT_URI"),
    )

    session_handler = SessionHandler(
        table_name=os.getenv("DYNAMODB_TABLE_SESSIONS"),
        region=os.getenv("AWS_REGION", "eu-central-1"),
        session_ttl_hours=int(os.getenv("OAUTH2_TOKEN_EXPIRY_MINUTES", "30")) // 60,
    )

    # Initialize agent executor
    auth_tools = AuthTools(oauth2_manager, session_handler)
    identity_tools = IdentityTools(session_handler, oauth2_manager)

    agent_executor = BedrockAgentExecutor(
        bedrock_model_id=os.getenv(
            "BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
        ),
        region=os.getenv("AWS_REGION", "eu-central-1"),
        auth_tools=auth_tools,
        identity_tools=identity_tools,
        session_handler=session_handler,
    )

    # Initialize MCP servers
    mcp_servers["auth_server"] = AuthServer(session_handler)
    mcp_servers["identity_server"] = IdentityServer(session_handler)
    mcp_servers["resource_server"] = ResourceServer(session_handler)

    logger.info("✓ OAuth2Manager initialized")
    logger.info("✓ SessionHandler initialized")
    logger.info("✓ BedrockAgentExecutor initialized")
    logger.info("✓ MCP Servers initialized (auth, identity, resource)")

    yield

    # Shutdown
    logger.info("🛑 Shutting down AgentCore Identity FastAPI server")
    if agent_executor:
        await agent_executor.close()
    for server in mcp_servers.values():
        await server.close()


# Create FastAPI app
app = FastAPI(
    title=os.getenv("APP_NAME", "AgentCore Identity"),
    version=os.getenv("APP_VERSION", "0.1.0"),
    description="OAuth2 Authentication and Identity Management for Bedrock Agents",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000", "http://localhost:8001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": os.getenv("APP_NAME"),
        "version": os.getenv("APP_VERSION"),
    }


# OAuth2 endpoints
@app.get("/auth/login")
async def login(scopes: Optional[str] = None, state: Optional[str] = None):
    """
    Initiate OAuth2 login flow

    Returns authorization URL
    """
    requested_scopes = scopes.split() if scopes else None
    auth_url = oauth2_manager.get_authorization_url(scopes=requested_scopes, state=state)

    logger.info(f"📝 Login initiated with scopes: {requested_scopes}")

    return {"authorization_url": auth_url}


@app.post("/auth/callback")
async def auth_callback(request: Request):
    """
    OAuth2 callback from Cognito

    Expects form data with 'code' and optional 'state'
    """
    try:
        form_data = await request.form()
        code = form_data.get("code")
        state = form_data.get("state")

        if not code:
            raise HTTPException(status_code=400, detail="Missing authorization code")

        # Exchange code for token
        token_response = oauth2_manager.exchange_code_for_token(code)

        # Validate ID token and get user info
        id_claims = oauth2_manager.validate_id_token(token_response.id_token)
        user_info = oauth2_manager.get_user_info(token_response.access_token)

        # Create session
        session_data = session_handler.create_session(
            user_id=user_info.sub,
            username=user_info.email or user_info.sub,
            access_token=token_response.access_token,
            scopes=token_response.scope.split() if token_response.scope else [],
            email=user_info.email,
            refresh_token=token_response.refresh_token,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        logger.info(f"✓ User authenticated: {user_info.email} (session: {session_data.session_id})")

        # Return HTML with redirect
        html = f"""
        <html>
            <head>
                <title>Authentication Successful</title>
                <script>
                    // Store session data in localStorage
                    localStorage.setItem('session_id', '{session_data.session_id}');
                    localStorage.setItem('access_token', '{token_response.access_token}');
                    localStorage.setItem('user_email', '{user_info.email}');

                    // Redirect to dashboard or home
                    window.location.href = '/dashboard?session={session_data.session_id}';
                </script>
            </head>
            <body>
                <p>Authentication successful! Redirecting...</p>
                <a href="/dashboard?session={session_data.session_id}">Click here if not redirected</a>
            </body>
        </html>
        """

        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"✗ Auth callback failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/dashboard")
async def dashboard(session: str):
    """Dashboard with session info"""
    session_data = session_handler.get_session(session)

    if not session_data:
        raise HTTPException(status_code=401, detail="Session not found or expired")

    html = f"""
    <html>
        <head>
            <title>AgentCore Identity Dashboard</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .container {{ max-width: 800px; margin: 0 auto; }}
                .info {{ background: #f0f0f0; padding: 20px; border-radius: 5px; margin: 10px 0; }}
                .scopes {{ background: #e8f4f8; padding: 10px; border-radius: 3px; }}
                code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>AgentCore Identity Dashboard</h1>

                <div class="info">
                    <h2>User Information</h2>
                    <p><strong>Username:</strong> {session_data.username}</p>
                    <p><strong>Email:</strong> {session_data.email}</p>
                    <p><strong>User ID:</strong> <code>{session_data.user_id}</code></p>
                </div>

                <div class="info">
                    <h2>Session Information</h2>
                    <p><strong>Session ID:</strong> <code>{session_data.session_id}</code></p>
                    <p><strong>Created:</strong> {session_data.created_at}</p>
                    <p><strong>Expires:</strong> {session_data.expires_at}</p>
                    <p><strong>Status:</strong> {'Active' if session_data.active else 'Inactive'}</p>
                </div>

                <div class="info">
                    <h2>OAuth2 Scopes</h2>
                    <div class="scopes">
                        {', '.join(session_data.scopes) if session_data.scopes else 'No scopes'}
                    </div>
                </div>

                <div class="info">
                    <h2>Actions</h2>
                    <p>
                        <a href="/auth/logout?session={session_data.session_id}">Logout</a> |
                        <a href="/api/sessions/{session_data.session_id}">View Session Details</a> |
                        <a href="/api/agents/invoke">Invoke Agent</a>
                    </p>
                </div>
            </div>
        </body>
    </html>
    """

    return HTMLResponse(content=html)


@app.get("/auth/logout")
async def logout(session: str):
    """Logout endpoint"""
    session_handler.revoke_session(session)
    logger.info(f"✓ User logged out (session: {session})")

    return RedirectResponse(url="/", status_code=302)


# Session endpoints
@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details"""
    session_data = session_handler.get_session(session_id)

    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    return session_data


@app.get("/api/sessions/user/{user_id}")
async def get_user_sessions(user_id: str):
    """Get all sessions for a user"""
    sessions = session_handler.get_user_sessions(user_id)
    return [s.model_dump() for s in sessions]


@app.post("/api/sessions/{session_id}/revoke")
async def revoke_session(session_id: str):
    """Revoke a session"""
    if not session_handler.revoke_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info(f"✓ Session revoked: {session_id}")

    return {"message": "Session revoked"}


# Agent endpoints
@app.post("/agents/invoke")
async def invoke_agent(request: AgentInvokeRequest):
    """
    Invoke a Bedrock Agent

    Requires valid session_id. The agent will validate the session and
    execute the prompt using available identity management tools.
    """
    try:
        if not request.session_id:
            raise HTTPException(status_code=400, detail="session_id is required")

        logger.info(f"🤖 Agent invoke request: prompt='{request.prompt[:50]}...'")

        # Validate session exists
        session = await session_handler.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=401, detail="Session not found or expired")

        # Check for required scope
        if "bedrock:agents:invoke" not in session.scopes:
            raise HTTPException(status_code=403, detail="Missing bedrock:agents:invoke scope")

        # Invoke agent
        result = await agent_executor.invoke(
            prompt=request.prompt, session_id=request.session_id
        )

        logger.info(f"✓ Agent invocation completed")

        return AgentInvokeResponse(
            response=result["response"],
            session_id=result["session_id"],
            user=session.email or session.username,
            scopes=session.scopes,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"✗ Agent invocation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# MCP endpoints
@app.post("/mcp/invoke")
async def mcp_invoke(request: MCPInvokeRequest):
    """
    Invoke an MCP tool

    Supports three MCP servers:
    - auth_server: OAuth2 scope operations
    - identity_server: User profile and session operations
    - resource_server: Resource management

    Requires valid session_id for authentication.
    """
    try:
        server_name = request.server
        tool_name = request.tool

        logger.info(f"🔧 MCP invoke: server={server_name}, tool={tool_name}")

        # Check server exists
        if server_name not in mcp_servers:
            raise HTTPException(
                status_code=400,
                detail=f"MCP server '{server_name}' not found. Available: {list(mcp_servers.keys())}",
            )

        server = mcp_servers[server_name]

        # Invoke tool
        result = await server.invoke_tool(
            tool_name=tool_name,
            params=request.input,
            session_id=request.session_id,
        )

        logger.info(f"✓ MCP tool executed: {tool_name}")

        return {
            "status": "success",
            "data": result,
        }

    except ValueError as e:
        logger.error(f"✗ MCP invocation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"✗ MCP invocation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/mcp/servers")
async def mcp_servers_list():
    """
    List available MCP servers and their tools
    """
    logger.info("📋 Listing MCP servers")

    servers_info = {}
    for name, server in mcp_servers.items():
        servers_info[name] = server.get_server_info()

    return {
        "servers": list(mcp_servers.keys()),
        "details": servers_info,
    }


@app.get("/mcp/servers/{server_name}")
async def mcp_server_info(server_name: str):
    """
    Get info about a specific MCP server and its tools
    """
    if server_name not in mcp_servers:
        raise HTTPException(status_code=404, detail=f"Server '{server_name}' not found")

    logger.info(f"📋 Getting info for MCP server: {server_name}")

    server = mcp_servers[server_name]
    return server.get_server_info()


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with instructions"""
    html = """
    <html>
        <head>
            <title>AgentCore Identity</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; max-width: 800px; margin: 0 auto; padding: 20px; }
                h1 { color: #333; }
                .section { background: #f9f9f9; padding: 20px; border-radius: 5px; margin: 20px 0; }
                code { background: #f0f0f0; padding: 5px 10px; border-radius: 3px; }
                a { color: #0066cc; text-decoration: none; }
                a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <h1>🔐 AgentCore Identity</h1>
            <p>OAuth2 Authentication and Identity Management for AWS Bedrock Agents</p>

            <div class="section">
                <h2>Get Started</h2>
                <p><a href="/auth/login">Login with Cognito</a></p>
                <p><a href="/health">Health Check</a></p>
            </div>

            <div class="section">
                <h2>API Endpoints</h2>
                <ul>
                    <li><code>GET /auth/login</code> - Initiate OAuth2 login</li>
                    <li><code>POST /auth/callback</code> - OAuth2 callback from Cognito</li>
                    <li><code>GET /api/sessions/{session_id}</code> - Get session details</li>
                    <li><code>POST /agents/invoke</code> - Invoke a Bedrock Agent</li>
                </ul>
            </div>

            <div class="section">
                <h2>Documentation</h2>
                <p><a href="/docs">OpenAPI Documentation</a></p>
                <p><a href="/redoc">ReDoc Documentation</a></p>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html)


def main():
    """Run FastAPI server"""
    host = os.getenv("FASTAPI_HOST", "0.0.0.0")
    port = int(os.getenv("FASTAPI_PORT", "8000"))
    debug = os.getenv("FASTAPI_DEBUG", "false").lower() == "true"

    logger.info(f"🚀 Starting server on {host}:{port}")

    uvicorn.run(
        "src.deployment.fastapi_server:app",
        host=host,
        port=port,
        reload=debug,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
