"""AWS IAM role and policy management for AgentCore Identity."""

import json
from typing import Dict, List

import boto3
from botocore.exceptions import ClientError


class IAMManager:
    """Manages IAM roles and policies for AgentCore Identity Service."""

    def __init__(self, region: str = "eu-central-1"):
        """Initialize IAM manager.

        Args:
            region: AWS region (for reference, IAM is global)
        """
        self.region = region
        self.iam_client = boto3.client("iam")

    def create_service_role(
        self,
        role_name: str,
        service: str = "lambda.amazonaws.com",
        policies: List[str] = None,
    ) -> str:
        """Create IAM role for service.

        Args:
            role_name: Name for the role
            service: AWS service principal (default: lambda.amazonaws.com)
            policies: List of policy ARNs to attach

        Returns:
            Role ARN

        Raises:
            Exception: If role creation fails
        """
        assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": service},
                    "Action": "sts:AssumeRole",
                }
            ],
        }

        try:
            response = self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(assume_role_policy),
                Description=f"Role for {role_name} in AgentCore Identity Service",
                Tags=[
                    {"Key": "Service", "Value": "agentcore-identity"},
                    {"Key": "Component", "Value": "iam"},
                ],
            )

            role_arn = response["Role"]["Arn"]

            # Attach policies if provided
            if policies:
                for policy_arn in policies:
                    self.iam_client.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)

            return role_arn

        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityAlreadyExists":
                # Role already exists, just return its ARN
                role = self.iam_client.get_role(RoleName=role_name)
                return role["Role"]["Arn"]
            raise Exception(f"Failed to create IAM role: {e}")

    def create_inline_policy(
        self,
        role_name: str,
        policy_name: str,
        policy_document: Dict,
    ) -> None:
        """Create inline policy for role.

        Args:
            role_name: Role to attach policy to
            policy_name: Name for the policy
            policy_document: Policy document (dict will be JSON-encoded)

        Raises:
            Exception: If policy creation fails
        """
        try:
            self.iam_client.put_role_policy(
                RoleName=role_name,
                PolicyName=policy_name,
                PolicyDocument=json.dumps(policy_document),
            )
        except ClientError as e:
            raise Exception(f"Failed to create inline policy: {e}")

    def create_dynamodb_policy(self) -> Dict:
        """Create policy for DynamoDB access.

        Returns:
            Policy document
        """
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:GetItem",
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                        "dynamodb:Query",
                        "dynamodb:Scan",
                    ],
                    "Resource": [
                        "arn:aws:dynamodb:*:*:table/agentcore-identity-*",
                        "arn:aws:dynamodb:*:*:table/agentcore-identity-*/index/*",
                    ],
                }
            ],
        }

    def create_kms_policy(self) -> Dict:
        """Create policy for KMS access.

        Returns:
            Policy document
        """
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "kms:Encrypt",
                        "kms:Decrypt",
                        "kms:DescribeKey",
                    ],
                    "Resource": "arn:aws:kms:*:*:key/*",
                    "Condition": {
                        "StringLike": {
                            "aws:userid": "*:agentcore-*"
                        }
                    },
                }
            ],
        }

    def create_cloudwatch_policy(self) -> Dict:
        """Create policy for CloudWatch logging.

        Returns:
            Policy document
        """
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                    ],
                    "Resource": "arn:aws:logs:*:*:log-group:/agentcore/*",
                }
            ],
        }

    def create_lambda_policy(self) -> Dict:
        """Create policy for Lambda invocation.

        Returns:
            Policy document
        """
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "lambda:InvokeFunction",
                    ],
                    "Resource": "arn:aws:lambda:*:*:function:agentcore-*",
                }
            ],
        }

    def create_full_policy(self) -> Dict:
        """Create combined policy with all required permissions.

        Returns:
            Full policy document
        """
        return {
            "Version": "2012-10-17",
            "Statement": [
                # DynamoDB permissions
                {
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:GetItem",
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                        "dynamodb:Query",
                        "dynamodb:Scan",
                    ],
                    "Resource": [
                        "arn:aws:dynamodb:*:*:table/agentcore-identity-*",
                        "arn:aws:dynamodb:*:*:table/agentcore-identity-*/index/*",
                    ],
                },
                # KMS permissions
                {
                    "Effect": "Allow",
                    "Action": [
                        "kms:Encrypt",
                        "kms:Decrypt",
                        "kms:DescribeKey",
                    ],
                    "Resource": "arn:aws:kms:*:*:key/*",
                },
                # CloudWatch permissions
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                    ],
                    "Resource": "arn:aws:logs:*:*:log-group:/agentcore/*",
                },
                # Lambda permissions
                {
                    "Effect": "Allow",
                    "Action": [
                        "lambda:InvokeFunction",
                    ],
                    "Resource": "arn:aws:lambda:*:*:function:agentcore-*",
                },
                # Secrets Manager (for OAuth secrets)
                {
                    "Effect": "Allow",
                    "Action": [
                        "secretsmanager:GetSecretValue",
                    ],
                    "Resource": "arn:aws:secretsmanager:*:*:secret:agentcore/*",
                },
            ],
        }

    def federate_role(
        self,
        role_name: str,
        saml_provider_arn: str,
        session_duration: int = 3600,
    ) -> str:
        """Create federated role for SAML/SSO.

        Args:
            role_name: Name for federated role
            saml_provider_arn: ARN of SAML provider
            session_duration: Session duration in seconds

        Returns:
            Role ARN

        Raises:
            Exception: If role creation fails
        """
        assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Federated": saml_provider_arn,
                    },
                    "Action": "sts:AssumeRoleWithSAML",
                    "Condition": {
                        "StringEquals": {
                            "SAML:aud": "https://signin.aws.amazon.com/saml",
                        }
                    },
                }
            ],
        }

        try:
            response = self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(assume_role_policy),
                MaxSessionDuration=session_duration,
                Description="Federated role for AgentCore Identity SSO",
            )

            return response["Role"]["Arn"]

        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityAlreadyExists":
                role = self.iam_client.get_role(RoleName=role_name)
                return role["Role"]["Arn"]
            raise Exception(f"Failed to create federated role: {e}")
