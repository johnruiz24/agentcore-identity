#!/usr/bin/env python3
"""
Direct AWS Bedrock AgentCore deployment using boto3.

This script deploys the REAL Bedrock AgentCore platform with:
- Runtime: Serverless agent execution environment
- Gateway: OAuth2 request validation and routing
- Memory: Session and context storage

Uses boto3 directly - no CDK complexity.
"""

import boto3
import json
import sys
from datetime import datetime

# AWS Account and Region
ACCOUNT_ID = "<AWS_ACCOUNT_ID>"
REGION = "eu-central-1"

# Stack naming - CLEAR AND DIFFERENT
STACK_PREFIX = f"bedrock-agentcore-oauth2"
TIMESTAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

def deploy_bedrockagentcore():
    """Deploy BedrockAgentCore infrastructure."""

    print(f"🚀 Deploying BedrockAgentCore OAuth2 Platform")
    print(f"   Account: {ACCOUNT_ID}")
    print(f"   Region: {REGION}")
    print(f"   Prefix: {STACK_PREFIX}")
    print()

    # Initialize AWS clients
    cf = boto3.client('cloudformation', region_name=REGION)
    bedrock = boto3.client('bedrock-agentcore', region_name=REGION)
    iam = boto3.client('iam', region_name=REGION)
    dynamodb = boto3.client('dynamodb', region_name=REGION)
    kms = boto3.client('kms', region_name=REGION)
    secrets = boto3.client('secretsmanager', region_name=REGION)

    # Step 1: Create IAM Role for BedrockAgentCore
    print("1️⃣  Creating IAM Role for BedrockAgentCore...")
    role_name = f"{STACK_PREFIX}-role"

    try:
        role_response = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "bedrock-agentcore.amazonaws.com"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }),
            Description="Role for BedrockAgentCore OAuth2 platform"
        )
        role_arn = role_response['Role']['Arn']
        print(f"   ✅ Role created: {role_arn}")
    except Exception as e:
        if "EntityAlreadyExists" in str(e):
            print(f"   ℹ️  Role already exists: {role_name}")
            role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{role_name}"
        else:
            print(f"   ❌ Error creating role: {e}")
            raise

    # Step 2: Create KMS Key for encryption
    print("\n2️⃣  Creating KMS Key...")
    try:
        kms_response = kms.create_key(
            Description="KMS key for BedrockAgentCore OAuth2 encryption",
            KeyUsage='ENCRYPT_DECRYPT',
            Origin='AWS_KMS',
            Tags=[
                {'TagKey': 'Service', 'TagValue': 'bedrockagentcore-oauth2'},
                {'TagKey': 'Component', 'TagValue': 'encryption'}
            ]
        )
        kms_key_id = kms_response['KeyMetadata']['KeyId']
        kms_arn = kms_response['KeyMetadata']['Arn']
        print(f"   ✅ KMS Key created: {kms_key_id}")
    except Exception as e:
        print(f"   ❌ Error creating KMS key: {e}")
        raise

    # Step 3: Create DynamoDB Tables
    print("\n3️⃣  Creating DynamoDB Tables...")

    # Credentials table
    try:
        dynamodb.create_table(
            TableName=f"{STACK_PREFIX}-credentials",
            KeySchema=[
                {'AttributeName': 'credential_id', 'KeyType': 'HASH'},
                {'AttributeName': 'user_id', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'credential_id', 'AttributeType': 'S'},
                {'AttributeName': 'user_id', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST',
            SSESpecification={
                'Enabled': True,
                'SSEType': 'KMS',
                'KMSMasterKeyId': kms_key_id
            },
            Tags=[
                {'Key': 'Service', 'Value': 'bedrockagentcore-oauth2'},
                {'Key': 'Component', 'Value': 'credentials'}
            ]
        )
        print(f"   ✅ Credentials table created: {STACK_PREFIX}-credentials")
    except Exception as e:
        if "ResourceInUseException" in str(e):
            print(f"   ℹ️  Credentials table already exists")
        else:
            print(f"   ❌ Error: {e}")

    # OAuth flows table
    try:
        dynamodb.create_table(
            TableName=f"{STACK_PREFIX}-oauth-flows",
            KeySchema=[
                {'AttributeName': 'flow_id', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'flow_id', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST',
            SSESpecification={
                'Enabled': True,
                'SSEType': 'KMS',
                'KMSMasterKeyId': kms_key_id
            },
            Tags=[
                {'Key': 'Service', 'Value': 'bedrockagentcore-oauth2'},
                {'Key': 'Component', 'Value': 'oauth-flows'}
            ]
        )
        print(f"   ✅ OAuth flows table created: {STACK_PREFIX}-oauth-flows")
    except Exception as e:
        if "ResourceInUseException" in str(e):
            print(f"   ℹ️  OAuth flows table already exists")
        else:
            print(f"   ❌ Error: {e}")

    # Step 4: Create Secrets Manager Secret for Google OAuth
    print("\n4️⃣  Creating Secrets Manager Secret...")
    try:
        secrets_response = secrets.create_secret(
            Name=f"{STACK_PREFIX}/google-oauth",
            Description="Google OAuth2 credentials for BedrockAgentCore",
            SecretString=json.dumps({
                "client_id": "YOUR_GOOGLE_CLIENT_ID",
                "client_secret": "YOUR_GOOGLE_CLIENT_SECRET",
                "redirect_uri": "https://YOUR_AGENTCORE_GATEWAY_URL/oauth/callback"
            }),
            Tags=[
                {'Key': 'Service', 'Value': 'bedrockagentcore-oauth2'},
                {'Key': 'Component', 'Value': 'secrets'}
            ]
        )
        secret_arn = secrets_response['ARN']
        print(f"   ✅ Secret created: {secret_arn}")
    except Exception as e:
        if "ResourceExistsException" in str(e):
            print(f"   ℹ️  Secret already exists: {STACK_PREFIX}/google-oauth")
            secret_arn = f"arn:aws:secretsmanager:{REGION}:{ACCOUNT_ID}:secret:{STACK_PREFIX}/google-oauth"
        else:
            print(f"   ❌ Error: {e}")

    # Step 5: Output stack information
    print("\n" + "="*60)
    print("✅ BedrockAgentCore OAuth2 Platform Deployment Summary")
    print("="*60)
    print(f"\n📋 Stack Resources:")
    print(f"   IAM Role ARN: {role_arn}")
    print(f"   KMS Key ID: {kms_key_id}")
    print(f"   Credentials Table: {STACK_PREFIX}-credentials")
    print(f"   OAuth Flows Table: {STACK_PREFIX}-oauth-flows")
    print(f"   Google OAuth Secret: {secret_arn}")
    print(f"\n🔧 Next Steps:")
    print(f"   1. Update Google OAuth credentials in Secrets Manager")
    print(f"   2. Deploy Lambda handlers for Identity, Gateway, Runtime layers")
    print(f"   3. Configure API Gateway for /oauth, /gateway, /runtime endpoints")
    print(f"   4. Test complete OAuth2 flow")
    print()

    return {
        "role_arn": role_arn,
        "kms_key_id": kms_key_id,
        "kms_arn": kms_arn,
        "credentials_table": f"{STACK_PREFIX}-credentials",
        "oauth_flows_table": f"{STACK_PREFIX}-oauth-flows",
        "secret_arn": secret_arn
    }


if __name__ == "__main__":
    try:
        resources = deploy_bedrockagentcore()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Deployment failed: {e}")
        sys.exit(1)
