"""One real, interactive synthetic UI, delivered either as HTML or an in-memory browser document.

No business-data API exists. JavaScript holds this local fixture's synthetic records and
runtime states. The agent can only interact through the browser Surface port. Inline mode
makes no network requests and does not alter any managed browser navigation policies.
"""
import html
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

SCENARIOS = {"normal", "notice", "transient", "outage", "session", "permission", "dialog", "slow", "drift", "ambiguous"}
STYLE = """
:root {font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;color:#18283a;background:#eef3f8}
* {box-sizing:border-box}
body {margin:0;padding:30px;background:#e8edf2}
h1 {font-size:25px;letter-spacing:-.35px;margin:0 0 18px} h2 {font-size:17px;margin:0 0 8px}
p {line-height:1.55} table {border-collapse:collapse;width:100%}
td {padding:13px 16px;border-bottom:1px solid #e2e8f0} tr:last-child td {border-bottom:0}
.layout {background:#fff;width:100%;border:1px solid #9aa9b8;border-radius:0;box-shadow:none;overflow:hidden}
.layout>tbody>tr>td {padding:26px}.field-table {max-width:610px;margin-bottom:16px}
.field-table td:first-child {font-size:13px;font-weight:700;color:#52677d;width:170px}
button,a {display:inline-block;padding:10px 16px;border-radius:0;font:inherit;font-size:14px}
button {background:#1e675d;color:#fff;border:1px solid #174f48;cursor:pointer;font-weight:700}
button:hover {background:#18574f} a {color:#225f78;font-weight:650;text-decoration:none} a:hover {text-decoration:underline}
input {width:100%;padding:11px 12px;border:1px solid #7f8f9f;border-radius:0;font:inherit}
.data-table {margin:4px 0 8px;border:1px solid #9aa9b8}
.data-table th,.data-table td {padding:12px 14px;border:1px solid #b8c3ce;text-align:left}
.data-table th {width:190px;background:#e7ebef;color:#334b61;font-size:13px;font-weight:700}
.data-table .label-cell {width:190px;background:#e7ebef;color:#334b61;font-size:13px;font-weight:700}
.data-table thead th {width:auto;background:#dce3e9}
.data-table .account-link {padding:0;color:#174f73;text-decoration:underline;font-weight:700}
.data-table .account-link:hover {color:#0e3856}
.actions {display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:18px}
.actions a {display:inline-flex;align-items:center;justify-content:center;min-height:40px;background:#1e675d;color:#fff;border:1px solid #174f48;border-radius:0;padding:10px 16px;font-weight:700;text-decoration:none!important;box-shadow:none}
.actions a:hover {background:#18574f;color:#fff;text-decoration:none}.actions a.secondary-action {background:#fff;color:#36546f;border-color:#b9c7d5;box-shadow:none}.actions a.secondary-action:hover {background:#eef3f7;color:#263f57}
.test-note {margin:14px 0 0;color:#65778a;font-size:12px;line-height:1.7}.test-note strong {color:#40576d}.test-note code {font:600 12px ui-monospace,SFMono-Regular,Consolas,monospace;color:#234c45;background:#eef5f3;border-radius:4px;padding:2px 4px}
.alert {border-left:4px solid #b45353;background:#fff5f5;padding:14px 16px;border-radius:0}
.quiet {color:#667588;font-size:12px;margin-top:15px} iframe {width:100%;height:720px;border:1px solid #9aa9b8;border-radius:0;background:#fff;box-shadow:none}
@media(max-width:700px){body{padding:18px}.layout>tbody>tr>td{padding:19px}}
"""


def sandbox_html(scenario: str = "normal") -> str:
    if scenario not in SCENARIOS:
        raise ValueError("unknown sandbox scenario")
    script = (Path(__file__).parent / "static" / "sandbox.js").read_text()
    script = "const SANDBOX_SCENARIO = " + json.dumps(scenario) + ";\n" + script
    workspace = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                 '<title>Legacy workspace</title><style>' + STYLE + '</style></head><body>'
                 '<main></main><p class="quiet">Synthetic data only</p><script>' + script + '</script></body></html>')
    version = "2" if scenario == "drift" else "1"
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<link rel="icon" href="data:,"><title>Legacy servicing sandbox</title>'
            '<style>' + STYLE + '</style></head><body><h1>Legacy Servicing / version ' + version + '</h1>'
            '<iframe title="Legacy workspace" srcdoc="' + html.escape(workspace, quote=True) + '"></iframe></body></html>')


def create_sandbox() -> FastAPI:
    app = FastAPI(title="Legacy Servicing UI Sandbox", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health():
        return {"status": "ok", "synthetic_only": True}

    @app.get("/legacy")
    async def legacy(scenario: str = "normal"):
        if scenario not in SCENARIOS:
            return JSONResponse({"code": "UNKNOWN_SCENARIO"}, status_code=400)
        return HTMLResponse(sandbox_html(scenario), headers={
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-src 'self' about:; img-src data:; frame-ancestors 'self'; form-action 'none'; base-uri 'none'",
        })

    return app
