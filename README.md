# AgentCore Identity

Public reference implementation for secure identity orchestration with Amazon Bedrock AgentCore.

This repository shows how to combine:

- Inbound user authentication with Cognito JWT
- AgentCore Gateway tool routing over MCP
- Outbound delegated OAuth for external providers
- Runtime orchestration with explicit identity boundaries

## Core Capabilities

- Zero-trust token handling with AgentCore Identity and credential providers
- Multi-target orchestration pattern (Atlassian + Google Calendar)
- CDK-based infrastructure provisioning
- Python runtime and MCP service integration
- E2E scenario validation assets for mixed target workflows

## Architecture Snapshot

The implementation follows a layered model:

1. Runtime layer: agent execution and orchestration logic
2. Gateway layer: tool discovery/routing through MCP
3. Identity layer: delegated OAuth and token vault boundary
4. Provider targets: external APIs (for example Jira and Calendar)

See visual deep dives in [docs/README.md](docs/README.md).

## Repository Layout

- `src/`: auth, runtime, providers, MCP servers, deployment app code
- `infra/cdk/`: CDK stack project (app entrypoints, stack definitions, Node toolchain files)
- `scripts/`: discovery, validation, and automation helpers
- `scripts/deploy/`: deployment orchestration entrypoints
- `deployment/`: phased deployment scripts and templates
- `examples/`: standalone runtime/demo examples
- `docs/`: architecture, setup, deployment, and article material

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- AWS CLI
- Docker (optional)

### Install dependencies

```bash
npm ci
pip install -r requirements.txt
```

### Configure environment

Use your own values only. Do not commit secrets.

```bash
export AWS_PROFILE=<AWS_PROFILE>
export AWS_REGION=<AWS_REGION>
export AWS_ACCOUNT_ID=<AWS_ACCOUNT_ID>
```

### Run locally (example)

```bash
python entrypoint.py
```

## Deploy (example)

```bash
AWS_PROFILE=<AWS_PROFILE> AWS_REGION=<AWS_REGION> \
(cd infra/cdk && npx cdk deploy BedrockIdentityFull --require-approval never)
```

## Public Release and Sanitization

This repo is sanitized for public sharing:

- Account identifiers and profiles are masked with placeholders
- Email and user-identifying values are masked
- Internal-only planning/audit material is excluded
- Docs were curated to keep only implementation-relevant content

## Documentation

- [Documentation Index](docs/README.md)
- [Atlassian OAuth Setup](docs/ATLASSIAN_OAUTH_SETUP.md)
- [Implementation Guides](docs/IMPLEMENTATION_GUIDES.md)
- [Production Deployment](docs/PRODUCTION_DEPLOYMENT.md)
- [Architecture Notes](docs/architecture/)
- [Article (refined)](docs/medium-article-agentcore-refined.html)
