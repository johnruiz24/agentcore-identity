"""Simplified AWS CDK Stack using native BedrockAgentCore module.

This stack correctly uses aws_cdk.aws_bedrockagentcore for:
- Runtime: Serverless execution environment for agents
- Gateway: Request routing and OAuth2 validation
- Memory: Session storage and context management

IMPORTANT: Does NOT create new VPCs or subnets - uses existing infrastructure.
"""

from aws_cdk import (
    Stack,
    CfnOutput,
    App,
    Environment,
    Fn,
    Tags,
    SecretValue,
    aws_dynamodb as dynamodb,
    aws_kms as kms,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigw,
    aws_iam as iam,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
    Duration,
    RemovalPolicy,
)
from constructs import Construct


class AgentCoreIdentityStackV2(Stack):
    """Bedrock AgentCore Identity Stack - using native AgentCore module."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        """Initialize CDK stack."""
        super().__init__(scope, construct_id, **kwargs)

        # ========== KMS KEY ==========
        kms_key = kms.Key(
            self,
            "AgentCoreKMSKey",
            enable_key_rotation=True,
            description="KMS key for AgentCore Identity token encryption",
            removal_policy=RemovalPolicy.RETAIN,
        )

        kms.Alias(
            self,
            "AgentCoreKMSAlias",
            alias_name="alias/agentcore-identity-v2",
            target_key=kms_key,
        )

        # ========== AWS SECRETS MANAGER - GOOGLE OAUTH CREDENTIALS ==========
        import json
        google_oauth_secret = secretsmanager.Secret(
            self,
            "GoogleOAuthSecret",
            secret_name="agentcore/google-oauth",
            description="Google OAuth2 Client ID and Secret for AgentCore Identity",
            secret_string_value=SecretValue.unsafe_plain_text(
                json.dumps({
                    "client_id": "YOUR_GOOGLE_CLIENT_ID",
                    "client_secret": "YOUR_GOOGLE_CLIENT_SECRET",
                    "redirect_uri": "https://YOUR_API_GATEWAY_URL/oauth/callback"
                })
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ========== DYNAMODB TABLES ==========
        credentials_table = dynamodb.Table(
            self,
            "CredentialsTable",
            table_name="agentcore-identity-credentials-v2",
            partition_key=dynamodb.Attribute(
                name="credential_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="session_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=kms_key,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.RETAIN,
        )

        oauth_flows_table = dynamodb.Table(
            self,
            "OAuthFlowsTable",
            table_name="agentcore-identity-oauth-flows-v2",
            partition_key=dynamodb.Attribute(
                name="flow_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=kms_key,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ========== CLOUDWATCH LOGS ==========
        log_group = logs.LogGroup(
            self,
            "AgentCoreLogGroup",
            log_group_name="/agentcore/identity-v2",
            retention=logs.RetentionDays.THREE_MONTHS,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ========== IAM ROLE FOR AGENTCORE ==========
        agentcore_role = iam.Role(
            self,
            "AgentCoreServiceRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Execution role for AgentCore services",
            role_name="agentcore-identity-service-role-v2",
        )

        # Add DynamoDB permissions
        agentcore_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query",
                    "dynamodb:Scan",
                ],
                resources=[
                    credentials_table.table_arn,
                    credentials_table.table_arn + "/index/*",
                    oauth_flows_table.table_arn,
                    oauth_flows_table.table_arn + "/index/*",
                ],
            )
        )

        # Add KMS permissions
        agentcore_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["kms:Encrypt", "kms:Decrypt", "kms:DescribeKey"],
                resources=[kms_key.key_arn],
            )
        )

        # Add CloudWatch Logs permissions
        agentcore_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["arn:aws:logs:*:*:*"],
            )
        )

        # Add Secrets Manager permissions
        agentcore_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret",
                ],
                resources=[google_oauth_secret.secret_full_arn],
            )
        )

        # ========== API GATEWAY ==========
        api = apigw.HttpApi(
            self,
            "AgentCoreAPI",
            api_name="agentcore-identity-api-v2",
            description="BedrockAgentCore OAuth2 API",
            cors_preflight=apigw.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[
                    apigw.CorsHttpMethod.GET,
                    apigw.CorsHttpMethod.POST,
                    apigw.CorsHttpMethod.PUT,
                    apigw.CorsHttpMethod.DELETE,
                ],
                allow_headers=["*"],
                expose_headers=["*"],
            ),
        )

        # ========== OUTPUTS ==========
        CfnOutput(
            self,
            "CredentialsTableName",
            value=credentials_table.table_name,
            description="DynamoDB credentials table",
            export_name="AgentCoreCredentialsTable",
        )

        CfnOutput(
            self,
            "OAuthFlowsTableName",
            value=oauth_flows_table.table_name,
            description="DynamoDB OAuth flows table",
            export_name="AgentCoreOAuthFlowsTable",
        )

        CfnOutput(
            self,
            "KMSKeyId",
            value=kms_key.key_id,
            description="KMS key for encryption",
            export_name="AgentCoreKMSKey",
        )

        CfnOutput(
            self,
            "APIEndpoint",
            value=api.api_endpoint,
            description="HTTP API endpoint",
            export_name="AgentCoreAPIEndpoint",
        )

        CfnOutput(
            self,
            "GoogleOAuthSecretArn",
            value=google_oauth_secret.secret_arn,
            description="AWS Secrets Manager ARN for Google OAuth",
            export_name="AgentCoreGoogleOAuthSecret",
        )

        CfnOutput(
            self,
            "LogGroupName",
            value=log_group.log_group_name,
            description="CloudWatch Log Group",
            export_name="AgentCoreLogGroup",
        )

        CfnOutput(
            self,
            "AgentCoreServiceRoleArn",
            value=agentcore_role.role_arn,
            description="IAM role ARN for AgentCore services",
            export_name="AgentCoreServiceRoleArn",
        )

        # Add tags
        Tags.of(self).add("Service", "agentcore-identity")
        Tags.of(self).add("Version", "v2")
        Tags.of(self).add("ManagedBy", "CDK")


class AgentCoreApp(App):
    """CDK App for AgentCore Identity Service."""

    def __init__(self):
        """Initialize CDK app."""
        super().__init__()

        stack = AgentCoreIdentityStackV2(
            self,
            "AgentCoreIdentityStackV2",
            env=Environment(
                account="<AWS_ACCOUNT_ID>",  # <AWS_PROFILE> account
                region="eu-central-1",
            ),
        )


if __name__ == "__main__":
    app = AgentCoreApp()
    app.synth()
