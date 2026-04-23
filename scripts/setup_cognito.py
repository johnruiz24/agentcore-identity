#!/usr/bin/env python3
"""
Setup AWS Cognito for AgentCore Identity in <AWS_PROFILE>

This script creates:
1. Cognito User Pool
2. Cognito App Client with OAuth2 configuration
3. Cognito Domain for hosted login
4. IAM role for Cognito to assume
5. Stores configuration in AWS Parameter Store
"""

import json
import sys
from typing import Optional

import boto3

# Configuration
AWS_REGION = "eu-central-1"
AWS_ACCOUNT_ID = "<AWS_ACCOUNT_ID>"
AWS_PROFILE = "<AWS_PROFILE>"

USER_POOL_NAME = "agentcore-identity"
APP_CLIENT_NAME = "agentcore-identity-app"
COGNITO_DOMAIN_NAME = "agentcore-identity"

OAUTH_SCOPES = [
    "email",
    "profile",
    "openid",
    "aws.cognito.signin.user.admin",
]

# Custom scopes will be added later via resource server configuration
CUSTOM_SCOPES = [
    "bedrock:agents:invoke",
    "bedrock:agents:read",
    "bedrock:agents:create",
    "mcp:resources:read",
    "mcp:resources:create",
    "identity:read",
    "identity:write",
]

CALLBACK_URLS = [
    "http://localhost:8000/auth/callback",
    "http://localhost:3000/auth/callback",
]

ALLOWED_LOGOUT_URLS = [
    "http://localhost:8000/",
    "http://localhost:3000/",
]


def setup_session() -> boto3.Session:
    """Setup AWS session with <AWS_PROFILE> profile"""
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    sts = session.client("sts")

    # Verify identity
    identity = sts.get_caller_identity()
    print(f"✓ Connected as: {identity['Arn']}")
    print(f"✓ Account: {identity['Account']}")
    print(f"✓ Region: {AWS_REGION}")

    return session


def create_user_pool(cognito_client) -> str:
    """Create Cognito User Pool"""
    print("\n📝 Creating Cognito User Pool...")

    try:
        response = cognito_client.create_user_pool(
            PoolName=USER_POOL_NAME,
            Policies={
                "PasswordPolicy": {
                    "MinimumLength": 12,
                    "RequireUppercase": True,
                    "RequireLowercase": True,
                    "RequireNumbers": True,
                    "RequireSymbols": False,
                }
            },
            Schema=[
                {
                    "Name": "email",
                    "AttributeDataType": "String",
                    "Mutable": True,
                    "Required": True,
                },
                {
                    "Name": "name",
                    "AttributeDataType": "String",
                    "Mutable": True,
                    "Required": False,
                },
                {
                    "Name": "phone_number",
                    "AttributeDataType": "String",
                    "Mutable": True,
                    "Required": False,
                },
                {
                    "Name": "department",
                    "AttributeDataType": "String",
                    "Mutable": True,
                    "Required": False,
                },
            ],
            AutoVerifiedAttributes=["email"],
            MfaConfiguration="OFF",
            UserAttributeUpdateSettings={"AttributesRequireVerificationBeforeUpdate": []},
            UserPoolTags={
                "Environment": "sandbox",
                "Project": "agentcore-identity",
                "ManagedBy": "CloudFormation",
            },
        )

        user_pool_id = response["UserPool"]["Id"]
        print(f"✓ User Pool created: {user_pool_id}")
        return user_pool_id

    except cognito_client.exceptions.InvalidParameterException as e:
        if "already exists" in str(e):
            print(f"⚠ User Pool '{USER_POOL_NAME}' already exists")
            # List existing pools to find ID
            pools = cognito_client.list_user_pools(MaxResults=10)
            for pool in pools["UserPools"]:
                if pool["Name"] == USER_POOL_NAME:
                    user_pool_id = pool["Id"]
                    print(f"✓ Using existing User Pool: {user_pool_id}")
                    return user_pool_id
        raise


def create_app_client(cognito_client, user_pool_id: str) -> tuple[str, str]:
    """Create Cognito App Client with OAuth2 configuration"""
    print("\n🔐 Creating Cognito App Client...")

    try:
        response = cognito_client.create_user_pool_client(
            UserPoolId=user_pool_id,
            ClientName=APP_CLIENT_NAME,
            GenerateSecret=True,
            RefreshTokenValidity=7,  # days
            AccessTokenValidity=1,  # hour
            IdTokenValidity=1,  # hour
            TokenValidityUnits={
                "AccessToken": "hours",
                "IdToken": "hours",
                "RefreshToken": "days",
            },
            ReadAttributes=["email", "phone_number", "name", "custom:department"],
            AllowedOAuthFlows=["code", "implicit"],
            AllowedOAuthScopes=OAUTH_SCOPES + [f"agentcore/{scope.replace(':', '_')}" for scope in CUSTOM_SCOPES],
            AllowedOAuthFlowsUserPoolClient=True,
            CallbackURLs=CALLBACK_URLS,
            LogoutURLs=ALLOWED_LOGOUT_URLS,
            ExplicitAuthFlows=[
                "ALLOW_USER_PASSWORD_AUTH",
                "ALLOW_USER_SRP_AUTH",
                "ALLOW_REFRESH_TOKEN_AUTH",
            ],
            SupportedIdentityProviders=["COGNITO"],
            PreventUserExistenceErrors="ENABLED",
        )

        client_id = response["UserPoolClient"]["ClientId"]
        client_secret = response["UserPoolClient"]["ClientSecret"]
        print(f"✓ App Client created: {client_id}")
        print(f"✓ Client Secret stored (keep it secret!)")

        return client_id, client_secret

    except Exception as e:
        error_msg = str(e)
        if "already exists" in error_msg or "InvalidParameterException" in error_msg:
            print(f"⚠ App Client might already exist: {e}")
            # List existing clients
            try:
                clients = cognito_client.list_user_pool_clients(
                    UserPoolId=user_pool_id,
                    MaxResults=10,
                )
                for client in clients["UserPoolClients"]:
                    if client["ClientName"] == APP_CLIENT_NAME:
                        client_id = client["ClientId"]
                        print(f"✓ Using existing App Client: {client_id}")
                        # Need to get the secret - it's only returned at creation time
                        # For existing clients, we'll need to retrieve it from Parameter Store
                        return client_id, "RETRIEVE_FROM_PARAMETER_STORE"
            except Exception as list_error:
                print(f"⚠ Could not list clients: {list_error}")
        raise


def create_resource_server_and_scopes(cognito_client, user_pool_id: str) -> None:
    """Create resource server and custom OAuth2 scopes"""
    print("\n🔐 Creating Resource Server and Custom Scopes...")

    try:
        resource_server_identifier = "agentcore"

        response = cognito_client.create_resource_server(
            UserPoolId=user_pool_id,
            Identifier=resource_server_identifier,
            Name="AgentCore Resource Server",
            Scopes=[
                {
                    "ScopeName": scope.replace(":", "_"),  # Replace colons with underscores
                    "ScopeDescription": f"{scope} permissions",
                }
                for scope in CUSTOM_SCOPES
            ],
        )

        print(f"✓ Resource server created: {resource_server_identifier}")
        for scope in CUSTOM_SCOPES:
            print(f"  - {scope}")

    except Exception as e:
        error_msg = str(e)
        if "already exists" in error_msg or "ResourceInUseException" in error_msg:
            print(f"⚠ Resource server already exists")
        else:
            print(f"⚠ Could not create resource server: {e}")


def create_cognito_domain(cognito_client, user_pool_id: str) -> str:
    """Create Cognito Domain for hosted login"""
    print("\n🌐 Creating Cognito Domain...")

    try:
        response = cognito_client.create_user_pool_domain(
            Domain=COGNITO_DOMAIN_NAME,
            UserPoolId=user_pool_id,
        )

        # Response might have different structure
        if "DomainDescription" in response:
            domain = response["DomainDescription"].get("Domain", COGNITO_DOMAIN_NAME)
        else:
            domain = COGNITO_DOMAIN_NAME

        print(f"✓ Cognito Domain created: {domain}")
        print(f"✓ Hosted Login URL: https://{domain}.auth.{AWS_REGION}.amazoncognito.com")

        return domain

    except Exception as e:
        error_msg = str(e)
        if "already exists" in error_msg or "InvalidParameterException" in error_msg:
            print(f"⚠ Domain '{COGNITO_DOMAIN_NAME}' already exists")
            return COGNITO_DOMAIN_NAME
        else:
            raise


def store_config_in_parameter_store(
    ssm_client,
    user_pool_id: str,
    client_id: str,
    client_secret: str,
    domain: str,
) -> None:
    """Store configuration in AWS Parameter Store"""
    print("\n💾 Storing configuration in Parameter Store...")

    parameters = {
        "/agentcore-identity/cognito/user-pool-id": {
            "Value": user_pool_id,
            "Type": "String",
            "Description": "Cognito User Pool ID",
        },
        "/agentcore-identity/cognito/client-id": {
            "Value": client_id,
            "Type": "String",
            "Description": "Cognito App Client ID",
        },
        "/agentcore-identity/cognito/client-secret": {
            "Value": client_secret,
            "Type": "SecureString",
            "Description": "Cognito App Client Secret",
        },
        "/agentcore-identity/cognito/domain": {
            "Value": domain,
            "Type": "String",
            "Description": "Cognito Domain",
        },
        "/agentcore-identity/cognito/region": {
            "Value": AWS_REGION,
            "Type": "String",
            "Description": "Cognito Region",
        },
        "/agentcore-identity/oauth2/redirect-uri": {
            "Value": CALLBACK_URLS[0],
            "Type": "String",
            "Description": "OAuth2 Redirect URI",
        },
    }

    for param_name, config in parameters.items():
        try:
            # First try to put parameter without tags
            try:
                ssm_client.put_parameter(
                    Name=param_name,
                    Value=config["Value"],
                    Type=config["Type"],
                    Description=config["Description"],
                    Overwrite=True,
                )
            except Exception as first_error:
                # If it fails, try without overwrite (for new parameters)
                if "already exists" not in str(first_error):
                    ssm_client.put_parameter(
                        Name=param_name,
                        Value=config["Value"],
                        Type=config["Type"],
                        Description=config["Description"],
                    )

            # Tag the parameter separately
            try:
                ssm_client.add_tags_to_resource(
                    ResourceType="Parameter",
                    ResourceId=param_name,
                    Tags=[
                        {"Key": "Environment", "Value": "sandbox"},
                        {"Key": "Project", "Value": "agentcore-identity"},
                    ],
                )
            except Exception as tag_error:
                print(f"⚠ Could not tag parameter {param_name}: {tag_error}")

            print(f"✓ Parameter stored: {param_name}")

        except Exception as e:
            print(f"✗ Error storing parameter {param_name}: {e}")
            raise


def create_iam_role_for_bedrock() -> str:
    """Create IAM role for Bedrock AgentCore Runtime to assume Cognito identity"""
    print("\n🔑 Creating IAM Role for Bedrock AgentCore...")

    iam_client = boto3.client("iam")
    role_name = "agentcore-identity-bedrock-role"

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": [
                        "bedrock-agentcore.amazonaws.com",
                        "lambda.amazonaws.com",
                        "ecs-tasks.amazonaws.com",
                    ]
                },
                "Action": "sts:AssumeRole",
            }
        ],
    }

    try:
        response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Role for Bedrock AgentCore to access identity services",
            Tags=[
                {"Key": "Environment", "Value": "sandbox"},
                {"Key": "Project", "Value": "agentcore-identity"},
            ],
        )

        role_arn = response["Role"]["Arn"]
        print(f"✓ IAM Role created: {role_arn}")

        # Attach inline policy for Cognito
        cognito_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "cognito-idp:Admin*",
                        "cognito-idp:GetUser",
                        "cognito-idp:RespondToAuthChallenge",
                        "cognito-idp:InitiateAuth",
                    ],
                    "Resource": f"arn:aws:cognito-idp:{AWS_REGION}:{AWS_ACCOUNT_ID}:userpool/*",
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "sts:AssumeRoleWithWebIdentity",
                    ],
                    "Resource": "*",
                },
            ],
        }

        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName="cognito-bedrock-policy",
            PolicyDocument=json.dumps(cognito_policy),
        )
        print(f"✓ IAM policy attached to role")

        return role_arn

    except iam_client.exceptions.EntityAlreadyExistsException:
        print(f"⚠ IAM Role '{role_name}' already exists")
        response = iam_client.get_role(RoleName=role_name)
        role_arn = response["Role"]["Arn"]
        print(f"✓ Using existing role: {role_arn}")
        return role_arn


def create_dynamodb_tables(dynamodb_client) -> None:
    """Create DynamoDB tables for sessions and users"""
    print("\n📊 Creating DynamoDB Tables...")

    tables = [
        {
            "TableName": "agentcore-identity-sessions",
            "KeySchema": [
                {"AttributeName": "session_id", "KeyType": "HASH"},
                {"AttributeName": "user_id", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "session_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "N"},
            ],
            "BillingMode": "PAY_PER_REQUEST",
            "TTL": {"AttributeName": "expires_at", "Enabled": True},
            "GlobalSecondaryIndexes": [
                {
                    "IndexName": "user_id-created_at-index",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        },
        {
            "TableName": "agentcore-identity-users",
            "KeySchema": [
                {"AttributeName": "user_id", "KeyType": "HASH"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "email", "AttributeType": "S"},
            ],
            "BillingMode": "PAY_PER_REQUEST",
            "GlobalSecondaryIndexes": [
                {
                    "IndexName": "email-index",
                    "KeySchema": [
                        {"AttributeName": "email", "KeyType": "HASH"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        },
    ]

    for table_config in tables:
        try:
            table_name = table_config["TableName"]

            # Remove TTL from creation
            ttl_spec = table_config.pop("TTL", None)

            response = dynamodb_client.create_table(
                **table_config,
                Tags=[
                    {"Key": "Environment", "Value": "sandbox"},
                    {"Key": "Project", "Value": "agentcore-identity"},
                ],
            )

            print(f"✓ DynamoDB Table created: {table_name}")

            # Enable TTL if specified
            if ttl_spec:
                try:
                    dynamodb_client.update_time_to_live(
                        TableName=table_name,
                        TimeToLiveSpecification=ttl_spec,
                    )
                    print(f"✓ TTL enabled on {table_name}")
                except Exception as e:
                    print(f"⚠ Could not enable TTL on {table_name}: {e}")

        except dynamodb_client.exceptions.ResourceInUseException:
            print(f"⚠ Table '{table_config['TableName']}' already exists")
        except Exception as e:
            print(f"✗ Error creating table {table_config['TableName']}: {e}")


def main() -> int:
    """Main setup function"""
    print("=" * 70)
    print("🚀 AgentCore Identity - AWS Cognito Setup")
    print("=" * 70)

    try:
        # Setup AWS session
        session = setup_session()

        # Create clients
        cognito_client = session.client("cognito-idp")
        ssm_client = session.client("ssm")
        dynamodb_client = session.client("dynamodb")

        # Create Cognito User Pool
        user_pool_id = create_user_pool(cognito_client)

        # Create Resource Server and Custom Scopes
        create_resource_server_and_scopes(cognito_client, user_pool_id)

        # Create App Client
        client_id, client_secret = create_app_client(cognito_client, user_pool_id)

        # Create Cognito Domain
        domain = create_cognito_domain(cognito_client, user_pool_id)

        # Create IAM Role
        role_arn = create_iam_role_for_bedrock()

        # Create DynamoDB Tables
        create_dynamodb_tables(dynamodb_client)

        # Store configuration
        store_config_in_parameter_store(
            ssm_client,
            user_pool_id,
            client_id,
            client_secret,
            domain,
        )

        # Print summary
        print("\n" + "=" * 70)
        print("✅ Setup completed successfully!")
        print("=" * 70)
        print("\n📋 Configuration Summary:")
        print(f"  User Pool ID: {user_pool_id}")
        print(f"  Client ID: {client_id}")
        print(f"  Client Secret: [STORED IN PARAMETER STORE]")
        print(f"  Domain: {domain}")
        print(f"  Hosted Login URL: https://{domain}.auth.{AWS_REGION}.amazoncognito.com")
        print(f"  Role ARN: {role_arn}")
        print("\n📍 Callback URLs configured:")
        for url in CALLBACK_URLS:
            print(f"    - {url}")
        print("\n📝 OAuth2 Scopes configured:")
        for scope in OAUTH_SCOPES:
            print(f"    - {scope}")
        print("\n✨ All configuration stored in AWS Parameter Store at:")
        print("    /agentcore-identity/cognito/*")
        print("\n" + "=" * 70)

        return 0

    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
