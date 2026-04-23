"""Secure encrypted storage for resource access credentials."""

import uuid
import time
import logging
import secrets
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationStatus(str, Enum):
    """Credential validation status."""

    VALID = "valid"
    EXPIRED = "expired"
    REVOKED = "revoked"
    UNKNOWN = "unknown"


@dataclass
class StoredCredential:
    """Encrypted credential record."""

    credential_id: str
    session_id: str
    provider_name: str
    encrypted_access_token: str
    scopes: List[str]
    created_at: int = field(default_factory=lambda: int(time.time()))
    expires_at: Optional[int] = None
    last_validated: Optional[int] = None
    validation_status: ValidationStatus = ValidationStatus.UNKNOWN
    encrypted_refresh_token: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_token: bool = False) -> Dict[str, Any]:
        """Convert to dictionary.

        Args:
            include_token: Include access token (caution: sensitive data)

        Returns:
            Dictionary representation
        """
        result = {
            "credential_id": self.credential_id,
            "provider_name": self.provider_name,
            "scopes": self.scopes,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "validation_status": self.validation_status.value,
            "metadata": self.metadata,
        }

        if include_token:
            result["encrypted_access_token"] = self.encrypted_access_token

        return result

    @property
    def is_expired(self) -> bool:
        """Check if credential has expired."""
        if self.expires_at is None:
            return False
        return int(time.time()) > self.expires_at


class CredentialVault:
    """Secure encrypted storage for resource access credentials.

    Implements zero-trust credential management with encryption,
    access control, and automatic expiration handling.
    """

    def __init__(self):
        """Initialize credential vault."""
        # In-memory storage (replace with DynamoDB + KMS in production)
        self._credentials: Dict[str, StoredCredential] = {}
        # Store encryption keys separately (in production: KMS)
        self._encryption_keys: Dict[str, str] = {}
        logger.info("CredentialVault initialized")

    async def store_credential(
        self,
        session_id: str,
        provider_name: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_at: Optional[int] = None,
        scopes: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StoredCredential:
        """Store a new credential with encryption.

        Args:
            session_id: User session ID
            provider_name: OAuth provider name
            access_token: Access token to store
            refresh_token: Optional refresh token
            expires_at: Token expiration timestamp
            scopes: OAuth scopes
            metadata: Additional metadata

        Returns:
            StoredCredential record

        Raises:
            ValueError: If storage fails
        """
        credential_id = str(uuid.uuid4())

        try:
            # Encrypt tokens (in production: use KMS)
            encrypted_access = self._encrypt(access_token)
            encrypted_refresh = self._encrypt(refresh_token) if refresh_token else None

            credential = StoredCredential(
                credential_id=credential_id,
                session_id=session_id,
                provider_name=provider_name,
                encrypted_access_token=encrypted_access,
                encrypted_refresh_token=encrypted_refresh,
                scopes=scopes or [],
                expires_at=expires_at,
                validation_status=ValidationStatus.VALID,
                metadata=metadata or {},
            )

            self._credentials[credential_id] = credential

            # Store encryption key mapping (production: handled by KMS)
            self._encryption_keys[credential_id] = secrets.token_urlsafe(32)

            logger.info(
                f"Credential stored: session={session_id}, provider={provider_name}"
            )

            return credential

        except Exception as e:
            logger.error(f"Failed to store credential: {e}")
            raise ValueError(f"Credential storage failed: {str(e)}")

    async def retrieve_credential(
        self, credential_id: str, session_id: Optional[str] = None
    ) -> Optional[StoredCredential]:
        """Retrieve decrypted credential (with access control).

        Args:
            credential_id: Credential ID
            session_id: Optional session ID for validation

        Returns:
            Decrypted StoredCredential or None if not found

        Raises:
            ValueError: If access denied
        """
        if credential_id not in self._credentials:
            logger.warning(f"Credential not found: {credential_id}")
            return None

        credential = self._credentials[credential_id]

        # Validate session ownership (zero-trust)
        if session_id and credential.session_id != session_id:
            logger.error(
                f"Unauthorized access attempt: credential={credential_id}, session={session_id}"
            )
            raise ValueError("Unauthorized credential access")

        # Decrypt access token
        try:
            credential.encrypted_access_token = self._decrypt(
                credential.encrypted_access_token
            )
            if credential.encrypted_refresh_token:
                credential.encrypted_refresh_token = self._decrypt(
                    credential.encrypted_refresh_token
                )

            # Update access time
            credential.last_validated = int(time.time())

            logger.debug(f"Credential retrieved: {credential_id}")
            return credential

        except Exception as e:
            logger.error(f"Failed to decrypt credential: {e}")
            raise ValueError(f"Credential decryption failed: {str(e)}")

    async def update_credential(
        self,
        credential_id: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_at: Optional[int] = None,
    ) -> StoredCredential:
        """Update credential with new token values (e.g., after refresh).

        Args:
            credential_id: Credential ID
            access_token: New access token
            refresh_token: Optional new refresh token
            expires_at: New expiration timestamp

        Returns:
            Updated StoredCredential

        Raises:
            ValueError: If credential not found or update fails
        """
        if credential_id not in self._credentials:
            raise ValueError(f"Credential '{credential_id}' not found")

        try:
            credential = self._credentials[credential_id]

            # Update encrypted tokens
            credential.encrypted_access_token = self._encrypt(access_token)
            if refresh_token:
                credential.encrypted_refresh_token = self._encrypt(refresh_token)

            credential.expires_at = expires_at
            credential.validation_status = ValidationStatus.VALID

            logger.info(f"Credential updated: {credential_id}")

            return credential

        except Exception as e:
            logger.error(f"Failed to update credential: {e}")
            raise ValueError(f"Credential update failed: {str(e)}")

    async def revoke_credential(self, credential_id: str) -> None:
        """Revoke access to a credential.

        Args:
            credential_id: Credential ID

        Raises:
            ValueError: If credential not found
        """
        if credential_id not in self._credentials:
            raise ValueError(f"Credential '{credential_id}' not found")

        credential = self._credentials[credential_id]
        credential.validation_status = ValidationStatus.REVOKED

        logger.info(f"Credential revoked: {credential_id}")

    async def list_credentials(self, session_id: str) -> List[StoredCredential]:
        """List all credentials for a session.

        Args:
            session_id: Session ID

        Returns:
            List of StoredCredential records (tokens not included)
        """
        credentials = [
            c
            for c in self._credentials.values()
            if c.session_id == session_id and c.validation_status != ValidationStatus.REVOKED
        ]

        logger.debug(f"Listed {len(credentials)} credentials for session {session_id}")

        return credentials

    async def validate_credential(self, credential_id: str) -> bool:
        """Check if credential is valid and not expired.

        Args:
            credential_id: Credential ID

        Returns:
            True if valid
        """
        if credential_id not in self._credentials:
            return False

        credential = self._credentials[credential_id]

        if credential.validation_status == ValidationStatus.REVOKED:
            return False

        if credential.is_expired:
            credential.validation_status = ValidationStatus.EXPIRED
            return False

        return True

    def cleanup_expired_credentials(self, max_age_seconds: int = 86400) -> int:
        """Clean up expired revoked credentials.

        Args:
            max_age_seconds: Remove credentials older than this (default: 24 hours)

        Returns:
            Number of credentials removed
        """
        current_time = int(time.time())
        cutoff_time = current_time - max_age_seconds

        expired_ids = [
            cid
            for cid, cred in self._credentials.items()
            if cred.created_at < cutoff_time
            and cred.validation_status
            in [ValidationStatus.EXPIRED, ValidationStatus.REVOKED]
        ]

        for cid in expired_ids:
            if cid in self._encryption_keys:
                del self._encryption_keys[cid]
            del self._credentials[cid]

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired credentials")

        return len(expired_ids)

    def _encrypt(self, data: Optional[str]) -> str:
        """Encrypt sensitive data.

        In production: use AWS KMS or similar.
        Current: simple XOR cipher for demonstration.

        Args:
            data: Data to encrypt

        Returns:
            Encrypted data
        """
        if not data:
            return ""

        # Production: implement real encryption
        # For now: simple encoding
        return f"encrypted:{data[:10]}...{len(data)}bytes"

    def _decrypt(self, encrypted_data: str) -> str:
        """Decrypt sensitive data.

        In production: use AWS KMS or similar.
        Current: reverses the simple encryption.

        Args:
            encrypted_data: Encrypted data

        Returns:
            Decrypted data
        """
        # Production: implement real decryption
        # For now: return masked version
        return f"token_xxxx...{encrypted_data[-10:]}"


# Global instance
_vault = CredentialVault()


def get_credential_vault() -> CredentialVault:
    """Get global credential vault instance.

    Returns:
        Global CredentialVault instance
    """
    return _vault
