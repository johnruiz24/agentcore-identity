"""AWS CloudWatch logging for audit trail and monitoring."""

import json
import time
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError


class CloudWatchLogger:
    """Manages CloudWatch logging for AgentCore Identity Service."""

    def __init__(
        self,
        log_group_name: str = "/agentcore/identity",
        region: str = "eu-central-1",
    ):
        """Initialize CloudWatch logger.

        Args:
            log_group_name: CloudWatch log group name
            region: AWS region
        """
        self.log_group_name = log_group_name
        self.region = region
        self.logs_client = boto3.client("logs", region_name=region)
        self._ensure_log_group()

    def _ensure_log_group(self) -> None:
        """Create log group if it doesn't exist."""
        try:
            self.logs_client.create_log_group(logGroupName=self.log_group_name)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceAlreadyExistsException":
                pass  # Log group already exists
            else:
                raise

    def log_auth_event(
        self,
        event_type: str,
        session_id: str,
        user_id: str,
        provider: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log authentication event.

        Args:
            event_type: Type of auth event (login, logout, token_refresh, etc.)
            session_id: Session ID
            user_id: User ID
            provider: OAuth provider name
            status: Status (success, failed, etc.)
            details: Additional event details
        """
        log_stream_name = f"auth-events-{time.strftime('%Y-%m-%d')}"
        self._ensure_log_stream(log_stream_name)

        message = {
            "timestamp": int(time.time() * 1000),
            "event_type": event_type,
            "session_id": session_id,
            "user_id": user_id,
            "provider": provider,
            "status": status,
            "details": details or {},
        }

        self._put_log_event(log_stream_name, json.dumps(message))

    def log_credential_event(
        self,
        event_type: str,
        credential_id: str,
        session_id: str,
        provider: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log credential operation event.

        Args:
            event_type: Type of credential event (store, retrieve, revoke, etc.)
            credential_id: Credential ID
            session_id: Session ID
            provider: OAuth provider name
            status: Status (success, failed, etc.)
            details: Additional event details
        """
        log_stream_name = f"credential-events-{time.strftime('%Y-%m-%d')}"
        self._ensure_log_stream(log_stream_name)

        message = {
            "timestamp": int(time.time() * 1000),
            "event_type": event_type,
            "credential_id": credential_id,
            "session_id": session_id,
            "provider": provider,
            "status": status,
            "details": details or {},
        }

        self._put_log_event(log_stream_name, json.dumps(message))

    def log_security_event(
        self,
        event_type: str,
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log security-related event.

        Args:
            event_type: Type of security event
            severity: Severity level (info, warning, error, critical)
            message: Event message
            details: Additional event details
        """
        log_stream_name = f"security-events-{time.strftime('%Y-%m-%d')}"
        self._ensure_log_stream(log_stream_name)

        message_obj = {
            "timestamp": int(time.time() * 1000),
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "details": details or {},
        }

        self._put_log_event(log_stream_name, json.dumps(message_obj))

    def _ensure_log_stream(self, log_stream_name: str) -> None:
        """Create log stream if it doesn't exist."""
        try:
            self.logs_client.create_log_stream(
                logGroupName=self.log_group_name,
                logStreamName=log_stream_name,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceAlreadyExistsException":
                pass  # Log stream already exists
            else:
                raise

    def _put_log_event(self, log_stream_name: str, message: str) -> None:
        """Put log event to stream."""
        try:
            self.logs_client.put_log_events(
                logGroupName=self.log_group_name,
                logStreamName=log_stream_name,
                logEvents=[
                    {
                        "timestamp": int(time.time() * 1000),
                        "message": message,
                    }
                ],
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidSequenceTokenException":
                # Token expired, get new sequence token and retry
                desc = self.logs_client.describe_log_streams(
                    logGroupName=self.log_group_name,
                    logStreamNamePrefix=log_stream_name,
                )
                if desc["logStreams"]:
                    sequence_token = desc["logStreams"][0].get("uploadSequenceToken")
                    self.logs_client.put_log_events(
                        logGroupName=self.log_group_name,
                        logStreamName=log_stream_name,
                        logEvents=[
                            {
                                "timestamp": int(time.time() * 1000),
                                "message": message,
                            }
                        ],
                        sequenceToken=sequence_token,
                    )
            else:
                raise

    def create_metric_alarm(
        self,
        alarm_name: str,
        metric_name: str,
        threshold: float,
        comparison_operator: str = "GreaterThanThreshold",
        period: int = 300,
        statistic: str = "Sum",
    ) -> None:
        """Create CloudWatch metric alarm.

        Args:
            alarm_name: Alarm name
            metric_name: Metric to monitor
            threshold: Alert threshold
            comparison_operator: Comparison operator (default: GreaterThanThreshold)
            period: Period in seconds (default: 5 minutes)
            statistic: Statistic type (Sum, Average, Maximum, Minimum)
        """
        cloudwatch = boto3.client("cloudwatch", region_name=self.region)

        try:
            cloudwatch.put_metric_alarm(
                AlarmName=alarm_name,
                MetricName=metric_name,
                Namespace="AgentCoreIdentity",
                Statistic=statistic,
                Period=period,
                Threshold=threshold,
                ComparisonOperator=comparison_operator,
                EvaluationPeriods=1,
                AlarmDescription=f"Alert for {metric_name} in AgentCore Identity Service",
            )
        except ClientError as e:
            raise Exception(f"Failed to create CloudWatch alarm: {e}")
