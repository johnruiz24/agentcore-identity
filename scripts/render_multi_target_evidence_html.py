#!/usr/bin/env python3
"""Render multi-target E2E JSON report into a detailed HTML evidence page."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
from pathlib import Path
from typing import Any


def summarize_response(step: dict[str, Any]) -> str:
    response = step.get("response", {})
    if response.get("error"):
        err = response["error"]
        return f"JSON-RPC error {err.get('code')}: {err.get('message')}"

    result = response.get("result", {})
    if result.get("isError"):
        content = result.get("content") or []
        if content and isinstance(content[0], dict):
            text = content[0].get("text")
            if isinstance(text, str):
                return text[:220]
        return "Tool returned isError=true"

    content = result.get("content") or []
    if content and isinstance(content[0], dict):
        text = content[0].get("text")
        if isinstance(text, str):
            return text[:220]

    return "ok"


def extract_google_event(step: dict[str, Any]) -> tuple[str, str]:
    response = step.get("response", {})
    result = response.get("result", {})
    content = result.get("content") or []
    if not content or not isinstance(content[0], dict):
        return "-", "-"

    text = content[0].get("text")
    if not isinstance(text, str):
        return "-", "-"

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return "-", "-"

    event_id = str(parsed.get("id", "-"))
    event_link = str(parsed.get("htmlLink", "-"))
    return event_id, event_link


def first_status(scenario: dict[str, Any]) -> str:
    steps = scenario.get("steps", [])
    if not steps:
        return "no_steps"
    for s in steps:
        if s.get("status") != "ok":
            return str(s.get("status"))
    return "ok"


def badge(status: str) -> str:
    klass = "ok" if status == "ok" else "error"
    if status == "error_result":
        klass = "error_result"
    return f"<span class='badge {klass}'>{html.escape(status)}</span>"


def esc_pre(obj: Any) -> str:
    return html.escape(json.dumps(obj, indent=2, ensure_ascii=False))


def render(report: dict[str, Any], source_path: Path) -> str:
    scenarios = report.get("scenarios", [])
    total_duration = round(sum(float(s.get("duration_ms", 0.0)) for s in scenarios), 2)
    avg_duration = round(total_duration / len(scenarios), 2) if scenarios else 0.0
    sorted_durations = sorted(float(s.get("duration_ms", 0.0)) for s in scenarios)
    p95_idx = max(int(len(sorted_durations) * 0.95) - 1, 0) if sorted_durations else 0
    p95 = round(sorted_durations[p95_idx], 2) if sorted_durations else 0.0

    by_status: dict[str, int] = {}
    for s in scenarios:
        st = first_status(s)
        by_status[st] = by_status.get(st, 0) + 1

    nav = "".join(
        f"<a href='#q{i+1}'>Q{i+1}</a>" for i in range(len(scenarios))
    )
    chips = " ".join(
        f"<span class='chip'>{html.escape(k)}: {v}</span>" for k, v in sorted(by_status.items())
    )

    rows = []
    for idx, sc in enumerate(scenarios, start=1):
        steps = sc.get("steps", [])
        last = steps[-1] if steps else {}
        status = first_status(sc)
        summary = summarize_response(last)
        consent = html.escape(str(last.get("consent_url", "-")))
        consent_html = "-" if consent == "-" else f"<a href='{consent}' target='_blank'>link</a>"
        google_steps = [s for s in steps if "google-calendar-openapi" in str(s.get("tool_name", ""))]
        event_id, event_link = ("-", "-")
        if google_steps:
            event_id, event_link = extract_google_event(google_steps[-1])

        event_html = html.escape(event_id)
        if event_link and event_link != "-":
            event_html = f"<a href='{html.escape(event_link)}' target='_blank'>{html.escape(event_id)}</a>"

        rows.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td><code>{html.escape(str(sc.get('id', '')))}</code></td>"
            f"<td>{html.escape(str(sc.get('question', '')))}</td>"
            f"<td>{badge(status)}</td>"
            f"<td>{html.escape(str(sc.get('duration_ms', 0.0)))}</td>"
            f"<td>{event_html}</td>"
            f"<td>{html.escape(summary)}</td>"
            f"<td>{consent_html}</td>"
            "</tr>"
        )

    sections = []
    for idx, sc in enumerate(scenarios, start=1):
        step_rows = []
        for st in sc.get("steps", []):
            args = esc_pre(st.get("arguments", {}))
            response = esc_pre(st.get("response", {}))
            summary = html.escape(summarize_response(st))
            step_rows.append(
                "<tr>"
                f"<td>{st.get('index', '-')}</td>"
                f"<td><code>{html.escape(str(st.get('logical_tool', '')))}</code></td>"
                f"<td><code>{html.escape(str(st.get('tool_name', '')))}</code></td>"
                f"<td><code>{html.escape(str(st.get('selected_subagent', '')))}</code></td>"
                f"<td>{badge(str(st.get('status', 'unknown')))}</td>"
                f"<td>{html.escape(str(st.get('duration_ms', 0.0)))}</td>"
                f"<td>{summary}</td>"
                "</tr>"
                f"<tr><td colspan='7'><details><summary>Arguments</summary><pre>{args}</pre></details>"
                f"<details><summary>Raw response</summary><pre>{response}</pre></details></td></tr>"
            )

        sections.append(
            f"<section class='card' id='q{idx}'>"
            f"<h3>Q{idx}. {html.escape(str(sc.get('question', '')))}</h3>"
            f"<p class='meta'><code>{html.escape(str(sc.get('id', '')))}</code> • duration {html.escape(str(sc.get('duration_ms', 0.0)))} ms • status {badge(first_status(sc))}</p>"
            "<div class='table-wrap'><table>"
            "<thead><tr><th>Step</th><th>Logical Tool</th><th>Resolved Tool</th><th>Subagent</th><th>Status</th><th>Duration ms</th><th>Summary</th></tr></thead>"
            f"<tbody>{''.join(step_rows)}</tbody>"
            "</table></div>"
            "</section>"
        )

    generated_at = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%SZ")

    return f"""<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>10 Complex Questions - Runtime Evidence</title>
<link rel='preconnect' href='https://fonts.googleapis.com'>
<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>
<link href='https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap' rel='stylesheet'>
<style>
:root{{--bg:#f4f7ff;--surface:#fff;--surface2:#edf3ff;--border:#d6def0;--text:#0f172a;--muted:#475569;--accent:#0b6bcb;--ok:#13824f;--warn:#b45309;--bad:#b91c1c;--sans:'Space Grotesk',system-ui,sans-serif;--mono:'JetBrains Mono',ui-monospace,monospace;}}
@media (prefers-color-scheme: dark){{:root{{--bg:#0b1220;--surface:#111a2b;--surface2:#17233a;--border:#2d3a55;--text:#e2e8f0;--muted:#9db0ce;--accent:#60a5fa;--ok:#22c55e;--warn:#f59e0b;--bad:#ff8f8f;}}}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(1000px 420px at 90% -20%, rgba(11,107,203,.15), transparent 55%),var(--bg);color:var(--text);font-family:var(--sans)}}
.layout{{display:grid;grid-template-columns:300px 1fr;min-height:100vh}}
.sidebar{{position:sticky;top:0;height:100vh;overflow:auto;padding:20px 14px;background:var(--surface);border-right:1px solid var(--border)}}
.sidebar h1{{margin:0 0 8px;font-size:21px}} .sidebar p{{margin:0 0 12px;color:var(--muted);font-size:13px}}
.nav a{{display:block;text-decoration:none;color:var(--text);padding:7px 10px;border-radius:8px;border:1px solid transparent;margin-bottom:6px;font-size:13px}}
.nav a:hover{{border-color:var(--border);background:var(--surface2)}}
.main{{padding:22px;max-width:1700px}}
.hero,.card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px;margin-bottom:12px}}
.kpis{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin-top:10px}}
.kpi{{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:8px}}
.kpi .l{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}} .kpi .v{{font-family:var(--mono);font-size:15px;margin-top:5px;overflow-wrap:anywhere}}
.chip{{display:inline-block;background:var(--surface2);border:1px solid var(--border);padding:4px 8px;border-radius:999px;font-size:12px;margin-right:6px;margin-top:6px}}
.table-wrap{{overflow:auto;border:1px solid var(--border);border-radius:10px}}
table{{width:100%;border-collapse:collapse;font-size:12px}} th,td{{padding:8px;border-bottom:1px solid var(--border);vertical-align:top;text-align:left;overflow-wrap:anywhere}} th{{position:sticky;top:0;background:var(--surface2);font-family:var(--mono);font-size:11px}}
.badge{{padding:2px 8px;border-radius:999px;border:1px solid var(--border);font-size:11px;font-weight:700}} .badge.ok{{color:var(--ok)}} .badge.error{{color:var(--warn)}} .badge.error_result{{color:var(--bad)}}
.meta{{color:var(--muted);font-size:13px}} details summary{{cursor:pointer;color:var(--accent)}} pre{{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:10px;overflow:auto;font-size:12px}}
@media (max-width:1200px){{.layout{{grid-template-columns:1fr}} .sidebar{{position:relative;height:auto;border-right:0;border-bottom:1px solid var(--border)}} .kpis{{grid-template-columns:1fr 1fr}}}}
</style>
</head>
<body>
<div class='layout'>
  <aside class='sidebar'>
    <h1>10Q Evidence</h1>
    <p>Atlassian + Google live execution</p>
    <nav class='nav'>
      <a href='#summary'>Summary</a>
      <a href='#table'>Question/Answer Table</a>
      {nav}
    </nav>
  </aside>
  <main class='main'>
    <section class='hero' id='summary'>
      <h2>10 Complex Atlassian Questions + 10 Google Calendar Events</h2>
      <p class='meta'>Generated at {generated_at}. Source report: <code>{html.escape(str(source_path))}</code></p>
      <div class='kpis'>
        <div class='kpi'><div class='l'>Total Questions</div><div class='v'>{len(scenarios)}</div></div>
        <div class='kpi'><div class='l'>Total Duration (ms)</div><div class='v'>{total_duration}</div></div>
        <div class='kpi'><div class='l'>Avg Duration (ms)</div><div class='v'>{avg_duration}</div></div>
        <div class='kpi'><div class='l'>P95 Duration (ms)</div><div class='v'>{p95}</div></div>
        <div class='kpi'><div class='l'>Tools Discovered</div><div class='v'>{len(report.get('tools', []))}</div></div>
      </div>
      <div>{chips}</div>
    </section>

    <section class='card' id='table'>
      <h3>10 Questions / Outcomes / Event IDs</h3>
      <div class='table-wrap'>
        <table>
          <thead><tr><th>#</th><th>Scenario</th><th>Question</th><th>Status</th><th>Duration ms</th><th>Google Event</th><th>Response Summary</th><th>Consent URL</th></tr></thead>
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Render detailed multi-target evidence HTML")
    parser.add_argument("--input", required=True, help="Path to run_multi_target_e2e JSON report")
    parser.add_argument("--output", required=True, help="Output HTML path")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    report = json.loads(input_path.read_text())
    html_text = render(report, input_path)
    output_path.write_text(html_text)
    print(f"HTML_FILE={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
