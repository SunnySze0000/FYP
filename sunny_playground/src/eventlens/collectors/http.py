"""Polite JSON fetching with retries and resumable on-disk caching.

Standard library only, so collectors run on any Python 3.10+ install.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "Mozilla/5.0 (EventLens FYP research collector)"
RETRY_STATUS = {429, 500, 502, 503, 504}


def get_json(url: str, params: dict | None = None, retries: int = 5, pause_s: float = 0.2) -> object:
    """GET a JSON document, retrying rate limits and transient errors with backoff."""
    full_url = f"{url}?{urlencode(params)}" if params else url
    for attempt in range(retries):
        try:
            request = Request(full_url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
            time.sleep(pause_s)
            return payload
        except HTTPError as error:
            if error.code not in RETRY_STATUS or attempt == retries - 1:
                raise RuntimeError(f"HTTP {error.code} for {full_url}") from None
        except (URLError, TimeoutError) as error:
            if attempt == retries - 1:
                raise RuntimeError(f"Network error for {full_url}: {error}") from None
        time.sleep(min(2**attempt, 30))
    raise RuntimeError(f"Gave up on {full_url}")


def write_json_atomic(path: Path, payload: object) -> None:
    """Write via a temporary file so an interrupted run never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(path)


def cached_json(path: Path, fetch) -> object:
    """Return the cached document at `path`, fetching and saving it if absent."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    payload = fetch()
    write_json_atomic(path, payload)
    return payload
