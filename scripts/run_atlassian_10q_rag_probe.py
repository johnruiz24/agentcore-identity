#!/usr/bin/env python3
"""Run 10 additional Atlassian questions and produce RAG-like answers + HTML evidence."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import time
from pathlib import Path
from typing import Any

import requests

FIELDS = ["key", "summary", "status", "priority", "assignee", "updated"]

QUESTIONS = [
    {
        "id": "atl_q1_recent_activity",
        "question": "Which MLL issues were updated most recently, and what are their current statuses?",
        "jql": "project = MLL ORDER BY updated DESC",
    },
    {
        "id": "atl_q2_open_high_priority",
        "question": "Which high-priority MLL issues are still not done?",
        "jql": "project = MLL AND priority in (\"P1 - High\", \"P2 - Medium High\", Highest, High) AND statusCategory != Done ORDER BY priority DESC, updated DESC",
    },
    {
        "id": "atl_q3_in_progress_work",
        "question": "What MLL work is currently in progress and who owns it?",
        "jql": "project = MLL AND status = \"In Progress\" ORDER BY updated DESC",
    },
    {
        "id": "atl_q4_dependency_risk",
        "question": "What unresolved MLL issues mention dependencies?",
        "jql": "project = MLL AND text ~ \"dependency\" AND statusCategory != Done ORDER BY updated DESC",
    },
    {
        "id": "atl_q5_incident_bug_queue",
        "question": "What open bugs/incidents are active in MLL right now?",
        "jql": "project = MLL AND issuetype in (Bug, Incident) AND statusCategory != Done ORDER BY updated DESC",
    },
    {
        "id": "atl_q6_security_compliance",
        "question": "What unresolved MLL items are related to security or compliance?",
        "jql": "project = MLL AND (text ~ \"security\" OR text ~ \"compliance\") AND statusCategory != Done ORDER BY updated DESC",
    },
    {
        "id": "atl_q7_model_drift",
        "question": "What unresolved MLL issues discuss model drift or regression?",
        "jql": "project = MLL AND (text ~ \"drift\" OR text ~ \"regression\") AND statusCategory != Done ORDER BY updated DESC",
    },
    {
        "id": "atl_q8_unassigned_open",
        "question": "Which open MLL issues have no assignee?",
        "jql": "project = MLL AND assignee is EMPTY AND statusCategory != Done ORDER BY updated DESC",
    },
    {
        "id": "atl_q9_recently_closed",
        "question": "Which MLL issues were closed most recently?",
        "jql": "project = MLL AND statusCategory = Done ORDER BY updated DESC",
    },
    {
        "id": "atl_q10_pipeline_experiment",
        "question": "What unresolved MLL issues mention pipeline or experiment work?",
        "jql": "project = MLL AND (text ~ \"pipeline\" OR text ~ \"experiment\") AND statusCategory != Done ORDER BY updated DESC",
    },
]


def jsonrpc(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-11-25",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=90)
    response.raise_for_status()
    return response.json()


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8"))
    except Exception:
        return {}


def ensure_user_bound_token(token: str) -> None:
    claims = _decode_jwt_payload(token)
    if "username" not in claims and "cognito:username" not in claims:
        raise RuntimeError(
            "Refusing to run 10Q with non-user token (likely client_credentials). "
            "Use USER_FEDERATION user JWT."
        )


def summarize_issues(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "No matching issues found for this query."

    lines = []
    for issue in issues[:5]:
        key = issue.get("key", "?")
        fields = issue.get("fields", {})
        summary = fields.get("summary", "(no summary)")
        status = (fields.get("status") or {}).get("name", "Unknown")
        priority = (fields.get("priority") or {}).get("name", "Unknown")
        assignee = (fields.get("assignee") or {}).get("displayName", "Unassigned")
        lines.append(f"{key}: {summary} | status={status} | priority={priority} | assignee={assignee}")

    return f"Matched {len(issues)} issue(s). Top results: " + " || ".join(lines)


def render_html(report: dict[str, Any], output_html: Path) -> None:
    scenarios = report["questions"]
    total = len(scenarios)
    total_ms = round(sum(q["duration_ms"] for q in scenarios), 2)
    avg_ms = round(total_ms / total, 2) if total else 0

    rows = []
    sections = []
    for idx, q in enumerate(scenarios, 1):
        status = q.get("status", "unknown")
        badge = "ok" if status == "ok" else "error"
        rows.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td><code>{html.escape(q['id'])}</code></td>"
            f"<td>{html.escape(q['question'])}</td>"
            f"<td><span class='badge {badge}'>{html.escape(status)}</span></td>"
            f"<td>{q['issue_count']}</td>"
            f"<td>{q['duration_ms']}</td>"
            f"<td>{html.escape(q['answer'])}</td>"
            "</tr>"
        )

        sections.append(
            f"<section class='card' id='q{idx}'>"
            f"<h3>Q{idx}. {html.escape(q['question'])}</h3>"
            f"<p class='meta'><code>{html.escape(q['id'])}</code> • issue_count={q['issue_count']} • duration={q['duration_ms']}ms</p>"
            f"<p><strong>Answer:</strong> {html.escape(q['answer'])}</p>"
            f"<details><summary>JQL</summary><pre>{html.escape(q['jql'])}</pre></details>"
            f"<details><summary>Raw response</summary><pre>{html.escape(json.dumps(q.get('raw_response', {}), indent=2))}</pre></details>"
            "</section>"
        )

    nav = "".join(f"<a href='#q{i}'>Q{i}</a>" for i in range(1, total + 1))

    html_text = f"""<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>Atlassian 10Q RAG Evidence</title>
<link rel='preconnect' href='https://fonts.googleapis.com'>
<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>
<link href='https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap' rel='stylesheet'>
<style>
:root{{--bg:#f4f7ff;--surface:#fff;--surface2:#edf3ff;--border:#d6def0;--text:#0f172a;--muted:#475569;--accent:#0b6bcb;--ok:#13824f;--bad:#b91c1c;--sans:'Space Grotesk',system-ui,sans-serif;--mono:'JetBrains Mono',ui-monospace,monospace;}}
@media (prefers-color-scheme: dark){{:root{{--bg:#0b1220;--surface:#111a2b;--surface2:#17233a;--border:#2d3a55;--text:#e2e8f0;--muted:#9db0ce;--accent:#60a5fa;--ok:#22c55e;--bad:#ff8f8f;}}}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(900px 420px at 90% -20%, rgba(11,107,203,.16), transparent 55%),var(--bg);color:var(--text);font-family:var(--sans)}}
.layout{{display:grid;grid-template-columns:290px 1fr;min-height:100vh}}
.sidebar{{position:sticky;top:0;height:100vh;overflow:auto;padding:20px 14px;background:var(--surface);border-right:1px solid var(--border)}}
.nav a{{display:block;text-decoration:none;color:var(--text);padding:7px 10px;border-radius:8px;border:1px solid transparent;margin-bottom:6px;font-size:13px}} .nav a:hover{{border-color:var(--border);background:var(--surface2)}}
.main{{padding:22px;max-width:1700px}} .hero,.card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px;margin-bottom:12px}}
.kpis{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:10px}} .kpi{{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:8px}}
.kpi .l{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}} .kpi .v{{font-family:var(--mono);font-size:15px;margin-top:5px;overflow-wrap:anywhere}}
.table-wrap{{overflow:auto;border:1px solid var(--border);border-radius:10px}} table{{width:100%;border-collapse:collapse;font-size:12px}} th,td{{padding:8px;border-bottom:1px solid var(--border);vertical-align:top;text-align:left;overflow-wrap:anywhere}} th{{position:sticky;top:0;background:var(--surface2);font-family:var(--mono);font-size:11px}}
.badge{{padding:2px 8px;border-radius:999px;border:1px solid var(--border);font-size:11px;font-weight:700}} .badge.ok{{color:var(--ok)}} .badge.error{{color:var(--bad)}}
.meta{{color:var(--muted);font-size:13px}} details summary{{cursor:pointer;color:var(--accent)}} pre{{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:10px;overflow:auto;font-size:12px}}
@media (max-width:1200px){{.layout{{grid-template-columns:1fr}} .sidebar{{position:relative;height:auto;border-right:0;border-bottom:1px solid var(--border)}} .kpis{{grid-template-columns:1fr 1fr}}}}
</style>
</head>
<body>
<div class='layout'>
  <aside class='sidebar'>
    <h1>Atlassian 10Q</h1>
    <p class='meta'>RAG-like evidence</p>
    <nav class='nav'><a href='#summary'>Summary</a><a href='#table'>Q/A Table</a>{nav}</nav>
  </aside>
  <main class='main'>
    <section class='hero' id='summary'>
      <h2>10 Additional Atlassian Questions with Interpreted Answers</h2>
      <p class='meta'>Generated at {html.escape(report['generated_at'])}</p>
      <div class='kpis'>
        <div class='kpi'><div class='l'>Questions</div><div class='v'>{total}</div></div>
        <div class='kpi'><div class='l'>Total Duration ms</div><div class='v'>{total_ms}</div></div>
        <div class='kpi'><div class='l'>Average ms</div><div class='v'>{avg_ms}</div></div>
        <div class='kpi'><div class='l'>Cloud ID</div><div class='v'>{html.escape(report['cloud_id'])}</div></div>
      </div>
    </section>

    <section class='card' id='table'>
      <h3>Questions and Answers</h3>
      <div class='table-wrap'>
        <table>
          <thead><tr><th>#</th><th>ID</th><th>Question</th><th>Status</th><th>Issue Count</th><th>Duration ms</th><th>Answer</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>

    {''.join(sections)}
  </main>
</div>
</body>
</html>
"""
    output_html.write_text(html_text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", default="/tmp/atlassian_live_state.json")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-html", required=True)
    parser.add_argument("--max-results", type=int, default=8)
    args = parser.parse_args()

    state = json.loads(Path(args.state_file).read_text())
    gateway_url = state["gateway_url"]
    token = state["token"]
    ensure_user_bound_token(token)

    jsonrpc(
        gateway_url,
        token,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "atlassian-10q-rag", "version": "1.0"},
            },
        },
    )

    accessible = jsonrpc(
        gateway_url,
        token,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "atlassian-openapi-dev3___listAtlassianAccessibleResources",
                "arguments": {},
            },
        },
    )
    resources_text = accessible["result"]["content"][0]["text"]
    resources = json.loads(resources_text)
    cloud_id = resources[0]["id"]

    report = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "gateway_url": gateway_url,
        "cloud_id": cloud_id,
        "questions": [],
    }

    for idx, question in enumerate(QUESTIONS, start=1):
        started = time.perf_counter()
        payload = {
            "jsonrpc": "2.0",
            "id": 1000 + idx,
            "method": "tools/call",
            "params": {
                "name": "atlassian-openapi-dev3___searchJiraIssuesDetailed",
                "arguments": {
                    "cloudId": cloud_id,
                    "jql": question["jql"],
                    "maxResults": args.max_results,
                    "fields": FIELDS,
                },
            },
        }
        raw = jsonrpc(gateway_url, token, payload)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        q_out = {
            "id": question["id"],
            "question": question["question"],
            "jql": question["jql"],
            "duration_ms": duration_ms,
            "status": "ok",
            "issue_count": 0,
            "answer": "",
            "raw_response": raw,
        }

        if raw.get("error"):
            q_out["status"] = "error"
            q_out["answer"] = f"JSON-RPC error {raw['error'].get('code')}: {raw['error'].get('message')}"
            report["questions"].append(q_out)
            continue

        if raw.get("result", {}).get("isError"):
            q_out["status"] = "error"
            text = raw.get("result", {}).get("content", [{}])[0].get("text", "Tool error")
            q_out["answer"] = str(text)
            report["questions"].append(q_out)
            continue

        try:
            text = raw["result"]["content"][0]["text"]
            parsed = json.loads(text)
            issues = parsed.get("issues", [])
        except Exception:
            issues = []

        q_out["issue_count"] = len(issues)
        q_out["answer"] = summarize_issues(issues)
        report["questions"].append(q_out)

    output_json = Path(args.output_json)
    output_html = Path(args.output_html)
    output_json.write_text(json.dumps(report, indent=2))
    render_html(report, output_html)

    print(f"OUTPUT_JSON={output_json}")
    print(f"OUTPUT_HTML={output_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
