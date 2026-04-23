# Atlassian OAuth Setup (AgentCore Outbound Auth)

This guide configures Atlassian OAuth 2.0 (3LO) for the AgentCore outbound OAuth client.

## 1) Create Atlassian app and get `client_id` / `client_secret`

1. Open Atlassian Developer Console: https://developer.atlassian.com/console/myapps/
2. Create app (`Create` -> `OAuth 2.0 integration`).
3. In app settings, open **Authorization** and add callback URL(s).
4. Open **Settings** and copy:
   - **Client ID** -> use as AgentCore `Client ID`
   - **Secret** -> use as AgentCore `Client secret`

## 2) Callback URL for AgentCore

In AgentCore Identity (`Add OAuth Client`, provider `Atlassian`), use the callback URL shown in the AgentCore flow.

For current AgentCore Atlassian provider docs, callback is:

- `https://bedrock-agentcore.<REGION>.amazonaws.com/identities/oauth2/callback`

Use the exact same value in Atlassian app Authorization settings to avoid `redirect_uri` mismatch.

## 3) Scopes (least privilege)

Recommended Jira read-only baseline:

- `read:jira-work`
- `read:jira-user`
- `offline_access`

Add more only if needed (for example write scopes for edits).

## 4) Configure CDK deploy contexts

Use values returned by AgentCore when the OAuth provider is created (`providerArn`, `secretArn`):

```bash
npx cdk deploy BedrockIdentityFull --require-approval never \
  -c environment=<ENVIRONMENT> \
  -c imageTag=arm64-latest \
  -c atlassianTargetEnabled=true \
  -c atlassianOauthProviderArn=<provider-arn> \
  -c atlassianOauthSecretArn=<secret-arn> \
  -c atlassianOauthScopes=read:jira-work,read:jira-user
```

## 5) Permission model (what the agent can access)

The agent uses delegated user OAuth tokens. In practice:

- The token is for the authenticated Atlassian user.
- Jira/Confluence APIs return only what that user is authorized to view/manage.
- Limiting scopes + Atlassian project permissions enforces access boundaries.

So your prompt queries about projects/issues will only work for projects your user can access.

## 6) Suggested first queries

1. List accessible Atlassian resources (to identify cloud/site id).
2. List Jira projects for that `cloudId`.
3. Search issues with JQL constrained to authorized projects.
