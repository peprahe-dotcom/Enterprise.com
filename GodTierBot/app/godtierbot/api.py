from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

from .service import BotService
from .settings import Mt5PollRequest, Mt5PollResponse, UiState


def create_app(service: BotService) -> FastAPI:
    app = FastAPI(title="GodTierBot", version="0.1.0")

    def require_admin(x_admin_password: str | None = Header(default=None)) -> None:
        if service.settings.admin_password is None:
            raise HTTPException(status_code=409, detail="not_configured")
        if x_admin_password != service.settings.admin_password:
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>GodTierBot</title>
    <style>
      body{font-family:system-ui,Segoe UI,Arial;margin:24px;max-width:720px}
      .row{display:flex;gap:12px;flex-wrap:wrap}
      button{padding:10px 14px;font-size:14px}
      pre{background:#111;color:#eee;padding:12px;border-radius:10px;overflow:auto}
      .muted{opacity:.7}
      input{padding:10px 12px;font-size:14px;width:260px}
    </style>
  </head>
  <body>
    <h2>GodTierBot</h2>
    <div class="row">
      <input id="pw" placeholder="Admin password" />
      <button onclick="pause()">Pause</button>
      <button onclick="resume()">Resume</button>
      <button onclick="refresh()">Refresh</button>
    </div>
    <p class="muted">MT5 WebRequest allowlist must include: http://127.0.0.1:8080</p>
    <pre id="out">Loading...</pre>
    <script>
      async function refresh(){
        const r = await fetch('/health');
        const j = await r.json();
        document.getElementById('out').textContent = JSON.stringify(j,null,2);
      }
      async function pause(){
        const pw = document.getElementById('pw').value;
        const r = await fetch('/control/pause',{method:'POST',headers:{'X-Admin-Password':pw}});
        await refresh();
        if(!r.ok){alert('Pause failed');}
      }
      async function resume(){
        const pw = document.getElementById('pw').value;
        const r = await fetch('/control/resume',{method:'POST',headers:{'X-Admin-Password':pw}});
        await refresh();
        if(!r.ok){alert('Resume failed');}
      }
      refresh();
      setInterval(refresh, 1500);
    </script>
  </body>
</html>
        """.strip()

    @app.get("/health")
    def health() -> dict:
        return {
            "ok": True,
            "paper_mode": service.settings.paper_mode,
            "trading_paused": service.ui.trading_paused,
            "mt5_connected": service.ui.mt5_connected,
            "mt5_last_account": service.ui.mt5_last_account,
        }

    @app.post("/mt5/poll", response_model=Mt5PollResponse)
    def mt5_poll(req: Mt5PollRequest) -> Mt5PollResponse:
        return service.poll_from_mt5(req)

    @app.post("/control/pause", dependencies=[Depends(require_admin)])
    def pause() -> dict:
        service.pause_trading()
        return {"ok": True}

    @app.post("/control/resume", dependencies=[Depends(require_admin)])
    def resume() -> dict:
        service.resume_trading()
        return {"ok": True}

    @app.get("/ui")
    def ui_state() -> UiState:
        return service.ui

    return app
