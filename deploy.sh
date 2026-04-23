#!/bin/bash

################################################################################
# Bedrock AgentCore Identity - Automated Deployment Script
#
# This script automates the AWS deployment of Bedrock AgentCore Identity
# Run this AFTER you have Google OAuth credentials ready
#
# Usage: bash deploy.sh <CLIENT_ID> <CLIENT_SECRET>
################################################################################

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
AWS_PROFILE="<AWS_PROFILE>"
AWS_REGION="eu-central-1"
AWS_ACCOUNT_ID="<AWS_ACCOUNT_ID>"
STACK_NAME="AgentCoreIdentityStack"

################################################################################
# Functions
################################################################################

print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_step() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

check_prerequisites() {
    print_header "CHECKING PREREQUISITES"

    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 not found. Install Python 3.11 or later"
        exit 1
    fi
    print_step "Python 3 found"

    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI not found. Install AWS CLI"
        exit 1
    fi
    print_step "AWS CLI found"

    # Check CDK
    if ! command -v cdk &> /dev/null; then
        print_error "AWS CDK not found. Run: npm install -g aws-cdk"
        exit 1
    fi
    print_step "AWS CDK found"

    # Check AWS credentials
    if ! aws sts get-caller-identity --profile "$AWS_PROFILE" &> /dev/null; then
        print_error "AWS credentials not configured for profile: $AWS_PROFILE"
        exit 1
    fi
    print_step "AWS credentials configured"

    # Check requirements.txt exists
    if [ ! -f "requirements.txt" ]; then
        print_error "requirements.txt not found. Run this script from project root"
        exit 1
    fi
    print_step "requirements.txt found"

    # Check Google credentials
    if [ -z "$1" ] || [ -z "$2" ]; then
        print_error "Google OAuth credentials not provided"
        echo ""
        echo "Usage: bash deploy.sh <CLIENT_ID> <CLIENT_SECRET>"
        echo ""
        echo "Example:"
        echo "  bash deploy.sh '123456789-abc123.apps.googleusercontent.com' 'GOCSPX-xyz123'"
        echo ""
        exit 1
    fi
    print_step "Google credentials provided"
}

install_dependencies() {
    print_header "INSTALLING DEPENDENCIES"
    pip install -q -r requirements.txt
    print_step "Dependencies installed"
}

set_aws_config() {
    print_header "CONFIGURING AWS"
    export AWS_PROFILE="$AWS_PROFILE"
    export AWS_REGION="$AWS_REGION"
    print_step "AWS_PROFILE = $AWS_PROFILE"
    print_step "AWS_REGION = $AWS_REGION"
}

bootstrap_cdk() {
    print_header "BOOTSTRAPPING CDK"
    print_warning "This only needs to run once"

    cdk bootstrap "aws://$AWS_ACCOUNT_ID/$AWS_REGION" \
        --profile "$AWS_PROFILE" \
        --quiet 2>/dev/null || true

    print_step "CDK bootstrap complete"
}

deploy_stack() {
    local client_id="$1"
    local client_secret="$2"

    print_header "DEPLOYING CDK STACK"
    print_warning "This will create AWS resources. Do you want to continue?"
    read -p "Type 'yes' to continue: " confirm

    if [ "$confirm" != "yes" ]; then
        print_error "Deployment cancelled by user"
        exit 1
    fi

    print_step "Starting deployment..."
    cdk deploy \
        --all \
        --require-approval never \
        --profile "$AWS_PROFILE" \
        --region "$AWS_REGION"

    print_step "Stack deployed successfully"
}

get_outputs() {
    print_header "RETRIEVING STACK OUTPUTS"

    API_ENDPOINT=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`APIEndpoint`].OutputValue' \
        --output text \
        --region "$AWS_REGION" \
        --profile "$AWS_PROFILE")

    echo -e "${GREEN}API Endpoint:${NC} $API_ENDPOINT"
    echo "API_ENDPOINT=$API_ENDPOINT" > /tmp/agentcore-deploy.env

    print_step "Stack outputs retrieved"
}

configure_oauth() {
    local client_id="$1"
    local client_secret="$2"

    print_header "CONFIGURING OAUTH CREDENTIALS"

    # Get API endpoint from previous output
    API_ENDPOINT=$(grep "API_ENDPOINT=" /tmp/agentcore-deploy.env | cut -d'=' -f2)

    print_warning "Update Google Cloud Console:"
    echo "1. Go to: https://console.cloud.google.com"
    echo "2. Find your OAuth 2.0 Client ID"
    echo "3. Add this redirect URI:"
    echo "   $API_ENDPOINT/oauth/callback"
    echo ""

    read -p "Press Enter after updating Google Console..."

    # Update Secrets Manager
    print_step "Updating AWS Secrets Manager..."

    aws secretsmanager update-secret \
        --secret-id "agentcore/google-oauth" \
        --secret-string "{
            \"client_id\": \"$client_id\",
            \"client_secret\": \"$client_secret\",
            \"redirect_uri\": \"$API_ENDPOINT/oauth/callback\"
        }" \
        --region "$AWS_REGION" \
        --profile "$AWS_PROFILE"

    print_step "Secrets Manager updated"
}

test_oauth() {
    print_header "TESTING OAUTH FLOW"

    API_ENDPOINT=$(grep "API_ENDPOINT=" /tmp/agentcore-deploy.env | cut -d'=' -f2)

    print_step "Testing OAuth initiation..."

    RESPONSE=$(curl -s -X POST "$API_ENDPOINT/oauth/initiate" \
        -H "Content-Type: application/json" \
        -d '{
            "action": "initiate",
            "provider": "google_calendar",
            "session_id": "test_'$(date +%s)'",
            "scopes": ["https://www.googleapis.com/auth/calendar.readonly"]
        }')

    if echo "$RESPONSE" | grep -q "authorization_url"; then
        print_step "OAuth flow test PASSED ✓"
        echo ""
        echo "Authorization URL:"
        echo "$RESPONSE" | grep -o '"authorization_url":"[^"]*"' | cut -d'"' -f4
        echo ""
    else
        print_error "OAuth flow test FAILED"
        echo "Response: $RESPONSE"
        exit 1
    fi
}

print_summary() {
    print_header "DEPLOYMENT COMPLETE ✓"

    API_ENDPOINT=$(grep "API_ENDPOINT=" /tmp/agentcore-deploy.env | cut -d'=' -f2)

    echo ""
    echo "Your Bedrock AgentCore Identity is now LIVE in AWS!"
    echo ""
    echo "API Endpoint: $API_ENDPOINT"
    echo ""
    echo "Next Steps:"
    echo "1. Monitor CloudWatch logs:"
    echo "   aws logs tail /agentcore/identity --follow"
    echo ""
    echo "2. View CloudWatch dashboard:"
    echo "   aws cloudwatch get-dashboard --dashboard-name agentcore-identity"
    echo ""
    echo "3. Start using the system:"
    echo "   - Call /oauth/initiate to start authentication"
    echo "   - Call /invoke to access calendar"
    echo ""
    echo "Documentation: See QUICK_START.md for more details"
    echo ""

    rm -f /tmp/agentcore-deploy.env
}

################################################################################
# Main Script
################################################################################

main() {
    CLIENT_ID="$1"
    CLIENT_SECRET="$2"

    print_header "BEDROCK AGENTCORE IDENTITY - DEPLOYMENT SCRIPT"

    check_prerequisites "$CLIENT_ID" "$CLIENT_SECRET"
    install_dependencies
    set_aws_config
    bootstrap_cdk
    deploy_stack "$CLIENT_ID" "$CLIENT_SECRET"
    get_outputs
    configure_oauth "$CLIENT_ID" "$CLIENT_SECRET"
    test_oauth
    print_summary
}

# Run main script
main "$@"
