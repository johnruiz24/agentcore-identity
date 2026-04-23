#!/usr/bin/env bash
set -euo pipefail

# Autonomous CDK-driven delivery pipeline:
# 1) Build + push runtime image to ECR
# 2) Deploy BedrockIdentityFull via CDK using live OAuth provider contexts
# 3) Smoke-test gateway tools discovery and Atlassian consent handshake
#
# Usage:
#   AWS_PROFILE=<AWS_PROFILE> AWS_REGION=eu-central-1 ./scripts/cdk_autonomous_lfg.sh

AWS_PROFILE="${AWS_PROFILE:-<AWS_PROFILE>}"
AWS_REGION="${AWS_REGION:-eu-central-1}"
ENVIRONMENT="${ENVIRONMENT:-dev3}"
STACK_ID="${STACK_ID:-BedrockIdentityFull}"
STACK_NAME="${STACK_NAME:-bedrock-agentcore-identity-${ENVIRONMENT}}"
REPO_NAME="${REPO_NAME:-bedrock-agentcore-identity-oauth2}"
ACCOUNT_ID="${ACCOUNT_ID:-$(AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" aws sts get-caller-identity --query Account --output text)}"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"
IMAGE_TAG="${IMAGE_TAG:-autonomous-$(date +%Y%m%d%H%M%S)}"
GATEWAY_ID="${GATEWAY_ID:-}"
NPM_CACHE_DIR="${NPM_CACHE_DIR:-/tmp/.npm-codex}"

echo "==> Discovering OAuth secret/provider contexts"
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
GOOGLE_SECRET_NAME="$(
  AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" \
    aws secretsmanager list-secrets --output json \
    | jq -r '.SecretList
      | map(select(.Name | contains("bedrock-agentcore-identity!default/oauth2/google-oauth-client-")))
      | first
      | .Name // empty'
)"
GOOGLE_SECRET_ARN="$(
  AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" \
    aws secretsmanager list-secrets --output json \
    | jq -r '.SecretList
      | map(select(.Name | contains("bedrock-agentcore-identity!default/oauth2/google-oauth-client-")))
      | first
      | .ARN // empty'
)"

if [[ -z "$ATLASSIAN_SECRET_NAME" || -z "$ATLASSIAN_SECRET_ARN" ]]; then
  echo "ERROR: Atlassian OAuth client secret not found in Secrets Manager." >&2
  exit 1
fi
if [[ -z "$GOOGLE_SECRET_NAME" || -z "$GOOGLE_SECRET_ARN" ]]; then
  echo "ERROR: Google OAuth client secret not found in Secrets Manager." >&2
  exit 1
fi

ATLASSIAN_PROVIDER_NAME="${ATLASSIAN_SECRET_NAME##*/}"
GOOGLE_PROVIDER_NAME="${GOOGLE_SECRET_NAME##*/}"
ATLASSIAN_PROVIDER_ARN="arn:aws:bedrock-agentcore:${AWS_REGION}:${ACCOUNT_ID}:token-vault/default/oauth2credentialprovider/${ATLASSIAN_PROVIDER_NAME}"
GOOGLE_PROVIDER_ARN="arn:aws:bedrock-agentcore:${AWS_REGION}:${ACCOUNT_ID}:token-vault/default/oauth2credentialprovider/${GOOGLE_PROVIDER_NAME}"

echo "==> Image target: ${ECR_URI}:${IMAGE_TAG}"
echo "==> Atlassian provider: ${ATLASSIAN_PROVIDER_NAME}"
echo "==> Google provider: ${GOOGLE_PROVIDER_NAME}"

echo "==> ECR login"
AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" \
  aws ecr get-login-password \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "==> Build + push image"
docker build --platform linux/arm64 -t "${ECR_URI}:${IMAGE_TAG}" .
docker push "${ECR_URI}:${IMAGE_TAG}"

echo "==> CDK deploy"
mkdir -p "$NPM_CACHE_DIR"
NPM_CONFIG_CACHE="$NPM_CACHE_DIR" \
AWS_SDK_LOAD_CONFIG=1 \
AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" \
  npx cdk deploy "$STACK_ID" --require-approval never --profile "$AWS_PROFILE" \
    -c "environment=${ENVIRONMENT}" \
    -c "imageTag=${IMAGE_TAG}" \
    -c googleCalendarTargetEnabled=true \
    -c "googleCalendarOauthProviderArn=${GOOGLE_PROVIDER_ARN}" \
    -c "googleCalendarOauthSecretArn=${GOOGLE_SECRET_ARN}" \
    -c "googleCalendarOauthScopes=https://www.googleapis.com/auth/calendar.events" \
    -c atlassianTargetEnabled=true \
    -c "atlassianOauthProviderArn=${ATLASSIAN_PROVIDER_ARN}" \
    -c "atlassianOauthSecretArn=${ATLASSIAN_SECRET_ARN}" \
    -c "atlassianOauthScopes=read:jira-work,read:jira-user"

echo "==> Smoke test: tools discovery"
if [[ -z "${GATEWAY_ID}" ]]; then
  GATEWAY_ID="$(
    AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" \
      aws cloudformation describe-stack-resources --stack-name "$STACK_NAME" \
      --query 'StackResources[?ResourceType==`AWS::BedrockAgentCore::Gateway`].PhysicalResourceId | [0]' \
      --output text
  )"
fi
if [[ -z "${GATEWAY_ID}" || "${GATEWAY_ID}" == "None" ]]; then
  echo "ERROR: Could not resolve Gateway ID from stack ${STACK_NAME}" >&2
  exit 1
fi
echo "==> Using Gateway ID: ${GATEWAY_ID}"
AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" \
  python scripts/discover_gateway_tools.py --gateway-id "$GATEWAY_ID"

echo "==> Smoke test: consent handshake"
SMOKE_LOG="/tmp/atlassian-smoke-${IMAGE_TAG}.log"
AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" bash -lc '
set -euo pipefail
GW_ID="'"$GATEWAY_ID"'"
retry=0
PROPS_JSON=""
until [[ $retry -ge 5 ]]; do
  if PROPS_JSON=$(aws --profile "'"$AWS_PROFILE"'" --region "'"$AWS_REGION"'" cloudcontrol get-resource --type-name AWS::BedrockAgentCore::Gateway --identifier "$GW_ID" --query "ResourceDescription.Properties" --output text 2>/tmp/cdk_lfg_cloudcontrol_err.log); then
    break
  fi
  retry=$((retry+1))
  sleep 3
done
if [[ -z "$PROPS_JSON" ]]; then
  cat /tmp/cdk_lfg_cloudcontrol_err.log >&2 || true
  echo "ERROR: Could not load gateway properties for $GW_ID" >&2
  exit 1
fi
GW_URL=$(printf "%s" "$PROPS_JSON" | jq -r ".GatewayUrl")
DISCOVERY_URL=$(printf "%s" "$PROPS_JSON" | jq -r ".AuthorizerConfiguration.CustomJWTAuthorizer.DiscoveryUrl")
CLIENT_ID=$(printf "%s" "$PROPS_JSON" | jq -r ".AuthorizerConfiguration.CustomJWTAuthorizer.AllowedClients[0]")
SCOPE=$(printf "%s" "$PROPS_JSON" | jq -r ".AuthorizerConfiguration.CustomJWTAuthorizer.AllowedScopes[0]")
POOL_ID=$(printf "%s" "$DISCOVERY_URL" | sed -E "s#https://cognito-idp\\.[^/]+/([^/]+)/.*#\\1#")
CLIENT_SECRET=$(aws --profile "'"$AWS_PROFILE"'" --region "'"$AWS_REGION"'" cognito-idp describe-user-pool-client --user-pool-id "$POOL_ID" --client-id "$CLIENT_ID" --query "UserPoolClient.ClientSecret" --output text)
OIDC=$(curl -sS "https://cognito-idp.'"$AWS_REGION"'.amazonaws.com/${POOL_ID}/.well-known/openid-configuration")
TOKEN_ENDPOINT=$(printf "%s" "$OIDC" | jq -r ".token_endpoint")
BASIC=$(printf "%s" "${CLIENT_ID}:${CLIENT_SECRET}" | base64)
ACCESS_TOKEN=$(curl -sS -X POST "$TOKEN_ENDPOINT" -H "Authorization: Basic $BASIC" -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "grant_type=client_credentials" --data-urlencode "scope=${SCOPE}" | jq -r ".access_token")
INIT="{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-11-25\",\"capabilities\":{},\"clientInfo\":{\"name\":\"autonomous-smoke\",\"version\":\"1.0\"}}}"
CALL="{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"atlassian-openapi-dev3___listAtlassianAccessibleResources\",\"arguments\":{}}}"
INIT_RES=$(curl -sS -X POST "$GW_URL" -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" -H "MCP-Protocol-Version: 2025-11-25" -d "$INIT")
CALL_RES=$(curl -sS -X POST "$GW_URL" -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" -H "MCP-Protocol-Version: 2025-11-25" -d "$CALL")
printf "INIT_PROTOCOL=%s\n" "$(printf "%s" "$INIT_RES" | jq -r ".result.protocolVersion")"
printf "CALL_ERROR_CODE=%s\n" "$(printf "%s" "$CALL_RES" | jq -r ".error.code // \"\"")"
printf "CALL_HAS_CONSENT_URL=%s\n" "$(printf "%s" "$CALL_RES" | jq -r ".error.data.elicitations[0].url | startswith(\"https://bedrock-agentcore.'"$AWS_REGION"'.amazonaws.com/identities/oauth2/authorize\")")"
' | tee "$SMOKE_LOG"

echo "==> Summary"
echo "IMAGE_TAG=${IMAGE_TAG}"
echo "GATEWAY_ID=${GATEWAY_ID}"
echo "SMOKE_LOG=${SMOKE_LOG}"
echo "DONE"
