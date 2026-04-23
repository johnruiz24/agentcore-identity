# AgentCore Identity

Production-grade reference for identity-safe AI agent orchestration on Amazon Bedrock AgentCore.

This project addresses one hard problem: how to let an agent call multiple external systems with delegated user OAuth without leaking trust boundaries.

## Hero Image

High-level architecture overview (runtime, gateway, identity, providers) in one view:

![AgentCore Identity Architecture Hero](docs/assets/agentcore-readme-hero-nanobanana.png)

## Readme Structure

This README is intentionally organized in this order:

1. Hero image
2. Problem and scope
3. Architecture visuals with context
4. Repository structure
5. Quick start and deploy
6. Image generation workflow

## Problem and Scope

### Problem statement

Teams are moving AI agents from demos to production, but identity architecture is usually the first breaking point.
In most implementations, runtime orchestration, token exchange, and provider access are mixed in the same execution path.
That coupling creates three recurring failures:

1. Token custody drift:
   - delegated OAuth artifacts are handled outside a hardened identity boundary
   - credentials leak into runtime logs, process memory, or ad hoc storage
2. Boundary ambiguity:
   - runtime components become responsible for both orchestration and trust decisions
   - JWT validation, scope enforcement, and provider access controls are not isolated
3. Operational fragility:
   - consent interruption paths are under-specified
   - callback resume behavior is inconsistent across providers

### What this repository is designed to solve

This repository is a reference implementation for identity-safe agent orchestration on Bedrock AgentCore, with explicit separation between:

- runtime orchestration (intent + tool selection)
- gateway enforcement and MCP routing
- identity boundary (delegated OAuth exchange + token vault custody)
- external provider execution with scoped delegated credentials

### Scope of the implementation

- Inbound identity validation with Cognito JWT
- MCP tool discovery and routing through AgentCore Gateway
- Outbound delegated OAuth through AgentCore Identity token vault
- Multi-target orchestration (Atlassian + Google Calendar)
- CDK infrastructure isolated from runtime code

### Success criteria

- Runtime can invoke provider actions without directly owning provider secrets.
- OAuth consent and callback are resumable and auditable.
- JWT/scope enforcement and token custody remain in dedicated trust boundaries.
- Infrastructure and runtime concerns are deployable independently.

## Architecture Visuals

### 1) System Map: Runtime, Gateway, Identity, Providers

This section expands the hero image above and explains ownership boundaries in detail.

How to read this image:

1. Start at the **Runtime zone**:
   - This is where prompt orchestration, intent handling, and tool selection occur.
   - Runtime decides *what to call*, but does not own OAuth tokens.
2. Move to the **Gateway zone (MCP)**:
   - This is the protocol boundary for `tools/list` and `tools/call`.
   - Gateway handles routing and contract-level controls before external access.
3. Move to the **Identity zone**:
   - This is the only place where delegated OAuth token exchange and vault operations happen.
   - Keeping this separate is the key security decision in this repo.
4. End at **External providers**:
   - Atlassian and Google APIs are called with delegated, scoped credentials.
   - Provider calls are the output of validated routing + identity checks.

What architectural decision this image communicates:

- The system is intentionally split so runtime logic and credential custody are isolated.
- Control plane and credential plane are not collapsed into the same layer.

### 2) Delegated OAuth Flow Sequence

This sequence explains the exact lifecycle of a user request that requires provider access.

![Delegated OAuth Sequence](docs/assets/agentcore-readme-oauth-sequence-nanobanana.png)

How to read this image:

1. Request enters the gateway and available tools are discovered (`tools/list`).
2. A provider-specific call is attempted (`tools/call`).
3. If delegated consent is missing, the flow emits an OAuth consent URL.
4. User completes consent and callback returns to the identity boundary.
5. Identity performs code exchange and persists delegated token material.
6. Original operation is retried with scoped delegated credentials.
7. Gateway returns normalized response to runtime/client.

Operational value of this image:

- It clarifies where interruptions are expected (consent step).
- It shows why the flow is resumable after callback.
- It makes explicit where to instrument logs/traces for failure diagnosis.

### 3) Zero-Trust Boundary Model

This model is security-first: it defines what each zone is allowed to see and do.

![Zero-Trust Boundary Map](docs/assets/agentcore-readme-zero-trust-nanobanana.png)

How to read this image:

1. Vertical boundaries represent trust cuts between runtime, gateway, identity, and provider planes.
2. Lock/shield markers represent policy enforcement points.
3. Labels such as JWT validation, token vault, and scoped OAuth mark where security controls are anchored.

Security assumptions encoded by this image:

- Runtime must never directly persist or own provider secrets.
- Token handling is constrained to the identity boundary.
- Gateway is an enforcement and routing boundary, not a token vault.
- External providers are reachable only through scoped delegated access.

Audit checklist derived from this image:

- Verify JWT and scope enforcement at ingress/gateway.
- Verify token vault access is restricted to identity paths only.
- Verify provider calls always use delegated scoped credentials.
- Verify logs avoid leaking raw token material.

### Code Mapping (Image -> Implementation Surface)

- System map:
  - runtime orchestration in `src/agents/`
  - gateway and service wiring in `src/deployment/`
  - identity and OAuth boundaries in `src/auth/` and `src/vault/`
- OAuth sequence:
  - request/flow scripts in `scripts/` (discovery, consent, E2E flows)
  - provider logic in `src/providers/`
- Zero-trust model:
  - scope and auth policy in `src/auth/`
  - secure credential handling in `src/vault/` and `src/storage/`

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
