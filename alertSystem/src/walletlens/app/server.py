"""EventLens web app: the event-risk monitor (standard-library server, vanilla JS front end).

    python -m walletlens app                      live data, rescans every 5 minutes
    python -m walletlens app --replay 2025-04-07T14:00   replay the research data at a past moment

API
---
GET  /api/state            holdings, latest scan, daily digest, model facts
POST /api/portfolio        {"holdings": ["SPY", ...]}
POST /api/rescan           start a scan now
POST /api/shutdown         stop the server (local only; used by restart.bat)
GET  /api/market/<id>      one market with its wallet hours and linked assets
GET  /api/holding/<sym>    one holding's profile: links by layer, history check, wallet checks
GET  /api/track            the forward track record of past alerts
GET  /api/evidence         the research tests behind every number
"""

from __future__ import annotations

import json
import mimetypes
import threading
import traceback
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from walletlens import logs
from walletlens.monitor.service import Service

log = logs.get("app")
STATIC = Path(__file__).parent / "static"


class Handler(BaseHTTPRequestHandler):
    service: Service

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)

    def _parts(self):
        return [unquote(p) for p in urlparse(self.path).path.strip("/").split("/") if p]

    def do_GET(self):  # noqa: N802
        parts = self._parts()
        try:
            if parts[:1] == ["api"]:
                s = self.service
                routes = {("state",): s.state, ("track",): s.track, ("evidence",): s.evidence}
                if tuple(parts[1:]) in routes:
                    return self._json(routes[tuple(parts[1:])]())
                if len(parts) == 3 and parts[1] == "market":
                    return self._json(s.market(parts[2]))
                if len(parts) == 3 and parts[1] == "holding":
                    return self._json(s.holding(parts[2]))
                raise LookupError("unknown endpoint")
            if parts[:1] == ["static"] and len(parts) == 2 and ".." not in parts[1]:
                return self._file(STATIC / parts[1])
            return self._file(STATIC / "index.html")
        except LookupError as error:
            self._json({"error": str(error)}, HTTPStatus.NOT_FOUND)
        except Exception as error:                 # noqa: BLE001
            log.error("GET %s failed: %s\n%s", self.path, error, traceback.format_exc())
            self._json({"error": "internal error, see logs"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):  # noqa: N802
        parts = self._parts()
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
            if parts == ["api", "portfolio"]:
                return self._json({"holdings": self.service.set_holdings(list(body.get("holdings") or []))})
            if parts == ["api", "shutdown"]:
                if self.client_address[0] not in ("127.0.0.1", "::1"):
                    raise LookupError("unknown endpoint")
                self._json({"stopping": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return None
            if parts == ["api", "rescan"]:
                threading.Thread(target=self.service.run_scan, daemon=True).start()
                return self._json({"started": True})
            raise LookupError("unknown endpoint")
        except LookupError as error:
            self._json({"error": str(error)}, HTTPStatus.NOT_FOUND)
        except (ValueError, json.JSONDecodeError) as error:
            self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    def _json(self, value, status=HTTPStatus.OK):
        body = json.dumps(value, default=str).replace("NaN", "null").replace("Infinity", "null").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path):
        if not path.is_file():
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", (mimetypes.guess_type(path.name)[0] or "application/octet-stream")
                         + ("; charset=utf-8" if path.suffix in (".html", ".js", ".css") else ""))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(service: Service, host: str, port: int) -> ThreadingHTTPServer:
    handler = type("EventLensHandler", (Handler,), {"service": service})
    return ThreadingHTTPServer((host, port), handler)


def serve(service: Service, host: str, port: int, open_browser: bool = True) -> None:
    server = make_server(service, host, port)
    service.start()
    url = f"http://{host}:{port}/"
    log.info("EventLens running at %s (%s data; Ctrl+C to stop)", url, service.source.name)
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("stopped")
    finally:
        server.server_close()
