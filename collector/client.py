"""Polite HTTP client for the MahaRERA public portal.

Design intent: we are a once-a-month, low-rate, off-peak visitor to a public,
captcha-free government list page. This client is deliberately *slow and gentle*:
a real browser User-Agent, a configurable delay between every request, bounded
retries with backoff, and sane timeouts. It does NOT touch captcha-gated pages.
"""

from __future__ import annotations

import logging
import random
import time

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger("honesthomes.client")

# A normal desktop browser UA. We are a real, identifiable visitor, not a stealth bot.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Errors worth retrying (transient). 4xx are NOT retried — they mean we asked wrong.
_RETRYABLE = (httpx.TransportError, httpx.TimeoutException)


class PoliteClient:
    """A thin wrapper over httpx that enforces a minimum gap between requests.

    Parameters
    ----------
    min_delay, max_delay:
        Each request sleeps a random duration in ``[min_delay, max_delay]`` seconds
        *before* firing. Randomising avoids a robotic fixed cadence. Defaults are
        intentionally generous — at monthly cadence there is no reason to rush.
    timeout:
        Per-request timeout in seconds. The gov site is slow; give it room.
    """

    def __init__(
        self,
        *,
        base_url: str = "https://maharera.maharashtra.gov.in",
        min_delay: float = 4.0,
        max_delay: float = 8.0,
        timeout: float = 45.0,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
        )

    def _sleep(self) -> None:
        delay = random.uniform(self.min_delay, self.max_delay)
        log.debug("sleeping %.1fs before next request", delay)
        time.sleep(delay)

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        wait=wait_exponential(multiplier=2, min=4, max=120),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def get(self, path: str, params: dict | None = None) -> httpx.Response:
        """GET a path, politely. Sleeps before the request; retries transient errors."""
        self._sleep()
        log.info("GET %s params=%s", path, params)
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PoliteClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
