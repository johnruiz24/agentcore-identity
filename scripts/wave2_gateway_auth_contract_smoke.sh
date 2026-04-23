#!/usr/bin/env bash
set -euo pipefail

# Wave 2 auth contract smoke checks for AgentCore Gateway.
# Defaults target the current promoted baseline; override with env vars when needed.

PROFILE="${PROFILE:-<AWS_PROFILE>}"
REGION="${REGION:-eu-central-1}"

BASELINE_GATEWAY_ID="${BASELINE_GATEWAY_ID:-<GATEWAY_ID>}"
# Optional overrides. If unset, values are discovered from gateway authorizer config.
BASELINE_POOL_ID="${BASELINE_POOL_ID:-}"
BASELINE_CLIENT_ID="${BASELINE_CLIENT_ID:-}"
BASELINE_SCOPE="${BASELINE_SCOPE:-}"

# Negative cross-client inputs (from a different stack/pool).
OTHER_POOL_ID="${OTHER_POOL_ID:-eu-central-1_1amp1xB5U}"
OTHER_CLIENT_ID="${OTHER_CLIENT_ID:-2sug9vgc11p2nldninl7u9jk4a}"
OTHER_SCOPE="${OTHER_SCOPE:-bedrockagentcorev2services-Gateway-B6F832E3/read}"

gateway_url() {
  aws cloudcontrol get-resource \
    --profile "$PROFILE" \
    --region "$REGION" \
    --type-name AWS::BedrockAgentCore::Gateway \
    --identifier "$BASELINE_GATEWAY_ID" \
    --output json | jq -r .ResourceDescription.Properties | jq -r .GatewayUrl
}

gateway_props() {
  aws cloudcontrol get-resource \
    --profile "$PROFILE" \
    --region "$REGION" \
    --type-name AWS::BedrockAgentCore::Gateway \
    --identifier "$BASELINE_GATEWAY_ID" \
    --output json | jq -r .ResourceDescription.Properties
}

token_url_for_pool() {
  local pool_id="$1"
  curl -sS "https://cognito-idp.${REGION}.amazonaws.com/${pool_id}/.well-known/openid-configuration" \
    | jq -r .token_endpoint
}

client_secret() {
  local pool_id="$1"
  local client_id="$2"
  aws cognito-idp describe-user-pool-client \
    --profile "$PROFILE" \
    --region "$REGION" \
    --user-pool-id "$pool_id" \
    --client-id "$client_id" \
    --query 'UserPoolClient.ClientSecret' \
    --output text
}

issue_token() {
  local pool_id="$1"
  local client_id="$2"
  local scope="$3"
  local secret
  local token_url
  secret="$(client_secret "$pool_id" "$client_id")"
  token_url="$(token_url_for_pool "$pool_id")"
  curl -sS -u "${client_id}:${secret}" \
    -d grant_type=client_credentials \
    -d "scope=${scope}" \
    "$token_url" | jq -r .access_token
}

post_initialize() {
  local url="$1"
  local token="${2:-}"
  local header_file="$3"
  local body_file="$4"
  local payload
  payload='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"wave2-smoke","version":"1.0"}}}'

  if [[ -n "$token" ]]; then
    curl -sS -D "$header_file" -o "$body_file" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer ${token}" \
      -X POST "$url" -d "$payload" || true
  else
    curl -sS -D "$header_file" -o "$body_file" \
      -H "Content-Type: application/json" \
      -X POST "$url" -d "$payload" || true
  fi
}

extract_code() {
  awk 'NR==1{print $2}' "$1"
}

URL="$(gateway_url)"
PROPS_JSON="$(gateway_props)"

if [[ -z "$BASELINE_POOL_ID" ]]; then
  BASELINE_POOL_ID="$(echo "$PROPS_JSON" | jq -r '.AuthorizerConfiguration.CustomJWTAuthorizer.DiscoveryUrl' | sed -E 's#^.*/(eu-[^/]+_[A-Za-z0-9]+).*#\1#')"
fi
if [[ -z "$BASELINE_CLIENT_ID" ]]; then
  BASELINE_CLIENT_ID="$(echo "$PROPS_JSON" | jq -r '.AuthorizerConfiguration.CustomJWTAuthorizer.AllowedClients[0]')"
fi
if [[ -z "$BASELINE_SCOPE" ]]; then
  BASELINE_SCOPE="$(echo "$PROPS_JSON" | jq -r '.AuthorizerConfiguration.CustomJWTAuthorizer.AllowedScopes[0]')"
fi

BASELINE_TOKEN="$(issue_token "$BASELINE_POOL_ID" "$BASELINE_CLIENT_ID" "$BASELINE_SCOPE")"
OTHER_TOKEN="$(issue_token "$OTHER_POOL_ID" "$OTHER_CLIENT_ID" "$OTHER_SCOPE")"

post_initialize "$URL" "" /tmp/w2_h_noauth /tmp/w2_b_noauth
post_initialize "$URL" "$BASELINE_TOKEN" /tmp/w2_h_auth /tmp/w2_b_auth
post_initialize "$URL" "$OTHER_TOKEN" /tmp/w2_h_cross /tmp/w2_b_cross

echo "GATEWAY_URL=$URL"
echo "BASELINE_POOL_ID=$BASELINE_POOL_ID"
echo "BASELINE_CLIENT_ID=$BASELINE_CLIENT_ID"
echo "BASELINE_SCOPE=$BASELINE_SCOPE"
echo "NOAUTH_HTTP=$(extract_code /tmp/w2_h_noauth)"
echo "BASELINE_AUTH_HTTP=$(extract_code /tmp/w2_h_auth)"
echo "CROSS_CLIENT_AUTH_HTTP=$(extract_code /tmp/w2_h_cross)"
echo -n "NOAUTH_BODY="; head -c 220 /tmp/w2_b_noauth | tr '\n' ' '; echo
echo -n "BASELINE_AUTH_BODY="; head -c 220 /tmp/w2_b_auth | tr '\n' ' '; echo
echo -n "CROSS_CLIENT_BODY="; head -c 220 /tmp/w2_b_cross | tr '\n' ' '; echo
