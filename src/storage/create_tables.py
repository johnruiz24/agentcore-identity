#!/usr/bin/env python3
"""
Create DynamoDB tables for AgentCore Identity Service.

Usage:
    python -m src.storage.create_tables
"""

import sys
import boto3
from botocore.exceptions import ClientError

from .dynamodb_vault import DynamoDBCredentialVault
from .dynamodb_flows import DynamoDBOAuthFlowStore
from .dynamodb_audit import DynamoDBauditStore


def create_all_tables(region: str = "eu-central-1"):
    """Create all required DynamoDB tables."""
    dynamodb_client = boto3.client("dynamodb", region_name=region)

    tables = [
        ("agentcore-identity-credentials", DynamoDBCredentialVault.create_table),
        ("agentcore-identity-oauth-flows", DynamoDBOAuthFlowStore.create_table),
        ("agentcore-identity-audit-logs", DynamoDBauditStore.create_table),
    ]

    print(f"Creating DynamoDB tables in {region}...")
    print()

    for table_name, create_func in tables:
        try:
            print(f"Creating {table_name}...")
            create_func(dynamodb_client, table_name)
            print(f"✅ {table_name} created successfully\n")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceInUseException":
                print(f"✅ {table_name} already exists\n")
            else:
                print(f"❌ Failed to create {table_name}: {e}\n")
                return False

    print("All DynamoDB tables ready!")
    return True


if __name__ == "__main__":
    region = sys.argv[1] if len(sys.argv) > 1 else "eu-central-1"
    success = create_all_tables(region)
    sys.exit(0 if success else 1)
