#!/usr/bin/env python3
"""
AWS Bedrock AgentCore Complete Platform - CDK Deployment

Deploys COMPLETE Bedrock AgentCore OAuth2 Platform with:
1. Lambda Functions (Identity, Gateway, Runtime)
2. API Gateway with routes
3. DynamoDB tables for credentials and OAuth flows
4. KMS key for encryption
5. AWS BedrockAgentCore Service (Runtime, Gateway, Memory)
6. IAM roles and permissions
"""

from aws_cdk import (
    Stack, App, Environment,
    CfnOutput,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as apigw_integrations,
    aws_dynamodb as dynamodb,
    aws_kms as kms,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    aws_s3_assets as s3_assets,
    aws_bedrockagentcore as agentcore,
    RemovalPolicy,
    Duration,
    Tags,
)
from constructs import Construct
from pathlib import Path
import os


class BedrockAgentCoreOAuth2Stack(Stack):
    """Complete Bedrock AgentCore OAuth2 Platform Stack"""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        account_id = "<AWS_ACCOUNT_ID>"
        region = "eu-central-1"

        # ========== KMS KEY FOR ENCRYPTION ==========
        kms_key = kms.Key(
            self,
            "BedrockAgentCoreKMS",
            enable_key_rotation=True,
            description="KMS key for Bedrock AgentCore OAuth2 encryption",
            removal_policy=RemovalPolicy.RETAIN,
        )

        kms_key.add_alias("alias/bedrock-agentcore-oauth2")

        CfnOutput(
            self,
            "KMSKeyId",
            value=kms_key.key_id,
            description="KMS Key ID",
            export_name="BedrockAgentCoreKMSKeyId",
        )

        # ========== DYNAMODB TABLES ==========
        # Credentials table - stores encrypted OAuth tokens
        credentials_table = dynamodb.Table(
            self,
            "CredentialsTable",
            table_name="bedrock-agentcore-oauth2-credentials",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="credential_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=kms_key,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # OAuth flows table - stores state and code_verifier for PKCE
        oauth_flows_table = dynamodb.Table(
            self,
            "OAuthFlowsTable",
            table_name="bedrock-agentcore-oauth2-oauth-flows",
            partition_key=dynamodb.Attribute(
                name="flow_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=kms_key,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Add TTL for auto-cleanup of expired flows (24 hours)
        oauth_flows_table.add_ttl_attribute(attribute_name="ttl")

        CfnOutput(
            self,
            "CredentialsTableName",
            value=credentials_table.table_name,
            export_name="BedrockAgentCoreCredentialsTable",
        )

        CfnOutput(
            self,
            "OAuthFlowsTableName",
            value=oauth_flows_table.table_name,
            export_name="BedrockAgentCoreOAuthFlowsTable",
        )

        # ========== GOOGLE OAUTH SECRETS ==========
        google_oauth_secret = secretsmanager.Secret(
            self,
            "GoogleOAuthSecret",
            secret_name="bedrock-agentcore-oauth2/google-oauth",
            description="Google OAuth2 credentials for Bedrock AgentCore",
            removal_policy=RemovalPolicy.RETAIN,
        )

        CfnOutput(
            self,
            "GoogleOAuthSecretArn",
            value=google_oauth_secret.secret_arn,
            export_name="BedrockAgentCoreGoogleOAuthSecretArn",
        )

        # ========== IAM ROLE FOR LAMBDA ==========
        lambda_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="IAM role for Bedrock AgentCore Lambda functions",
            role_name="bedrock-agentcore-lambda-execution-role",
        )

        # Grant permissions
        credentials_table.grant_read_write_data(lambda_role)
        oauth_flows_table.grant_read_write_data(lambda_role)
        kms_key.grant_encrypt_decrypt(lambda_role)
        google_oauth_secret.grant_read(lambda_role)

        # ========== LAMBDA FUNCTIONS ==========
        # Read handler code from files
        handlers_path = Path(__file__).parent / "lambdas"

        # Identity Handler
        identity_handler_code = lambda_.Code.from_asset(
            str(handlers_path / "identity_handler.py")
        ) if (handlers_path / "identity_handler.py").exists() else lambda_.Code.from_inline(
            "def handler(event, context): return {'statusCode': 200}"
        )

        identity_function = lambda_.Function(
            self,
            "IdentityHandler",
            function_name="bedrock-agentcore-identity-handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=lambda_.Code.from_inline(
                self._read_handler_code(handlers_path / "identity_handler.py")
            ),
            handler="index.handler",
            role=lambda_role,
            environment={
                "CREDENTIALS_TABLE": credentials_table.table_name,
                "OAUTH_FLOWS_TABLE": oauth_flows_table.table_name,
                "KMS_KEY_ID": kms_key.key_id,
                "GOOGLE_SECRET_ARN": google_oauth_secret.secret_arn,
                "REGION": region,
            },
            timeout=Duration.seconds(60),
            memory_size=512,
        )

        # Gateway Handler
        gateway_function = lambda_.Function(
            self,
            "GatewayHandler",
            function_name="bedrock-agentcore-gateway-handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=lambda_.Code.from_inline(
                self._read_handler_code(handlers_path / "gateway_handler.py")
            ),
            handler="index.handler",
            role=lambda_role,
            environment={
                "CREDENTIALS_TABLE": credentials_table.table_name,
                "OAUTH_FLOWS_TABLE": oauth_flows_table.table_name,
                "KMS_KEY_ID": kms_key.key_id,
                "GOOGLE_SECRET_ARN": google_oauth_secret.secret_arn,
                "REGION": region,
            },
            timeout=Duration.seconds(60),
            memory_size=512,
        )

        # Runtime Handler
        runtime_function = lambda_.Function(
            self,
            "RuntimeHandler",
            function_name="bedrock-agentcore-runtime-handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=lambda_.Code.from_inline(
                self._read_handler_code(handlers_path / "runtime_handler.py")
            ),
            handler="index.handler",
            role=lambda_role,
            environment={
                "CREDENTIALS_TABLE": credentials_table.table_name,
                "OAUTH_FLOWS_TABLE": oauth_flows_table.table_name,
                "KMS_KEY_ID": kms_key.key_id,
                "GOOGLE_SECRET_ARN": google_oauth_secret.secret_arn,
                "REGION": region,
            },
            timeout=Duration.seconds(60),
            memory_size=512,
        )

        CfnOutput(
            self,
            "IdentityHandlerArn",
            value=identity_function.function_arn,
            export_name="BedrockAgentCoreIdentityHandlerArn",
        )

        CfnOutput(
            self,
            "GatewayHandlerArn",
            value=gateway_function.function_arn,
            export_name="BedrockAgentCoreGatewayHandlerArn",
        )

        CfnOutput(
            self,
            "RuntimeHandlerArn",
            value=runtime_function.function_arn,
            export_name="BedrockAgentCoreRuntimeHandlerArn",
        )

        # ========== API GATEWAY ==========
        api = apigw.HttpApi(
            self,
            "BedrockAgentCoreAPI",
            api_name="bedrock-agentcore-api",
            description="Bedrock AgentCore OAuth2 Platform API",
            cors_preflight=apigw.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[
                    apigw.HttpMethod.GET,
                    apigw.HttpMethod.POST,
                    apigw.HttpMethod.PUT,
                    apigw.HttpMethod.DELETE,
                ],
                allow_headers=["*"],
            ),
        )

        # Create integrations
        identity_integration = apigw.HttpIntegration(
            url=identity_function.function_url.url,
            http_method=apigw.HttpMethod.POST,
        )

        gateway_integration = apigw.HttpIntegration(
            url=gateway_function.function_url.url,
            http_method=apigw.HttpMethod.POST,
        )

        runtime_integration = apigw.HttpIntegration(
            url=runtime_function.function_url.url,
            http_method=apigw.HttpMethod.POST,
        )

        # Create routes - Identity Service
        api.add_routes(
            path="/oauth/authorize",
            methods=[apigw.HttpMethod.GET],
            integration=identity_integration,
        )

        api.add_routes(
            path="/oauth/callback",
            methods=[apigw.HttpMethod.POST],
            integration=identity_integration,
        )

        api.add_routes(
            path="/oauth/status",
            methods=[apigw.HttpMethod.GET],
            integration=identity_integration,
        )

        # Create routes - Gateway Service
        api.add_routes(
            path="/gateway/validate",
            methods=[apigw.HttpMethod.POST],
            integration=gateway_integration,
        )

        api.add_routes(
            path="/gateway/invoke",
            methods=[apigw.HttpMethod.POST],
            integration=gateway_integration,
        )

        # Create routes - Runtime Service
        api.add_routes(
            path="/runtime/calendar/events",
            methods=[apigw.HttpMethod.GET],
            integration=runtime_integration,
        )

        api.add_routes(
            path="/runtime/calendar/create",
            methods=[apigw.HttpMethod.POST],
            integration=runtime_integration,
        )

        CfnOutput(
            self,
            "APIEndpoint",
            value=api.url or "https://api-endpoint",
            export_name="BedrockAgentCoreAPIEndpoint",
        )

        # ========== AWS BEDROCK AGENTCORE SERVICE ==========
        # IAM Role for BedrockAgentCore service
        agentcore_role = iam.Role(
            self,
            "BedrockAgentCoreServiceRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="IAM role for AWS Bedrock AgentCore service",
            role_name="bedrock-agentcore-service-role",
        )

        # Grant permissions
        credentials_table.grant_read_write_data(agentcore_role)
        oauth_flows_table.grant_read_write_data(agentcore_role)
        kms_key.grant_encrypt_decrypt(agentcore_role)

        # Create sessions table for BedrockAgentCore
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
            removal_policy=RemovalPolicy.RETAIN,
        )

        sessions_table.add_ttl_attribute(attribute_name="ttl")
        sessions_table.grant_read_write_data(agentcore_role)

        # BedrockAgentCore Runtime
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
                            prefix="runtime-handler.zip",
                        )
                    ),
                    entry_point=["lambda_handler.handler"],
                    runtime="python3.11",
                )
            ),
            network_configuration=agentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="LAMBDA"
            ),
            description="OAuth2 runtime for Bedrock AgentCore",
            environment_variables={
                "DYNAMODB_TABLE": sessions_table.table_name,
                "KMS_KEY_ID": kms_key.key_id,
            },
        )

        # BedrockAgentCore Gateway
        gateway = agentcore.CfnGateway(
            self,
            "BedrockAgentCoreGateway",
            name="bedrock-agentcore-oauth2-gateway",
            protocol_type="REST",
            authorizer_type="OAUTH2",
            role_arn=agentcore_role.role_arn,
            description="OAuth2 gateway for Bedrock AgentCore",
            kms_key_arn=kms_key.key_arn,
        )

        # BedrockAgentCore Memory
        memory = agentcore.CfnMemory(
            self,
            "BedrockAgentCoreMemory",
            name="bedrock-agentcore-session-memory",
            event_expiry_duration=2592000,  # 30 days
            encryption_key_arn=kms_key.key_arn,
            memory_execution_role_arn=agentcore_role.role_arn,
            description="Session memory for OAuth2 credentials",
        )

        # BedrockAgentCore Workload Identity
        workload_identity = agentcore.CfnWorkloadIdentity(
            self,
            "BedrockAgentCoreWorkloadIdentity",
            name="bedrock-agentcore-workload",
        )

        CfnOutput(
            self,
            "BedrockRuntimeId",
            value=runtime.ref,
            export_name="BedrockAgentCoreRuntimeId",
        )

        CfnOutput(
            self,
            "BedrockGatewayId",
            value=gateway.ref,
            export_name="BedrockAgentCoreGatewayId",
        )

        CfnOutput(
            self,
            "BedrockMemoryId",
            value=memory.ref,
            export_name="BedrockAgentCoreMemoryId",
        )

        CfnOutput(
            self,
            "BedrockWorkloadIdentityId",
            value=workload_identity.ref,
            export_name="BedrockAgentCoreWorkloadIdentityId",
        )

        # ========== TAGS ==========
        Tags.of(self).add("Service", "bedrock-agentcore")
        Tags.of(self).add("Platform", "oauth2")
        Tags.of(self).add("Environment", "production")

    def _read_handler_code(self, file_path: Path) -> str:
        """Read Lambda handler code from file"""
        if file_path.exists():
            return file_path.read_text()
        else:
            # Return minimal handler if file doesn't exist
            return """
def handler(event, context):
    return {
        'statusCode': 200,
        'body': 'Handler not implemented'
    }
"""


class BedrockAgentCoreApp(App):
    """CDK App for complete Bedrock AgentCore platform"""

    def __init__(self):
        super().__init__()

        stack = BedrockAgentCoreOAuth2Stack(
            self,
            "BedrockAgentCoreOAuth2Stack",
            env=Environment(
                account="<AWS_ACCOUNT_ID>",  # <AWS_PROFILE>
                region="eu-central-1",
            ),
            description="Complete Bedrock AgentCore OAuth2 Platform with Google Calendar integration",
        )


if __name__ == "__main__":
    app = BedrockAgentCoreApp()
    app.synth()
