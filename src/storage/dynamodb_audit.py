"""DynamoDB implementation for audit logging."""

import json
import time
import uuid
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError


class AuditEntry:
    """Audit log entry."""

    def __init__(
        self,
        entry_id: str,
        session_id: str,
        user_id: str,
        action: str,
        resource: str,
        result: str,
        timestamp: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict] = None,
    ):
        self.entry_id = entry_id
        self.session_id = session_id
        self.user_id = user_id
        self.action = action
        self.resource = resource
        self.result = result
        self.timestamp = timestamp
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.details = details or {}


class DynamoDBauditStore:
    """DynamoDB-backed audit log store for compliance and security analysis."""

    def __init__(self, table_name: str = "agentcore-identity-audit-logs", region: str = "eu-central-1"):
        """Initialize audit store.

        Args:
            table_name: DynamoDB table name
            region: AWS region
        """
        self.table_name = table_name
        self.region = region
        self.dynamodb = boto3.resource("dynamodb", region_name=region)
        self.table = self.dynamodb.Table(table_name)

    async def log_entry(
        self,
        session_id: str,
        user_id: str,
        action: str,
        resource: str,
        result: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict] = None,
    ) -> AuditEntry:
        """Log an audit entry."""
        entry_id = str(uuid.uuid4())
        timestamp = int(time.time())
        retention_days = 90

        try:
            item = {
                "entry_id": entry_id,
                "session_id": session_id,
                "user_id": user_id,
                "action": action,
                "resource": resource,
                "result": result,
                "timestamp": timestamp,
                "ip_address": ip_address or "unknown",
                "user_agent": user_agent or "unknown",
                "details": json.dumps(details or {}),
                "ttl": timestamp + (retention_days * 86400),  # Auto-expire after 90 days
            }

            self.table.put_item(Item=item)

            return AuditEntry(
                entry_id=entry_id,
                session_id=session_id,
                user_id=user_id,
                action=action,
                resource=resource,
                result=result,
                timestamp=timestamp,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details,
            )
        except ClientError as e:
            raise Exception(f"Failed to log audit entry: {e}")

    async def get_session_logs(self, session_id: str, limit: int = 100) -> List[AuditEntry]:
        """Get audit logs for a session."""
        try:
            response = self.table.query(
                IndexName="session_id-timestamp-index",
                KeyConditionExpression="session_id = :session_id",
                ExpressionAttributeValues={":session_id": session_id},
                ScanIndexForward=False,  # Newest first
                Limit=limit,
            )

            entries = []
            for item in response.get("Items", []):
                entries.append(
                    AuditEntry(
                        entry_id=item["entry_id"],
                        session_id=item["session_id"],
                        user_id=item["user_id"],
                        action=item["action"],
                        resource=item["resource"],
                        result=item["result"],
                        timestamp=item["timestamp"],
                        ip_address=item.get("ip_address"),
                        user_agent=item.get("user_agent"),
                        details=json.loads(item.get("details", "{}")),
                    )
                )

            return entries
        except ClientError as e:
            raise Exception(f"Failed to get session logs: {e}")

    async def get_user_logs(self, user_id: str, limit: int = 100) -> List[AuditEntry]:
        """Get audit logs for a user."""
        try:
            response = self.table.query(
                IndexName="user_id-timestamp-index",
                KeyConditionExpression="user_id = :user_id",
                ExpressionAttributeValues={":user_id": user_id},
                ScanIndexForward=False,  # Newest first
                Limit=limit,
            )

            entries = []
            for item in response.get("Items", []):
                entries.append(
                    AuditEntry(
                        entry_id=item["entry_id"],
                        session_id=item["session_id"],
                        user_id=item["user_id"],
                        action=item["action"],
                        resource=item["resource"],
                        result=item["result"],
                        timestamp=item["timestamp"],
                        ip_address=item.get("ip_address"),
                        user_agent=item.get("user_agent"),
                        details=json.loads(item.get("details", "{}")),
                    )
                )

            return entries
        except ClientError as e:
            raise Exception(f"Failed to get user logs: {e}")

    async def query_by_action(self, action: str, start_time: Optional[int] = None, end_time: Optional[int] = None) -> List[AuditEntry]:
        """Query audit logs by action (for compliance analysis)."""
        try:
            if start_time is None:
                start_time = int(time.time()) - (90 * 86400)  # Last 90 days
            if end_time is None:
                end_time = int(time.time())

            response = self.table.query(
                IndexName="action-timestamp-index",
                KeyConditionExpression="action = :action AND #ts BETWEEN :start_time AND :end_time",
                ExpressionAttributeNames={"#ts": "timestamp"},
                ExpressionAttributeValues={
                    ":action": action,
                    ":start_time": start_time,
                    ":end_time": end_time,
                },
            )

            entries = []
            for item in response.get("Items", []):
                entries.append(
                    AuditEntry(
                        entry_id=item["entry_id"],
                        session_id=item["session_id"],
                        user_id=item["user_id"],
                        action=item["action"],
                        resource=item["resource"],
                        result=item["result"],
                        timestamp=item["timestamp"],
                        ip_address=item.get("ip_address"),
                        user_agent=item.get("user_agent"),
                        details=json.loads(item.get("details", "{}")),
                    )
                )

            return entries
        except ClientError as e:
            raise Exception(f"Failed to query audit logs: {e}")

    @staticmethod
    def create_table(dynamodb_client=None, table_name: str = "agentcore-identity-audit-logs"):
        """Create DynamoDB table for audit logs."""
        if dynamodb_client is None:
            dynamodb_client = boto3.client("dynamodb", region_name="eu-central-1")

        try:
            dynamodb_client.create_table(
                TableName=table_name,
                KeySchema=[
                    {"AttributeName": "entry_id", "KeyType": "HASH"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "entry_id", "AttributeType": "S"},
                    {"AttributeName": "session_id", "AttributeType": "S"},
                    {"AttributeName": "user_id", "AttributeType": "S"},
                    {"AttributeName": "action", "AttributeType": "S"},
                    {"AttributeName": "timestamp", "AttributeType": "N"},
                ],
                BillingMode="PAY_PER_REQUEST",
                GlobalSecondaryIndexes=[
                    {
                        "IndexName": "session_id-timestamp-index",
                        "KeySchema": [
                            {"AttributeName": "session_id", "KeyType": "HASH"},
                            {"AttributeName": "timestamp", "KeyType": "RANGE"},
                        ],
                        "Projection": {"ProjectionType": "ALL"},
                    },
                    {
                        "IndexName": "user_id-timestamp-index",
                        "KeySchema": [
                            {"AttributeName": "user_id", "KeyType": "HASH"},
                            {"AttributeName": "timestamp", "KeyType": "RANGE"},
                        ],
                        "Projection": {"ProjectionType": "ALL"},
                    },
                    {
                        "IndexName": "action-timestamp-index",
                        "KeySchema": [
                            {"AttributeName": "action", "KeyType": "HASH"},
                            {"AttributeName": "timestamp", "KeyType": "RANGE"},
                        ],
                        "Projection": {"ProjectionType": "ALL"},
                    },
                ],
                Tags=[
                    {"Key": "Service", "Value": "agentcore-identity"},
                    {"Key": "Component", "Value": "audit-logs"},
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
