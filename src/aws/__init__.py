"""AWS integration modules for AgentCore Identity Service."""

from src.aws.cloudwatch_logger import CloudWatchLogger
from src.aws.iam_manager import IAMManager
from src.aws.kms_manager import KMSManager
from src.aws.lambda_client import LambdaClient

__all__ = [
    "CloudWatchLogger",
    "IAMManager",
    "KMSManager",
    "LambdaClient",
]
