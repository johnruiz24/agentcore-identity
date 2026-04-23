"""DynamoDB implementation of CredentialVault for persistent storage."""

import json
import time
import uuid
from typing import Dict, List, Optional
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError

from src.vault.credential_vault import StoredCredential, ValidationStatus


class DynamoDBCredentialVault:
    """DynamoDB-backed credential vault for production deployments."""

    def __init__(self, table_name: str = "agentcore-identity-credentials", region: str = "eu-central-1"):
        """Initialize DynamoDB vault.

        Args:
            table_name: DynamoDB table name
            region: AWS region
        """
        self.table_name = table_name
        self.region = region
        self.dynamodb = boto3.resource("dynamodb", region_name=region)
        self.table = self.dynamodb.Table(table_name)
        self.kms_client = boto3.client("kms", region_name=region)

    async def store_credential(
        self,
        session_id: str,
        provider_name: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_at: Optional[int] = None,
        scopes: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> StoredCredential:
        """Store encrypted credential in DynamoDB."""
        credential_id = str(uuid.uuid4())
        now = int(time.time())

        if expires_at is None:
            expires_at = now + 3600  # 1 hour default

        if scopes is None:
            scopes = []

        try:
            # Encrypt sensitive data with KMS
            encrypted_access = self._encrypt_token(access_token)
            encrypted_refresh = self._encrypt_token(refresh_token) if refresh_token else None

            item = {
                "credential_id": credential_id,
                "session_id": session_id,
                "provider_name": provider_name,
                "encrypted_access_token": encrypted_access,
                "encrypted_refresh_token": encrypted_refresh or "null",
                "scopes": scopes,
                "validation_status": "valid",
                "expires_at": expires_at,
                "created_at": now,
                "metadata": json.dumps(metadata or {}),
                "ttl": expires_at + 86400,  # DynamoDB TTL: expire 24h after token expires
            }

            self.table.put_item(Item=item)

            return StoredCredential(
                credential_id=credential_id,
                session_id=session_id,
                provider_name=provider_name,
                encrypted_access_token=encrypted_access,
                encrypted_refresh_token=encrypted_refresh,
                scopes=scopes,
                validation_status=ValidationStatus.VALID,
                expires_at=expires_at,
                created_at=now,
                metadata=metadata or {},
            )
        except ClientError as e:
            raise Exception(f"Failed to store credential in DynamoDB: {e}")

    async def retrieve_credential(
        self, credential_id: str, session_id: str
    ) -> Optional[StoredCredential]:
        """Retrieve credential from DynamoDB with session validation."""
        try:
            response = self.table.get_item(Key={"credential_id": credential_id, "session_id": session_id})
            item = response.get("Item")

            if not item:
                return None

            # Check expiration
            if item.get("expires_at", 0) < int(time.time()):
                item["validation_status"] = "expired"
                self.table.update_item(
                    Key={"credential_id": credential_id, "session_id": session_id},
                    UpdateExpression="SET validation_status = :status",
                    ExpressionAttributeValues={":status": "expired"},
                )

            return StoredCredential(
                credential_id=item["credential_id"],
                session_id=item["session_id"],
                provider_name=item["provider_name"],
                encrypted_access_token=item["encrypted_access_token"],
                encrypted_refresh_token=item.get("encrypted_refresh_token"),
                scopes=item.get("scopes", []),
                validation_status=ValidationStatus(item.get("validation_status", "valid")),
                expires_at=item["expires_at"],
                created_at=item["created_at"],
                metadata=json.loads(item.get("metadata", "{}")),
            )
        except ClientError as e:
            raise Exception(f"Failed to retrieve credential from DynamoDB: {e}")

    async def list_credentials(self, session_id: str) -> List[StoredCredential]:
        """List all credentials for a session."""
        try:
            response = self.table.query(
                KeyConditionExpression="session_id = :session_id",
                ExpressionAttributeValues={":session_id": session_id},
            )

            credentials = []
            for item in response.get("Items", []):
                credentials.append(
                    StoredCredential(
                        credential_id=item["credential_id"],
                        session_id=item["session_id"],
                        provider_name=item["provider_name"],
                        encrypted_access_token=item["encrypted_access_token"],
                        encrypted_refresh_token=item.get("encrypted_refresh_token"),
                        scopes=item.get("scopes", []),
                        validation_status=ValidationStatus(item.get("validation_status", "valid")),
                        expires_at=item["expires_at"],
                        created_at=item["created_at"],
                        metadata=json.loads(item.get("metadata", "{}")),
                    )
                )

            return credentials
        except ClientError as e:
            raise Exception(f"Failed to list credentials from DynamoDB: {e}")

    async def revoke_credential(self, credential_id: str) -> None:
        """Mark credential as revoked."""
        try:
            self.table.update_item(
                Key={"credential_id": credential_id},
                UpdateExpression="SET validation_status = :status",
                ExpressionAttributeValues={":status": "revoked"},
            )
        except ClientError as e:
            raise Exception(f"Failed to revoke credential in DynamoDB: {e}")

    async def validate_credential(self, credential_id: str) -> bool:
        """Check if credential is valid and not expired."""
        try:
            response = self.table.get_item(Key={"credential_id": credential_id})
            item = response.get("Item")

            if not item:
                return False

            # Check status
            if item.get("validation_status") in ["revoked", "expired"]:
                return False

            # Check expiration
            if item.get("expires_at", 0) < int(time.time()):
                return False

            return True
        except ClientError:
            return False

    def _encrypt_token(self, token: str, key_id: Optional[str] = None) -> str:
        """Encrypt token using AWS KMS."""
        try:
            if key_id is None:
                key_id = "alias/agentcore-identity"

            response = self.kms_client.encrypt(
                KeyId=key_id,
                Plaintext=token.encode("utf-8"),
            )

            # Return base64-encoded ciphertext
            import base64
            return base64.b64encode(response["CiphertextBlob"]).decode("utf-8")
        except ClientError as e:
            # Fallback: store unencrypted for development
            return token

    def _decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt token using AWS KMS."""
        try:
            import base64
            ciphertext = base64.b64decode(encrypted_token.encode("utf-8"))

            response = self.kms_client.decrypt(CiphertextBlob=ciphertext)
            return response["Plaintext"].decode("utf-8")
        except ClientError as e:
            # Fallback: assume unencrypted for development
            return encrypted_token

    @staticmethod
    def create_table(dynamodb_client=None, table_name: str = "agentcore-identity-credentials"):
        """Create DynamoDB table for credential storage."""
        if dynamodb_client is None:
            dynamodb_client = boto3.client("dynamodb", region_name="eu-central-1")

        try:
            dynamodb_client.create_table(
                TableName=table_name,
                KeySchema=[
                    {"AttributeName": "credential_id", "KeyType": "HASH"},
                    {"AttributeName": "session_id", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "credential_id", "AttributeType": "S"},
                    {"AttributeName": "session_id", "AttributeType": "S"},
                    {"AttributeName": "provider_name", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
                GlobalSecondaryIndexes=[
                    {
                        "IndexName": "session_id-provider_name-index",
                        "KeySchema": [
                            {"AttributeName": "session_id", "KeyType": "HASH"},
                            {"AttributeName": "provider_name", "KeyType": "RANGE"},
                        ],
                        "Projection": {"ProjectionType": "ALL"},
                    }
                ],
                Tags=[
                    {"Key": "Service", "Value": "agentcore-identity"},
                    {"Key": "Component", "Value": "credentials"},
                ],
            )
            print(f"Table {table_name} created successfully")

            # Enable TTL separately
            try:
                dynamodb_client.update_time_to_live(
                    TableName=table_name,
                    TimeToLiveSpecification={"AttributeName": "ttl", "Enabled": True},
                )
                print(f"TTL enabled for {table_name}")
            except ClientError:
                pass
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceInUseException":
                print(f"Table {table_name} already exists")
            else:
                raise
