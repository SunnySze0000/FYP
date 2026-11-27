"""Polite JSON GET with retries. Standard library only so it runs on any Python 3.10+."""

from __future__ import annotations

import http.client
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "Mozilla/5.0 (WalletLens research; HKUST FYP)"
RETRY_STATUS = {429, 500, 502, 503, 504}


class ApiError(RuntimeError):
    def __init__(self, status: int | None, url: str, message: str = ""):
        super().__init__(f"HTTP {status} for {url} {message}".strip())
        self.status = status
        self.url = url


def get_json(url: str, params: dict | None = None, retries: int = 5, pause_s: float = 0.15,
             timeout_s: float = 30) -> object:
    """GET a JSON document; retry rate limits and transient errors with exponential backoff."""
    clean = {k: v for k, v in (params or {}).items() if v is not None}
    full = f"{url}?{urlencode(clean, doseq=True)}" if clean else url   # lists -> repeated keys
    for attempt in range(retries):
        try:
            request = Request(full, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urlopen(request, timeout=timeout_s) as response:
                payload = json.load(response)
            time.sleep(pause_s)
            return payload
        except HTTPError as error:
            if error.code not in RETRY_STATUS or attempt == retries - 1:
                raise ApiError(error.code, full) from None
            wait = error.headers.get("Retry-After") if error.headers else None
            time.sleep(float(wait) if wait and wait.isdigit() else min(2 ** attempt, 30))
        except (URLError, TimeoutError, ConnectionError, http.client.HTTPException, ValueError) as error:
            # dropped connections, truncated bodies (IncompleteRead) and half-received JSON: retry
            if attempt == retries - 1:
                raise ApiError(None, full, str(error)) from None
            time.sleep(min(2 ** attempt, 30))
    raise ApiError(None, full, "gave up")
