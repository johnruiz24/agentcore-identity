# AgentCore Identity

Production-style reference for identity-safe AI agent orchestration on Amazon Bedrock AgentCore.

This repository focuses on one core problem: enabling an agent to call multiple external systems with delegated user OAuth while preserving strict identity boundaries.

## What You Get

- Inbound identity validation with Cognito JWT
- MCP tool discovery/routing through AgentCore Gateway
- Outbound delegated OAuth providers with token vault isolation
- Multi-target orchestration patterns (Atlassian + Google Calendar)
- CDK infrastructure project separated from runtime/service code

## Architecture

The implementation is structured into four boundaries:

1. Runtime boundary: agent orchestration and tool decisioning
2. Gateway boundary: MCP protocol transport and tool exposure
3. Identity boundary: delegated OAuth and secure token exchange
4. Provider boundary: external APIs reachable only through approved scopes

## Architecture Visuals

![AgentCore Identity Architecture Hero](docs/assets/agentcore-readme-hero-nanobanana.png)

![Delegated OAuth Sequence](docs/assets/agentcore-readme-oauth-sequence-nanobanana.png)

![Zero-Trust Boundary Map](docs/assets/agentcore-readme-zero-trust-nanobanana.png)

## Repository Structure

- `src/`: runtime/auth/providers/MCP services
- `infra/cdk/`: CDK app and stack definitions
- `scripts/`: validation and automation utilities
- `scripts/deploy/`: deployment entry scripts
- `deployment/`: deployment assets and phased workflows
- `deployment/compose/`: compose bundles for local/full-stack scenarios
- `examples/`: isolated runnable examples
- `docs/`: setup, deployment, and image-generation guidance

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- AWS CLI configured
- Docker (optional)

### Install

```bash
pip install -r requirements.txt
cd infra/cdk && npm ci
```

### Configure environment

```bash
export AWS_PROFILE=<AWS_PROFILE>
export AWS_REGION=<AWS_REGION>
export AWS_ACCOUNT_ID=<AWS_ACCOUNT_ID>
```

### Run service locally

```bash
python entrypoint.py
```

### Deploy infrastructure (example)

```bash
cd infra/cdk
AWS_PROFILE=<AWS_PROFILE> AWS_REGION=<AWS_REGION> \
npx cdk deploy BedrockIdentityFull --require-approval never
```

## Nano Banana Image Generation

This repo includes an explicit workflow for high-quality architecture imagery.

- Codex skill: `image-generator` (Gemini Nano Banana Pro backend)
- Workflow doc: [docs/IMAGE_GENERATION_NANOBANANA.md](docs/IMAGE_GENERATION_NANOBANANA.md)

Practical guidance:

- Use the skill when generating architecture hero images, explainer assets, or docs visuals.
- Keep generated assets under `docs/assets/`.
- Never commit secrets/API keys in prompts, scripts, or outputs.

## Security and Public-Safe Policy

- Sensitive values are masked using placeholders
- Internal-only planning/audit artifacts are excluded
- Environment/account/profile data must remain externalized

## Documentation Entry Points

- [Documentation Index](docs/README.md)
- [Atlassian OAuth Setup](docs/ATLASSIAN_OAUTH_SETUP.md)
- [Production Deployment](docs/PRODUCTION_DEPLOYMENT.md)
- [Image Generation (Nano Banana)](docs/IMAGE_GENERATION_NANOBANANA.md)
