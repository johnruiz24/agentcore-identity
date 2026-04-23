#!/usr/bin/env python3
"""
Deploy Bedrock AgentCore Identity CloudFormation Stack

This script deploys the complete infrastructure for AgentCore Identity including:
- AWS Cognito (OAuth2 Identity Provider)
- DynamoDB (Session & User Storage)
- IAM Roles & Policies
- CloudWatch Logging
"""

import json
import sys
import time
import logging
from typing import Optional, Dict, Any

import boto3
import click

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class CloudFormationDeployer:
    """Deploy AgentCore Identity CloudFormation Stack"""

    def __init__(
        self,
        region: str = "eu-central-1",
        profile: str = "<AWS_PROFILE>",
    ):
        """Initialize CloudFormation deployer"""
        session = boto3.Session(profile_name=profile, region_name=region)
        self.cf_client = session.client("cloudformation")
        self.ssm_client = session.client("ssm")
        self.sts_client = session.client("sts")
        self.region = region
        self.profile = profile

        # Get account ID
        identity = self.sts_client.get_caller_identity()
        self.account_id = identity["Account"]
        self.arn = identity["Arn"]

        logger.info(f"Connected to AWS Account: {self.account_id}")
        logger.info(f"Region: {region}")
        logger.info(f"ARN: {self.arn}")

    def validate_template(self, template_path: str) -> bool:
        """Validate CloudFormation template"""
        logger.info(f"📋 Validating template: {template_path}")

        try:
            with open(template_path, "r") as f:
                template = f.read()

            response = self.cf_client.validate_template(TemplateBody=template)
            logger.info(f"✅ Template is valid")
            logger.info(f"   Parameters: {len(response.get('Parameters', []))}")
            logger.info(f"   Description: {response.get('Description', 'N/A')}")

            return True

        except Exception as e:
            logger.error(f"❌ Template validation failed: {e}")
            return False

    def create_or_update_stack(
        self,
        stack_name: str,
        template_path: str,
        parameters: Dict[str, str],
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create or update CloudFormation stack"""

        logger.info(f"🚀 Deploying stack: {stack_name}")

        # Read template
        with open(template_path, "r") as f:
            template = f.read()

        # Convert parameters to CloudFormation format
        cf_parameters = [
            {"ParameterKey": k, "ParameterValue": v}
            for k, v in parameters.items()
        ]

        # Convert tags
        cf_tags = [
            {"Key": k, "Value": v}
            for k, v in (tags or {}).items()
        ]

        try:
            # Check if stack exists
            existing_stacks = self.cf_client.list_stacks(
                StackStatusFilter=[
                    "CREATE_COMPLETE",
                    "UPDATE_COMPLETE",
                    "UPDATE_ROLLBACK_COMPLETE",
                ]
            )

            stack_exists = any(
                s["StackName"] == stack_name
                for s in existing_stacks.get("StackSummaries", [])
            )

            if stack_exists:
                logger.info(f"📝 Stack exists, updating...")
                response = self.cf_client.update_stack(
                    StackName=stack_name,
                    TemplateBody=template,
                    Parameters=cf_parameters,
                    Capabilities=["CAPABILITY_NAMED_IAM"],
                    Tags=cf_tags,
                )
                operation = "UPDATE"
                stack_id = response["StackId"]

            else:
                logger.info(f"📝 Creating new stack...")
                response = self.cf_client.create_stack(
                    StackName=stack_name,
                    TemplateBody=template,
                    Parameters=cf_parameters,
                    Capabilities=["CAPABILITY_NAMED_IAM"],
                    Tags=cf_tags,
                )
                operation = "CREATE"
                stack_id = response["StackId"]

            logger.info(f"✅ Stack {operation} initiated: {stack_id}")

            # Wait for stack operation to complete
            return self._wait_for_stack(stack_name, operation)

        except Exception as e:
            logger.error(f"❌ Stack operation failed: {e}")
            raise

    def _wait_for_stack(self, stack_name: str, operation: str) -> str:
        """Wait for stack operation to complete"""

        if operation == "CREATE":
            waiter = self.cf_client.get_waiter("stack_create_complete")
            success_status = "CREATE_COMPLETE"
        else:
            waiter = self.cf_client.get_waiter("stack_update_complete")
            success_status = "UPDATE_COMPLETE"

        logger.info(f"⏳ Waiting for stack {operation}...")

        try:
            waiter.wait(StackName=stack_name)
            logger.info(f"✅ Stack {operation} completed successfully!")

            # Get stack details
            response = self.cf_client.describe_stacks(StackName=stack_name)
            stack = response["Stacks"][0]

            logger.info(f"   Stack ID: {stack['StackId']}")
            logger.info(f"   Status: {stack['StackStatus']}")

            return stack["StackId"]

        except Exception as e:
            logger.error(f"❌ Stack {operation} failed: {e}")

            # Get events for debugging
            events = self.cf_client.describe_stack_events(StackName=stack_name)
            logger.error("\n📋 Recent Stack Events:")
            for event in events.get("StackEvents", [])[:10]:
                status = event.get("ResourceStatus", "")
                reason = event.get("ResourceStatusReason", "")
                resource = event.get("LogicalResourceId", "")
                logger.error(f"   {resource}: {status} - {reason}")

            raise

    def get_stack_outputs(self, stack_name: str) -> Dict[str, str]:
        """Get CloudFormation stack outputs"""

        logger.info(f"📤 Retrieving stack outputs: {stack_name}")

        try:
            response = self.cf_client.describe_stacks(StackName=stack_name)
            stack = response["Stacks"][0]

            outputs = {}
            for output in stack.get("Outputs", []):
                key = output["OutputKey"]
                value = output["OutputValue"]
                outputs[key] = value
                logger.info(f"   {key}: {value}")

            return outputs

        except Exception as e:
            logger.error(f"❌ Failed to retrieve outputs: {e}")
            return {}

    def store_outputs_in_parameter_store(
        self,
        stack_name: str,
        outputs: Dict[str, str],
        environment: str,
    ) -> None:
        """Store stack outputs in AWS Parameter Store"""

        logger.info(f"💾 Storing outputs in Parameter Store")

        for key, value in outputs.items():
            param_name = f"/agentcore-identity/{environment}/outputs/{key}"

            try:
                self.ssm_client.put_parameter(
                    Name=param_name,
                    Value=value,
                    Type="String",
                    Overwrite=True,
                    Description=f"CloudFormation Output: {key}",
                    Tags=[
                        {"Key": "Stack", "Value": stack_name},
                        {"Key": "Environment", "Value": environment},
                    ],
                )
                logger.info(f"   ✅ {param_name}")

            except Exception as e:
                logger.error(f"   ❌ Failed to store {param_name}: {e}")

    def delete_stack(self, stack_name: str) -> None:
        """Delete CloudFormation stack"""

        logger.warning(f"🗑️  Deleting stack: {stack_name}")

        try:
            self.cf_client.delete_stack(StackName=stack_name)

            waiter = self.cf_client.get_waiter("stack_delete_complete")
            logger.info(f"⏳ Waiting for stack deletion...")
            waiter.wait(StackName=stack_name)

            logger.info(f"✅ Stack deleted successfully!")

        except Exception as e:
            logger.error(f"❌ Stack deletion failed: {e}")
            raise

    def get_stack_status(self, stack_name: str) -> Optional[str]:
        """Get CloudFormation stack status"""

        try:
            response = self.cf_client.describe_stacks(StackName=stack_name)
            stack = response["Stacks"][0]
            return stack.get("StackStatus")

        except Exception:
            return None


@click.command()
@click.option(
    "--action",
    type=click.Choice(["deploy", "delete", "status", "outputs"]),
    default="deploy",
    help="Action to perform",
)
@click.option(
    "--stack-name",
    default="agentcore-identity-stack",
    help="CloudFormation stack name",
)
@click.option(
    "--template",
    default="deployment/cloudformation-stack.yaml",
    help="Path to CloudFormation template",
)
@click.option(
    "--environment",
    default="sandbox",
    help="Environment name (dev, sandbox, prod)",
)
@click.option(
    "--region",
    default="eu-central-1",
    help="AWS region",
)
@click.option(
    "--profile",
    default="<AWS_PROFILE>",
    help="AWS profile name",
)
@click.option(
    "--callback-url",
    default="http://localhost:8000/auth/callback",
    help="OAuth2 callback URL",
)
@click.option(
    "--domain",
    default="agentcore-identity",
    help="Cognito domain prefix",
)
def main(
    action: str,
    stack_name: str,
    template: str,
    environment: str,
    region: str,
    profile: str,
    callback_url: str,
    domain: str,
):
    """Deploy Bedrock AgentCore Identity CloudFormation Stack"""

    deployer = CloudFormationDeployer(region=region, profile=profile)

    try:
        if action == "deploy":
            # Validate template
            if not deployer.validate_template(template):
                sys.exit(1)

            # Deploy stack
            parameters = {
                "EnvironmentName": environment,
                "AppName": "agentcore-identity",
                "Domain": domain,
                "CallbackURL": callback_url,
                "LogoutURL": callback_url.replace("/callback", "/logout"),
            }

            tags = {
                "Environment": environment,
                "Application": "agentcore-identity",
                "ManagedBy": "CloudFormation",
            }

            deployer.create_or_update_stack(
                stack_name=stack_name,
                template_path=template,
                parameters=parameters,
                tags=tags,
            )

            # Get outputs
            outputs = deployer.get_stack_outputs(stack_name)

            # Store in Parameter Store
            deployer.store_outputs_in_parameter_store(
                stack_name=stack_name,
                outputs=outputs,
                environment=environment,
            )

            logger.info("\n" + "=" * 70)
            logger.info("✅ DEPLOYMENT COMPLETE!")
            logger.info("=" * 70)
            logger.info("\n📋 Configuration Summary:")
            logger.info(f"  Stack Name: {stack_name}")
            logger.info(f"  Environment: {environment}")
            logger.info(f"  Region: {region}")
            logger.info(f"  Account ID: {deployer.account_id}")
            logger.info(f"\n🔐 OAuth2 Configuration:")
            logger.info(f"  Cognito Domain: {outputs.get('CognitoDomainUrl', 'N/A')}")
            logger.info(f"  User Pool ID: {outputs.get('CognitoUserPoolId', 'N/A')}")
            logger.info(f"  App Client ID: {outputs.get('CognitoAppClientId', 'N/A')}")
            logger.info(f"\n📊 Infrastructure:")
            logger.info(f"  Sessions Table: {outputs.get('SessionsTableName', 'N/A')}")
            logger.info(f"  Users Table: {outputs.get('UsersTableName', 'N/A')}")
            logger.info(f"  Bedrock Role: {outputs.get('BedrockAgentRoleArn', 'N/A')}")
            logger.info("\n" + "=" * 70)

        elif action == "delete":
            click.confirm(
                f"Are you sure you want to delete stack '{stack_name}'?",
                abort=True,
            )
            deployer.delete_stack(stack_name)

        elif action == "status":
            status = deployer.get_stack_status(stack_name)
            if status:
                logger.info(f"Stack '{stack_name}' status: {status}")
            else:
                logger.warning(f"Stack '{stack_name}' not found")

        elif action == "outputs":
            deployer.get_stack_outputs(stack_name)

    except Exception as e:
        logger.error(f"❌ Deployment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
