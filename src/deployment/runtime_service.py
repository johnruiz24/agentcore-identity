"""Bedrock AgentCore Runtime Service.

Executa Bedrock Agents usando as credenciais gerenciadas pelo Identity Service.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

import boto3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class BedrockAgentCoreRuntime:
    """Runtime for executing Bedrock Agents.
    
    Responsibilities:
    - Host and execute Bedrock Agents
    - Use credentials from Identity Service
    - Manage agent lifecycle
    - Handle tool invocations
    """

    def __init__(self):
        """Initialize Bedrock AgentCore Runtime."""
        self.region = os.getenv("AWS_REGION", "eu-central-1")
        self.bedrock_client = boto3.client("bedrock-agent-runtime", region_name=self.region)
        self.bedrock_agents_client = boto3.client("bedrock-agent", region_name=self.region)
        
        logger.info(f"🚀 Bedrock AgentCore Runtime initialized (Region: {self.region})")

    async def invoke_agent(
        self,
        agent_id: str,
        session_id: str,
        input_text: str,
        session_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Invoke a Bedrock Agent.
        
        Args:
            agent_id: ID of the agent to invoke
            session_id: Session ID for credential lookup
            input_text: Input text for the agent
            session_state: Optional session state
            
        Returns:
            Agent response
        """
        try:
            logger.info(f"Invoking agent {agent_id} with session {session_id}")
            
            # Call Bedrock Agent Runtime
            response = self.bedrock_client.invoke_agent(
                agentId=agent_id,
                agentAliasId="LFSTUWBWTH",  # Default alias
                sessionId=session_id,
                inputText=input_text,
                sessionState=session_state or {},
            )
            
            # Process response
            result = {
                "agent_id": agent_id,
                "session_id": session_id,
                "status": "success",
                "response": response,
            }
            
            logger.info(f"✅ Agent invocation successful")
            return result
            
        except Exception as e:
            logger.error(f"❌ Agent invocation failed: {e}")
            return {
                "agent_id": agent_id,
                "session_id": session_id,
                "status": "error",
                "error": str(e),
            }

    async def list_agents(self) -> Dict[str, Any]:
        """List all available agents."""
        try:
            response = self.bedrock_agents_client.list_agents()
            return {
                "status": "success",
                "agents": response.get("agentSummaries", []),
            }
        except Exception as e:
            logger.error(f"Error listing agents: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def health_check(self) -> Dict[str, Any]:
        """Health check for runtime service."""
        return {
            "service": "bedrock-agentcore-runtime",
            "status": "healthy",
            "region": self.region,
        }


# Global runtime instance
runtime: Optional[BedrockAgentCoreRuntime] = None


async def get_runtime() -> BedrockAgentCoreRuntime:
    """Get or create runtime instance."""
    global runtime
    if runtime is None:
        runtime = BedrockAgentCoreRuntime()
    return runtime


if __name__ == "__main__":
    async def main():
        rt = await get_runtime()
        health = await rt.health_check()
        print(json.dumps(health, indent=2))

    asyncio.run(main())
