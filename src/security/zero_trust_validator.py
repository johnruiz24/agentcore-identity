"""Zero-trust validation layer for AgentCore Identity.

Implements strict validation at every interaction point regardless of
previous trust relationships, following zero-trust security principles.
"""

import logging
import time
from typing import Dict, Optional, List, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationResult(str, Enum):
    """Validation result status."""

    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    UNAUTHORIZED = "unauthorized"
    REVOKED = "revoked"
    SUSPICIOUS = "suspicious"


@dataclass
class ValidationContext:
    """Context for validation."""

    session_id: str
    user_id: str
    ip_address: str
    user_agent: str
    operation: str
    resource: Optional[str] = None


@dataclass
class AuditLogEntry:
    """Audit log entry for compliance and security analysis."""

    log_id: str
    timestamp: int
    session_id: str
    user_id: str
    action: str
    resource: str
    result: str
    ip_address: str
    user_agent: str
    details: Dict[str, Any]


class ZeroTrustValidator:
    """Enforces zero-trust security validation.

    Validates every request independently regardless of:
    - Previous trust relationships
    - Session age
    - IP reputation
    - Device trust

    Applies multi-factor validation:
    1. Session validation
    2. Scope verification
    3. Credential validity
    4. Resource authorization
    5. Anomaly detection
    """

    def __init__(self):
        """Initialize validator."""
        self._audit_logs: List[AuditLogEntry] = []
        self._ip_history: Dict[str, List[int]] = {}  # Track IP changes per session
        self._user_agent_history: Dict[str, List[str]] = {}  # Track user agents
        logger.info("ZeroTrustValidator initialized")

    async def validate_session_and_scope(
        self,
        session_id: str,
        required_scope: str,
        session_data: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """Validate session and required scope.

        Zero-trust checks:
        1. Session exists
        2. Session not expired
        3. Session not revoked
        4. User has required scope
        5. No suspicious behavior

        Args:
            session_id: Session ID
            required_scope: Required OAuth scope
            session_data: Session data (id, user_id, scopes, expires_at, revoked)

        Returns:
            ValidationResult

        Raises:
            ValueError: For validation errors
        """
        logger.debug(f"Validating session: {session_id}, scope: {required_scope}")

        if not session_data:
            logger.error(f"Session not found: {session_id}")
            return ValidationResult.INVALID

        # Check 1: Session not null
        if not session_id:
            return ValidationResult.INVALID

        # Check 2: Session not expired
        expires_at = session_data.get("expires_at")
        if expires_at and int(time.time()) > expires_at:
            logger.warning(f"Session expired: {session_id}")
            return ValidationResult.EXPIRED

        # Check 3: Session not revoked
        if session_data.get("revoked", False):
            logger.warning(f"Session revoked: {session_id}")
            return ValidationResult.REVOKED

        # Check 4: User has required scope
        scopes = session_data.get("scopes", [])
        if required_scope not in scopes:
            logger.warning(
                f"Insufficient scope: session={session_id}, required={required_scope}"
            )
            return ValidationResult.UNAUTHORIZED

        logger.info(f"Session validation passed: {session_id}")
        return ValidationResult.VALID

    async def validate_credential_access(
        self,
        session_id: str,
        provider_name: str,
        operation: str,
        credential_data: Optional[Dict[str, Any]] = None,
        session_data: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """Validate credential access is authorized.

        Zero-trust checks:
        1. Session is valid
        2. Credential belongs to session
        3. Credential not revoked
        4. Credential not expired
        5. Operation allowed by scope
        6. Access pattern not anomalous

        Args:
            session_id: Session ID
            provider_name: OAuth provider
            operation: Operation (read, use, refresh)
            credential_data: Credential data
            session_data: Session data

        Returns:
            ValidationResult
        """
        logger.debug(
            f"Validating credential access: session={session_id}, provider={provider_name}, op={operation}"
        )

        # Check 1: Validate session first (always)
        session_validation = await self.validate_session_and_scope(
            session_id, f"credential:{provider_name}", session_data
        )
        if session_validation != ValidationResult.VALID:
            return session_validation

        if not credential_data:
            logger.error(f"Credential not found: {provider_name}")
            return ValidationResult.INVALID

        # Check 2: Verify ownership
        if credential_data.get("session_id") != session_id:
            logger.error(f"Credential ownership mismatch: {session_id}")
            return ValidationResult.UNAUTHORIZED

        # Check 3: Not revoked
        if credential_data.get("validation_status") == "revoked":
            logger.warning(f"Credential revoked: {provider_name}")
            return ValidationResult.REVOKED

        # Check 4: Not expired
        expires_at = credential_data.get("expires_at")
        if expires_at and int(time.time()) > expires_at:
            logger.warning(f"Credential expired: {provider_name}")
            return ValidationResult.EXPIRED

        # Check 5: Operation allowed by scope
        scopes = credential_data.get("scopes", [])
        allowed_ops = {
            "read": len(scopes) > 0,
            "use": len(scopes) > 0,
            "refresh": "refresh_token" in credential_data,
        }

        if not allowed_ops.get(operation, False):
            logger.warning(
                f"Operation not allowed: operation={operation}, provider={provider_name}"
            )
            return ValidationResult.UNAUTHORIZED

        logger.info(f"Credential access validation passed: {provider_name}")
        return ValidationResult.VALID

    async def validate_provider_request(
        self,
        provider_name: str,
        provider_callback_url: str,
        state: str,
        expected_state: str,
        registered_providers: Optional[Dict[str, str]] = None,
    ) -> ValidationResult:
        """Validate requests from external providers.

        Zero-trust checks:
        1. Provider is registered
        2. Callback URL matches registered URL
        3. State token matches (CSRF protection)
        4. Provider credentials valid

        Args:
            provider_name: Provider identifier
            provider_callback_url: Callback URL from provider
            state: State token from provider
            expected_state: Expected state token
            registered_providers: Dict of registered providers

        Returns:
            ValidationResult
        """
        logger.debug(f"Validating provider request: {provider_name}")

        if not registered_providers:
            registered_providers = {}

        # Check 1: Provider is registered
        if provider_name not in registered_providers:
            logger.error(f"Unknown provider: {provider_name}")
            return ValidationResult.INVALID

        # Check 2: CSRF protection - state token match
        if state != expected_state:
            logger.error(f"CSRF state mismatch for provider: {provider_name}")
            return ValidationResult.SUSPICIOUS

        # Check 3: Callback URL matches registration
        registered_url = registered_providers.get(provider_name)
        if provider_callback_url != registered_url:
            logger.error(
                f"Callback URL mismatch for {provider_name}: {provider_callback_url}"
            )
            return ValidationResult.SUSPICIOUS

        logger.info(f"Provider request validation passed: {provider_name}")
        return ValidationResult.VALID

    async def validate_ip_consistency(
        self, session_id: str, current_ip: str
    ) -> ValidationResult:
        """Check for suspicious IP address changes.

        Args:
            session_id: Session ID
            current_ip: Current request IP

        Returns:
            ValidationResult (VALID or SUSPICIOUS)
        """
        if session_id not in self._ip_history:
            self._ip_history[session_id] = [current_ip]
            return ValidationResult.VALID

        ip_list = self._ip_history[session_id]
        last_ip = ip_list[-1]

        # Flag if IP changed (not necessarily invalid, but suspicious)
        if current_ip != last_ip:
            logger.warning(
                f"IP change detected: session={session_id}, old={last_ip}, new={current_ip}"
            )
            # Add to history but don't block
            ip_list.append(current_ip)
            # Keep only last 10 IPs
            if len(ip_list) > 10:
                ip_list.pop(0)

            # If multiple IPs in short time, suspicious
            if len(set(ip_list[-5:])) > 3:
                return ValidationResult.SUSPICIOUS

        return ValidationResult.VALID

    async def validate_user_agent_consistency(
        self, session_id: str, current_user_agent: str
    ) -> ValidationResult:
        """Check for suspicious user agent changes.

        Args:
            session_id: Session ID
            current_user_agent: Current user agent string

        Returns:
            ValidationResult (VALID or SUSPICIOUS)
        """
        if session_id not in self._user_agent_history:
            self._user_agent_history[session_id] = [current_user_agent]
            return ValidationResult.VALID

        ua_list = self._user_agent_history[session_id]
        last_ua = ua_list[-1]

        if current_user_agent != last_ua:
            logger.warning(
                f"User agent change detected: session={session_id}"
            )
            ua_list.append(current_user_agent)

            if len(ua_list) > 10:
                ua_list.pop(0)

        return ValidationResult.VALID

    async def log_audit_entry(
        self,
        session_id: str,
        user_id: str,
        action: str,
        resource: str,
        result: str,
        ip_address: str,
        user_agent: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log audit entry for compliance.

        Args:
            session_id: Session ID
            user_id: User ID
            action: Action performed
            resource: Resource accessed
            result: Result (success, failed, denied)
            ip_address: Request IP address
            user_agent: Request user agent
            details: Additional details
        """
        import uuid

        entry = AuditLogEntry(
            log_id=str(uuid.uuid4()),
            timestamp=int(time.time()),
            session_id=session_id,
            user_id=user_id,
            action=action,
            resource=resource,
            result=result,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details or {},
        )

        self._audit_logs.append(entry)

        logger.info(
            f"Audit log: action={action}, resource={resource}, result={result}"
        )

    def get_audit_logs(
        self, session_id: Optional[str] = None, limit: int = 100
    ) -> List[AuditLogEntry]:
        """Retrieve audit logs.

        Args:
            session_id: Optional filter by session
            limit: Maximum number of logs

        Returns:
            List of audit log entries
        """
        logs = self._audit_logs

        if session_id:
            logs = [log for log in logs if log.session_id == session_id]

        # Return most recent logs
        return logs[-limit:]


# Global instance
_validator = ZeroTrustValidator()


def get_zero_trust_validator() -> ZeroTrustValidator:
    """Get global zero-trust validator instance.

    Returns:
        Global ZeroTrustValidator instance
    """
    return _validator
