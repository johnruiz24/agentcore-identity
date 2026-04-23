# ADR-2026-02-25: Hybrid OAuth2 Baseline Selection

Date: 2026-02-25  
Status: accepted

## Context
The repository has multiple active stacks with overlapping intent and inconsistent documentation.
Decisions must be based on observed AWS resources, not stack naming.

Evidence source:
- Internal validation notes (not published in the public repository).

## Decision
Adopt hybrid OAuth2 architecture as target:
- Inbound auth/authz: Cognito JWT at gateway boundary.
- Outbound MCP access: provider OAuth via Identity/Vault boundary.

Promoted baseline:
- `bedrock-agentcore-identity-dev`

Promotion rule:
1. Candidate was smoke-validated and accepted.
2. If subsequent functional MCP tests fail, create a new clean stack and deprecate ambiguous predecessors.

## Consequences
Positive:
- Reduces ambiguity and drift.
- Aligns with enterprise security boundary model.
- Preserves optional path to new stack if current baseline is insufficient.

Negative:
- Requires explicit acceptance test suite and deprecation cleanup.
- Short-term dual-stack complexity remains until decision is finalized.

## Next Actions
- Execute functional MCP invocation tests with protocol-valid payloads.
- Complete outbound OAuth vault contract hardening and tests.
- Mark legacy/non-baseline stacks as deprecated in canonical docs.
