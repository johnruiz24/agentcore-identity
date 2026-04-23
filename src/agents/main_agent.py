"""Bedrock Agent implementation for AgentCore Identity."""

import asyncio
import json
import logging
import boto3
from typing import Any, Dict, List, Optional
import os
from .mcp_subagent_orchestrator import MCPSubagentOrchestrator, OrchestrationResult
from .subagent_tool_router import SubagentSpec, SubagentToolRouter

logger = logging.getLogger(__name__)

# Initialize Bedrock Agents Runtime client
bedrock_agent_client = boto3.client(
    'bedrock-agent-runtime',
    region_name=os.getenv('AWS_REGION', 'us-east-1')
)


class BedrockAgentExecutor:
    """Executor for Bedrock agents with custom tools for identity management.

    This class orchestrates agent invocation, tool execution, and session validation
    using AWS Bedrock as the LLM backbone.
    """

    def __init__(
        self,
        bedrock_model_id: str,
        region: str,
        auth_tools: Any,
        identity_tools: Any,
        session_handler: Any,
    ):
        """Initialize Bedrock agent executor.

        Args:
            bedrock_model_id: Model ID for Bedrock (e.g., claude-3.5-sonnet)
            region: AWS region
            auth_tools: AuthTools instance for authentication operations
            identity_tools: IdentityTools instance for identity operations
            session_handler: SessionHandler instance for session management
        """
        self.bedrock_model_id = bedrock_model_id
        self.region = region
        self.auth_tools = auth_tools
        self.identity_tools = identity_tools
        self.session_handler = session_handler

        logger.info(f"🤖 Initializing Bedrock Agent Executor")
        logger.info(f"   Model: {bedrock_model_id}")
        logger.info(f"   Region: {region}")
        self._subagent_router = SubagentToolRouter(
            {
                "atlassian.list_accessible_resources": "___listAtlassianAccessibleResources",
                "atlassian.search_projects": "___searchJiraProjects",
                "atlassian.search_issues": "___searchJiraIssues",
                "google.create_calendar_event": "___createCalendarEvent",
            }
        )

    def route_subagent_tool(
        self,
        *,
        requested_logical_tool: str,
        arguments: Dict[str, Any],
        subagents: List[SubagentSpec],
        caller: Any,
        preferred_subagent: Optional[str] = None,
    ) -> OrchestrationResult:
        """Route and execute MCP-target tool calls from runtime orchestrator.

        This is the integration point for multi-target subagents (e.g., Jira/Calendar).
        It ensures unavailable tools are returned as structured errors instead of
        blindly attempting tool calls.
        """
        orchestrator = MCPSubagentOrchestrator(router=self._subagent_router, caller=caller)
        return orchestrator.execute(
            requested_logical_tool=requested_logical_tool,
            arguments=arguments,
            subagents=subagents,
            preferred_subagent=preferred_subagent,
        )

    async def validate_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Validate session before agent invocation.

        Args:
            session_id: UUID of the session to validate

        Returns:
            Session data if valid, None otherwise

        Raises:
            ValueError: If session is invalid or expired
        """
        logger.info(f"🔐 Validating session: {session_id}")

        session = await self.session_handler.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        logger.info(f"✓ Session validated: {session_id}")
        return session

    async def _execute_tool(
        self, tool_name: str, tool_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a tool by name with given input.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool not found or execution fails
        """
        logger.info(f"🔧 Executing tool: {tool_name}")

        # Authentication tools
        if tool_name == "validate_token":
            return await self.auth_tools.validate_token(tool_input.get("token"))
        elif tool_name == "refresh_session":
            return await self.auth_tools.refresh_session(tool_input.get("session_id"))
        elif tool_name == "get_token_info":
            return await self.auth_tools.get_token_info(tool_input.get("session_id"))
        elif tool_name == "revoke_session":
            return await self.auth_tools.revoke_session(tool_input.get("session_id"))

        # Identity tools
        elif tool_name == "get_user_profile":
            return await self.identity_tools.get_user_profile(
                tool_input.get("session_id")
            )
        elif tool_name == "list_user_sessions":
            return await self.identity_tools.list_user_sessions(
                tool_input.get("session_id")
            )
        elif tool_name == "get_session_details":
            return await self.identity_tools.get_session_details(
                tool_input.get("session_id")
            )
        elif tool_name == "check_scope":
            return await self.identity_tools.check_scope(
                tool_input.get("session_id"), tool_input.get("required_scope")
            )
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def _build_tool_definitions(self) -> List[Dict[str, Any]]:
        """Build list of tool definitions for the agent.

        Returns:
            List of tool definitions in Bedrock format
        """
        tools = []
        tools.extend(self.auth_tools.get_tool_definitions())
        tools.extend(self.identity_tools.get_tool_definitions())
        return tools

    async def invoke(
        self, prompt: str, session_id: str, temperature: float = 0.3
    ) -> Dict[str, Any]:
        """Invoke the Bedrock agent with a prompt.

        This is the main entry point for agent invocation. It validates the session,
        prepares tool definitions, and orchestrates the agent interaction.

        Args:
            prompt: User prompt for the agent
            session_id: UUID of the user's session
            temperature: Temperature for model (0.0-1.0)

        Returns:
            Dictionary containing:
                - response (str): Agent's final response
                - session_id (str): Session ID used
                - user_id (str): User ID from session
                - model (str): Model used
                - tokens_used (int): Approximate tokens used
                - tools_called (list): Tools that were invoked

        Raises:
            ValueError: If session invalid or agent invocation fails
        """
        logger.info(f"🚀 Invoking Bedrock agent for session: {session_id}")

        try:
            # Validate session
            session = await self.validate_session(session_id)

            # Build tool definitions
            tools = self._build_tool_definitions()
            logger.info(f"📋 Loaded {len(tools)} tools for agent")

            # Prepare context (handle both dict and object formats)
            if isinstance(session, dict):
                session_dict = session
            else:
                session_dict = {
                    "session_id": session.session_id,
                    "user_id": session.user_id,
                    "email": session.email,
                    "scopes": session.scopes,
                }

            system_prompt = self._get_system_prompt(session_dict)
            context = {
                "session_id": session_id,
                "user_id": session_dict.get("user_id"),
                "user_email": session_dict.get("email"),
                "scopes": session_dict.get("scopes", []),
            }

            # Invoke actual Bedrock Agent
            response = await self._invoke_bedrock_agent(
                prompt=prompt,
                context=context,
                session_id=session_id,
                temperature=temperature,
            )

            logger.info(f"✓ Agent invocation completed")

            # Extract user_id from session (handle both dict and object)
            if isinstance(session_dict, dict):
                user_id = session_dict.get("user_id", "unknown")
            else:
                user_id = getattr(session_dict, "user_id", "unknown")

            return {
                "response": response["message"],
                "session_id": session_id,
                "user_id": user_id,
                "model": self.bedrock_model_id,
                "tokens_used": response.get("tokens_used", 0),
                "tools_called": response.get("tools_called", []),
            }

        except Exception as e:
            logger.error(f"✗ Agent invocation failed: {e}")
            raise ValueError(f"Agent invocation failed: {str(e)}")

    def _get_system_prompt(self, session: Any) -> str:
        """Get system prompt customized for the user's session.

        Args:
            session: Session data (dict or SessionData object)

        Returns:
            System prompt string
        """
        from .prompts import AGENT_SYSTEM_PROMPT

        # Handle both dict and object formats
        if isinstance(session, dict):
            scopes = session.get("scopes", [])
            user_id = session.get("user_id", "unknown")
            email = session.get("email", "unknown")
            session_id = session.get("session_id", "unknown")
            created_at = session.get("created_at", "unknown")
            expires_at = session.get("expires_at", "unknown")
        else:
            scopes = session.scopes if hasattr(session, 'scopes') else []
            user_id = session.user_id if hasattr(session, 'user_id') else "unknown"
            email = session.email if hasattr(session, 'email') else "unknown"
            session_id = session.session_id if hasattr(session, 'session_id') else "unknown"
            created_at = session.created_at if hasattr(session, 'created_at') else "unknown"
            expires_at = session.expires_at if hasattr(session, 'expires_at') else "unknown"

        scopes_text = ", ".join(scopes) if scopes else "no scopes"

        return f"""{AGENT_SYSTEM_PROMPT}

## Current User Context

- User ID: {user_id}
- Email: {email}
- Session ID: {session_id}
- Granted Scopes: {scopes_text}
- Session Created: {created_at}
- Session Expires: {expires_at}

You must respect these scope boundaries when helping the user."""

    async def _invoke_bedrock_agent(
        self,
        prompt: str,
        context: Dict[str, Any],
        session_id: str,
        temperature: float,
    ) -> Dict[str, Any]:
        """Invoke actual AWS Bedrock Agent.

        Calls the AWS Bedrock Agents Runtime API to execute the agent
        with the provided prompt and session context.

        Args:
            prompt: User prompt for the agent
            context: Session context (user_id, scopes, etc.)
            session_id: Session ID for tracking
            temperature: Model temperature (currently unused, Bedrock agents don't support it)

        Returns:
            Agent response with message, tokens used, and tools called

        Raises:
            Exception: If agent invocation fails
        """
        try:
            agent_id = os.getenv('BEDROCK_AGENT_ID')
            alias_id = os.getenv('BEDROCK_AGENT_ALIAS_ID', 'TSTALIASID')

            if not agent_id:
                logger.warning("BEDROCK_AGENT_ID not set, using simulation mode")
                return await self._simulate_agent_response_fallback(prompt, context)

            logger.info(f"📞 Invoking Bedrock Agent: {agent_id}")

            # Build the input with session context
            input_text = f"""{prompt}

## Session Context
- Session ID: {session_id}
- User ID: {context['user_id']}
- User Email: {context['user_email']}
- Granted Scopes: {', '.join(context['scopes'])}
"""

            # Invoke the agent
            response = bedrock_agent_client.invoke_agent(
                agentId=agent_id,
                agentAliasId=alias_id,
                sessionId=session_id,
                inputText=input_text,
            )

            # Parse the streaming response
            event_stream = response.get('completion', [])
            agent_response = ""
            tools_called = []

            for event in event_stream:
                if 'chunk' in event:
                    chunk_data = event['chunk'].get('bytes', b'').decode('utf-8')
                    if chunk_data:
                        agent_response += chunk_data
                elif 'trace' in event:
                    trace_data = event['trace'].get('trace', {})
                    # Extract tool calls if any
                    if 'toolUse' in str(trace_data):
                        tools_called.append(trace_data)

            logger.info(f"✓ Agent response received ({len(agent_response)} chars)")

            return {
                "message": agent_response if agent_response else "Agent invocation completed without response.",
                "tokens_used": 0,  # Bedrock doesn't return token counts in agent invocation
                "tools_called": tools_called,
                "stop_reason": "end_turn",
            }

        except Exception as e:
            logger.error(f"✗ Bedrock agent invocation failed: {e}")
            # Fallback to simulation if Bedrock fails
            logger.info("⚠️  Falling back to simulation mode")
            return await self._simulate_agent_response_fallback(prompt, context)

    async def _simulate_agent_response_fallback(
        self,
        prompt: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Fallback simulation when Bedrock is unavailable.

        This is used when BEDROCK_AGENT_ID is not configured or
        Bedrock API calls fail, to allow testing without production setup.

        Args:
            prompt: User prompt
            context: Session context

        Returns:
            Simulated agent response
        """
        logger.info("🔄 Using fallback simulation mode")

        response_text = f"""[SIMULATION MODE] I'm processing your identity management request.

Session Context:
- User: {context['user_email']}
- Scopes: {', '.join(context['scopes'])}

Request: {prompt[:150]}

In production, I would now invoke available tools to:
1. Validate OAuth2 tokens
2. Manage session lifecycle
3. Check user permissions
4. Return relevant identity data

Available tools (in production):
- validate_token: Validate OAuth2 bearer tokens
- refresh_session: Refresh user sessions with new tokens
- get_user_profile: Retrieve user identity information
- list_user_sessions: List active sessions for the user
- revoke_session: Revoke specific session
- get_session_details: Get detailed session metadata
- check_scope: Verify if user has specific OAuth2 scope

To activate production mode, set BEDROCK_AGENT_ID environment variable."""

        return {
            "message": response_text,
            "tokens_used": len(prompt.split()) * 2,
            "tools_called": [],
            "stop_reason": "end_turn",
        }

    async def close(self) -> None:
        """Clean up resources."""
        logger.info("🧹 Closing Bedrock agent executor")
        # Add any cleanup logic if needed
