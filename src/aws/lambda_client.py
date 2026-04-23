"""AWS Lambda integration for tool execution."""

import json
import logging
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError


logger = logging.getLogger(__name__)


class LambdaClient:
    """Manages Lambda function invocations for AgentCore Identity tools."""

    def __init__(self, region: str = "eu-central-1"):
        """Initialize Lambda client.

        Args:
            region: AWS region
        """
        self.region = region
        self.lambda_client = boto3.client("lambda", region_name=region)

    def invoke_function(
        self,
        function_name: str,
        payload: Dict[str, Any],
        async_invocation: bool = False,
    ) -> Dict[str, Any]:
        """Invoke Lambda function.

        Args:
            function_name: Name or ARN of Lambda function
            payload: Payload to send to function
            async_invocation: Whether to invoke asynchronously (default: synchronous)

        Returns:
            Response from Lambda function

        Raises:
            Exception: If invocation fails
        """
        try:
            invocation_type = "Event" if async_invocation else "RequestResponse"

            response = self.lambda_client.invoke(
                FunctionName=function_name,
                InvocationType=invocation_type,
                Payload=json.dumps(payload),
            )

            if async_invocation:
                # Async invocation - just return status
                return {
                    "StatusCode": response["StatusCode"],
                    "RequestId": response.get("LogResult", ""),
                }

            # Synchronous invocation - parse response
            if response["StatusCode"] == 200:
                response_payload = json.loads(response["Payload"].read())
                return response_payload
            else:
                raise Exception(f"Lambda invocation failed with status {response['StatusCode']}")

        except ClientError as e:
            logger.error(f"Failed to invoke Lambda function {function_name}: {e}")
            raise Exception(f"Lambda invocation error: {e}")

    def invoke_tool(
        self,
        tool_name: str,
        session_id: str,
        user_id: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Invoke a tool via Lambda.

        Args:
            tool_name: Name of the tool to invoke
            session_id: Session ID for authorization
            user_id: User ID performing action
            arguments: Tool arguments

        Returns:
            Tool result

        Raises:
            Exception: If tool invocation fails
        """
        function_name = f"agentcore-tool-{tool_name}"

        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "tool": tool_name,
            "arguments": arguments,
        }

        return self.invoke_function(function_name, payload)

    def create_function(
        self,
        function_name: str,
        runtime: str,
        handler: str,
        role_arn: str,
        code_location: str,
        environment_variables: Optional[Dict[str, str]] = None,
        timeout: int = 60,
        memory_size: int = 256,
    ) -> str:
        """Create Lambda function.

        Args:
            function_name: Name for the function
            runtime: Lambda runtime (e.g., 'python3.11')
            handler: Handler path (e.g., 'index.handler')
            role_arn: IAM role ARN for Lambda execution
            code_location: S3 location of code (bucket/key)
            environment_variables: Environment variables to set
            timeout: Function timeout in seconds
            memory_size: Memory allocation in MB

        Returns:
            Function ARN

        Raises:
            Exception: If function creation fails
        """
        try:
            bucket, key = code_location.split("/", 1)

            response = self.lambda_client.create_function(
                FunctionName=function_name,
                Runtime=runtime,
                Role=role_arn,
                Handler=handler,
                Code={"S3Bucket": bucket, "S3Key": key},
                Environment={"Variables": environment_variables or {}},
                Timeout=timeout,
                MemorySize=memory_size,
                Tags={
                    "Service": "agentcore-identity",
                    "Component": "tools",
                },
            )

            return response["FunctionArn"]

        except ClientError as e:
            logger.error(f"Failed to create Lambda function {function_name}: {e}")
            raise Exception(f"Lambda creation error: {e}")

    def update_function_code(
        self,
        function_name: str,
        code_location: str,
    ) -> str:
        """Update Lambda function code.

        Args:
            function_name: Name of the function
            code_location: S3 location of new code (bucket/key)

        Returns:
            Function ARN

        Raises:
            Exception: If update fails
        """
        try:
            bucket, key = code_location.split("/", 1)

            response = self.lambda_client.update_function_code(
                FunctionName=function_name,
                S3Bucket=bucket,
                S3Key=key,
            )

            return response["FunctionArn"]

        except ClientError as e:
            logger.error(f"Failed to update Lambda function {function_name}: {e}")
            raise Exception(f"Lambda update error: {e}")
