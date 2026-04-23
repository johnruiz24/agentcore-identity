"""API Gateway configuration for AgentCore Identity Service."""

import json
from typing import Dict, List

import boto3
from botocore.exceptions import ClientError


class APIGatewayConfig:
    """Manages API Gateway setup for AgentCore Identity endpoints."""

    def __init__(self, region: str = "eu-central-1"):
        """Initialize API Gateway configuration.

        Args:
            region: AWS region
        """
        self.region = region
        self.apigw_client = boto3.client("apigatewayv2", region_name=region)

    def create_http_api(
        self,
        api_name: str = "agentcore-identity-api",
        description: str = "AgentCore Identity Service HTTP API",
    ) -> str:
        """Create HTTP API in API Gateway.

        Args:
            api_name: Name for the API
            description: API description

        Returns:
            API ID
        """
        try:
            response = self.apigw_client.create_api(
                Name=api_name,
                ProtocolType="HTTP",
                Description=description,
                CorsConfiguration={
                    "AllowOrigins": ["*"],
                    "AllowMethods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                    "AllowHeaders": ["*"],
                    "ExposeHeaders": ["*"],
                    "MaxAge": 300,
                    "AllowCredentials": False,
                },
                Tags={
                    "Service": "agentcore-identity",
                    "Component": "api",
                },
            )

            return response["ApiId"]

        except ClientError as e:
            if "already exists" in str(e):
                # API already exists, find it
                apis = self.apigw_client.get_apis()
                for api in apis.get("Items", []):
                    if api["Name"] == api_name:
                        return api["ApiId"]
            raise Exception(f"Failed to create API Gateway: {e}")

    def create_routes(
        self,
        api_id: str,
        lambda_role_arn: str,
        routes: List[Dict],
    ) -> None:
        """Create API Gateway routes.

        Args:
            api_id: API ID
            lambda_role_arn: IAM role ARN for Lambda integration
            routes: List of route configurations

        Each route should have:
        - path: API path (e.g., "/auth/token")
        - method: HTTP method (GET, POST, etc.)
        - lambda_function: Lambda function name to invoke
        """
        try:
            # Create integration for each route
            for route in routes:
                path = route["path"]
                method = route["method"]
                lambda_function = route["lambda_function"]

                # Create Lambda integration
                integration_response = self.apigw_client.create_integration(
                    ApiId=api_id,
                    IntegrationType="AWS_PROXY",
                    IntegrationMethod="POST",
                    PayloadFormatVersion="2.0",
                    CredentialsArn=lambda_role_arn,
                    Target=f"arn:aws:lambda:{self.region}:123456789012:function:{lambda_function}",
                )

                integration_id = integration_response["IntegrationId"]

                # Create route
                route_key = f"{method} {path}"
                self.apigw_client.create_route(
                    ApiId=api_id,
                    RouteKey=route_key,
                    Target=f"integrations/{integration_id}",
                    AuthorizationType="AWS_IAM",
                )

        except ClientError as e:
            raise Exception(f"Failed to create routes: {e}")

    def create_stage(
        self,
        api_id: str,
        stage_name: str = "prod",
        throttle_settings: Dict = None,
    ) -> str:
        """Create deployment stage.

        Args:
            api_id: API ID
            stage_name: Stage name (prod, dev, etc.)
            throttle_settings: Rate limiting settings

        Returns:
            Stage URL
        """
        try:
            if throttle_settings is None:
                throttle_settings = {
                    "RateLimit": 10000,
                    "BurstLimit": 5000,
                }

            response = self.apigw_client.create_stage(
                ApiId=api_id,
                StageName=stage_name,
                AutoDeploy=True,
                ThrottleSettings=throttle_settings,
                DefaultRouteSettings={
                    "ThrottleSettings": throttle_settings,
                },
                Tags={
                    "Service": "agentcore-identity",
                    "Stage": stage_name,
                },
            )

            return response["InvokeUrl"]

        except ClientError as e:
            raise Exception(f"Failed to create stage: {e}")

    def add_cors_configuration(
        self,
        api_id: str,
        allowed_origins: List[str],
        allowed_methods: List[str],
    ) -> None:
        """Update CORS configuration.

        Args:
            api_id: API ID
            allowed_origins: List of allowed origins
            allowed_methods: List of allowed HTTP methods
        """
        try:
            self.apigw_client.update_api(
                ApiId=api_id,
                CorsConfiguration={
                    "AllowOrigins": allowed_origins,
                    "AllowMethods": allowed_methods,
                    "AllowHeaders": ["*"],
                    "ExposeHeaders": ["*"],
                    "MaxAge": 300,
                },
            )
        except ClientError as e:
            raise Exception(f"Failed to update CORS: {e}")

    def enable_api_logging(
        self,
        api_id: str,
        log_group_arn: str,
        format_string: str = None,
    ) -> None:
        """Enable CloudWatch logging for API Gateway.

        Args:
            api_id: API ID
            log_group_arn: CloudWatch log group ARN
            format_string: Custom log format string
        """
        try:
            if format_string is None:
                format_string = (
                    "$context.requestId $context.error.message $context.error.messageString"
                )

            self.apigw_client.update_stage(
                ApiId=api_id,
                StageName="prod",
                AccessLogSettings={
                    "DestinationArn": log_group_arn,
                    "Format": format_string,
                },
            )
        except ClientError as e:
            raise Exception(f"Failed to enable API logging: {e}")


def get_default_routes() -> List[Dict]:
    """Get default API routes for AgentCore Identity.

    Returns:
        List of route configurations
    """
    return [
        {
            "path": "/auth/token",
            "method": "POST",
            "lambda_function": "agentcore-auth-token",
        },
        {
            "path": "/auth/callback",
            "method": "GET",
            "lambda_function": "agentcore-auth-callback",
        },
        {
            "path": "/credentials/list",
            "method": "GET",
            "lambda_function": "agentcore-list-credentials",
        },
        {
            "path": "/credentials/{id}",
            "method": "GET",
            "lambda_function": "agentcore-get-credential",
        },
        {
            "path": "/credentials/{id}",
            "method": "DELETE",
            "lambda_function": "agentcore-revoke-credential",
        },
        {
            "path": "/oauth/flows",
            "method": "GET",
            "lambda_function": "agentcore-list-oauth-flows",
        },
        {
            "path": "/oauth/flows/{id}",
            "method": "GET",
            "lambda_function": "agentcore-get-oauth-flow",
        },
        {
            "path": "/audit/logs",
            "method": "GET",
            "lambda_function": "agentcore-get-audit-logs",
        },
        {
            "path": "/health",
            "method": "GET",
            "lambda_function": "agentcore-health-check",
        },
    ]
