#!/usr/bin/env bash
set -euo pipefail

# Deploy/upgrade BedrockIdentityFull with Atlassian Jira outbound OAuth target.
# This script discovers Atlassian oauth2 secret/provider naming created in AgentCore Identity.

AWS_PROFILE="${AWS_PROFILE:-<AWS_PROFILE>}"
AWS_REGION="${AWS_REGION:-eu-central-1}"
ENVIRONMENT="${ENVIRONMENT:-dev3}"
IMAGE_TAG="${IMAGE_TAG:-arm64-latest}"
STACK_ID="${STACK_ID:-BedrockIdentityFull}"
NPM_CACHE_DIR="${NPM_CACHE_DIR:-/tmp/.npm-codex}"
ATLASSIAN_SCOPES="${ATLASSIAN_SCOPES:-read:jira-work,read:jira-user}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Discovering AWS account"
ACCOUNT_ID="$(
  AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" \
    aws sts get-caller-identity --query Account --output text
)"
echo "ACCOUNT_ID=$ACCOUNT_ID"

echo "==> Discovering Atlassian OAuth secret in Secrets Manager"
ATLASSIAN_SECRET_NAME="$(
  AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" \
    aws secretsmanager list-secrets --output json \
      | jq -r '.SecretList
        | map(select(.Name | contains("bedrock-agentcore-identity!default/oauth2/atlassian-oauth-client-")))
        | first
        | .Name // empty'
)"
ATLASSIAN_SECRET_ARN="$(
  AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" \
    aws secretsmanager list-secrets --output json \
      | jq -r '.SecretList
        | map(select(.Name | contains("bedrock-agentcore-identity!default/oauth2/atlassian-oauth-client-")))
        | first
        | .ARN // empty'
)"
if [[ -z "$ATLASSIAN_SECRET_NAME" || "$ATLASSIAN_SECRET_NAME" == "None" ]]; then
  echo "ERROR: Could not find Atlassian oauth2 secret. Create OAuth client in AgentCore Identity first." >&2
  exit 1
fi
if [[ -z "$ATLASSIAN_SECRET_ARN" || "$ATLASSIAN_SECRET_ARN" == "None" ]]; then
  echo "ERROR: Could not resolve Atlassian oauth2 secret ARN." >&2
  exit 1
fi
ATLASSIAN_PROVIDER_NAME="${ATLASSIAN_SECRET_NAME##*/}"
ATLASSIAN_PROVIDER_ARN="arn:aws:bedrock-agentcore:${AWS_REGION}:${ACCOUNT_ID}:token-vault/default/oauth2credentialprovider/${ATLASSIAN_PROVIDER_NAME}"

echo "ATLASSIAN_SECRET_NAME=$ATLASSIAN_SECRET_NAME"
echo "ATLASSIAN_PROVIDER_NAME=$ATLASSIAN_PROVIDER_NAME"
echo "ATLASSIAN_PROVIDER_ARN=$ATLASSIAN_PROVIDER_ARN"

echo "==> Optionally discovering Google target credentials to keep existing target"
GOOGLE_SECRET_NAME="$(
  AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" \
    aws secretsmanager list-secrets --output json \
      | jq -r '.SecretList
        | map(select(.Name | contains("bedrock-agentcore-identity!default/oauth2/google-oauth-client-")))
        | first
        | .Name // empty'
)"
GOOGLE_FLAGS=()
if [[ -n "$GOOGLE_SECRET_NAME" ]]; then
  GOOGLE_SECRET_ARN="$(
    AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" \
      aws secretsmanager list-secrets --output json \
        | jq -r '.SecretList
          | map(select(.Name | contains("bedrock-agentcore-identity!default/oauth2/google-oauth-client-")))
          | first
          | .ARN // empty'
  )"
  GOOGLE_PROVIDER_NAME="${GOOGLE_SECRET_NAME##*/}"
  GOOGLE_PROVIDER_ARN="arn:aws:bedrock-agentcore:${AWS_REGION}:${ACCOUNT_ID}:token-vault/default/oauth2credentialprovider/${GOOGLE_PROVIDER_NAME}"
  GOOGLE_FLAGS=(
    -c googleCalendarTargetEnabled=true
    -c "googleCalendarOauthProviderArn=${GOOGLE_PROVIDER_ARN}"
    -c "googleCalendarOauthSecretArn=${GOOGLE_SECRET_ARN}"
    -c "googleCalendarOauthScopes=https://www.googleapis.com/auth/calendar.events"
  )
  echo "GOOGLE_PROVIDER_NAME=$GOOGLE_PROVIDER_NAME (kept enabled)"
else
  echo "Google oauth secret not found; proceeding with Atlassian target only."
fi

echo "==> Running CDK deploy"
mkdir -p "$NPM_CACHE_DIR"
(
  cd "$REPO_ROOT/infra/cdk"
  NPM_CONFIG_CACHE="$NPM_CACHE_DIR" \
  AWS_SDK_LOAD_CONFIG=1 \
  AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" \
    npx cdk deploy "$STACK_ID" --require-approval never --profile "$AWS_PROFILE" \
      -c "environment=${ENVIRONMENT}" \
      -c "imageTag=${IMAGE_TAG}" \
      "${GOOGLE_FLAGS[@]}" \
      -c atlassianTargetEnabled=true \
      -c "atlassianOauthProviderArn=${ATLASSIAN_PROVIDER_ARN}" \
      -c "atlassianOauthSecretArn=${ATLASSIAN_SECRET_ARN}" \
      -c "atlassianOauthScopes=${ATLASSIAN_SCOPES}"
)

echo "==> Done"
echo "Atlassian target enabled for stack environment=${ENVIRONMENT}."
