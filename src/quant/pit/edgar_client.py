"""A polite, resumable EDGAR client that keeps the declared contact out of source, logs and manifests.

The SEC refuses automated requests whose User-Agent does not declare who is asking (verified: HTTP 403 from data.sec.gov and www.sec.gov for an agent without an email-style contact) and caps
automated traffic at 10 requests per second. This client:

* reads the agent from the environment variable `EDGAR_USER_AGENT` and refuses to run without it; the value is never written to disk, never logged and never part of an exception message;
* paces itself below the cap (default 6 requests per second) and honours `Retry-After`;
* retries timeouts, truncated bodies, 429 and 5xx with exponential backoff, and stops at the first 403 instead of hammering a service that has refused it;
* records one line per request in a JSONL manifest (time, URL, status, bytes, SHA-256 of the body) and nothing else, so an acquisition can be audited without containing any request header;
* is usable as the `opener` of `security_master.fetch_json`, so the repository's existing on-disk caches and 404 markers keep their layout.

Nothing here parses what it fetches.
"""

from __future__ import annotations

import gzip
import hashlib
import http.client
import json
import os
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

ENV_VAR = "EDGAR_USER_AGENT"
MAX_REQUESTS_PER_SECOND = 10.0


class EdgarAccessError(RuntimeError):
    """Raised when the SEC refuses access or retries are exhausted. Never contains the user agent."""


class EdgarClient:
    def __init__(self, *, requests_per_second: float = 6.0, manifest: Optional[Path] = None, max_retries: int = 6, timeout: float = 60.0,
                 user_agent: Optional[str] = None, transport: Optional[Callable[[str, dict], tuple[int, dict, bytes]]] = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
        agent = user_agent if user_agent is not None else os.environ.get(ENV_VAR, "")
        if not agent.strip() or "@" not in agent:
            raise EdgarAccessError(f"set {ENV_VAR} to a User-Agent that declares a contact (the SEC refuses requests without one); it is read from the environment and never stored")
        if not 0 < requests_per_second <= MAX_REQUESTS_PER_SECOND:
            raise ValueError(f"requests_per_second must be in (0, {MAX_REQUESTS_PER_SECOND}]")
        self._agent = agent
        self.interval = 1.0 / requests_per_second
        self.manifest = Path(manifest) if manifest else None
        self.max_retries = max_retries
        self.timeout = timeout
        self._transport = transport or self._urllib_transport
        self._sleep, self._clock = sleep, clock
        self._last = -1e9
        self.requests = 0

    def __repr__(self) -> str:                                  # the agent must never leak through a traceback or a log line
        return f"EdgarClient(rps={1 / self.interval:.1f}, requests={self.requests})"

    # ── transport ────────────────────────────────────────────────────────
    def _urllib_transport(self, url: str, headers: dict) -> tuple[int, dict, bytes]:
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers or {}), b""

    def _pace(self) -> None:
        wait = self.interval - (self._clock() - self._last)
        if wait > 0:
            self._sleep(wait)
        self._last = self._clock()

    def _log(self, url: str, status: int, body: bytes, attempt: int) -> None:
        if not self.manifest:
            return
        self.manifest.parent.mkdir(parents=True, exist_ok=True)
        line = {"retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "url": url, "status": status, "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest() if body else None, "attempt": attempt}
        with self.manifest.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, sort_keys=True) + "\n")

    # ── public ───────────────────────────────────────────────────────────
    def get(self, url: str) -> bytes:
        """The body of `url`. Raises `urllib.error.HTTPError(404)` for a missing document (callers cache that), `EdgarAccessError` otherwise."""
        headers = {"User-Agent": self._agent, "Accept-Encoding": "gzip", "Accept": "application/json"}
        for attempt in range(1, self.max_retries + 1):
            self._pace()
            self.requests += 1
            try:
                status, response_headers, body = self._transport(url, headers)
            except (urllib.error.URLError, http.client.HTTPException, socket.timeout, TimeoutError, ConnectionError, OSError):
                self._log(url, 0, b"", attempt)
                self._sleep(min(60.0, 2.0 ** attempt))
                continue
            if status == 200:
                if response_headers.get("Content-Encoding", "").lower() == "gzip" or body[:2] == b"\x1f\x8b":
                    try:
                        body = gzip.decompress(body)
                    except (OSError, EOFError):
                        self._log(url, 0, b"", attempt)                     # truncated body: retry
                        self._sleep(min(60.0, 2.0 ** attempt))
                        continue
                self._log(url, 200, body, attempt)
                return body
            self._log(url, status, b"", attempt)
            if status == 404:
                raise urllib.error.HTTPError(url, 404, "Not Found", http.client.HTTPMessage(), None)
            if status == 403:
                raise EdgarAccessError(f"HTTP 403 from the SEC for {url}: the declared User-Agent was refused or the request rate was throttled; stopping")
            if status in (429, 500, 502, 503, 504):
                retry_after = response_headers.get("Retry-After")
                self._sleep(float(retry_after) if retry_after and retry_after.isdigit() else min(60.0, 2.0 ** attempt))
                continue
            raise EdgarAccessError(f"HTTP {status} from the SEC for {url}")
        raise EdgarAccessError(f"gave up on {url} after {self.max_retries} attempts")

    def opener(self) -> Callable[[str], bytes]:
        """The callable `security_master.fetch_json(..., opener=...)` expects."""
        return self.get
