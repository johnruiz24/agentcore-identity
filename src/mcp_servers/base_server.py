"""Base MCP server with HTTP+SSE transport and session-based authentication."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


class Tool:
    """Definition of an MCP tool."""

    def __init__(
        self,
        name: str,
        description: str,
        params_schema: Dict[str, Any],
        required_scopes: List[str],
        handler: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Awaitable[Any]]] = None,
    ):
        """Initialize tool definition.

        Args:
            name: Tool name (must be unique per server)
            description: Human-readable description
            params_schema: JSON schema for parameters
            required_scopes: List of OAuth2 scopes required
            handler: Async callable to execute the tool
        """
        self.name = name
        self.description = description
        self.params_schema = params_schema
        self.required_scopes = required_scopes
        self.handler = handler

    async def execute(
        self, params: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute the tool.

        Args:
            params: Tool input parameters
            context: Execution context including session

        Returns:
            Tool result

        Raises:
            Exception: If execution fails
        """
        if not self.handler:
            raise NotImplementedError(f"Tool {self.name} has no handler")

        return await self.handler(params, context)


class MCPServer:
    """Base Model Context Protocol server with HTTP+SSE transport.

    Implements:
    - Session-based authentication
    - OAuth2 scope validation
    - Tool execution with context passing
    - Error handling and logging
    """

    def __init__(
        self,
        name: str,
        session_handler: Any,
    ):
        """Initialize MCP server.

        Args:
            name: Server name (e.g., "auth_server", "identity_server")
            session_handler: SessionHandler instance for session validation
        """
        self.name = name
        self.session_handler = session_handler
        self.tools: Dict[str, Tool] = {}
        self.sessions: Dict[str, Dict[str, Any]] = {}  # In-memory session cache

        logger.info(f"📦 Initializing MCP Server: {name}")

    def register_tool(self, tool: Tool) -> None:
        """Register a tool with this server.

        Args:
            tool: Tool instance to register
        """
        self.tools[tool.name] = tool
        logger.info(f"   ✓ Registered tool: {tool.name}")

    async def validate_session(
        self, session_id: str, required_scopes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Validate session and check scopes.

        Args:
            session_id: Session UUID
            required_scopes: List of scopes required (if any)

        Returns:
            Session data

        Raises:
            ValueError: If session invalid, expired, or lacking scopes
        """
        logger.info(f"🔐 Validating session: {session_id}")

        # Get session from SessionHandler
        session = await self.session_handler.get_session(session_id)

        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Check required scopes
        if required_scopes:
            missing_scopes = set(required_scopes) - set(session.scopes)
            if missing_scopes:
                raise ValueError(
                    f"Missing scopes: {missing_scopes}. User has: {session.scopes}"
                )

        logger.info(f"✓ Session validated: {session_id}")
        return {
            "session_id": session_id,
            "user_id": session.user_id,
            "email": session.email,
            "scopes": session.scopes,
            "created_at": session.created_at,
            "expires_at": session.expires_at,
        }

    async def invoke_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        session_id: str,
    ) -> Dict[str, Any]:
        """Invoke a tool with session validation.

        Args:
            tool_name: Name of the tool to invoke
            params: Tool input parameters
            session_id: Session UUID for authentication/authorization

        Returns:
            Tool result

        Raises:
            ValueError: If tool not found, session invalid, or scopes missing
        """
        try:
            logger.info(f"🔧 Invoking tool: {tool_name} for session: {session_id}")

            # Check tool exists
            if tool_name not in self.tools:
                raise ValueError(f"Tool {tool_name} not found on server {self.name}")

            tool = self.tools[tool_name]

            # Validate session and scopes
            session_data = await self.validate_session(
                session_id, tool.required_scopes
            )

            # Execute tool with context
            result = await tool.execute(params, context={"session": session_data})

            logger.info(f"✓ Tool executed: {tool_name}")
            return {
                "tool": tool_name,
                "result": result,
                "session_id": session_id,
                "timestamp": int(__import__("time").time()),
            }

        except Exception as e:
            logger.error(f"✗ Tool execution failed: {e}")
            raise

    def get_tools_list(self) -> List[Dict[str, Any]]:
        """Get list of available tools.

        Returns:
            List of tool definitions
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.params_schema,
                "requiredScopes": tool.required_scopes,
            }
            for tool in self.tools.values()
        ]

    def get_server_info(self) -> Dict[str, Any]:
        """Get server information.

        Returns:
            Server metadata
        """
        return {
            "name": self.name,
            "tools": len(self.tools),
            "toolsList": self.get_tools_list(),
        }

    async def handle_mcp_message(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle incoming MCP message.

        Message format:
        {
            "method": "tool_invoke",
            "params": {
                "session_id": "uuid",
                "tool": "tool_name",
                "input": {...}
            }
        }

        Args:
            message: MCP message

        Returns:
            Response message

        Raises:
            ValueError: If message invalid or execution fails
        """
        try:
            method = message.get("method")

            if method == "get_server_info":
                logger.info("📋 Getting server info")
                return {
                    "status": "success",
                    "data": self.get_server_info(),
                }

            elif method == "get_tools":
                logger.info("📋 Getting tools list")
                return {
                    "status": "success",
                    "data": {"tools": self.get_tools_list()},
                }

            elif method == "tool_invoke":
                params = message.get("params", {})
                session_id = params.get("session_id")
                tool_name = params.get("tool")
                tool_input = params.get("input", {})

                if not session_id or not tool_name:
                    raise ValueError("Missing session_id or tool name")

                result = await self.invoke_tool(tool_name, tool_input, session_id)
                return {
                    "status": "success",
                    "data": result,
                }

            else:
                raise ValueError(f"Unknown method: {method}")

        except Exception as e:
            logger.error(f"✗ MCP message handling failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def close(self) -> None:
        """Clean up resources."""
        logger.info(f"🧹 Closing MCP Server: {self.name}")
        self.sessions.clear()
