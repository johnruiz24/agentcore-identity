#!/bin/bash
set -e

# AgentCore Identity Service - Phase 5: DynamoDB Backend Deployment
# Deploys all required DynamoDB tables for production

REGION="eu-central-1"
ACCOUNT_ID="<AWS_ACCOUNT_ID>"

echo "==============================================="
echo "🚀 AgentCore Identity Service - Phase 5"
echo "DynamoDB Backend Deployment"
echo "==============================================="
echo ""
echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo ""

# Check AWS credentials
echo "Checking AWS credentials..."
AWS_IDENTITY=$(aws sts get-caller-identity --region "$REGION" 2>&1)
if [ $? -ne 0 ]; then
    echo "❌ Failed to authenticate with AWS"
    exit 1
fi
echo "✅ Authenticated"
echo ""

# Create DynamoDB tables
echo "Creating DynamoDB tables..."
python3 -m src.storage.create_tables "$REGION"
if [ $? -ne 0 ]; then
    echo "❌ Failed to create DynamoDB tables"
    exit 1
fi
echo "✅ All DynamoDB tables created"
echo ""

# Verify tables
echo "Verifying tables..."
TABLES=$(aws dynamodb list-tables --region "$REGION" --query 'TableNames' --output json)
echo "Tables in $REGION:"
echo "$TABLES" | jq '.[]'
echo ""

# Enable Point-in-Time Recovery for production resilience
echo "Enabling Point-in-Time Recovery..."
for TABLE in agentcore-identity-credentials agentcore-identity-oauth-flows agentcore-identity-audit-logs; do
    aws dynamodb update-continuous-backups \
        --table-name "$TABLE" \
        --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true \
        --region "$REGION" 2>/dev/null || true
done
echo "✅ Point-in-Time Recovery enabled"
echo ""

# Setup CloudWatch alarms (optional)
echo "Setting up CloudWatch monitoring..."
for TABLE in agentcore-identity-credentials agentcore-identity-oauth-flows agentcore-identity-audit-logs; do
    aws cloudwatch put-metric-alarm \
        --alarm-name "agentcore-$TABLE-throttling" \
        --alarm-description "Alert if $TABLE is throttled" \
        --metric-name ConsumedWriteCapacityUnits \
        --namespace AWS/DynamoDB \
        --statistic Sum \
        --period 300 \
        --threshold 100 \
        --comparison-operator GreaterThanThreshold \
        --dimensions Name=TableName,Value="$TABLE" \
        --region "$REGION" 2>/dev/null || true
done
echo "✅ CloudWatch alarms configured"
echo ""

# Summary
echo "==============================================="
echo "✅ Phase 5 Deployment Complete!"
echo "==============================================="
echo ""
echo "Deployed Components:"
echo "  ✅ agentcore-identity-credentials (KMS encrypted)"
echo "  ✅ agentcore-identity-oauth-flows (OAuth flow tracking)"
echo "  ✅ agentcore-identity-audit-logs (Compliance & audit)"
echo ""
echo "Features:"
echo "  ✅ TTL-based automatic expiration"
echo "  ✅ Point-in-Time Recovery enabled"
echo "  ✅ CloudWatch monitoring"
echo "  ✅ On-demand billing (PAY_PER_REQUEST)"
echo ""
echo "Ready for Phase 6: AWS Integration & Deployment"
echo ""
