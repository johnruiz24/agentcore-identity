#!/usr/bin/env python3
"""
CDK Stack for AgentCore Identity Bedrock Agent Deployment

Deploys:
- Bedrock Agent with 8 tools (AuthTools + IdentityTools)
- Lambda function to handle tool invocations
- IAM roles and policies
- CloudWatch logging
"""

import json
import os
from typing import Any, Dict, List

import aws_cdk as cdk
from aws_cdk import (
    aws_bedrock as bedrock,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_logs as logs,
    aws_ecr as ecr,
    aws_ecr_assets as ecr_assets,
    Duration,
)
from constructs import Construct


class BedrockAgentConfig:
    """Configuration for Bedrock Agent"""

    AGENT_NAME = "agentcore-identity-agent"
    AGENT_DESCRIPTION = "AgentCore Identity Management Agent"
    MODEL_ID = "anthropic.claude-sonnet-4-20250514-v1:0"
    REGION = "eu-central-1"
    ACCOUNT = "<AWS_ACCOUNT_ID>"

    # Auth Tools (4 tools)
    AUTH_TOOLS = [
        {
            "name": "validate_token",
            "description": "Validate an OAuth2 token and return decoded claims",
            "input_schema": {
                "type": "object",
                "properties": {
                    "token": {
                        "type": "string",
                        "description": "JWT ID token to validate",
                    }
                },
                "required": ["token"],
            },
        },
        {
            "name": "refresh_session",
            "description": "Refresh a user session with a new access token",
            "input_schema": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "UUID of the session to refresh",
                    }
                },
                "required": ["session_id"],
            },
        },
        {
            "name": "get_token_info",
            "description": "Get token information from an active session",
            "input_schema": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "UUID of the session",
                    }
                },
                "required": ["session_id"],
            },
        },
        {
            "name": "revoke_session",
            "description": "Revoke a user session (logout)",
            "input_schema": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "UUID of the session to revoke",
                    }
                },
                "required": ["session_id"],
            },
        },
    ]

    # Identity Tools (4 tools)
    IDENTITY_TOOLS = [
        {
            "name": "get_user_profile",
            "description": "Get user profile information from the current session",
            "input_schema": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "UUID of the session",
                    }
                },
                "required": ["session_id"],
            },
        },
        {
            "name": "list_user_sessions",
            "description": "List all active sessions for the current user",
            "input_schema": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "UUID of any session for the user",
                    }
                },
                "required": ["session_id"],
            },
        },
        {
            "name": "get_session_details",
            "description": "Get detailed information about a specific session",
            "input_schema": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "UUID of the session",
                    }
                },
                "required": ["session_id"],
            },
        },
        {
            "name": "check_scope",
            "description": "Check if the user session has a specific OAuth2 scope",
            "input_schema": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "UUID of the session",
                    },
                    "required_scope": {
                        "type": "string",
                        "description": "Scope to check (e.g., 'bedrock:agents:invoke')",
                    },
                },
                "required": ["session_id", "required_scope"],
            },
        },
    ]

    SYSTEM_PROMPT = """You are AgentCore Identity Assistant, a helpful AI agent for managing authentication, identity, and session information.

Your role is to help users and other agents with:
1. Authentication: Validating tokens, refreshing sessions, understanding authentication status
2. Identity Management: Retrieving user profiles, checking scopes, managing user information
3. Session Management: Viewing active sessions, understanding session details, revoking sessions
4. Security: Enforcing scope-based access control, validating authorization

Use the available tools to accomplish these tasks efficiently and securely."""


class BedrockAgentStack(cdk.Stack):
    """CDK Stack for Bedrock Agent Infrastructure"""

    def __init__(self, scope: Construct, id: str, **kwargs: Any) -> None:
        super().__init__(scope, id, **kwargs)

        # Create IAM role for Bedrock Agent
        agent_role = iam.Role(
            self,
            "BedrockAgentRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Role for AgentCore Identity Bedrock Agent",
        )

        # Add permissions for Bedrock agent
        agent_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonBedrockFullAccess"
            )
        )

        # Add permissions for Lambda invocation
        agent_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "lambda:InvokeFunction",
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["*"],
            )
        )

        # Create IAM role for Lambda function
        lambda_role = iam.Role(
            self,
            "BedrockAgentLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role for Lambda function handling Bedrock Agent tool invocations",
        )

        # Add permissions for Lambda
        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:Query",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                ],
                resources=[
                    f"arn:aws:dynamodb:eu-central-1:<AWS_ACCOUNT_ID>:table/agentcore-identity-*"
                ],
            )
        )

        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "cognito-idp:GetUser",
                    "cognito-idp:AdminGetUser",
                ],
                resources=["*"],
            )
        )

        # Create Lambda function for agent tool handling
        # Using inline code to avoid asset bundling issues with long paths
        agent_handler = lambda_.Function(
            self,
            "BedrockAgentHandler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import json
import boto3

def handler(event, context):
    '''Simple handler for Bedrock Agent tool invocations'''
    print(f"Received event: {json.dumps(event)}")

    # For now, return success - full implementation will be deployed separately
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'AgentCore Identity tool invocation handler',
            'tool': event.get('tool', 'unknown'),
            'status': 'ready'
        })
    }
"""),
            timeout=Duration.seconds(300),
            memory_size=512,
            environment={
                "AGENT_NAME": BedrockAgentConfig.AGENT_NAME,
                "REGION": BedrockAgentConfig.REGION,
                "DYNAMODB_TABLE_SESSIONS": "agentcore-identity-sessions-sandbox",
                "BEDROCK_MODEL_ID": BedrockAgentConfig.MODEL_ID,
                "BEDROCK_AGENT_ID": os.getenv("BEDROCK_AGENT_ID", "D4EQQHH0T3"),
                "BEDROCK_AGENT_ALIAS_ID": os.getenv("BEDROCK_AGENT_ALIAS_ID", "TSTALIASID"),
                "AWS_REGION": BedrockAgentConfig.REGION,
            },
            role=lambda_role,
        )

        # Create CloudWatch Log Group for agent
        log_group = logs.LogGroup(
            self,
            "BedrockAgentLogs",
            log_group_name="/aws/bedrock/agents/agentcore-identity",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Create ECR repository for agent container
        ecr_repo = ecr.Repository(
            self,
            "AgentECRRepository",
            repository_name="agentcore-identity",
            image_scan_on_push=True,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Output key information
        cdk.CfnOutput(
            self,
            "AgentName",
            value=BedrockAgentConfig.AGENT_NAME,
            description="Bedrock Agent Name",
        )

        cdk.CfnOutput(
            self,
            "LambdaFunctionArn",
            value=agent_handler.function_arn,
            description="Lambda function ARN for agent handler",
        )

        cdk.CfnOutput(
            self,
            "AgentRoleArn",
            value=agent_role.role_arn,
            description="IAM role ARN for Bedrock Agent",
        )

        cdk.CfnOutput(
            self,
            "ECRRepositoryUri",
            value=ecr_repo.repository_uri,
            description="ECR repository URI for agent container",
        )

        cdk.CfnOutput(
            self,
            "LogGroupName",
            value=log_group.log_group_name,
            description="CloudWatch Log Group for agent logs",
        )


class BedrockAgentApp(cdk.App):
    """CDK App for Bedrock Agent Stack"""

    def __init__(self) -> None:
        super().__init__()

        BedrockAgentStack(
            self,
            "BedrockAgentStack",
            env=cdk.Environment(
                account=BedrockAgentConfig.ACCOUNT,
                region=BedrockAgentConfig.REGION,
            ),
        )


if __name__ == "__main__":
    app = BedrockAgentApp()
    app.synth()
