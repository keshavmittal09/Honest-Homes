"""Configure and test lead notifications without hand-editing anything fragile.

The awkward part of Telegram setup is the chat id: BotFather gives you a token
but never the id, and the usual advice is to open a getUpdates URL in a browser
and read raw JSON. This does that for you, and writes the values into .env in
place so an existing key is updated rather than duplicated -- a duplicated key
in a .env is silently resolved by load order, which is exactly the sort of thing
that makes a working config look broken.

    # 1. after creating the bot in @BotFather and sending it any message:
    python -m api.notify_setup chatid --token 1234:AA...     # discovers the id
    python -m api.notify_setup chatid --token 1234:AA... --write

    # 2. gmail: an App Password, never your login password
    python -m api.notify_setup email --user you@gmail.com --pass "abcd efgh ijkl mnop" --write

    # 3. confirm it actually sends
    python -m api.notify_setup status
    python -m api.notify_setup test

Secrets are never printed back: anything that looks like a credential is masked
in all output, so this is safe to run with someone watching your screen.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

import httpx

ENV = Path(__file__).resolve().parent.parent / ".env"

KEYS = {
    "email": ["HH_SMTP_USER", "HH_SMTP_PASS", "HH_NOTIFY_EMAIL"],
    "telegram": ["HH_TELEGRAM_TOKEN", "HH_TELEGRAM_CHAT"],
    "whatsapp": ["HH_CALLMEBOT_PHONE", "HH_CALLMEBOT_KEY"],
}


def mask(v: str) -> str:
    """Enough to recognise a value, never enough to reuse it."""
    if not v:
        return "(empty)"
    if len(v) <= 8:
        return v[0] + "*" * (len(v) - 1)
    return "%s...%s (%d chars)" % (v[:4], v[-2:], len(v))


def env_write(pairs: dict[str, str]) -> None:
    """Update-or-append each key in .env, preserving everything else verbatim."""
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    seen = set()
    out = []
    for line in lines:
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(1) in pairs:
            k = m.group(1)
            out.append("%s=%s" % (k, pairs[k]))
            seen.add(k)
        else:
            out.append(line)
    for k, v in pairs.items():
        if k not in seen:
            out.append("%s=%s" % (k, v))
    ENV.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\nwrote %s:" % ENV)
    for k in pairs:
        print("  %-22s %s" % (k, mask(pairs[k])))


def cmd_chatid(token: str, write: bool) -> int:
    """Read the bot's pending updates and pull out who has messaged it."""
    url = "https://api.telegram.org/bot%s/getUpdates" % token
    try:
        r = httpx.get(url, timeout=15)
    except Exception as e:
        print("could not reach Telegram: %s" % e)
        return 1
    if r.status_code == 404:
        print("Telegram says 404 -- the token is wrong or the bot was deleted.")
        return 1
    data = r.json()
    if not data.get("ok"):
        print("Telegram rejected the token: %s" % data.get("description"))
        return 1

    chats = {}
    for u in data.get("result", []):
        msg = u.get("message") or u.get("edited_message") or u.get("channel_post") or {}
        ch = msg.get("chat") or {}
        if ch.get("id") is not None:
            name = " ".join(x for x in [ch.get("first_name"), ch.get("last_name")] if x) \
                   or ch.get("title") or ch.get("username") or "(no name)"
            chats[ch["id"]] = "%s [%s]" % (name, ch.get("type"))

    if not chats:
        print("No messages found for this bot yet.\n"
              "Open Telegram, find your bot, and send it any message (\"hi\" is fine),\n"
              "then run this again. Telegram only reveals a chat id once the chat exists.")
        return 2

    print("Found %d chat(s):" % len(chats))
    for cid, who in chats.items():
        print("  chat_id %-16s %s" % (cid, who))

    if write:
        if len(chats) > 1:
            print("\nMore than one chat -- pass --chat <id> to choose, not writing.")
            return 2
        cid = str(next(iter(chats)))
        env_write({"HH_TELEGRAM_TOKEN": token, "HH_TELEGRAM_CHAT": cid})
    else:
        print("\nRe-run with --write to save the token and chat id to .env")
    return 0


def cmd_email(user: str, password: str, to: str, write: bool) -> int:
    """Verify the Gmail App Password by actually logging in before saving it."""
    print("testing SMTP login for %s ..." % user)
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as s:
            s.starttls()
            s.login(user, password)
    except smtplib.SMTPAuthenticationError:
        print("Gmail refused the login.\n"
              "  - it must be an App Password, not your normal password\n"
              "  - App Passwords need 2-Step Verification switched on first\n"
              "  - paste it without spaces if you copied it with them")
        return 1
    except Exception as e:
        print("SMTP failed: %s" % e)
        return 1
    print("SMTP login OK")
    if write:
        pairs = {"HH_SMTP_USER": user, "HH_SMTP_PASS": password}
        if to:
            pairs["HH_NOTIFY_EMAIL"] = to
        env_write(pairs)
    else:
        print("Re-run with --write to save to .env")
    return 0


def cmd_status() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV)
    except ImportError:
        pass
    print("notification channels\n")
    any_on = False
    for channel, keys in KEYS.items():
        vals = {k: os.getenv(k, "") for k in keys}
        required = keys[:2]
        on = all(vals[k] for k in required)
        any_on = any_on or on
        print("  %-9s %s" % (channel, "ON" if on else "off"))
        for k in keys:
            print("      %-22s %s" % (k, mask(vals[k])))
    if not any_on:
        print("\nNothing is configured, so /api/lead will store leads but send nothing.")
    return 0


def cmd_test() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV)
    except ImportError:
        pass
    from .notify import notify_lead
    from datetime import datetime

    rec = {"name": "TEST — Honest Homes setup check", "phone": "+91 00000 00000",
           "project": "notification test, safe to ignore", "type": "test",
           "message": "If you are reading this, notifications work.",
           "ts": datetime.now().isoformat(timespec="seconds")}
    res = asyncio.run(notify_lead(rec))
    if not res:
        print("No channel is configured -- nothing was sent. Run `status` first.")
        return 2
    print("send results:")
    for k, v in res.items():
        print("  %-9s %s" % (k, "SENT" if v else "FAILED (see log above)"))
    return 0 if all(res.values()) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("chatid", help="discover your Telegram chat id")
    p.add_argument("--token", required=True)
    p.add_argument("--chat", default="", help="pick one id when the bot has several chats")
    p.add_argument("--write", action="store_true")

    p = sub.add_parser("email", help="verify a Gmail App Password and save it")
    p.add_argument("--user", required=True)
    p.add_argument("--pass", dest="password", required=True)
    p.add_argument("--to", default="", help="recipient (defaults to --user)")
    p.add_argument("--write", action="store_true")

    sub.add_parser("status", help="show which channels are configured")
    sub.add_parser("test", help="send a test notification through every channel")

    a = ap.parse_args()
    if a.cmd == "chatid":
        if a.chat and a.write:
            env_write({"HH_TELEGRAM_TOKEN": a.token, "HH_TELEGRAM_CHAT": a.chat})
            return 0
        return cmd_chatid(a.token, a.write)
    if a.cmd == "email":
        return cmd_email(a.user, a.password.replace(" ", ""), a.to, a.write)
    if a.cmd == "status":
        return cmd_status()
    if a.cmd == "test":
        return cmd_test()
    return 1


if __name__ == "__main__":
    sys.exit(main())
