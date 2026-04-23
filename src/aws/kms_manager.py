"""AWS KMS integration for token encryption/decryption."""

import base64
from typing import Optional

import boto3
from botocore.exceptions import ClientError


class KMSManager:
    """Manages encryption/decryption using AWS KMS."""

    def __init__(self, key_alias: str = "alias/agentcore-identity", region: str = "eu-central-1"):
        """Initialize KMS manager.

        Args:
            key_alias: KMS key alias (must exist in AWS account)
            region: AWS region
        """
        self.key_alias = key_alias
        self.region = region
        self.kms_client = boto3.client("kms", region_name=region)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext using KMS.

        Args:
            plaintext: Text to encrypt

        Returns:
            Base64-encoded ciphertext

        Raises:
            Exception: If encryption fails
        """
        try:
            response = self.kms_client.encrypt(
                KeyId=self.key_alias,
                Plaintext=plaintext.encode("utf-8"),
            )
            # Return base64-encoded ciphertext for storage
            return base64.b64encode(response["CiphertextBlob"]).decode("utf-8")
        except ClientError as e:
            raise Exception(f"KMS encryption failed: {e}")

    def decrypt(self, ciphertext_b64: str) -> str:
        """Decrypt KMS-encrypted ciphertext.

        Args:
            ciphertext_b64: Base64-encoded ciphertext

        Returns:
            Decrypted plaintext

        Raises:
            Exception: If decryption fails
        """
        try:
            ciphertext_blob = base64.b64decode(ciphertext_b64.encode("utf-8"))
            response = self.kms_client.decrypt(CiphertextBlob=ciphertext_blob)
            return response["Plaintext"].decode("utf-8")
        except ClientError as e:
            raise Exception(f"KMS decryption failed: {e}")

    def create_key(self, description: str) -> str:
        """Create new KMS key for production.

        Args:
            description: Key description

        Returns:
            Key ID (ARN)
        """
        try:
            response = self.kms_client.create_key(
                Description=description,
                KeyUsage="ENCRYPT_DECRYPT",
                Origin="AWS_KMS",
                Tags=[
                    {"TagKey": "Service", "TagValue": "agentcore-identity"},
                    {"TagKey": "Component", "TagValue": "encryption"},
                ],
            )
            key_id = response["KeyMetadata"]["KeyId"]

            # Create alias for easier reference
            try:
                self.kms_client.create_alias(AliasName=self.key_alias, TargetKeyId=key_id)
            except ClientError:
                pass  # Alias might already exist

            return key_id
        except ClientError as e:
            raise Exception(f"Failed to create KMS key: {e}")

    @staticmethod
    def get_or_create_key(
        key_alias: str = "alias/agentcore-identity", region: str = "eu-central-1"
    ) -> str:
        """Get existing KMS key or create new one.

        Args:
            key_alias: KMS key alias
            region: AWS region

        Returns:
            Key ID
        """
        kms_client = boto3.client("kms", region_name=region)

        try:
            # Try to get existing key
            response = kms_client.describe_key(KeyId=key_alias)
            return response["KeyMetadata"]["KeyId"]
        except ClientError:
            # Key doesn't exist, create it
            manager = KMSManager(key_alias, region)
            return manager.create_key(f"AgentCore Identity encryption key")
