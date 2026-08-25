"""Mint one MahaRERA API token from one captcha.

The whole Tier-2 pipeline turns on a single fact: solving one captcha on any
project page mints a bearer token that then works for *every* project for about
90 minutes of wall-clock time. So the human cost of a full region is not 2,700
captchas, it is one captcha per 90 minutes.

`run_detail_assist` can do this, but it is built to walk a list of projects and
capture each one, which makes "did it work?" hard to read. This does exactly one
thing and says so plainly: open a page, wait for you to solve the captcha, then
confirm the token was captured and how long it is good for.

    python -m collector.get_token                 # uses a project in the default region
    python -m collector.get_token --rera P51700000002

Once it prints TOKEN CAPTURED, run:

    python -m collector.fetch_detail_api --region kharghar-panvel --max-docs 0
"""

from __future__ import annotations

import argparse
import base64
import datetime
import json
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = ROOT / "data" / "snapshots" / "detail"

# What `fetch_detail_api._reference()` looks for when it scans captures: a token
# from authenticatePublic, plus at least one real data endpoint path.
DATA_PATHS = ("/public/projectregistartion/", "/complaint/", "/reatappeal/")


def token_seconds_left(tok: str) -> int:
    try:
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        return int(json.loads(base64.urlsafe_b64decode(p))["exp"] - time.time())
    except Exception:
        return -1


def _pick_target(rera: str, region_name: str) -> tuple[str, str, str]:
    """(rera_id, name, detail_url). Any project mints a token that works for all,
    but using one from the region being collected keeps the capture useful."""
    from collector.regions import region as _region

    index_path = ROOT / "data" / "snapshots" / "index" / "2026-06-02" / "rows.jsonl"
    rows = {}
    for line in index_path.open(encoding="utf-8"):
        r = json.loads(line)
        rows[r["rera_id"]] = r

    if rera:
        row = rows.get(rera)
        if not row:
            raise SystemExit("%s is not in the index" % rera)
        return rera, row.get("project_name") or "", row.get("detail_url") or ""

    want = set(_region(region_name)["pincodes"])
    for rid, row in rows.items():
        if str(row.get("pincode") or "") in want and row.get("detail_url"):
            return rid, row.get("project_name") or "", row["detail_url"]
    raise SystemExit("no project with a detail_url found in region %r" % region_name)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rera", default="", help="specific project to open")
    ap.add_argument("--region", default="kharghar-panvel")
    ap.add_argument("--wait", type=int, default=600,
                    help="seconds to wait for the captcha before giving up")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("playwright is not installed:  pip install playwright")

    rid, name, url = _pick_target(args.rera, args.region)
    if not url:
        raise SystemExit("that project has no detail_url in the index")

    captured: list[dict] = []
    seen: set[str] = set()
    all_urls: list[str] = []          # every response, for diagnosis

    def on_response(resp):
        u = resp.url
        all_urls.append(u)
        if "maharera" not in u or u in seen:
            return
        path = urlparse(u).path
        if "authenticatePublic" not in u and not any(p in path for p in DATA_PATHS):
            return
        try:
            body = resp.json()
        except Exception:
            return
        seen.add(u)
        captured.append({"url": u, "status": resp.status, "json": body})

    print("=" * 66)
    print("  MahaRERA token — one captcha, then every project for ~90 minutes")
    print("=" * 66)
    print("  Project : %s" % (name or rid))
    print("  RERA id : %s" % rid)
    print("\n  An Edge window is opening. It may appear BEHIND this terminal —")
    print("  check your taskbar if you do not see it.\n")
    print("  1. Solve the captcha in that window")
    print("  2. Wait for the project page to finish loading")
    print("  3. Leave it alone — this script closes it for you\n")
    print("  Waiting up to %d minutes...\n" % (args.wait // 60))

    out_dir = OUT_ROOT / datetime.date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, channel="msedge")
        ctx = browser.new_context(viewport={"width": 1320, "height": 940},
                                  accept_downloads=True)
        page = ctx.new_page()
        page.on("response", on_response)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print("  (page load warning: %s)" % str(e)[:70])

        deadline = time.time() + args.wait
        token, last_note, reloads = None, 0.0, 0
        while time.time() < deadline:
            # The portal intermittently serves a truncated JS bundle, and its
            # micro-frontend loader then gives up with "Unable to load the app"
            # and never renders the captcha. A reload usually draws a complete
            # copy; without this the wait just runs out against a dead page.
            if not captured and time.time() - last_note > 14:
                try:
                    if "Unable to load the app" in page.content() and reloads < 12:
                        reloads += 1
                        print("    portal served a broken bundle — reloading (%d)"
                              % reloads, flush=True)
                        page.reload(wait_until="domcontentloaded", timeout=60000)
                        time.sleep(3)
                except Exception:
                    pass
            for c in captured:
                if "authenticatePublic" in c["url"]:
                    try:
                        token = c["json"]["responseObject"]["accessToken"]
                    except (KeyError, TypeError):
                        pass
            paths = {urlparse(c["url"]).path for c in captured
                     if any(p in urlparse(c["url"]).path for p in DATA_PATHS)}
            if token and paths:
                # Give the page a moment to finish its remaining calls, so the
                # capture carries the full endpoint list the collector reuses.
                time.sleep(6)
                break
            if time.time() - last_note > 20:
                last_note = time.time()
                # A screenshot of the page the script is actually driving. When
                # nothing is being captured the usual cause is a captcha solved
                # in some other window, and this is the only way to tell.
                shot = OUT_ROOT / ".assist" / "token-page.png"
                shot.parent.mkdir(parents=True, exist_ok=True)
                try:
                    page.screenshot(path=str(shot))
                except Exception:
                    pass
                print("    ... waiting — %d responses seen, %d API calls%s"
                      % (len(all_urls), len(captured),
                         ", TOKEN SEEN" if token else ""))
            time.sleep(1.0)

        try:
            browser.close()
        except Exception:
            pass

    if not token:
        print("\n  NO TOKEN CAPTURED.")
        print("  The captcha was probably not solved, or the page did not finish")
        print("  loading. Re-run and let the project page render fully.")
        raise SystemExit(1)

    paths = [p for p in {urlparse(c["url"]).path for c in captured}
             if any(d in p for d in DATA_PATHS)]
    out = out_dir / ("%s.api.json" % rid)
    out.write_text(json.dumps(captured, ensure_ascii=False), encoding="utf-8")

    left = token_seconds_left(token)
    print("\n" + "=" * 66)
    print("  TOKEN CAPTURED — good for ~%d minutes" % (left // 60))
    print("=" * 66)
    print("  API calls captured : %d" % len(captured))
    print("  Data endpoints     : %d" % len(paths))
    print("  Written to         : %s" % out)
    if not paths:
        print("\n  WARNING: no data endpoints captured. The token is valid but the")
        print("  collector also needs the endpoint list — let the project page")
        print("  finish loading next time.")
    print("\n  Now run:")
    print("    python -m collector.fetch_detail_api --region %s --max-docs 0"
          % args.region)


if __name__ == "__main__":
    main()
