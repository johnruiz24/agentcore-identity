# Public Release Brainstorm and Execution Notes

Date: 2026-04-23
Scope: Prepare `agentcore-identity` for public GitHub publication.

## Objectives

1. Keep the repository useful as a public technical reference.
2. Remove or mask sensitive/internal data.
3. Keep only documentation that helps external users understand and run the project.
4. Improve README and docs structure for fast onboarding.

## Adjustments Decided

- Refresh root README with clear architecture, setup, deployment, and security sections.
- Curate docs set to architecture/setup/deployment/article references only.
- Remove internal planning/audit/archive artifacts from `docs/`.
- Enforce placeholders for account/profile/user-identifying values.
- Fix internal repository metadata links to public GitHub URLs.
- Remove internal-only GitLab recovery scripts from `scripts/`.

## Sanitization Policy

Use placeholders for any environment-specific or identifying values:

- `<AWS_ACCOUNT_ID>`
- `<AWS_PROFILE>`
- `<AWS_REGION>`
- `<EMAIL_PLACEHOLDER>`
- `<GATEWAY_ID>`
- `<RUNTIME_ID>`

Never commit:

- real OAuth client secrets
- real tokens
- real user emails
- internal account IDs or private infrastructure URLs

## Removed as Non-Public/Non-Essential

- `docs/brainstorms/`
- `docs/plans/`
- `docs/prompts/`
- `docs/audits/`
- `docs/archive/`
- draft/status/prd files and article archive variants
- internal GitLab self-heal scripts

## Result

The repository now targets external developers directly, with:

- a cleaned and publishable docs tree
- masked sensitive fields
- improved discoverability and onboarding
