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

See diagrams and deep-dive docs in [docs/README.md](docs/README.md).

## Repository Structure

- `src/`: runtime/auth/providers/MCP services
- `infra/cdk/`: CDK app and stack definitions
- `scripts/`: validation and automation utilities
- `scripts/deploy/`: deployment entry scripts
- `deployment/`: deployment assets and phased workflows
- `deployment/compose/`: compose bundles for local/full-stack scenarios
- `examples/`: isolated runnable examples
- `tools/`: auxiliary tooling packages
- `docs/`: setup, architecture, operations, and article content

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

This repo includes image-generation tooling references for documentation and asset workflows.

- Claude path reference package: `tools/image-generator-openai/`
- Codex equivalent skill: `image-generator` (Gemini Nano Banana Pro backend)

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
- [Implementation Guides](docs/IMPLEMENTATION_GUIDES.md)
- [Production Deployment](docs/PRODUCTION_DEPLOYMENT.md)
- [Architecture Notes](docs/architecture/)
- [Refined Article](docs/medium-article-agentcore-refined.html)
