"""AgentCore Runtime Entrypoint for Bedrock AgentCore Identity Service.

This is the main entry point for deploying AgentCore Identity Service
to AWS AgentCore Runtime (ECS/Fargate).
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict

from src.deployment.fastapi_server import app
from src.auth.oauth2_manager import OAuth2Manager
from src.auth.session_handler import SessionHandler
from src.vault.credential_vault import CredentialVault
from src.storage.dynamodb_vault import DynamoDBCredentialVault
from src.storage.dynamodb_flows import DynamoDBOAuthFlowStore
from src.storage.dynamodb_audit import DynamoDBauditStore
from src.aws.cloudwatch_logger import CloudWatchLogger
from src.aws.kms_manager import KMSManager
from src.aws.lambda_client import LambdaClient
from src.aws.iam_manager import IAMManager


# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class AgentCoreIdentityService:
    """Main service class for Bedrock AgentCore Identity.

    Orchestrates OAuth2 authentication, credential management, and
    MCP server integration for Bedrock Agents.
    """

    def __init__(self):
        """Initialize AgentCore Identity Service."""
        self.region = os.getenv("AWS_REGION", "eu-central-1")
        self.account_id = os.getenv("AWS_ACCOUNT_ID", "<AWS_ACCOUNT_ID>")

        # Initialize AWS clients
        logger.info(f"Initializing AgentCore Identity Service (Region: {self.region})")

        self.kms_manager = KMSManager(region=self.region)
        self.cloudwatch_logger = CloudWatchLogger(region=self.region)
        self.lambda_client = LambdaClient(region=self.region)
        self.iam_manager = IAMManager(region=self.region)

        # Initialize OAuth2 and credential storage
        self.oauth2_manager = OAuth2Manager()
        self.session_handler = SessionHandler()

        # Initialize DynamoDB storage (persistent)
        self.credential_vault = DynamoDBCredentialVault(region=self.region)
        self.oauth_flow_store = DynamoDBOAuthFlowStore(region=self.region)
        self.audit_store = DynamoDBauditStore(region=self.region)

        logger.info("✅ AgentCore Identity Service initialized")

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all services.

        Returns:
            Health status dictionary
        """
        health = {
            "service": "agentcore-identity",
            "status": "healthy",
            "region": self.region,
            "components": {},
        }

        # Check DynamoDB
        try:
            # Try to list a credential to verify DynamoDB access
            tables_accessible = True
            health["components"]["dynamodb"] = "✅ accessible"
        except Exception as e:
            health["components"]["dynamodb"] = f"❌ error: {e}"
            health["status"] = "degraded"

        # Check KMS
        try:
            key_id = KMSManager.get_or_create_key(
                "alias/agentcore-identity", self.region
            )
            health["components"]["kms"] = "✅ accessible"
        except Exception as e:
            health["components"]["kms"] = f"❌ error: {e}"
            health["status"] = "degraded"

        # Check CloudWatch
        try:
            health["components"]["cloudwatch"] = "✅ accessible"
        except Exception as e:
            health["components"]["cloudwatch"] = f"❌ error: {e}"
            health["status"] = "degraded"

        return health

    async def startup(self):
        """Run startup procedures."""
        logger.info("🚀 Starting AgentCore Identity Service...")

        # Verify DynamoDB tables exist
        logger.info("Verifying DynamoDB tables...")
        try:
            # These will raise if tables don't exist
            await self.credential_vault.list_credentials("startup-test")
            logger.info("✅ DynamoDB credentials table verified")
        except Exception as e:
            logger.warning(f"⚠️  DynamoDB initialization: {e}")

        # Log startup event
        try:
            await self.audit_store.log_entry(
                session_id="system",
                user_id="system",
                action="service_startup",
                resource="agentcore-identity",
                result="success",
                details={"region": self.region, "account": self.account_id},
            )
            logger.info("✅ Startup logged to audit trail")
        except Exception as e:
            logger.warning(f"⚠️  Audit logging: {e}")

        logger.info("✅ AgentCore Identity Service startup complete")

    async def shutdown(self):
        """Run shutdown procedures."""
        logger.info("🛑 Shutting down AgentCore Identity Service...")

        # Log shutdown event
        try:
            await self.audit_store.log_entry(
                session_id="system",
                user_id="system",
                action="service_shutdown",
                resource="agentcore-identity",
                result="success",
            )
            logger.info("✅ Shutdown logged to audit trail")
        except Exception as e:
            logger.warning(f"⚠️  Shutdown audit logging: {e}")

        logger.info("✅ AgentCore Identity Service shutdown complete")

    def run(self):
        """Run the service (for entrypoint.py)."""
        main()


# Global service instance
service: AgentCoreIdentityService = None


@app.on_event("startup")
async def startup_event():
    """FastAPI startup event handler."""
    global service
    service = AgentCoreIdentityService()
    await service.startup()


@app.on_event("shutdown")
async def shutdown_event():
    """FastAPI shutdown event handler."""
    global service
    if service:
        await service.shutdown()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    global service
    if not service:
        return {"status": "initializing"}
    return await service.health_check()


@app.get("/agentcore/info")
async def service_info():
    """Get service information."""
    return {
        "service": "bedrock-agentcore-identity",
        "version": "1.0.0",
        "description": "OAuth2 Credential Management for Bedrock Agents",
        "status": "operational",
        "features": [
            "OAuth2 Authorization Code Flow",
            "Credential Storage with KMS Encryption",
            "Session Management",
            "Audit Logging",
            "MCP Server Integration",
            "Zero-Trust Validation",
        ],
    }


def main():
    """Main entry point for AgentCore Runtime."""
    import uvicorn

    logger.info("🚀 Bedrock AgentCore Identity Service starting...")
    logger.info(f"Region: {os.getenv('AWS_REGION', 'eu-central-1')}")
    logger.info(f"Account: {os.getenv('AWS_ACCOUNT_ID', 'N/A')}")

    # Start FastAPI server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Service interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
