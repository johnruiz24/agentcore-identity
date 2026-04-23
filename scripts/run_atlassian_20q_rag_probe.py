#!/usr/bin/env python3
"""Run 20 complex Atlassian questions with full invocation evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import time
from pathlib import Path
from typing import Any

import requests

FIELDS = ["key", "summary", "status", "priority", "assignee", "updated", "labels"]

QUESTIONS = [
    ("q01_recent_activity", "Which MLL issues changed most recently and what is their delivery status mix?", "project = MLL ORDER BY updated DESC"),
    ("q02_blockers_open", "Which unresolved MLL issues are marked as blockers or dependencies?", "project = MLL AND (labels in (blocker, dependency) OR text ~ \"dependency\") AND statusCategory != Done ORDER BY priority DESC, updated DESC"),
    ("q03_incident_queue", "List active bug/incident queue in MLL with owners and priorities.", "project = MLL AND issuetype in (Bug, Incident) AND statusCategory != Done ORDER BY priority DESC, updated DESC"),
    ("q04_security_risk", "Find unresolved security/compliance-related MLL work items.", "project = MLL AND (text ~ \"security\" OR text ~ \"compliance\" OR labels in (security, compliance)) AND statusCategory != Done ORDER BY updated DESC"),
    ("q05_data_quality", "Which unresolved MLL tickets mention data quality, data drift, or validation gaps?", "project = MLL AND (text ~ \"data quality\" OR text ~ \"drift\" OR text ~ \"validation\") AND statusCategory != Done ORDER BY updated DESC"),
    ("q06_release_readiness", "Show unresolved release-readiness work in MLL.", "project = MLL AND labels in (release, readiness, go-live) AND statusCategory != Done ORDER BY priority DESC, updated DESC"),
    ("q07_unassigned_open", "Which open MLL issues are unassigned?", "project = MLL AND assignee is EMPTY AND statusCategory != Done ORDER BY updated DESC"),
    ("q08_in_progress_owners", "What MLL work is currently in progress and who owns it?", "project = MLL AND status = \"In Progress\" ORDER BY updated DESC"),
    ("q09_blocked_items", "Which MLL issues are explicitly blocked?", "project = MLL AND status = BLOCKED ORDER BY updated DESC"),
    ("q10_recently_closed", "Which MLL issues were closed most recently?", "project = MLL AND statusCategory = Done ORDER BY updated DESC"),
    ("q11_experiment_pipeline", "What unresolved MLL work mentions experiment or pipeline topics?", "project = MLL AND (text ~ \"experiment\" OR text ~ \"pipeline\") AND statusCategory != Done ORDER BY updated DESC"),
    ("q12_mlops_operability", "Which unresolved MLL tickets mention observability, monitoring, or alerting?", "project = MLL AND (text ~ \"observability\" OR text ~ \"monitoring\" OR text ~ \"alert\") AND statusCategory != Done ORDER BY updated DESC"),
    ("q13_cost_efficiency", "List unresolved MLL cost-optimization or efficiency tickets.", "project = MLL AND (text ~ \"cost\" OR text ~ \"efficiency\" OR text ~ \"optimization\") AND statusCategory != Done ORDER BY updated DESC"),
    ("q14_llm_agentic", "Which unresolved MLL issues mention agentic, MCP, or LLM integration?", "project = MLL AND (text ~ \"agentic\" OR text ~ \"MCP\" OR text ~ \"LLM\") AND statusCategory != Done ORDER BY updated DESC"),
    ("q15_api_integration", "Find unresolved MLL API integration risks and external dependency work.", "project = MLL AND (text ~ \"API\" OR text ~ \"integration\") AND statusCategory != Done ORDER BY updated DESC"),
    ("q16_migration_refactor", "Which unresolved MLL items involve migration, refactor, or architecture changes?", "project = MLL AND (text ~ \"migration\" OR text ~ \"refactor\" OR text ~ \"architecture\") AND statusCategory != Done ORDER BY updated DESC"),
    ("q17_latency_perf", "Which unresolved MLL tickets mention performance, latency, or scalability?", "project = MLL AND (text ~ \"performance\" OR text ~ \"latency\" OR text ~ \"scalability\") AND statusCategory != Done ORDER BY updated DESC"),
    ("q18_qa_testing", "What unresolved MLL work references testing, QA, or flaky behavior?", "project = MLL AND (text ~ \"testing\" OR text ~ \"QA\" OR text ~ \"flaky\") AND statusCategory != Done ORDER BY updated DESC"),
    ("q19_product_feedback", "Which unresolved MLL issues are related to feedback or user-facing pain points?", "project = MLL AND (text ~ \"feedback\" OR text ~ \"user\" OR text ~ \"UX\") AND statusCategory != Done ORDER BY updated DESC"),
    ("q20_sprint_risk_matrix", "Build a sprint risk snapshot from unresolved MLL issues with highest urgency signal.", "project = MLL AND statusCategory != Done ORDER BY priority DESC, updated DESC"),
]


def jsonrpc(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-11-25",
    }
    r = requests.post(url, headers=headers, json=payload, timeout=90)
    r.raise_for_status()
    return r.json()


def extract_consent_url(resp: dict[str, Any]) -> str | None:
    try:
        return resp["error"]["data"]["elicitations"][0]["url"]
    except Exception:
        return None


def is_consent_required(resp: dict[str, Any]) -> bool:
    return resp.get("error", {}).get("code") == -32042


def wait_for_access(
    *,
    gateway_url: str,
    token: str,
) -> tuple[dict[str, Any], int, str | None]:
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "atlassian-openapi-dev3___listAtlassianAccessibleResources", "arguments": {}},
    }
    attempts = 1
    resp = jsonrpc(gateway_url, token, payload)
    if "result" in resp and not resp["result"].get("isError"):
        return resp, attempts, None
    if is_consent_required(resp):
        consent_url = extract_consent_url(resp)
        if consent_url:
            print(f"CONSENT_URL={consent_url}", flush=True)
        raise RuntimeError(
            "Consent required. Open CONSENT_URL once, click Accept, then rerun this command."
        )
    raise RuntimeError(f"Unexpected accessibleResources response: {json.dumps(resp)}")


def parse_issues(raw: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        text = raw["result"]["content"][0]["text"]
        parsed = json.loads(text)
        return parsed.get("issues", [])
    except Exception:
        return []


def answer_from_issues(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "No matching issues found for this query."

    status_counts: dict[str, int] = {}
    for it in issues:
        status = ((it.get("fields") or {}).get("status") or {}).get("name", "Unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    status_mix = ", ".join(f"{k}:{v}" for k, v in sorted(status_counts.items()))
    top = []
    for it in issues[:5]:
        f = it.get("fields") or {}
        key = it.get("key", "?")
        summary = f.get("summary", "(no summary)")
        pr = (f.get("priority") or {}).get("name", "Unknown")
        st = (f.get("status") or {}).get("name", "Unknown")
        owner = (f.get("assignee") or {}).get("displayName", "Unassigned")
        top.append(f"{key}: {summary} | {st} | {pr} | {owner}")

    return f"Matched {len(issues)} issue(s). Status mix [{status_mix}]. Top: " + " || ".join(top)


def render_html(report: dict[str, Any], output: Path) -> None:
    rows = []
    sections = []
    for i, q in enumerate(report["questions"], 1):
        badge = "ok" if q["status"] == "ok" else "error"
        rows.append(
            "<tr>"
            f"<td>{i}</td><td><code>{html.escape(q['id'])}</code></td><td>{html.escape(q['question'])}</td>"
            f"<td><span class='badge {badge}'>{q['status']}</span></td><td>{q['issue_count']}</td><td>{q['duration_ms']}</td>"
            f"<td>{html.escape(q['answer'])}</td>"
            "</tr>"
        )
        sections.append(
            f"<section class='card' id='q{i}'><h3>Q{i}. {html.escape(q['question'])}</h3>"
            f"<p class='meta'><code>{q['id']}</code> • duration={q['duration_ms']}ms • issues={q['issue_count']}</p>"
            f"<p><strong>Answer:</strong> {html.escape(q['answer'])}</p>"
            f"<details><summary>Invocation payload</summary><pre>{html.escape(json.dumps(q['invocation_payload'], indent=2))}</pre></details>"
            f"<details><summary>Raw response</summary><pre>{html.escape(json.dumps(q['raw_response'], indent=2))}</pre></details>"
            "</section>"
        )

    nav = "".join(f"<a href='#q{i}'>Q{i}</a>" for i in range(1, len(report["questions"]) + 1))
    total_ms = round(sum(q["duration_ms"] for q in report["questions"]), 2)

    doc = f"""<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>Atlassian 20Q Bombard Evidence</title>
<link rel='preconnect' href='https://fonts.googleapis.com'><link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>
<link href='https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap' rel='stylesheet'>
<style>
:root{{--bg:#f4f7ff;--surface:#fff;--surface2:#edf3ff;--border:#d6def0;--text:#0f172a;--muted:#475569;--accent:#0b6bcb;--ok:#13824f;--bad:#b91c1c;--sans:'Space Grotesk',system-ui,sans-serif;--mono:'JetBrains Mono',ui-monospace,monospace;}}
@media (prefers-color-scheme: dark){{:root{{--bg:#0b1220;--surface:#111a2b;--surface2:#17233a;--border:#2d3a55;--text:#e2e8f0;--muted:#9db0ce;--accent:#60a5fa;--ok:#22c55e;--bad:#ff8f8f;}}}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(900px 420px at 90% -20%, rgba(11,107,203,.16), transparent 55%),var(--bg);color:var(--text);font-family:var(--sans)}}
.layout{{display:grid;grid-template-columns:290px 1fr;min-height:100vh}}.sidebar{{position:sticky;top:0;height:100vh;overflow:auto;padding:20px 14px;background:var(--surface);border-right:1px solid var(--border)}}
.nav a{{display:block;text-decoration:none;color:var(--text);padding:7px 10px;border-radius:8px;border:1px solid transparent;margin-bottom:6px;font-size:13px}} .nav a:hover{{border-color:var(--border);background:var(--surface2)}}
.main{{padding:22px;max-width:1700px}} .hero,.card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px;margin-bottom:12px}}
.table-wrap{{overflow:auto;border:1px solid var(--border);border-radius:10px}} table{{width:100%;border-collapse:collapse;font-size:12px}} th,td{{padding:8px;border-bottom:1px solid var(--border);vertical-align:top;text-align:left;overflow-wrap:anywhere}} th{{position:sticky;top:0;background:var(--surface2);font-family:var(--mono);font-size:11px}}
.badge{{padding:2px 8px;border-radius:999px;border:1px solid var(--border);font-size:11px;font-weight:700}} .badge.ok{{color:var(--ok)}} .badge.error{{color:var(--bad)}}
.meta{{color:var(--muted);font-size:13px}} details summary{{cursor:pointer;color:var(--accent)}} pre{{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:10px;overflow:auto;font-size:12px}}
</style></head><body>
<div class='layout'><aside class='sidebar'><h1>Atlassian 20Q</h1><p class='meta'>Full invocation evidence</p><nav class='nav'><a href='#summary'>Summary</a><a href='#table'>Table</a>{nav}</nav></aside>
<main class='main'><section class='hero' id='summary'><h2>20 Complex Atlassian Questions (One-shot consent run)</h2>
<p class='meta'>generated_at={html.escape(report['generated_at'])}</p>
<p class='meta'>gateway_url={html.escape(report['gateway_url'])}</p>
<p class='meta'>cloud_id={html.escape(report['cloud_id'])}</p>
<p class='meta'>invocations=20 • total_duration_ms={total_ms}</p></section>
<section class='card' id='table'><h3>Question/Answer Matrix</h3><div class='table-wrap'><table><thead><tr><th>#</th><th>ID</th><th>Question</th><th>Status</th><th>Issue Count</th><th>Duration ms</th><th>Answer</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
{''.join(sections)}</main></div></body></html>"""
    output.write_text(doc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", default="/tmp/atlassian_consent_guard_state.json")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-html", required=True)
    parser.add_argument("--max-results", type=int, default=10)
    args = parser.parse_args()

    st = json.loads(Path(args.state_file).read_text())
    gateway_url = st["gateway_url"]
    token = st["token"]

    jsonrpc(gateway_url, token, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "atlassian-20q-rag", "version": "1.0"}},
    })

    accessible, auth_attempts, consent_url = wait_for_access(
        gateway_url=gateway_url,
        token=token,
    )

    cloud_id = json.loads(accessible["result"]["content"][0]["text"])[0]["id"]

    report = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "gateway_url": gateway_url,
        "cloud_id": cloud_id,
        "auth_attempts": auth_attempts,
        "consent_url": consent_url,
        "questions": [],
    }

    for idx, (qid, qtext, jql) in enumerate(QUESTIONS, start=1):
        payload = {
            "jsonrpc": "2.0",
            "id": 1000 + idx,
            "method": "tools/call",
            "params": {
                "name": "atlassian-openapi-dev3___searchJiraIssuesDetailed",
                "arguments": {
                    "cloudId": cloud_id,
                    "jql": jql,
                    "maxResults": args.max_results,
                    "fields": FIELDS,
                },
            },
        }
        t0 = time.perf_counter()
        raw = jsonrpc(gateway_url, token, payload)
        dur = round((time.perf_counter() - t0) * 1000, 2)

        status = "ok"
        answer = ""
        issues = []

        if raw.get("error"):
            status = "error"
            answer = f"JSON-RPC error {raw['error'].get('code')}: {raw['error'].get('message')}"
        elif raw.get("result", {}).get("isError"):
            status = "error"
            answer = str(raw.get("result", {}).get("content", [{}])[0].get("text", "tool error"))
        else:
            issues = parse_issues(raw)
            answer = answer_from_issues(issues)

        report["questions"].append({
            "id": qid,
            "question": qtext,
            "jql": jql,
            "status": status,
            "issue_count": len(issues),
            "duration_ms": dur,
            "answer": answer,
            "invocation_payload": payload,
            "raw_response": raw,
        })

    Path(args.output_json).write_text(json.dumps(report, indent=2))
    render_html(report, Path(args.output_html))
    print(f"OUTPUT_JSON={args.output_json}")
    print(f"OUTPUT_HTML={args.output_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
