#!/usr/bin/env python3
"""
Complete Bedrock AgentCore OAuth2 Platform Deployment via boto3.

Deploys:
1. Lambda functions (Identity, Gateway, Runtime handlers)
2. API Gateway with routes
3. Lambda permissions for API Gateway
"""

import boto3
import json
import zipfile
import io
import os
from pathlib import Path

# AWS Clients
lambda_client = boto3.client('lambda', region_name='eu-central-1')
apigw_client = boto3.client('apigatewayv2', region_name='eu-central-1')
iam_client = boto3.client('iam', region_name='eu-central-1')

# Constants
ACCOUNT_ID = '<AWS_ACCOUNT_ID>'
REGION = 'eu-central-1'
ROLE_ARN = f'arn:aws:iam::{ACCOUNT_ID}:role/bedrock-agentcore-oauth2-role'
CREDENTIALS_TABLE = 'bedrock-agentcore-oauth2-credentials'
OAUTH_FLOWS_TABLE = 'bedrock-agentcore-oauth2-oauth-flows'
KMS_KEY_ID = '739a8dc1-c9f4-4e95-934e-437daf7a6164'
GOOGLE_SECRET_ARN = f'arn:aws:secretsmanager:{REGION}:{ACCOUNT_ID}:secret:bedrock-agentcore-oauth2/google-oauth'


def create_lambda_zip(handler_code: str) -> bytes:
    """Create a ZIP file with Lambda handler code."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr('lambda_handler.py', handler_code)

    zip_buffer.seek(0)
    return zip_buffer.read()


def read_handler_file(filename: str) -> str:
    """Read handler code from file."""
    filepath = Path(f'src/deployment/lambdas/{filename}')
    if not filepath.exists():
        raise FileNotFoundError(f"Handler file not found: {filepath}")

    return filepath.read_text()


def deploy_lambda_function(function_name: str, handler_code: str, env_vars: dict):
    """Deploy a Lambda function."""
    print(f"\n📦 Deploying Lambda: {function_name}...")

    zip_content = create_lambda_zip(handler_code)

    try:
        # Try to update existing function
        response = lambda_client.update_function_code(
            FunctionName=function_name,
            ZipFile=zip_content
        )
        print(f"   ✅ Updated existing function: {function_name}")

        # Update environment variables
        lambda_client.update_function_configuration(
            FunctionName=function_name,
            Environment={'Variables': env_vars}
        )
        print(f"   ✅ Updated environment variables")

    except lambda_client.exceptions.ResourceNotFoundException:
        # Create new function
        response = lambda_client.create_function(
            FunctionName=function_name,
            Runtime='python3.11',
            Role=ROLE_ARN,
            Handler='lambda_handler.handler',
            Code={'ZipFile': zip_content},
            Environment={'Variables': env_vars},
            Timeout=60,
            MemorySize=512,
            Description=f'Bedrock AgentCore {function_name}',
            Tags={
                'Service': 'bedrock-agentcore',
                'Platform': 'oauth2'
            }
        )
        print(f"   ✅ Created new function: {function_name}")

    return response['FunctionArn']


def create_api_gateway() -> tuple[str, str]:
    """Create API Gateway HTTP API and return API ID and endpoint."""
    print("\n🌐 Creating API Gateway...")

    try:
        # Try to find existing API
        apis = apigw_client.get_apis()
        for api in apis.get('Items', []):
            if api['Name'] == 'bedrock-agentcore-api':
                api_id = api['ApiId']
                print(f"   ℹ️  Found existing API: {api_id}")
                return api_id, api['ApiEndpoint']

        # Create new API
        response = apigw_client.create_api(
            Name='bedrock-agentcore-api',
            ProtocolType='HTTP',
            Description='Bedrock AgentCore OAuth2 API',
            CorsConfiguration={
                'AllowOrigins': ['*'],
                'AllowMethods': ['GET', 'POST', 'PUT', 'DELETE'],
                'AllowHeaders': ['*'],
                'ExposeHeaders': ['*'],
                'MaxAge': 300
            },
            RouteSelectionExpression='$request.method $request.path'
        )

        api_id = response['ApiId']
        endpoint = response['ApiEndpoint']
        print(f"   ✅ Created API: {api_id}")
        print(f"   🔗 Endpoint: {endpoint}")

        return api_id, endpoint

    except Exception as e:
        print(f"   ❌ Error creating API: {e}")
        raise


def create_lambda_integration(api_id: str, lambda_arn: str, function_name: str) -> str:
    """Create Lambda integration for API Gateway."""
    print(f"\n🔗 Creating integration for {function_name}...")

    try:
        response = apigw_client.create_integration(
            ApiId=api_id,
            IntegrationType='AWS_PROXY',
            IntegrationUri=lambda_arn,
            PayloadFormatVersion='2.0'
        )

        integration_id = response['IntegrationId']
        print(f"   ✅ Integration created: {integration_id}")

        return integration_id

    except Exception as e:
        print(f"   ❌ Error: {e}")
        raise


def create_route(api_id: str, route_key: str, integration_id: str, function_name: str):
    """Create a route in API Gateway."""
    print(f"   📍 Creating route: {route_key}")

    try:
        response = apigw_client.create_route(
            ApiId=api_id,
            RouteKey=route_key,
            Target=f'integrations/{integration_id}'
        )

        print(f"      ✅ Route created")
        return response['RouteId']

    except Exception as e:
        print(f"      ❌ Error: {e}")
        # Continue - route might already exist
        return None


def add_lambda_permission(function_name: str, api_id: str):
    """Add permission for API Gateway to invoke Lambda."""
    print(f"\n🔐 Adding Lambda permission for {function_name}...")

    try:
        lambda_client.add_permission(
            FunctionName=function_name,
            StatementId=f'AllowAPIGateway-{api_id}',
            Action='lambda:InvokeFunction',
            Principal='apigateway.amazonaws.com',
            SourceArn=f'arn:aws:execute-api:{REGION}:{ACCOUNT_ID}:{api_id}/*'
        )
        print(f"   ✅ Permission added")

    except lambda_client.exceptions.ResourceConflictException:
        print(f"   ℹ️  Permission already exists")
    except Exception as e:
        print(f"   ❌ Error: {e}")


def create_api_stage(api_id: str):
    """Create API stage."""
    print(f"\n📋 Creating API stage...")

    try:
        response = apigw_client.create_stage(
            ApiId=api_id,
            StageName='prod',
            AutoDeploy=True,
            Description='Production stage for Bedrock AgentCore'
        )

        print(f"   ✅ Stage created: prod")
        return response['StageName']

    except Exception as e:
        print(f"   ⚠️  Stage error (might exist): {e}")
        return 'prod'


def main():
    """Main deployment function."""

    print("=" * 70)
    print("🚀 BEDROCK AGENTCORE OAUTH2 PLATFORM - COMPLETE DEPLOYMENT")
    print("=" * 70)
    print(f"\n📍 Region: {REGION}")
    print(f"📍 Account: {ACCOUNT_ID}")
    print(f"📍 Role: {ROLE_ARN}")

    # Environment variables for Lambda functions
    base_env = {
        'CREDENTIALS_TABLE': CREDENTIALS_TABLE,
        'OAUTH_FLOWS_TABLE': OAUTH_FLOWS_TABLE,
        'KMS_KEY_ID': KMS_KEY_ID,
        'GOOGLE_SECRET_ARN': GOOGLE_SECRET_ARN,
        'REGION': REGION
    }

    # ========== DEPLOY LAMBDA FUNCTIONS ==========
    print("\n" + "=" * 70)
    print("STEP 1: DEPLOY LAMBDA FUNCTIONS")
    print("=" * 70)

    try:
        # Read handler code
        identity_code = read_handler_file('identity_handler.py')
        gateway_code = read_handler_file('gateway_handler.py')
        runtime_code = read_handler_file('runtime_handler.py')

        # Deploy functions
        identity_arn = deploy_lambda_function(
            'bedrock-agentcore-identity-handler',
            identity_code,
            base_env
        )

        gateway_arn = deploy_lambda_function(
            'bedrock-agentcore-gateway-handler',
            gateway_code,
            base_env
        )

        runtime_arn = deploy_lambda_function(
            'bedrock-agentcore-runtime-handler',
            runtime_code,
            base_env
        )

    except Exception as e:
        print(f"\n❌ Failed to deploy Lambda functions: {e}")
        return False

    # ========== CREATE API GATEWAY ==========
    print("\n" + "=" * 70)
    print("STEP 2: CREATE API GATEWAY")
    print("=" * 70)

    try:
        api_id, endpoint = create_api_gateway()

    except Exception as e:
        print(f"\n❌ Failed to create API Gateway: {e}")
        return False

    # ========== CREATE INTEGRATIONS ==========
    print("\n" + "=" * 70)
    print("STEP 3: CREATE LAMBDA INTEGRATIONS")
    print("=" * 70)

    try:
        identity_integration = create_lambda_integration(
            api_id,
            identity_arn,
            'identity-handler'
        )

        gateway_integration = create_lambda_integration(
            api_id,
            gateway_arn,
            'gateway-handler'
        )

        runtime_integration = create_lambda_integration(
            api_id,
            runtime_arn,
            'runtime-handler'
        )

    except Exception as e:
        print(f"\n❌ Failed to create integrations: {e}")
        return False

    # ========== CREATE ROUTES ==========
    print("\n" + "=" * 70)
    print("STEP 4: CREATE API ROUTES")
    print("=" * 70)

    try:
        # Identity routes
        print("\n📍 Identity Service Routes:")
        create_route(api_id, 'GET /oauth/authorize', identity_integration, 'identity')
        create_route(api_id, 'POST /oauth/callback', identity_integration, 'identity')
        create_route(api_id, 'GET /oauth/status', identity_integration, 'identity')

        # Gateway routes
        print("\n📍 Gateway Service Routes:")
        create_route(api_id, 'POST /gateway/validate', gateway_integration, 'gateway')
        create_route(api_id, 'POST /gateway/invoke', gateway_integration, 'gateway')

        # Runtime routes
        print("\n📍 Runtime Service Routes:")
        create_route(api_id, 'GET /runtime/calendar/events', runtime_integration, 'runtime')
        create_route(api_id, 'POST /runtime/calendar/create', runtime_integration, 'runtime')

    except Exception as e:
        print(f"\n❌ Failed to create routes: {e}")
        return False

    # ========== ADD LAMBDA PERMISSIONS ==========
    print("\n" + "=" * 70)
    print("STEP 5: ADD LAMBDA PERMISSIONS")
    print("=" * 70)

    add_lambda_permission('bedrock-agentcore-identity-handler', api_id)
    add_lambda_permission('bedrock-agentcore-gateway-handler', api_id)
    add_lambda_permission('bedrock-agentcore-runtime-handler', api_id)

    # ========== CREATE STAGE ==========
    print("\n" + "=" * 70)
    print("STEP 6: CREATE API STAGE")
    print("=" * 70)

    stage = create_api_stage(api_id)

    # ========== SUCCESS ==========
    print("\n" + "=" * 70)
    print("✅ DEPLOYMENT COMPLETE")
    print("=" * 70)

    api_url = f"{endpoint}/prod"

    print(f"\n🎯 API Endpoint: {api_url}")
    print(f"\n📋 Lambda Functions Deployed:")
    print(f"   • bedrock-agentcore-identity-handler")
    print(f"   • bedrock-agentcore-gateway-handler")
    print(f"   • bedrock-agentcore-runtime-handler")

    print(f"\n🔗 Available Routes:")
    print(f"   GET  {api_url}/oauth/authorize")
    print(f"   POST {api_url}/oauth/callback")
    print(f"   GET  {api_url}/oauth/status")
    print(f"   POST {api_url}/gateway/validate")
    print(f"   POST {api_url}/gateway/invoke")
    print(f"   GET  {api_url}/runtime/calendar/events")
    print(f"   POST {api_url}/runtime/calendar/create")

    print(f"\n📌 Next Steps:")
    print(f"   1. Test OAuth2 flow: {api_url}/oauth/authorize?user_id=<EMAIL_PLACEHOLDER>")
    print(f"   2. Configure Google OAuth credentials in Secrets Manager")
    print(f"   3. Set up API authentication headers")
    print(f"   4. Test end-to-end flow")

    return True


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
