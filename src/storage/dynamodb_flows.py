"""DynamoDB implementation for OAuth flow storage."""

import json
import time
import uuid
from typing import Dict, Optional
from enum import Enum

import boto3
from botocore.exceptions import ClientError


class FlowStatus(str, Enum):
    """OAuth flow status."""

    INITIATED = "initiated"
    AUTHORIZED = "authorized"
    TOKEN_EXCHANGED = "token_exchanged"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class OAuthFlow:
    """OAuth flow data model."""

    def __init__(
        self,
        flow_id: str,
        session_id: str,
        provider_name: str,
        state: str,
        authorization_url: str,
        status: FlowStatus,
        expires_at: int,
        completed_at: Optional[int] = None,
        credential_id: Optional[str] = None,
        error: Optional[str] = None,
    ):
        self.flow_id = flow_id
        self.session_id = session_id
        self.provider_name = provider_name
        self.state = state
        self.authorization_url = authorization_url
        self.status = status
        self.expires_at = expires_at
        self.completed_at = completed_at
        self.credential_id = credential_id
        self.error = error


class DynamoDBOAuthFlowStore:
    """DynamoDB-backed OAuth flow store for tracking 3-legged OAuth flows."""

    def __init__(self, table_name: str = "agentcore-identity-oauth-flows", region: str = "eu-central-1"):
        """Initialize OAuth flow store.

        Args:
            table_name: DynamoDB table name
            region: AWS region
        """
        self.table_name = table_name
        self.region = region
        self.dynamodb = boto3.resource("dynamodb", region_name=region)
        self.table = self.dynamodb.Table(table_name)

    async def create_flow(
        self,
        session_id: str,
        provider_name: str,
        state: str,
        authorization_url: str,
        ttl_seconds: int = 1800,  # 30 minutes
    ) -> OAuthFlow:
        """Create a new OAuth flow."""
        flow_id = str(uuid.uuid4())
        now = int(time.time())
        expires_at = now + ttl_seconds

        try:
            item = {
                "flow_id": flow_id,
                "session_id": session_id,
                "provider_name": provider_name,
                "state": state,
                "authorization_url": authorization_url,
                "status": FlowStatus.INITIATED.value,
                "expires_at": expires_at,
                "created_at": now,
                "ttl": expires_at + 86400,  # Keep for 24h after expiry
            }

            self.table.put_item(Item=item)

            return OAuthFlow(
                flow_id=flow_id,
                session_id=session_id,
                provider_name=provider_name,
                state=state,
                authorization_url=authorization_url,
                status=FlowStatus.INITIATED,
                expires_at=expires_at,
            )
        except ClientError as e:
            raise Exception(f"Failed to create OAuth flow: {e}")

    async def get_flow(self, flow_id: str) -> Optional[OAuthFlow]:
        """Retrieve OAuth flow by ID."""
        try:
            response = self.table.get_item(Key={"flow_id": flow_id})
            item = response.get("Item")

            if not item:
                return None

            # Check expiration
            if item.get("expires_at", 0) < int(time.time()):
                item["status"] = FlowStatus.EXPIRED.value
                await self.update_flow_status(flow_id, FlowStatus.EXPIRED)

            return OAuthFlow(
                flow_id=item["flow_id"],
                session_id=item["session_id"],
                provider_name=item["provider_name"],
                state=item["state"],
                authorization_url=item["authorization_url"],
                status=FlowStatus(item.get("status", FlowStatus.INITIATED.value)),
                expires_at=item["expires_at"],
                completed_at=item.get("completed_at"),
                credential_id=item.get("credential_id"),
                error=item.get("error"),
            )
        except ClientError as e:
            raise Exception(f"Failed to get OAuth flow: {e}")

    async def update_flow_status(
        self, flow_id: str, status: FlowStatus, credential_id: Optional[str] = None, error: Optional[str] = None
    ) -> None:
        """Update OAuth flow status."""
        try:
            update_expr = "SET #status = :status"
            expr_values = {":status": status.value}

            if status == FlowStatus.COMPLETED:
                update_expr += ", completed_at = :now"
                expr_values[":now"] = int(time.time())

            if credential_id:
                update_expr += ", credential_id = :cred_id"
                expr_values[":cred_id"] = credential_id

            if error:
                update_expr += ", #error = :error"
                expr_values[":error"] = error

            self.table.update_item(
                Key={"flow_id": flow_id},
                UpdateExpression=update_expr,
                ExpressionAttributeNames={"#status": "status", "#error": "error"},
                ExpressionAttributeValues=expr_values,
            )
        except ClientError as e:
            raise Exception(f"Failed to update OAuth flow: {e}")

    async def list_flows_for_session(self, session_id: str) -> list[OAuthFlow]:
        """List all flows for a session."""
        try:
            response = self.table.query(
                IndexName="session_id-index",
                KeyConditionExpression="session_id = :session_id",
                ExpressionAttributeValues={":session_id": session_id},
            )

            flows = []
            for item in response.get("Items", []):
                flows.append(
                    OAuthFlow(
                        flow_id=item["flow_id"],
                        session_id=item["session_id"],
                        provider_name=item["provider_name"],
                        state=item["state"],
                        authorization_url=item["authorization_url"],
                        status=FlowStatus(item.get("status", FlowStatus.INITIATED.value)),
                        expires_at=item["expires_at"],
                        completed_at=item.get("completed_at"),
                        credential_id=item.get("credential_id"),
                        error=item.get("error"),
                    )
                )

            return flows
        except ClientError as e:
            raise Exception(f"Failed to list OAuth flows: {e}")

    @staticmethod
    def create_table(dynamodb_client=None, table_name: str = "agentcore-identity-oauth-flows"):
        """Create DynamoDB table for OAuth flows."""
        if dynamodb_client is None:
            dynamodb_client = boto3.client("dynamodb", region_name="eu-central-1")

        try:
            dynamodb_client.create_table(
                TableName=table_name,
                KeySchema=[
                    {"AttributeName": "flow_id", "KeyType": "HASH"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "flow_id", "AttributeType": "S"},
                    {"AttributeName": "session_id", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
                GlobalSecondaryIndexes=[
                    {
                        "IndexName": "session_id-index",
                        "KeySchema": [
                            {"AttributeName": "session_id", "KeyType": "HASH"},
                        ],
                        "Projection": {"ProjectionType": "ALL"},
                    }
                ],
                Tags=[
                    {"Key": "Service", "Value": "agentcore-identity"},
                    {"Key": "Component", "Value": "oauth-flows"},
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
