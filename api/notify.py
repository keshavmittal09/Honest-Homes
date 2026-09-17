"""Instant notification when a visitor submits the unlock/lead form.

Fires from /api/lead on every submission. Three channels, each turned on purely
by setting its environment variables -- nothing sends until configured, and any
combination can run at once:

  Email (Gmail SMTP, free)
      HH_SMTP_USER   your gmail address
      HH_SMTP_PASS   a Gmail *App Password* (Google account -> Security ->
                     2-Step Verification -> App passwords). NOT your login password.
      HH_NOTIFY_EMAIL  where to send (defaults to HH_SMTP_USER)

  Telegram (free, most reliable instant push)
      HH_TELEGRAM_TOKEN   from @BotFather
      HH_TELEGRAM_CHAT    your chat id (message the bot, then read it from
                          https://api.telegram.org/bot<TOKEN>/getUpdates)

  WhatsApp (CallMeBot, free but third-party/rate-limited)
      HH_CALLMEBOT_PHONE  your number with country code, e.g. 9198xxxxxxx
      HH_CALLMEBOT_KEY    the api key CallMeBot gives you after the one-time
                          activation message (see callmebot.com/apps/)

Design: notifications must NEVER break or slow a submission. Every channel is
wrapped so a failure is logged and swallowed -- the visitor's form still
succeeds, and one dead channel does not stop the others.
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import urllib.parse
from email.message import EmailMessage

import httpx

log = logging.getLogger("hh.notify")


def _lines(rec: dict) -> tuple[str, str]:
    """(subject, body) for one lead. Phone shown in full here because this goes
    only to the operator, not publicly."""
    who = rec.get("name") or "Someone"
    proj = rec.get("project") or rec.get("project_id") or "(no project)"
    subject = "New Honest Homes lead: %s" % who
    body = (
        "New form submission on Honest Homes\n\n"
        "Name    : %s\n"
        "Phone   : %s\n"
        "Project : %s\n"
        "Type    : %s\n"
        "Message : %s\n"
        "Time    : %s\n"
    ) % (who, rec.get("phone") or "-", proj, rec.get("type") or "lead",
         rec.get("message") or "-", rec.get("ts") or "-")
    return subject, body


def _send_email(subject: str, body: str) -> None:
    user = os.getenv("HH_SMTP_USER", "")
    pw = os.getenv("HH_SMTP_PASS", "")
    if not (user and pw):
        return
    to = os.getenv("HH_NOTIFY_EMAIL", user)
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    # Blocking smtplib call — run it off the event loop via asyncio.to_thread.
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as s:
        s.starttls()
        s.login(user, pw)
        s.send_message(msg)


async def _send_telegram(text: str) -> None:
    token = os.getenv("HH_TELEGRAM_TOKEN", "")
    chat = os.getenv("HH_TELEGRAM_CHAT", "")
    if not (token and chat):
        return
    async with httpx.AsyncClient(timeout=10) as c:
        await c.post("https://api.telegram.org/bot%s/sendMessage" % token,
                     json={"chat_id": chat, "text": text})


async def _send_whatsapp(text: str) -> None:
    phone = os.getenv("HH_CALLMEBOT_PHONE", "")
    key = os.getenv("HH_CALLMEBOT_KEY", "")
    if not (phone and key):
        return
    url = "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode(
        {"phone": phone, "text": text, "apikey": key})
    async with httpx.AsyncClient(timeout=15) as c:
        await c.get(url)


async def notify_lead(rec: dict) -> dict:
    """Fan out to every configured channel. Returns which ones fired, for the
    /api/lead response and the log — handy to confirm from outside that
    notifications are actually wired up in production."""
    subject, body = _lines(rec)
    results: dict[str, bool] = {}

    async def _run(name: str, coro):
        try:
            await coro
            results[name] = True
        except Exception as e:
            results[name] = False
            log.error("notify[%s] failed: %s", name, e)

    tasks = []
    if os.getenv("HH_SMTP_USER") and os.getenv("HH_SMTP_PASS"):
        tasks.append(_run("email", asyncio.to_thread(_send_email, subject, body)))
    if os.getenv("HH_TELEGRAM_TOKEN") and os.getenv("HH_TELEGRAM_CHAT"):
        tasks.append(_run("telegram", _send_telegram(body)))
    if os.getenv("HH_CALLMEBOT_PHONE") and os.getenv("HH_CALLMEBOT_KEY"):
        tasks.append(_run("whatsapp", _send_whatsapp(body)))

    if tasks:
        await asyncio.gather(*tasks)
    return results
