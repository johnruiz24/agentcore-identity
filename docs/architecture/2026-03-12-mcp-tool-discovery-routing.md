# MCP Tool Discovery and Routing (Google + Atlassian)

## How the Agent Knows Which Tools It Can Use

The agent does **not** hardcode target tools.

At runtime it does:

1. `initialize` on Gateway MCP endpoint.
2. `tools/list` to fetch all exposed tools.
3. Reads each tool `name` and `inputSchema`.
4. Selects the minimal set of tools that can satisfy the user request.
5. Calls `tools/call` with validated arguments.

Current discovered tools in `<ENVIRONMENT>`:

- `x_amz_bedrock_agentcore_search`
- `atlassian-openapi-<ENVIRONMENT>___listAtlassianAccessibleResources`
- `atlassian-openapi-<ENVIRONMENT>___searchJiraIssues`
- `atlassian-openapi-<ENVIRONMENT>___searchJiraProjects`
- `google-calendar-openapi-<ENVIRONMENT>___createCalendarEvent`

## Cross-Target Orchestration Pattern

For mixed Jira + Calendar queries, the typical chain is:

1. Atlassian site discovery: `listAtlassianAccessibleResources`
2. Jira project/issue lookup: `searchJiraProjects` and/or `searchJiraIssues`
3. Calendar action: `createCalendarEvent`

If outbound OAuth token is missing for a tool target, Gateway returns:

- error code `-32042`
- `elicitations.url` (consent URL)

After user consent, the same flow can continue and tool calls execute.

## Test Assets Added

- Scenario file: `tests/e2e/data/multi_target_complex_questions.json`
- Scenario validator tests: `tests/e2e/test_multi_target_scenarios.py`
- E2E runner: `scripts/run_multi_target_e2e.py`

## Run Commands

Dry run (plan + tool mapping only):

```bash
python scripts/run_multi_target_e2e.py \
  --gateway-id <GATEWAY_ID> \
  --mode dry-run
```

Live run (real `tools/call` invocations):

```bash
python scripts/run_multi_target_e2e.py \
  --gateway-id <GATEWAY_ID> \
  --mode live
```

Live report file:

- `/tmp/multi_target_e2e_live.json`
