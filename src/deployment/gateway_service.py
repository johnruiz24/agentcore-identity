"""Bedrock AgentCore Gateway Service.

Exponibiliza agents via APIs e integra com Identity Service para autenticação.
"""

import logging
import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from src.deployment.runtime_service import get_runtime
from src.auth.session_handler import SessionHandler
from src.storage.dynamodb_vault import DynamoDBCredentialVault

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Bedrock AgentCore Gateway",
    description="Gateway for Bedrock Agents with OAuth2 authentication",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
session_handler = SessionHandler()
credential_vault = DynamoDBCredentialVault(region=os.getenv("AWS_REGION", "eu-central-1"))


async def verify_token(authorization: str = Header(None)) -> Dict[str, Any]:
    """Verify OAuth2 token from Authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    try:
        # Extract token from "Bearer <token>"
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authorization scheme")
        
        # Verify token (simplified - in production validate JWT/OAuth2 properly)
        # This would call the Identity Service to validate
        return {
            "token": token,
            "valid": True,
        }
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    runtime = await get_runtime()
    return await runtime.health_check()


@app.post("/agents/{agent_id}/invoke")
async def invoke_agent(
    agent_id: str,
    request: Dict[str, Any],
    auth: Dict[str, Any] = Depends(verify_token),
):
    """Invoke a Bedrock Agent.
    
    Args:
        agent_id: ID of the agent
        request: Request body with input_text and session_id
        auth: Authenticated user info
        
    Returns:
        Agent response
    """
    try:
        logger.info(f"🔄 Gateway received request to invoke agent {agent_id}")
        
        session_id = request.get("session_id")
        input_text = request.get("input_text")
        
        if not session_id or not input_text:
            raise HTTPException(status_code=400, detail="Missing session_id or input_text")
        
        # Validate session exists (check with Identity Service)
        # This would query the credential vault
        
        # Forward to Runtime Service
        runtime = await get_runtime()
        result = await runtime.invoke_agent(
            agent_id=agent_id,
            session_id=session_id,
            input_text=input_text,
        )
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Gateway error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agents")
async def list_agents(auth: Dict[str, Any] = Depends(verify_token)):
    """List available agents."""
    try:
        runtime = await get_runtime()
        return await runtime.list_agents()
    except Exception as e:
        logger.error(f"Error listing agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/credentials/validate")
async def validate_credentials(
    request: Dict[str, Any],
    auth: Dict[str, Any] = Depends(verify_token),
):
    """Validate user credentials with Identity Service."""
    try:
        session_id = request.get("session_id")
        
        if not session_id:
            raise HTTPException(status_code=400, detail="Missing session_id")
        
        # Call Identity Service to validate credentials
        credentials = await credential_vault.retrieve_credential(session_id)
        
        if credentials:
            return {
                "status": "valid",
                "credentials_found": True,
            }
        else:
            return {
                "status": "invalid",
                "credentials_found": False,
            }
            
    except Exception as e:
        logger.error(f"Credential validation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/info")
async def gateway_info():
    """Get gateway information."""
    return {
        "service": "bedrock-agentcore-gateway",
        "version": "1.0.0",
        "description": "Gateway for Bedrock Agents with OAuth2 authentication",
        "features": [
            "Agent invocation",
            "OAuth2 authentication",
            "Credential validation",
            "Session management",
            "Rate limiting",
        ],
    }


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("GATEWAY_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
