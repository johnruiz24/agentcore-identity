# Inbound Contract: Cognito JWT -> AgentCore Gateway

Date: 2026-02-25  
Scope: Baseline stack `bedrock-agentcore-identity-dev`

## Purpose
Define the minimum inbound authentication/authorization contract for callers invoking the AgentCore Gateway.

## Identity Source
- OIDC issuer: Cognito User Pool (`eu-central-1_MH3IsY9b1`)
- Discovery URL:
  - `https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_MH3IsY9b1/.well-known/openid-configuration`

## Token Flow (Current Baseline)
- OAuth flow: `client_credentials`
- Client type: confidential app client
- Expected token type: `Bearer`

## Required Claims / Validation Expectations
- `iss` must match configured Cognito issuer.
- `aud`/client relationship must match allowed client(s) configured on gateway.
- Token must be unexpired and signature-valid per JWKS.
- Requested operation must map to allowed scopes.

Operational note:
- In this baseline, `client_credentials` access tokens currently have `aud=null`.
- Gateway enforcement uses `allowedClients` + `allowedScopes`; explicit `allowedAudience` validation was removed after causing false rejections.

## Current Scope Model
- Resource server scope examples:
  - `<resource-server>/read`
  - `<resource-server>/write`

## Observed Behavior
- Missing token -> `401` (`Missing Bearer token`)
- Valid token + MCP initialize -> `200`
- Invalid scope at token request -> `invalid_scope`
- Token from non-authorized Cognito client/pool -> `401` (`Invalid Bearer token`)

## Gaps to Address
- Add explicit mapping from scopes to MCP tool/action permissions.
- Decide whether to enable interactive user flow in addition to `client_credentials`.
- Add negative tests for issuer/audience mismatch at gateway boundary.
