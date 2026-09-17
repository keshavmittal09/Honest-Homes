"""Operator console — a password-gated page for running scrapes without the CLI.

The point: a teammate (or you, when you don't want a terminal) can collect data
for specific pincodes or RERA ids by filling a form and clicking Run, then watch
the log. It shells out to the SAME tested collector modules, so the console adds
a front door, not a second code path.

It is deliberately LOCAL and gated:
  * Mounted only when HH_OPS_PASSWORD is set (no password -> console disabled).
  * Meant to run on the operator machine (the one with the repo + Python + the
    captured data), reached at http://localhost:8099/ops. Not for the public site.

Karnataka runs are fully autonomous (no captcha). MahaRERA needs a one-time
captcha per ~90 min: the console opens the token window (get_token) for the
operator to solve, exactly as the CLI does -- no Claude, no me.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "data" / "_ops_logs"
router = APIRouter()

# In-memory job registry (single operator machine, so a dict is enough).
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def enabled() -> bool:
    return bool(os.getenv("HH_OPS_PASSWORD"))


def _auth(request: Request) -> None:
    if not enabled():
        raise HTTPException(404)
    supplied = request.headers.get("X-Ops-Key") or request.query_params.get("key") or ""
    if supplied != os.getenv("HH_OPS_PASSWORD"):
        raise HTTPException(401, "bad or missing operator key")


# Only these commands can be launched, and only with argument shapes we build
# here -- never a string from the browser. The console composes argv itself.
def _run(job_id: str, argv: list[str], title: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logf = LOG_DIR / ("%s.log" % job_id)
    with _LOCK:
        _JOBS[job_id] = {"title": title, "argv": argv, "status": "running",
                         "started": time.time(), "log": str(logf)}
    try:
        with open(logf, "w", encoding="utf-8") as f:
            f.write("$ %s\n\n" % " ".join(argv))
            f.flush()
            p = subprocess.Popen(argv, cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT,
                                 env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"})
            with _LOCK:
                _JOBS[job_id]["pid"] = p.pid
            rc = p.wait()
        with _LOCK:
            _JOBS[job_id]["status"] = "done" if rc == 0 else "failed"
            _JOBS[job_id]["rc"] = rc
    except Exception as e:
        with _LOCK:
            _JOBS[job_id]["status"] = "failed"
            _JOBS[job_id]["error"] = str(e)[:200]


def _launch(argv: list[str], title: str) -> str:
    job_id = "%d" % int(time.time() * 1000)
    threading.Thread(target=_run, args=(job_id, argv, title), daemon=True).start()
    return job_id


_PIN = re.compile(r"^\d{6}$")
_RID = re.compile(r"^(?:PR\d{13}|P\d{11})$")


@router.post("/ops/api/run")
async def ops_run(payload: dict, request: Request):
    _auth(request)
    source = str(payload.get("source", ""))
    mode = str(payload.get("mode", ""))
    raw = [x.strip() for x in re.split(r"[,\s]+", str(payload.get("values", ""))) if x.strip()]
    py = sys.executable

    if source == "karnataka":
        # Karnataka: autonomous. build reads whatever the scan cached for the
        # target pincodes; for ad-hoc pincodes we pass them through.
        pins = [p for p in raw if _PIN.match(p)]
        if not pins:
            raise HTTPException(400, "enter one or more 6-digit pincodes")
        argv = [py, "-m", "collector.krera_region", "scan", "--pincodes", ",".join(pins)]
        return {"jobId": _launch(argv, "Karnataka scan: " + ", ".join(pins))}

    if source == "maharera":
        if mode == "ids":
            ids = [r for r in raw if _RID.match(r)]
            if not ids:
                raise HTTPException(400, "enter valid RERA ids (P########### or PR#############)")
            argv = [py, "-m", "collector.fetch_detail_api", "--ids", ",".join(ids), "--max-docs", "0"]
            return {"jobId": _launch(argv, "MahaRERA ids: " + ", ".join(ids))}
        pins = [p for p in raw if _PIN.match(p)]
        if not pins:
            raise HTTPException(400, "enter one or more 6-digit pincodes")
        argv = [py, "-m", "collector.fetch_detail_api", "--pincodes", ",".join(pins), "--max-docs", "0"]
        return {"jobId": _launch(argv, "MahaRERA pincodes: " + ", ".join(pins))}

    raise HTTPException(400, "unknown source")


@router.post("/ops/api/token")
async def ops_token(request: Request):
    """Open the MahaRERA captcha window for the operator to solve (get_token)."""
    _auth(request)
    argv = [sys.executable, "-m", "collector.get_token", "--wait", "1800"]
    return {"jobId": _launch(argv, "MahaRERA token (solve the captcha in the Edge window)")}


@router.get("/ops/api/jobs")
async def ops_jobs(request: Request):
    _auth(request)
    with _LOCK:
        out = []
        for jid, j in sorted(_JOBS.items(), reverse=True)[:20]:
            out.append({"id": jid, "title": j["title"], "status": j["status"],
                        "started": j["started"], "rc": j.get("rc")})
    return {"jobs": out}


@router.get("/ops/api/log")
async def ops_log(request: Request, job: str, tail: int = 120):
    _auth(request)
    with _LOCK:
        j = _JOBS.get(job)
    if not j:
        raise HTTPException(404)
    try:
        lines = Path(j["log"]).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    return {"status": j["status"], "lines": lines[-tail:]}


@router.get("/ops", response_class=HTMLResponse)
async def ops_page():
    if not enabled():
        return HTMLResponse("<h3>Operator console is disabled.</h3>"
                            "<p>Set <code>HH_OPS_PASSWORD</code> in the environment to enable it.</p>",
                            status_code=404)
    return HTMLResponse(_PAGE)


_PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Honest Homes — Operator Console</title>
<style>
  :root{--ink:#1a2530;--ink2:#4a5763;--line:#e6e2da;--brand:#1b4e80;--bg:#f6f3ee;--ok:#1c8456;--bad:#bb3b36;}
  *{box-sizing:border-box} body{margin:0;font-family:'Segoe UI',system-ui,sans-serif;color:var(--ink);background:var(--bg)}
  .wrap{max-width:880px;margin:0 auto;padding:24px 18px}
  h1{font-size:22px;margin:0 0 2px} .sub{color:var(--ink2);font-size:13px;margin-bottom:20px}
  .card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin-bottom:16px}
  label{display:block;font-size:12px;font-weight:650;color:var(--ink2);margin:10px 0 5px}
  input,select,textarea{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px;font:inherit;font-size:14px}
  textarea{min-height:66px;resize:vertical}
  .row{display:flex;gap:12px;flex-wrap:wrap} .row>div{flex:1;min-width:180px}
  button{background:var(--brand);color:#fff;border:0;border-radius:8px;padding:10px 18px;font:inherit;font-weight:650;cursor:pointer;margin-top:14px}
  button.ghost{background:#fff;color:var(--brand);border:1px solid var(--brand)}
  .muted{color:var(--ink2);font-size:12.5px;line-height:1.5}
  pre{background:#12181d;color:#d7e0e6;border-radius:8px;padding:12px;font-size:12px;max-height:340px;overflow:auto;white-space:pre-wrap}
  .pill{display:inline-block;font-size:11px;font-weight:700;padding:2px 9px;border-radius:20px}
  .running{background:#fff4d6;color:#8a6d1a} .done{background:#dcf3e7;color:var(--ok)} .failed{background:#fbe3e2;color:var(--bad)}
</style></head><body><div class="wrap">
  <h1>Honest Homes — Operator Console</h1>
  <div class="sub">Collect data for specific pincodes or RERA ids. Runs on this machine; nothing here is public.</div>

  <div class="card" id="gate">
    <label>Operator key</label>
    <input id="key" type="password" placeholder="the HH_OPS_PASSWORD">
    <button onclick="saveKey()">Unlock</button>
    <div class="muted" id="gatemsg" style="margin-top:8px"></div>
  </div>

  <div id="app" hidden>
    <div class="card">
      <div class="row">
        <div>
          <label>State</label>
          <select id="source" onchange="onSource()">
            <option value="karnataka">Karnataka (Bengaluru) — no captcha, fully automatic</option>
            <option value="maharera">Maharashtra (MahaRERA) — needs a captcha first</option>
          </select>
        </div>
        <div id="modewrap" hidden>
          <label>Look up by</label>
          <select id="mode"><option value="pincodes">Pincodes</option><option value="ids">RERA ids</option></select>
        </div>
      </div>
      <label id="vlabel">Pincodes (comma or space separated)</label>
      <textarea id="values" placeholder="560066, 560037, 560103"></textarea>

      <div id="mahanote" class="muted" hidden style="margin-top:10px;padding:10px 12px;background:var(--bg);border-radius:8px">
        MahaRERA needs a live access token (one captcha, good ~90 min). Click
        <b>Get MahaRERA access</b>, solve the captcha in the window that opens, then Run.
        <div><button class="ghost" onclick="getToken()">Get MahaRERA access</button></div>
      </div>

      <button onclick="run()">Run</button>
    </div>

    <div class="card">
      <div class="row" style="justify-content:space-between;align-items:center">
        <div><b>Jobs</b> <span class="muted">— auto-refreshes</span></div>
        <button class="ghost" style="margin:0" onclick="refresh()">Refresh</button>
      </div>
      <div id="jobs" style="margin-top:10px"></div>
      <pre id="log" hidden></pre>
    </div>
  </div>

<script>
let KEY=localStorage.getItem('ops-key')||'';
const $=id=>document.getElementById(id);
function saveKey(){KEY=$('key').value.trim();localStorage.setItem('ops-key',KEY);check();}
async function api(path,opts={}){opts.headers=Object.assign({'X-Ops-Key':KEY,'Content-Type':'application/json'},opts.headers||{});const r=await fetch(path,opts);if(!r.ok)throw new Error((await r.json().catch(()=>({}))).detail||r.status);return r.json();}
async function check(){try{await api('/ops/api/jobs');$('gate').hidden=true;$('app').hidden=false;onSource();refresh();}catch(e){$('gatemsg').textContent='Key not accepted.';}}
function onSource(){const m=$('source').value==='maharera';$('modewrap').hidden=!m;$('mahanote').hidden=!m;onMode();}
function onMode(){const ids=$('source').value==='maharera'&&$('mode').value==='ids';$('vlabel').textContent=ids?'RERA ids (comma or space separated)':'Pincodes (comma or space separated)';$('values').placeholder=ids?'P52000034056, PR1270002600767':'560066, 560037, 560103';}
$('mode')&&$('mode').addEventListener('change',onMode);
let curJob=null;
async function run(){try{const d=await api('/ops/api/run',{method:'POST',body:JSON.stringify({source:$('source').value,mode:$('mode').value,values:$('values').value})});curJob=d.jobId;refresh();poll();}catch(e){alert(e.message);}}
async function getToken(){try{const d=await api('/ops/api/token',{method:'POST'});curJob=d.jobId;refresh();poll();}catch(e){alert(e.message);}}
async function refresh(){try{const d=await api('/ops/api/jobs');$('jobs').innerHTML=d.jobs.map(j=>`<div style="padding:8px 0;border-top:1px solid var(--line);cursor:pointer" onclick="showLog('${j.id}')"><span class="pill ${j.status}">${j.status}</span> &nbsp;${j.title}</div>`).join('')||'<div class="muted">No jobs yet.</div>';}catch(e){}}
async function showLog(id){curJob=id;poll();}
async function poll(){if(!curJob)return;try{const d=await api('/ops/api/log?job='+curJob+'&tail=200');$('log').hidden=false;$('log').textContent=d.lines.join('\n');$('log').scrollTop=$('log').scrollHeight;if(d.status==='running')setTimeout(poll,2000);else refresh();}catch(e){}}
setInterval(refresh,5000);
if(KEY)check();
</script>
</div></body></html>"""
