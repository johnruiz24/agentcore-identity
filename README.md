# AgentCore Identity

Production-grade reference for identity-safe AI agent orchestration on Amazon Bedrock AgentCore.

This project addresses one hard problem: how to let an agent call multiple external systems with delegated user OAuth without leaking trust boundaries.

## Readme Structure

This README is intentionally organized in this order:

1. Problem and scope
2. Architecture visuals with context
3. Repository structure
4. Quick start and deploy
5. Image generation workflow

## Problem and Scope

Most agent prototypes break in production at identity boundaries. This repository is built around:

- Inbound identity validation with Cognito JWT
- MCP tool discovery and routing through AgentCore Gateway
- Outbound delegated OAuth through AgentCore Identity token vault
- Multi-target orchestration (Atlassian + Google Calendar)
- CDK infrastructure isolated from runtime code

## Architecture Visuals

### 1) System Map: Runtime, Gateway, Identity, Providers

This diagram gives the high-level architecture and component boundaries.

![AgentCore Identity Architecture Hero](docs/assets/agentcore-readme-hero-nanobanana.png)

Use this to understand:

- where agent reasoning runs
- where protocol routing happens (`tools/list`, `tools/call`)
- where token exchange is isolated
- where external API calls are finally executed

### 2) Delegated OAuth Flow Sequence

This view explains the request path for a user action that needs provider access.

![Delegated OAuth Sequence](docs/assets/agentcore-readme-oauth-sequence-nanobanana.png)

Use this to understand:

- when consent URL elicitation happens
- how callback and token exchange resume the flow
- where delegated tokens are used for provider APIs

### 3) Zero-Trust Boundary Model

This view focuses on security boundaries rather than feature flow.

![Zero-Trust Boundary Map](docs/assets/agentcore-readme-zero-trust-nanobanana.png)

Use this to understand:

- which layer is allowed to see what
- why token material is isolated from runtime orchestration
- where policy and scope enforcement should be audited

## Repository Structure

- `src/`: runtime, auth, providers, MCP services
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

### Run locally

```bash
python entrypoint.py
```

### Deploy infrastructure (example)

```bash
cd infra/cdk
AWS_PROFILE=<AWS_PROFILE> AWS_REGION=<AWS_REGION> \
npx cdk deploy BedrockIdentityFull --require-approval never
```

## Nano Banana Image Workflow

For Codex, use:

- Skill: `image-generator` (Gemini Nano Banana Pro backend)
- Guide: [docs/IMAGE_GENERATION_NANOBANANA.md](docs/IMAGE_GENERATION_NANOBANANA.md)

Rules:

- keep generated visuals in `docs/assets/`
- never include secrets in prompts or generated artifacts
- regenerate diagrams whenever trust boundaries or flows change

## Documentation Index

- [Documentation Index](docs/README.md)
- [Atlassian OAuth Setup](docs/ATLASSIAN_OAUTH_SETUP.md)
- [Production Deployment](docs/PRODUCTION_DEPLOYMENT.md)
- [Image Generation (Nano Banana)](docs/IMAGE_GENERATION_NANOBANANA.md)
