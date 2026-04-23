#!/usr/bin/env python3
"""
AWS BedrockAgentCore - Complete CDK Deployment

Deploys REAL AWS BedrockAgentCore service with:
- Runtime: Agent execution environment
- Gateway: Request routing and OAuth validation
- Memory: Session and context storage
"""

from aws_cdk import (
    Stack, App, Environment,
    CfnOutput,
    aws_bedrockagentcore as agentcore,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_kms as kms,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigw,
    aws_secretsmanager as secretsmanager,
    RemovalPolicy,
    Duration,
)
from constructs import Construct


class BedrockAgentCoreStack(Stack):
    """AWS Bedrock AgentCore Stack - REAL AWS Service"""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # ========== IAM ROLE FOR AGENTCORE ==========
        agentcore_role = iam.Role(
            self,
            "BedrockAgentCoreRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="IAM role for AWS Bedrock AgentCore",
            role_name="bedrock-agentcore-service-role",
        )

        # ========== KMS KEY ==========
        kms_key = kms.Key(
            self,
            "BedrockAgentCoreKMS",
            enable_key_rotation=True,
            description="KMS key for Bedrock AgentCore encryption",
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Grant permissions
        kms_key.grant_encrypt_decrypt(agentcore_role)

        # ========== DYNAMODB FOR SESSIONS ==========
        sessions_table = dynamodb.Table(
            self,
            "AgentCoreSessions",
            table_name="bedrock-agentcore-sessions",
            partition_key=dynamodb.Attribute(
                name="session_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=kms_key,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Grant DynamoDB permissions
        sessions_table.grant_read_write_data(agentcore_role)

        # ========== RUNTIME ==========
        print("🚀 Deploying AWS Bedrock AgentCore Runtime...")

        runtime = agentcore.CfnRuntime(
            self,
            "BedrockAgentCoreRuntime",
            agent_runtime_name="bedrock-agentcore-oauth2-runtime",
            role_arn=agentcore_role.role_arn,
            agent_runtime_artifact=agentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                code_configuration=agentcore.CfnRuntime.CodeConfigurationProperty(
                    code=agentcore.CfnRuntime.CodeProperty(
                        s3=agentcore.CfnRuntime.S3LocationProperty(
                            bucket="bedrock-agentcore-artifacts",
                            prefix="runtime-handler.zip"
                        )
                    ),
                    entry_point=["lambda_handler.handler"],
                    runtime="python3.11"
                )
            ),
            network_configuration=agentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="LAMBDA"
            ),
            description="OAuth2 runtime for Bedrock AgentCore",
            environment_variables={
                "DYNAMODB_TABLE": sessions_table.table_name,
                "KMS_KEY_ID": kms_key.key_id,
            }
        )

        # ========== GATEWAY ==========
        print("🔐 Deploying AWS Bedrock AgentCore Gateway...")

        gateway = agentcore.CfnGateway(
            self,
            "BedrockAgentCoreGateway",
            name="bedrock-agentcore-oauth2-gateway",
            protocol_type="REST",
            authorizer_type="OAUTH2",
            role_arn=agentcore_role.role_arn,
            description="OAuth2 gateway for Bedrock AgentCore",
            kms_key_arn=kms_key.key_arn
        )

        # ========== MEMORY ==========
        print("💾 Deploying AWS Bedrock AgentCore Memory...")

        memory = agentcore.CfnMemory(
            self,
            "BedrockAgentCoreMemory",
            name="bedrock-agentcore-session-memory",
            event_expiry_duration=2592000,  # 30 days in seconds
            encryption_key_arn=kms_key.key_arn,
            memory_execution_role_arn=agentcore_role.role_arn,
            description="Session memory for OAuth2 credentials"
        )

        # ========== WORKLOAD IDENTITY ==========
        workload_identity = agentcore.CfnWorkloadIdentity(
            self,
            "BedrockAgentCoreWorkloadIdentity",
            name="bedrock-agentcore-workload"
        )

        # ========== OUTPUTS ==========
        CfnOutput(
            self,
            "RuntimeId",
            value=runtime.ref,
            description="Bedrock AgentCore Runtime ID",
            export_name="BedrockAgentCoreRuntimeId",
        )

        CfnOutput(
            self,
            "GatewayId",
            value=gateway.ref,
            description="Bedrock AgentCore Gateway ID",
            export_name="BedrockAgentCoreGatewayId",
        )

        CfnOutput(
            self,
            "MemoryId",
            value=memory.ref,
            description="Bedrock AgentCore Memory ID",
            export_name="BedrockAgentCoreMemoryId",
        )

        CfnOutput(
            self,
            "WorkloadIdentityId",
            value=workload_identity.ref,
            description="Bedrock AgentCore Workload Identity ID",
            export_name="BedrockAgentCoreWorkloadIdentityId",
        )

        CfnOutput(
            self,
            "RoleArn",
            value=agentcore_role.role_arn,
            description="Bedrock AgentCore Service Role ARN",
            export_name="BedrockAgentCoreRoleArn",
        )

        CfnOutput(
            self,
            "SessionsTable",
            value=sessions_table.table_name,
            description="DynamoDB sessions table",
            export_name="BedrockAgentCoreSessionsTable",
        )


class BedrockAgentCoreApp(App):
    """CDK App for Bedrock AgentCore."""

    def __init__(self):
        super().__init__()

        stack = BedrockAgentCoreStack(
            self,
            "BedrockAgentCoreStack",
            env=Environment(
                account="<AWS_ACCOUNT_ID>",  # <AWS_PROFILE>
                region="eu-central-1",
            ),
        )


if __name__ == "__main__":
    app = BedrockAgentCoreApp()
    app.synth()
