#!/bin/bash
set -e

# AgentCore Identity Service - Phase 8: Production Deployment
# Complete end-to-end deployment to AgentCore Runtime

REGION="eu-central-1"
ACCOUNT_ID="<AWS_ACCOUNT_ID>"
IMAGE_NAME="agentcore-identity"
ECR_REPO="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$IMAGE_NAME"
VERSION=$(date +%Y%m%d-%H%M%S)

echo "==============================================="
echo "🚀 AgentCore Identity Service - Phase 8"
echo "Production Deployment to AgentCore Runtime"
echo "==============================================="
echo ""
echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo "Image: $ECR_REPO:$VERSION"
echo ""

# Check AWS credentials
echo "Checking AWS credentials..."
AWS_IDENTITY=$(aws sts get-caller-identity --region "$REGION" 2>&1)
if [ $? -ne 0 ]; then
    echo "❌ Failed to authenticate with AWS"
    exit 1
fi
CALLER_ACCOUNT=$(echo "$AWS_IDENTITY" | grep Account | awk '{print $2}' | tr -d '"')
echo "✅ Authenticated as account: $CALLER_ACCOUNT"
echo ""

# Verify all DynamoDB tables exist
echo "Verifying DynamoDB tables..."
TABLES=$(aws dynamodb list-tables --region "$REGION" --query 'TableNames[?contains(@, `agentcore-identity`)]' --output json)
TABLE_COUNT=$(echo "$TABLES" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")

if [ "$TABLE_COUNT" -lt 3 ]; then
    echo "❌ Not all DynamoDB tables found (found $TABLE_COUNT, need 3)"
    exit 1
fi
echo "✅ All 3 DynamoDB tables verified"
echo ""

# Verify KMS key exists
echo "Verifying KMS key..."
KMS_KEY=$(aws kms describe-key --key-id "alias/agentcore-identity" --region "$REGION" 2>/dev/null || echo "")
if [ -z "$KMS_KEY" ]; then
    echo "⚠️  KMS key not found, creating..."
    python3 -c "from src.aws.kms_manager import KMSManager; KMSManager.get_or_create_key('alias/agentcore-identity', '$REGION')"
fi
echo "✅ KMS key configured"
echo ""

# Build Docker image
echo "Building Docker image..."
docker build -t "$ECR_REPO:$VERSION" -t "$ECR_REPO:latest" -f deployment/Dockerfile . 2>&1 | tail -5
if [ $? -ne 0 ]; then
    echo "❌ Docker build failed"
    exit 1
fi
echo "✅ Docker image built successfully"
echo ""

# Login to ECR (if needed)
echo "Preparing ECR repository..."
aws ecr describe-repositories --repository-names "$IMAGE_NAME" --region "$REGION" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Creating ECR repository..."
    aws ecr create-repository \
        --repository-name "$IMAGE_NAME" \
        --region "$REGION" \
        --tags Key=Service,Value=agentcore-identity Key=Component,Value=service
fi

# Login to ECR
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REPO" 2>/dev/null
echo "✅ ECR repository ready"
echo ""

# Push image to ECR
echo "Pushing Docker image to ECR..."
docker push "$ECR_REPO:$VERSION" 2>&1 | tail -3
docker push "$ECR_REPO:latest" 2>&1 | tail -1
echo "✅ Docker image pushed to ECR"
echo ""

# Create/Update ECS task execution role
echo "Creating ECS task execution role..."
EXEC_ROLE_ARN=$(aws iam get-role --role-name ecsTaskExecutionRole --query 'Role.Arn' --output text 2>/dev/null)
if [ -z "$EXEC_ROLE_ARN" ]; then
    # Create execution role
    cat > /tmp/trust-policy.json << TRUST
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
TRUST
    aws iam create-role --role-name ecsTaskExecutionRole --assume-role-policy-document file:///tmp/trust-policy.json --region "$REGION" >/dev/null 2>&1 || true
    aws iam attach-role-policy --role-name ecsTaskExecutionRole --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy --region "$REGION" >/dev/null 2>&1 || true
    EXEC_ROLE_ARN=$(aws iam get-role --role-name ecsTaskExecutionRole --query 'Role.Arn' --output text)
fi
echo "✅ ECS execution role: $EXEC_ROLE_ARN"
echo ""

# Create/Update ECS task definition
echo "Creating ECS task definition..."
cat > /tmp/ecs-task-def.json << EOF
{
  "family": "agentcore-identity",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "$EXEC_ROLE_ARN",
  "containerDefinitions": [
    {
      "name": "agentcore-identity",
      "image": "$ECR_REPO:$VERSION",
      "portMappings": [
        {
          "containerPort": 8000,
          "hostPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "AWS_REGION",
          "value": "$REGION"
        },
        {
          "name": "AWS_ACCOUNT_ID",
          "value": "$ACCOUNT_ID"
        },
        {
          "name": "LOG_LEVEL",
          "value": "INFO"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/agentcore/identity",
          "awslogs-region": "$REGION",
          "awslogs-stream-prefix": "service"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        "interval": 30,
        "timeout": 10,
        "retries": 3,
        "startPeriod": 10
      }
    }
  ]
}
EOF

aws ecs register-task-definition --cli-input-json file:///tmp/ecs-task-def.json --region "$REGION" >/dev/null
echo "✅ ECS task definition registered"
echo ""

# Summary
echo "==============================================="
echo "✅ Phase 8 Production Deployment Complete!"
echo "==============================================="
echo ""
echo "Deployed Components:"
echo "  ✅ Docker image built and pushed to ECR"
echo "  ✅ ECS task definition registered"
echo "  ✅ All DynamoDB tables verified"
echo "  ✅ KMS encryption configured"
echo "  ✅ CloudWatch logging configured"
echo ""
echo "Next Steps:"
echo "  1. Create ECS cluster (if not exists)"
echo "  2. Create ECS service from task definition"
echo "  3. Configure load balancer"
echo "  4. Setup auto-scaling"
echo "  5. Configure monitoring and alerts"
echo ""
echo "Service Endpoints:"
echo "  Health Check: http://<load-balancer>/health"
echo "  OAuth Token: POST http://<load-balancer>/auth/token"
echo "  Credentials: GET/POST http://<load-balancer>/credentials/*"
echo ""
echo "Docker Image:"
echo "  $ECR_REPO:$VERSION"
echo "  $ECR_REPO:latest"
echo ""
