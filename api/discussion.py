"""Buyer discussion — what people who actually live there say.

The verdict answers "what does the official record show". This answers the
question the record cannot: did possession actually happen, is the water supply
real, what did the builder say when you pushed. Buyers already trade this on
Reddit and in WhatsApp groups; the point of hosting it here is that it sits next
to the sourced record instead of floating free of it.

Three decisions shape the code:

* **Posts are scoped to one project.** No open forum. A thread that cannot
  wander is easier to keep useful and far easier to moderate.
* **Posts answer a prompt.** A blank box produces venting; "Did possession
  happen on time?" produces something the next buyer can compare. The prompt is
  stored with the post so the page can group by question.
* **Identity comes from the lead gate.** The visitor already gave a name and
  phone to unlock the report, so a post can be attributed without a second
  sign-up. The phone is never shown and never returned by the API -- only a
  salted hash is stored, which is enough to rate-limit and to recognise a
  repeat poster without holding a contact list in a public table.

Nothing here is presented as verified fact. The UI must keep it visually distinct
from the record, and every post carries `unverified` so that cannot be forgotten.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import re
from pathlib import Path

import httpx

log = logging.getLogger("hh.discussion")

ROOT = Path(__file__).resolve().parent.parent
LOCAL_FILE = ROOT / "data" / "discussion.jsonl"

TABLE = "discussions"
MAX_BODY = 2000
MIN_BODY = 20

# The questions worth asking a neighbour. Free text is still allowed, but a
# prompt gives the answer somewhere to belong and makes posts comparable.
PROMPTS = [
    {"key": "possession", "label": "Possession & handover",
     "ask": "Did possession happen on time? What was the delay, if any?"},
    {"key": "quality", "label": "Construction quality",
     "ask": "How has the build held up — seepage, fittings, finishing?"},
    {"key": "amenities", "label": "Promised vs delivered",
     "ask": "Which promised amenities actually exist today?"},
    {"key": "builder", "label": "Dealing with the builder",
     "ask": "How did the builder respond when you raised something?"},
    {"key": "society", "label": "Society & maintenance",
     "ask": "Has the society been formed? What is maintenance like?"},
    {"key": "area", "label": "Living in the area",
     "ask": "What is the commute, water supply and daily life really like?"},
    {"key": "other", "label": "Something else",
     "ask": "Anything a buyer should know before they pay?"},
]
PROMPT_KEYS = {p["key"] for p in PROMPTS}

RELATION = {
    "resident": "Lives here",
    "buyer": "Booked a unit",
    "considering": "Considering buying",
    "visited": "Visited the site",
    "other": "Other",
}

# Contact details in a public post are a safety problem, not a feature: they get
# scraped, and a phone number posted in anger is a real-world harm we would be
# the publisher of.
_PHONE = re.compile(r"(?:(?:\+?91[\s-]?)?[6-9]\d{9})")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_URL = re.compile(r"https?://\S+|www\.\S+")


def _salt() -> str:
    # Falls back to a constant so hashing still works undeployed; the value only
    # needs to be secret in production, where the env var is set.
    return os.getenv("HH_HASH_SALT", "honest-homes-local-salt")


def author_hash(phone: str) -> str:
    return hashlib.sha256((_salt() + (phone or "").strip()).encode()).hexdigest()[:32]


def clean_body(text: str) -> tuple[str, list[str]]:
    """Strip contact details. Returns the cleaned text and what was removed, so
    the poster can be told rather than silently edited."""
    removed = []
    out = text
    if _PHONE.search(out):
        out = _PHONE.sub("[phone removed]", out)
        removed.append("a phone number")
    if _EMAIL.search(out):
        out = _EMAIL.sub("[email removed]", out)
        removed.append("an email address")
    if _URL.search(out):
        out = _URL.sub("[link removed]", out)
        removed.append("a link")
    return out, removed


def _display_name(name: str) -> str:
    """First name plus an initial. Full names on a public post about a named
    builder is more exposure than a buyer signed up for."""
    parts = [p for p in (name or "").strip().split() if p]
    if not parts:
        return "A buyer"
    if len(parts) == 1:
        return parts[0][:20]
    return "%s %s." % (parts[0][:20], parts[1][0].upper())


def validate(payload: dict) -> tuple[dict | None, str]:
    body = str(payload.get("body", "")).strip()[:MAX_BODY]
    if len(body) < MIN_BODY:
        return None, "Please write at least %d characters — enough for it to help someone." % MIN_BODY

    rera_id = str(payload.get("projectId", "")).strip()[:40]
    if not rera_id:
        return None, "This post is not attached to a project."

    prompt = str(payload.get("prompt", "other")).strip()
    if prompt not in PROMPT_KEYS:
        prompt = "other"
    relation = str(payload.get("relation", "other")).strip()
    if relation not in RELATION:
        relation = "other"

    cleaned, removed = clean_body(body)
    return {
        "rera_id": rera_id,
        "prompt": prompt,
        "relation": relation,
        "body": cleaned,
        "author": _display_name(payload.get("name", "")),
        "author_hash": author_hash(str(payload.get("phone", ""))),
        "status": "visible",
        "created_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "_removed": removed,
    }, ""


# --------------------------------------------------------------------------
# storage
# --------------------------------------------------------------------------

def _sb() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    return url, os.getenv("SUPABASE_KEY", "")


async def insert(rec: dict) -> bool:
    url, key = _sb()
    if not (url and key):
        return False
    row = {k: v for k, v in rec.items() if not k.startswith("_")}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{url}/rest/v1/{TABLE}",
                headers={"apikey": key, "Authorization": f"Bearer {key}",
                         "Content-Type": "application/json", "Prefer": "return=minimal"},
                json=row,
            )
        if r.status_code in (200, 201, 204):
            return True
        log.error("discussion insert HTTP %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        log.error("discussion insert failed: %s", e)
    return False


async def fetch(rera_id: str, limit: int = 50) -> list[dict]:
    """Visible posts for one project, newest first."""
    url, key = _sb()
    rows: list[dict] = []
    if url and key:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    f"{url}/rest/v1/{TABLE}",
                    headers={"apikey": key, "Authorization": f"Bearer {key}"},
                    params={"rera_id": f"eq.{rera_id}", "status": "eq.visible",
                            "order": "created_at.desc", "limit": str(limit)},
                )
            if r.status_code == 200:
                rows = r.json()
            else:
                log.error("discussion fetch HTTP %s: %s", r.status_code, r.text[:200])
        except Exception as e:
            log.error("discussion fetch failed: %s", e)
    if not rows:
        rows = _local_read(rera_id, limit)
    # The hash exists to recognise a repeat poster server-side. It must never
    # leave the server: it is derived from a phone number.
    return [{k: v for k, v in row.items() if k != "author_hash"} for row in rows]


def local_write(rec: dict) -> None:
    try:
        LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOCAL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({k: v for k, v in rec.items() if not k.startswith("_")},
                               ensure_ascii=False) + "\n")
    except Exception as e:
        log.error("discussion local write failed: %s", e)


def _local_read(rera_id: str, limit: int) -> list[dict]:
    if not LOCAL_FILE.exists():
        return []
    out = []
    try:
        for line in LOCAL_FILE.open(encoding="utf-8"):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("rera_id") == rera_id and row.get("status") == "visible":
                out.append(row)
    except OSError:
        return []
    out.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return out[:limit]


async def report(post_id: str, reason: str) -> bool:
    """Flag a post for review. Hidden immediately, on the principle that a wrong
    hide is recoverable and a wrong publish is not."""
    url, key = _sb()
    if not (url and key) or not post_id:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.patch(
                f"{url}/rest/v1/{TABLE}",
                headers={"apikey": key, "Authorization": f"Bearer {key}",
                         "Content-Type": "application/json", "Prefer": "return=minimal"},
                params={"id": f"eq.{post_id}"},
                json={"status": "reported", "report_reason": str(reason)[:200]},
            )
        return r.status_code in (200, 204)
    except Exception as e:
        log.error("discussion report failed: %s", e)
        return False
