"""Lambda function handlers for AgentCore Identity Service tools."""

import json
import logging
from typing import Any, Dict

from src.auth.oauth2_manager import OAuth2Manager
from src.auth.session_handler import SessionHandler
from src.storage.dynamodb_vault import DynamoDBCredentialVault
from src.storage.dynamodb_flows import DynamoDBOAuthFlowStore
from src.storage.dynamodb_audit import DynamoDBauditStore
from src.aws.cloudwatch_logger import CloudWatchLogger


logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize services
oauth2_manager = OAuth2Manager()
session_handler = SessionHandler()
vault = DynamoDBCredentialVault()
flow_store = DynamoDBOAuthFlowStore()
audit_store = DynamoDBauditStore()
logger_cw = CloudWatchLogger()


def validate_oauth_token(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler to validate OAuth token.

    Args:
        event: Lambda event with token in body
        context: Lambda context

    Returns:
        Validation result
    """
    try:
        body = json.loads(event.get("body", "{}"))
        token = body.get("token")
        session_id = body.get("session_id")

        if not token or not session_id:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing token or session_id"}),
            }

        # Validate token
        is_valid = oauth2_manager.validate_token(token)

        if is_valid:
            logger_cw.log_auth_event(
                event_type="token_validation",
                session_id=session_id,
                user_id="system",
                provider="oauth2",
                status="success",
            )
            return {
                "statusCode": 200,
                "body": json.dumps({"valid": True, "token": token[:20] + "..."}),
            }
        else:
            logger_cw.log_auth_event(
                event_type="token_validation",
                session_id=session_id,
                user_id="system",
                provider="oauth2",
                status="failed",
                details={"reason": "Invalid token"},
            )
            return {
                "statusCode": 401,
                "body": json.dumps({"valid": False, "error": "Invalid token"}),
            }

    except Exception as e:
        logger.error(f"Token validation error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


def get_user_credentials(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler to retrieve user credentials.

    Args:
        event: Lambda event with credential_id and session_id
        context: Lambda context

    Returns:
        Credential data or error
    """
    try:
        body = json.loads(event.get("body", "{}"))
        credential_id = body.get("credential_id")
        session_id = body.get("session_id")

        if not credential_id or not session_id:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing credential_id or session_id"}),
            }

        # Retrieve credential
        import asyncio
        credential = asyncio.run(vault.retrieve_credential(credential_id, session_id))

        if not credential:
            logger_cw.log_credential_event(
                event_type="retrieve",
                credential_id=credential_id,
                session_id=session_id,
                provider="unknown",
                status="not_found",
            )
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "Credential not found"}),
            }

        logger_cw.log_credential_event(
            event_type="retrieve",
            credential_id=credential_id,
            session_id=session_id,
            provider=credential.provider_name,
            status="success",
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "credential_id": credential.credential_id,
                "provider": credential.provider_name,
                "scopes": credential.scopes,
                "expires_at": credential.expires_at,
            }),
        }

    except Exception as e:
        logger.error(f"Credential retrieval error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


def revoke_credentials(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler to revoke credentials.

    Args:
        event: Lambda event with credential_id
        context: Lambda context

    Returns:
        Revocation result
    """
    try:
        body = json.loads(event.get("body", "{}"))
        credential_id = body.get("credential_id")
        session_id = body.get("session_id")

        if not credential_id:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing credential_id"}),
            }

        # Revoke credential
        import asyncio
        asyncio.run(vault.revoke_credential(credential_id))

        logger_cw.log_credential_event(
            event_type="revoke",
            credential_id=credential_id,
            session_id=session_id or "unknown",
            provider="unknown",
            status="success",
        )

        return {
            "statusCode": 200,
            "body": json.dumps({"revoked": True, "credential_id": credential_id}),
        }

    except Exception as e:
        logger.error(f"Credential revocation error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


def list_session_credentials(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler to list credentials for session.

    Args:
        event: Lambda event with session_id
        context: Lambda context

    Returns:
        List of credentials
    """
    try:
        body = json.loads(event.get("body", "{}"))
        session_id = body.get("session_id")

        if not session_id:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing session_id"}),
            }

        # List credentials
        import asyncio
        credentials = asyncio.run(vault.list_credentials(session_id))

        return {
            "statusCode": 200,
            "body": json.dumps({
                "session_id": session_id,
                "credentials": [
                    {
                        "credential_id": c.credential_id,
                        "provider": c.provider_name,
                        "scopes": c.scopes,
                        "status": c.validation_status.value,
                    }
                    for c in credentials
                ],
            }),
        }

    except Exception as e:
        logger.error(f"List credentials error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }
