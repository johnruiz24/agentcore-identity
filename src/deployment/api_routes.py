"""FastAPI routes for AgentCore Identity OAuth and token exchange."""

import logging
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from src.auth.oauth_flow_orchestrator import get_oauth_flow_orchestrator
from src.auth.token_exchange_service import get_token_exchange_service
from src.vault.credential_vault import get_credential_vault
from src.security.zero_trust_validator import get_zero_trust_validator
from src.resources.google_calendar import get_google_calendar_service

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/oauth", tags=["OAuth"])

# Get service instances
oauth_orchestrator = get_oauth_flow_orchestrator()
token_exchange_service = get_token_exchange_service()
credential_vault = get_credential_vault()
zero_trust_validator = get_zero_trust_validator()
google_calendar = get_google_calendar_service()


# ============================================================================
# Pydantic Models
# ============================================================================


class OAuthFlowInitRequest(BaseModel):
    """Request to initiate OAuth flow."""

    session_id: str
    provider_name: str
    scopes: Optional[list[str]] = None


class OAuthFlowCallbackRequest(BaseModel):
    """OAuth provider callback."""

    code: str
    state: str


class TokenExchangeRequest(BaseModel):
    """Request to exchange token."""

    session_id: str
    provider_name: str
    scopes: Optional[list[str]] = None


class CalendarEventsRequest(BaseModel):
    """Request to get calendar events."""

    session_id: str
    calendar_id: str = "primary"
    max_results: int = 10


# ============================================================================
# OAuth Flow Endpoints
# ============================================================================


@router.post("/initiate")
async def initiate_oauth_flow(
    request: Request, body: OAuthFlowInitRequest
) -> Dict:
    """Initiate a 3-legged OAuth flow.

    Returns authorization URL user should visit.
    """
    try:
        logger.info(
            f"Initiating OAuth flow: session={body.session_id}, provider={body.provider_name}"
        )

        # Get client IP for audit
        client_ip = request.client.host if request.client else "unknown"

        # Validate session (in production: check against DynamoDB)
        await zero_trust_validator.validate_session_and_scope(
            body.session_id, f"oauth:{body.provider_name}"
        )

        # Initiate flow
        flow = await oauth_orchestrator.initiate_flow(
            session_id=body.session_id,
            provider_name=body.provider_name,
            scopes=body.scopes,
        )

        # Log audit entry
        await zero_trust_validator.log_audit_entry(
            session_id=body.session_id,
            user_id="unknown",  # Would come from session in production
            action="oauth_flow_initiated",
            resource=body.provider_name,
            result="success",
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent", "unknown"),
            details={"flow_id": flow.flow_id},
        )

        return {
            "flow_id": flow.flow_id,
            "authorization_url": flow.authorization_url,
            "expires_at": flow.expires_at,
            "provider": flow.provider_name,
        }

    except ValueError as e:
        logger.error(f"OAuth flow initiation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/callback/{flow_id}")
async def oauth_callback(
    flow_id: str, request: Request, code: str = Query(...), state: str = Query(...)
) -> Dict:
    """Handle OAuth provider callback.

    Called by provider after user authorizes.
    """
    try:
        logger.info(f"Processing OAuth callback: flow_id={flow_id}")

        # Get client IP for audit
        client_ip = request.client.host if request.client else "unknown"

        # Handle callback
        completion = await oauth_orchestrator.handle_callback(
            flow_id=flow_id, code=code, state=state
        )

        # Log audit entry
        await zero_trust_validator.log_audit_entry(
            session_id="unknown",  # Would come from flow in production
            user_id="unknown",
            action="oauth_callback_received",
            resource=completion.provider_name,
            result=completion.status,
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent", "unknown"),
            details={"flow_id": flow_id, "credential_id": completion.credential_id},
        )

        if completion.error:
            logger.error(f"OAuth callback failed: {completion.error}")
            return {
                "status": "error",
                "error": completion.error,
                "flow_id": flow_id,
            }

        return {
            "status": "success",
            "flow_id": flow_id,
            "credential_id": completion.credential_id,
            "provider": completion.provider_name,
        }

    except ValueError as e:
        logger.error(f"OAuth callback processing failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/flow/{flow_id}/status")
async def get_flow_status(flow_id: str) -> Dict:
    """Get status of OAuth flow.

    Returns flow status and details.
    """
    try:
        flow = await oauth_orchestrator.get_flow_status(flow_id)

        return {
            "flow_id": flow.flow_id,
            "status": flow.status.value,
            "provider": flow.provider_name,
            "expires_at": flow.expires_at,
            "completed_at": flow.completed_at,
            "error": flow.error,
            "credential_id": flow.credential_id,
        }

    except ValueError as e:
        logger.error(f"Flow status lookup failed: {e}")
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Token Exchange Endpoints
# ============================================================================


@router.post("/exchange")
async def exchange_token(request: Request, body: TokenExchangeRequest) -> Dict:
    """Initiate token exchange for resource provider.

    Converts user OAuth token to resource-specific access token.
    """
    try:
        logger.info(
            f"Initiating token exchange: session={body.session_id}, provider={body.provider_name}"
        )

        client_ip = request.client.host if request.client else "unknown"

        # Initiate exchange
        exchange = await token_exchange_service.initiate_exchange(
            session_id=body.session_id,
            provider_name=body.provider_name,
            user_token="",  # In production: get from session
            scopes=body.scopes,
        )

        # Log audit entry
        await zero_trust_validator.log_audit_entry(
            session_id=body.session_id,
            user_id="unknown",
            action="token_exchange_initiated",
            resource=body.provider_name,
            result="success",
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent", "unknown"),
            details={"exchange_id": exchange.exchange_id},
        )

        return {
            "exchange_id": exchange.exchange_id,
            "status": exchange.status.value,
            "provider": body.provider_name,
        }

    except ValueError as e:
        logger.error(f"Token exchange failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Credential Vault Endpoints
# ============================================================================


@router.get("/credentials")
async def list_credentials(session_id: str) -> Dict:
    """List all stored credentials for session.

    Does not include sensitive token data.
    """
    try:
        logger.debug(f"Listing credentials for session: {session_id}")

        credentials = await credential_vault.list_credentials(session_id)

        return {
            "credentials": [c.to_dict() for c in credentials],
            "count": len(credentials),
        }

    except Exception as e:
        logger.error(f"Failed to list credentials: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/credentials/{provider}")
async def get_credential(session_id: str, provider: str) -> Dict:
    """Get credential for specific provider.

    Returns decrypted credential (sensitive data).
    """
    try:
        logger.debug(f"Retrieving credential: provider={provider}, session={session_id}")

        # In production: look up credential by provider and session
        # For now: return placeholder
        return {
            "provider": provider,
            "status": "valid",
            "scopes": ["calendar"],
            "expires_at": None,
        }

    except ValueError as e:
        logger.error(f"Credential retrieval failed: {e}")
        raise HTTPException(status_code=403, detail="Access denied")
    except Exception as e:
        logger.error(f"Failed to retrieve credential: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Google Calendar Integration Endpoints
# ============================================================================


@router.post("/calendar/events")
async def get_calendar_events(
    request: Request, body: CalendarEventsRequest
) -> Dict:
    """Get calendar events using OAuth credential.

    Demonstrates resource provider integration with OAuth.
    """
    try:
        logger.info(f"Getting calendar events: session={body.session_id}")

        client_ip = request.client.host if request.client else "unknown"

        # In production:
        # 1. Validate session
        # 2. Get credential from vault
        # 3. Decrypt access token
        # 4. Call Google Calendar API

        # For now: return mock data
        result = {
            "calendar_id": body.calendar_id,
            "events": [
                {
                    "id": "1",
                    "summary": "Team Standup",
                    "start": {"dateTime": "2026-02-24T09:00:00"},
                    "end": {"dateTime": "2026-02-24T09:30:00"},
                }
            ],
            "count": 1,
        }

        # Log audit entry
        await zero_trust_validator.log_audit_entry(
            session_id=body.session_id,
            user_id="unknown",
            action="calendar_events_fetched",
            resource="google_calendar",
            result="success",
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent", "unknown"),
            details={"event_count": 1},
        )

        return result

    except ValueError as e:
        logger.error(f"Calendar events fetch failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Health Check
# ============================================================================


@router.get("/health")
async def health_check() -> Dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "agentcore-identity",
        "version": "1.0.0",
    }
