"""AWS CDK Stack for Bedrock AgentCore Identity Service.

Infrastructure-as-Code deployment for complete OAuth2 credential management
platform on AWS, including:
- AWS BedrockAgentCore (Runtime, Gateway, Memory)
- DynamoDB, KMS, Lambda, API Gateway
- Complete three-layer architecture: Identity → Gateway → Runtime

Uses native aws_cdk.aws_bedrockagentcore module for proper AgentCore deployment.
"""

from aws_cdk import (
    Stack,
    CfnOutput,
    App,
    Environment,
    Fn,
    Tags,
    aws_dynamodb as dynamodb,
    aws_kms as kms,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as integrations,
    aws_iam as iam,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_secretsmanager as secretsmanager,
    aws_bedrockagentcore as agentcore,
    Duration,
    RemovalPolicy,
    SecretValue,
)
from constructs import Construct
from aws_cdk.aws_apigatewayv2_integrations import HttpLambdaIntegration


class AgentCoreIdentityStack(Stack):
    """CDK Stack for AgentCore Identity Service."""

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
            alias_name="alias/agentcore-identity",
            target_key=kms_key,
        )

        # ========== AWS SECRETS MANAGER - GOOGLE OAUTH CREDENTIALS ==========
        google_oauth_secret = secretsmanager.Secret(
            self,
            "GoogleOAuthSecret",
            secret_name="agentcore/google-oauth",
            description="Google OAuth2 Client ID and Secret for AgentCore Identity",
            secret_string_value=SecretValue.plain_text(
                '{"client_id": "YOUR_GOOGLE_CLIENT_ID", "client_secret": "YOUR_GOOGLE_CLIENT_SECRET", "redirect_uri": "https://YOUR_API_GATEWAY_URL/oauth/callback"}'
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ========== DYNAMODB TABLES ==========
        credentials_table = dynamodb.Table(
            self,
            "CredentialsTable",
            table_name="agentcore-identity-credentials",
            partition_key=dynamodb.Attribute(
                name="credential_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="session_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=kms_key,
            point_in_time_recovery=True,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.RETAIN,
        )

        credentials_table.add_global_secondary_index(
            index_name="session_id-provider_name-index",
            partition_key=dynamodb.Attribute(
                name="session_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="provider_name", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        oauth_flows_table = dynamodb.Table(
            self,
            "OAuthFlowsTable",
            table_name="agentcore-identity-oauth-flows",
            partition_key=dynamodb.Attribute(
                name="flow_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=kms_key,
            point_in_time_recovery=True,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.RETAIN,
        )

        oauth_flows_table.add_global_secondary_index(
            index_name="session_id-index",
            partition_key=dynamodb.Attribute(
                name="session_id", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        audit_table = dynamodb.Table(
            self,
            "AuditLogsTable",
            table_name="agentcore-identity-audit-logs",
            partition_key=dynamodb.Attribute(
                name="entry_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=kms_key,
            point_in_time_recovery=True,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.RETAIN,
        )

        audit_table.add_global_secondary_index(
            index_name="session_id-timestamp-index",
            partition_key=dynamodb.Attribute(
                name="session_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp", type=dynamodb.AttributeType.NUMBER
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        audit_table.add_global_secondary_index(
            index_name="user_id-timestamp-index",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp", type=dynamodb.AttributeType.NUMBER
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        audit_table.add_global_secondary_index(
            index_name="action-timestamp-index",
            partition_key=dynamodb.Attribute(
                name="action", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp", type=dynamodb.AttributeType.NUMBER
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # ========== CLOUDWATCH LOGS ==========
        log_group = logs.LogGroup(
            self,
            "AgentCoreLogGroup",
            log_group_name="/agentcore/identity",
            retention=logs.RetentionDays.THREE_MONTHS,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ========== IAM ROLE ==========
        lambda_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Execution role for AgentCore Identity Lambda functions",
            role_name="agentcore-identity-lambda-role",
        )

        # Add permissions
        lambda_role.add_to_policy(
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
                    audit_table.table_arn,
                    audit_table.table_arn + "/index/*",
                ],
            )
        )

        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["kms:Encrypt", "kms:Decrypt", "kms:DescribeKey"],
                resources=[kms_key.key_arn],
            )
        )

        lambda_role.add_to_policy(
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

        # Secrets Manager permissions for Google OAuth credentials
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret",
                ],
                resources=[google_oauth_secret.secret_full_arn],
            )
        )

        # Lambda invoke permissions (for Gateway to invoke Runtime)
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=["arn:aws:lambda:*:*:function:agentcore-*"],
            )
        )

        # ========== BEDROCK AGENTCORE RUNTIME ==========
        # Create BedrockAgentCore runtime for serverless agent execution
        # Runtime requires artifact (code), network configuration, and authorization
        runtime = agentcore.CfnRuntime(
            self,
            "AgentCoreRuntime",
            agent_runtime_artifact=agentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                code_configuration=agentcore.CfnRuntime.CodeConfigurationProperty(
                    code=agentcore.CfnRuntime.CodeProperty(
                        s3=agentcore.CfnRuntime.S3LocationProperty(
                            bucket="agentcore-artifacts",
                            prefix="runtime.zip"
                        )
                    ),
                    entry_point="index.handler",
                    runtime="python3.11"
                )
            ),
            agent_runtime_name="agentcore-identity-runtime",
            role_arn=lambda_role.role_arn,
            network_configuration=agentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="LAMBDA"  # Use Lambda networking (no VPC required)
            ),
            description="OAuth2 credential runtime for Bedrock AgentCore",
            environment_variables={
                "DYNAMODB_CREDENTIALS_TABLE": credentials_table.table_name,
                "DYNAMODB_OAUTH_FLOWS_TABLE": oauth_flows_table.table_name,
                "DYNAMODB_AUDIT_TABLE": audit_table.table_name,
                "KMS_KEY_ID": kms_key.key_id,
                "REGION": self.region,
            },
            tags={
                "Service": "agentcore-identity",
                "Component": "runtime",
            }
        )

        # ========== BEDROCK AGENTCORE GATEWAY ==========
        # Create BedrockAgentCore gateway for request routing and OAuth validation
        gateway = agentcore.CfnGateway(
            self,
            "AgentCoreGateway",
            name="agentcore-identity-gateway",
            protocol_type="REST",
            authorizer_type="OAUTH2",
            role_arn=lambda_role.role_arn,
            description="OAuth2 gateway for Bedrock AgentCore Identity",
            kms_key_arn=kms_key.key_arn,
            authorizer_configuration={
                "oauth2_provider_arn": google_oauth_secret.secret_arn,
                "oauth2_scopes": ["email", "profile", "https://www.googleapis.com/auth/calendar"],
            },
            tags={
                "Service": "agentcore-identity",
                "Component": "gateway",
            }
        )

        # ========== BEDROCK AGENTCORE MEMORY (Session Storage) ==========
        # Create BedrockAgentCore memory for session persistence and context management
        memory = agentcore.CfnMemory(
            self,
            "AgentCoreMemory",
            name="agentcore-identity-memory",
            event_expiry_duration=2592000,  # 30 days in seconds
            encryption_key_arn=kms_key.key_arn,
            memory_execution_role_arn=lambda_role.role_arn,
            description="Session memory storage for OAuth2 credentials",
            memory_strategies=[
                {
                    "memory_type": "LONG_TERM",
                    "ttl_seconds": 2592000,  # 30 days
                }
            ],
            tags={
                "Service": "agentcore-identity",
                "Component": "memory",
            }
        )

        # ========== BEDROCK AGENTCORE WORKLOAD IDENTITY ==========
        # Create workload identity for secure service-to-service communication
        workload_identity = agentcore.CfnWorkloadIdentity(
            self,
            "AgentCoreWorkloadIdentity",
            name="agentcore-identity-workload",
            tags={
                "Service": "agentcore-identity",
                "Component": "workload-identity",
            }
        )

        # ========== LAMBDA FUNCTIONS ==========
        # Note: In production, Lambda functions would be packaged separately
        # This is a placeholder for the actual Lambda handlers

        # ========== API GATEWAY ==========
        api = apigw.HttpApi(
            self,
            "AgentCoreAPI",
            api_name="agentcore-identity-api",
            description="OAuth2 API for Bedrock AgentCore Identity",
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

        # ========== CLOUDWATCH METRICS & ALARMS ==========

        # DynamoDB Throttling Alarms
        credentials_table_throttle = cloudwatch.Alarm(
            self,
            "CredentialsTableThrottleAlarm",
            metric=credentials_table.metric_user_errors(
                statistic=cloudwatch.Stats.SUM
            ),
            threshold=1,
            evaluation_periods=1,
            alarm_description="Alert when credentials table has user errors (throttling)"
        )

        oauth_flows_table_throttle = cloudwatch.Alarm(
            self,
            "OAuthFlowsTableThrottleAlarm",
            metric=oauth_flows_table.metric_user_errors(
                statistic=cloudwatch.Stats.SUM
            ),
            threshold=1,
            evaluation_periods=1,
            alarm_description="Alert when OAuth flows table has user errors (throttling)"
        )

        audit_table_throttle = cloudwatch.Alarm(
            self,
            "AuditTableThrottleAlarm",
            metric=audit_table.metric_user_errors(
                statistic=cloudwatch.Stats.SUM
            ),
            threshold=1,
            evaluation_periods=1,
            alarm_description="Alert when audit table has user errors (throttling)"
        )

        # Create CloudWatch Dashboard
        dashboard = cloudwatch.Dashboard(
            self,
            "AgentCoreIdentityDashboard",
            dashboard_name="agentcore-identity",
        )

        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="DynamoDB Read/Write Capacity",
                left=[
                    credentials_table.metric_consumed_read_capacity_units(
                        statistic=cloudwatch.Stats.SUM
                    ),
                    credentials_table.metric_consumed_write_capacity_units(
                        statistic=cloudwatch.Stats.SUM
                    ),
                ],
            ),
            cloudwatch.GraphWidget(
                title="Lambda Invocations",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/Lambda",
                        metric_name="Invocations",
                        statistic=cloudwatch.Stats.SUM,
                        period=Duration.minutes(5),
                    ),
                ],
            ),
        )

        # ========== ECR REPOSITORY ==========
        ecr_repo = ecr.Repository(
            self,
            "AgentCoreECR",
            repository_name="agentcore-identity",
            image_scan_on_push=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ========== OUTPUTS ==========
        # BedrockAgentCore Resources
        CfnOutput(
            self,
            "RuntimeId",
            value=runtime.ref,
            description="BedrockAgentCore Runtime ID",
            export_name="AgentCoreRuntimeId",
        )

        CfnOutput(
            self,
            "GatewayId",
            value=gateway.ref,
            description="BedrockAgentCore Gateway ID",
            export_name="AgentCoreGatewayId",
        )

        CfnOutput(
            self,
            "MemoryId",
            value=memory.ref,
            description="BedrockAgentCore Memory ID for session storage",
            export_name="AgentCoreMemoryId",
        )

        CfnOutput(
            self,
            "WorkloadIdentityId",
            value=workload_identity.ref,
            description="BedrockAgentCore Workload Identity ID",
            export_name="AgentCoreWorkloadIdentityId",
        )

        # DynamoDB Resources
        CfnOutput(
            self,
            "CredentialsTableName",
            value=credentials_table.table_name,
            description="DynamoDB table for credentials",
        )

        CfnOutput(
            self,
            "OAuthFlowsTableName",
            value=oauth_flows_table.table_name,
            description="DynamoDB table for OAuth flows",
        )

        CfnOutput(
            self,
            "AuditLogsTableName",
            value=audit_table.table_name,
            description="DynamoDB table for audit logs",
        )

        CfnOutput(
            self,
            "KMSKeyId",
            value=kms_key.key_id,
            description="KMS key for encryption",
        )

        CfnOutput(
            self,
            "APIEndpoint",
            value=api.api_endpoint,
            description="HTTP API endpoint",
        )

        CfnOutput(
            self,
            "ECRRepositoryUri",
            value=ecr_repo.repository_uri,
            description="ECR repository URI",
        )

        CfnOutput(
            self,
            "LambdaRoleArn",
            value=lambda_role.role_arn,
            description="Lambda execution role ARN",
        )

        CfnOutput(
            self,
            "GoogleOAuthSecretArn",
            value=google_oauth_secret.secret_arn,
            description="AWS Secrets Manager ARN for Google OAuth credentials",
        )

        CfnOutput(
            self,
            "LogGroupName",
            value=log_group.log_group_name,
            description="CloudWatch Log Group for monitoring",
        )

        CfnOutput(
            self,
            "DashboardName",
            value=dashboard.dashboard_name,
            description="CloudWatch Dashboard for monitoring",
        )


class AgentCoreApp(App):
    """CDK App for AgentCore Identity Service."""

    def __init__(self):
        """Initialize CDK app."""
        super().__init__()

        stack = AgentCoreIdentityStack(
            self,
            "AgentCoreIdentityStack",
            env=Environment(
                account=Fn.sub("${AWS::AccountId}"),
                region=Fn.sub("${AWS::Region}"),
            ),
        )

        # Add tags
        Tags.of(stack).add("Service", "agentcore-identity")
        Tags.of(stack).add("Component", "infrastructure")
        Tags.of(stack).add("ManagedBy", "CDK")


if __name__ == "__main__":
    app = AgentCoreApp()
    app.synth()
