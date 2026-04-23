# Production Deployment Guide

## Overview

AgentCore Identity is deployed using Docker containers on AWS with CloudFormation infrastructure as code.

## Prerequisites

- AWS Account (<AWS_PROFILE>)
- Docker and Docker Compose installed locally
- AWS CLI configured
- GitHub Actions for CI/CD
- Codecov for coverage tracking

## Local Development

### Using Docker Compose

```bash
# Build and start services
docker-compose up -d

# View logs
docker-compose logs -f agentcore-identity

# Run tests in container
docker-compose exec agentcore-identity pytest

# Shutdown
docker-compose down
```

### Direct Python

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export AWS_REGION=eu-central-1
export COGNITO_USER_POOL_ID=eu-central-1_d3VRWMX7h
# ... set all required vars from .env

# Run server
python -m src.deployment.fastapi_server
```

## Docker Image

### Build Image

```bash
docker build -f deployment/Dockerfile -t agentcore-identity:latest .
```

### Push to ECR

```bash
# Login to ECR
aws ecr get-login-password --region eu-central-1 | \
  docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.eu-central-1.amazonaws.com

# Tag image
docker tag agentcore-identity:latest \
  <AWS_ACCOUNT_ID>.dkr.ecr.eu-central-1.amazonaws.com/agentcore-identity:latest

# Push
docker push <AWS_ACCOUNT_ID>.dkr.ecr.eu-central-1.amazonaws.com/agentcore-identity:latest
```

## CloudFormation Deployment

### Deploy Stack

```bash
python scripts/deploy_cloudformation.py \
  --action deploy \
  --stack-name agentcore-identity-prod \
  --environment production \
  --region eu-central-1 \
  --profile <AWS_PROFILE>
```

### Update Stack

```bash
python scripts/deploy_cloudformation.py \
  --action deploy \
  --stack-name agentcore-identity-prod \
  --environment production
```

### Monitor Stack

```bash
python scripts/deploy_cloudformation.py \
  --action status \
  --stack-name agentcore-identity-prod
```

### Get Outputs

```bash
python scripts/deploy_cloudformation.py \
  --action outputs \
  --stack-name agentcore-identity-prod
```

## Environment Configuration

### Production Environment Variables

```bash
# AWS
AWS_REGION=eu-central-1
AWS_ACCOUNT_ID=<AWS_ACCOUNT_ID>
AWS_PROFILE=<AWS_PROFILE>

# Bedrock
BEDROCK_MODEL_ID=eu.anthropic.claude-sonnet-4-5-20250929-v1:0

# Cognito (from Parameter Store)
COGNITO_USER_POOL_ID=eu-central-1_d3VRWMX7h
COGNITO_CLIENT_ID=27ecvseqj5a2hurs205te4cqci
COGNITO_CLIENT_SECRET=<from-parameter-store>
COGNITO_DOMAIN=agentcore-identity

# OAuth2
OAUTH2_REDIRECT_URI=https://your-domain.com/auth/callback
OAUTH2_TOKEN_EXPIRY_MINUTES=30

# DynamoDB
DYNAMODB_TABLE_SESSIONS=agentcore-identity-sessions
DYNAMODB_TABLE_USERS=agentcore-identity-users

# FastAPI
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000
FASTAPI_DEBUG=false

# Logging
LOG_LEVEL=INFO
```

### Retrieve from Parameter Store

```bash
# Get all parameters
aws ssm get-parameters \
  --names /agentcore-identity/production/* \
  --query 'Parameters[*].[Name,Value]' \
  --profile <AWS_PROFILE>
```

## Health Checks

### Local Health Check

```bash
curl http://localhost:8000/health
```

### Production Health Check

```bash
# Via AWS Load Balancer
curl https://agentcore-identity-prod.example.com/health

# Via CloudWatch
aws cloudwatch describe-alarms \
  --alarm-names agentcore-identity-health \
  --profile <AWS_PROFILE>
```

## Monitoring

### CloudWatch Logs

```bash
# View logs
aws logs tail /aws/agentcore-identity/production --follow \
  --profile <AWS_PROFILE>

# Get specific errors
aws logs filter-log-events \
  --log-group-name /aws/agentcore-identity/production \
  --filter-pattern "ERROR" \
  --profile <AWS_PROFILE>
```

### CloudWatch Metrics

```bash
# List custom metrics
aws cloudwatch list-metrics \
  --namespace AgentCoreIdentity \
  --profile <AWS_PROFILE>

# Get metric data
aws cloudwatch get-metric-statistics \
  --namespace AgentCoreIdentity \
  --metric-name TokenExchangeLatency \
  --start-time 2026-02-23T00:00:00Z \
  --end-time 2026-02-24T00:00:00Z \
  --period 3600 \
  --statistics Average \
  --profile <AWS_PROFILE>
```

## Backup and Disaster Recovery

### DynamoDB Backups

```bash
# Enable point-in-time recovery
aws dynamodb update-continuous-backups \
  --table-name agentcore-identity-sessions \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true \
  --profile <AWS_PROFILE>

# Create on-demand backup
aws dynamodb create-backup \
  --table-name agentcore-identity-sessions \
  --backup-name agentcore-sessions-backup-$(date +%Y%m%d) \
  --profile <AWS_PROFILE>
```

### Parameter Store Backups

```bash
# Export all parameters
aws ssm describe-parameters \
  --filters Key=Name,Values=/agentcore-identity/production \
  --query 'Parameters[*].[Name,Value]' \
  --output table \
  --profile <AWS_PROFILE> > backup.txt
```

## Scaling

### Auto-Scaling Configuration

```bash
# Create Auto Scaling Group (if using ECS)
aws autoscaling create-auto-scaling-group \
  --auto-scaling-group-name agentcore-identity-asg \
  --launch-template LaunchTemplateName=agentcore-identity \
  --min-size 2 \
  --max-size 10 \
  --desired-capacity 3 \
  --profile <AWS_PROFILE>
```

## Rollback Procedure

### Rollback via CloudFormation

```bash
# Cancel update
aws cloudformation cancel-update-stack \
  --stack-name agentcore-identity-prod \
  --profile <AWS_PROFILE>

# Rollback to previous version
python scripts/deploy_cloudformation.py \
  --action rollback \
  --stack-name agentcore-identity-prod
```

## Security

### SSL/TLS Certificates

```bash
# Request certificate (if not already done)
aws acm request-certificate \
  --domain-name agentcore-identity-prod.example.com \
  --validation-method DNS \
  --profile <AWS_PROFILE>
```

### Security Groups

```bash
# Update inbound rules
aws ec2 authorize-security-group-ingress \
  --group-id sg-12345678 \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0 \
  --profile <AWS_PROFILE>
```

## Troubleshooting

### Stack Creation Failed

```bash
# View stack events
aws cloudformation describe-stack-events \
  --stack-name agentcore-identity-prod \
  --query 'StackEvents[*].[Timestamp,ResourceStatus,ResourceStatusReason]' \
  --profile <AWS_PROFILE>
```

### Service Health Issues

```bash
# Check ECS task status
aws ecs describe-tasks \
  --cluster agentcore-identity-prod \
  --tasks <task-arn> \
  --profile <AWS_PROFILE>

# View container logs
aws logs get-log-events \
  --log-group-name /ecs/agentcore-identity \
  --log-stream-name ecs/agentcore-identity/<container-id>
```

## Performance Tuning

### DynamoDB Optimization

```bash
# Update provisioned capacity
aws dynamodb update-table \
  --table-name agentcore-identity-sessions \
  --provisioned-throughput ReadCapacityUnits=10,WriteCapacityUnits=10 \
  --profile <AWS_PROFILE>

# Enable autoscaling
aws application-autoscaling register-scalable-target \
  --service-namespace dynamodb \
  --resource-id table/agentcore-identity-sessions \
  --scalable-dimension dynamodb:table:WriteCapacityUnits \
  --min-capacity 5 \
  --max-capacity 40 \
  --profile <AWS_PROFILE>
```

## Cost Optimization

### Monitor Costs

```bash
# Get cost by service
aws ce get-cost-and-usage \
  --time-period Start=2026-02-01,End=2026-02-23 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --profile <AWS_PROFILE>
```

## References

- [AWS CloudFormation](https://docs.aws.amazon.com/cloudformation/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [AWS Security Best Practices](https://aws.amazon.com/architecture/security-identity-compliance/)
- [Production Readiness Checklist](https://aws.amazon.com/builders/events/workshops/aws-well-architected-review/)
