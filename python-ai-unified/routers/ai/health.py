"""/ai/health and /ai/domain-analyzer — health check + domain analyzer page.

Source routes (Server 2 core, present on Server 3):
  - GET /health          -> /ai/health
  - GET /domain-analyzer -> /ai/domain-analyzer (serves a static HTML page)
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["health"])


@router.get("/health")
async def ai_health():
    """AI service health check. Source: GET /health on prompt-enhance (Server 3)."""
    return {
        "status": "healthy",
        "service": "python-ai-unified",
        "namespace": "/ai",
    }


_DOMAIN_ANALYZER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ThinkVelocity Domain Analyzer</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; max-width: 720px; }
    textarea { width: 100%; min-height: 120px; }
    pre { background: #f4f4f5; padding: 1rem; border-radius: 8px; overflow: auto; }
    button { padding: .5rem 1rem; cursor: pointer; }
  </style>
</head>
<body>
  <h1>Domain Analyzer</h1>
  <p>Paste a prompt to analyze its domain, intent, and complexity.</p>
  <textarea id="prompt" placeholder="Enter a prompt..."></textarea>
  <p><button onclick="run()">Analyze</button></p>
  <pre id="out">Results will appear here.</pre>
  <script>
    async function run() {
      const prompt = document.getElementById('prompt').value;
      const out = document.getElementById('out');
      out.textContent = 'Analyzing...';
      try {
        const res = await fetch('/ai/diagnostic/all', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt })
        });
        out.textContent = JSON.stringify(await res.json(), null, 2);
      } catch (e) {
        out.textContent = 'Error: ' + e;
      }
    }
  </script>
</body>
</html>"""


@router.get("/domain-analyzer", response_class=HTMLResponse)
async def domain_analyzer():
    """Serve the domain analyzer HTML page. Source: GET /domain-analyzer (Server 3).

    The canonical Server 3 build ships its own static HTML asset; this is a
    faithful, functional equivalent wired to /ai/diagnostic/all. See RECONCILE.md.
    """
    return HTMLResponse(content=_DOMAIN_ANALYZER_HTML)
