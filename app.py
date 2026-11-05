"""Local web server for the trainer. Run via start.bat / start.command (or: python app.py).
Binds to 127.0.0.1 only - nothing is exposed to your network."""
import json
import mimetypes
import os
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import core

STATIC = Path(__file__).resolve().parent / "static"
SERVER = None

GET_ROUTES = {
    "health": lambda q: core.health(),
    "drills": lambda q: core.list_drills(),
    "exam_session": lambda q: core.exam_session(),
    "free_text": lambda q: core.get_free(),
    "cards": lambda q: core.cards_next(int(q.get("n", ["10"])[0]), (q.get("tag") or [None])[0] or None),
    "snippets": lambda q: core.snippets(),
    "stats": lambda q: core.stats(),
}

POST_ROUTES = {
    "open": lambda b: core.open_session(b.get("id"), bool(b.get("exam")), b.get("minutes", 120), bool(b.get("restart"))),
    "restart_timer": lambda b: core.restart_timer(b["key"]),
    "save": lambda b: core.save_text(b["key"], b["text"]),
    "check": lambda b: core.check(b["key"], b["text"], bool(b.get("full", True))),
    "finish": lambda b: core.finish_exam(b["text"]),
    "free": lambda b: core.check_free(b["text"], bool(b.get("full", True))),
    "hints": lambda b: core.hints(b["key"]),
    "reveal": lambda b: core.reveal(b["key"], b["text"]),
    "card": lambda b: core.card_answer(b["i"], bool(b["correct"])),
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _guard(self):
        # only accept requests addressed to localhost (blocks DNS-rebinding style access)
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("localhost", "127.0.0.1", "[::1]"):
            self._send(403, {"error": "forbidden"})
            return False
        return True

    def do_GET(self):
        if not self._guard():
            return
        u = urlparse(self.path)
        if u.path.startswith("/api/"):
            fn = GET_ROUTES.get(u.path[5:])
            if not fn:
                return self._send(404, {"error": "not found"})
            try:
                return self._send(200, fn(parse_qs(u.query)))
            except core.UserError as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:  # noqa: BLE001
                return self._send(500, {"error": "%s: %s" % (type(e).__name__, e)})
        rel = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
        f = (STATIC / rel).resolve()
        if STATIC not in f.parents and f != STATIC or not f.is_file():
            return self._send(404, b"not found", "text/plain")
        self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    def do_POST(self):
        if not self._guard():
            return
        # Block cross-site requests: a page on another site can send a "simple" POST to localhost.
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).hostname not in ("localhost", "127.0.0.1", "::1"):
            return self._send(403, {"error": "cross-origin request blocked"})
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            return self._send(415, {"error": "JSON required"})
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return self._send(404, {"error": "not found"})
        name = path[5:]
        if name == "quit":
            self._send(200, {"ok": True})
            threading.Thread(target=SERVER.shutdown, daemon=True).start()
            return
        fn = POST_ROUTES.get(name)
        if not fn:
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 600_000:
                return self._send(413, {"error": "too large"})
            body = json.loads(self.rfile.read(n) or b"{}")
            self._send(200, fn(body))
        except core.UserError as e:
            self._send(400, {"error": str(e)})
        except (KeyError, ValueError, TypeError) as e:
            self._send(400, {"error": "bad request: %s" % e})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": "%s: %s" % (type(e).__name__, e)})


class Server(ThreadingHTTPServer):
    # On Windows, SO_REUSEADDR lets a second program bind a port that is already in use (and quietly
    # steal or share it). Turn that off so a busy port is reported as busy and we move on to the next.
    allow_reuse_address = False


def port_in_use(p):
    s = socket.socket()
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", p)) == 0
    finally:
        s.close()


def main():
    global SERVER
    port = int(os.environ.get("TRAINER_PORT", "47651"))
    for p in range(port, port + 50):
        if port_in_use(p):
            continue
        try:
            SERVER = Server(("127.0.0.1", p), Handler)
            break
        except OSError:
            continue
    else:
        sys.exit("No free port found near %d. Set TRAINER_PORT to another number." % port)
    url = "http://localhost:%d/" % SERVER.server_address[1]
    h = core.health()
    print("CloudFormation practical trainer", flush=True)
    print("  Running at %s" % url, flush=True)
    if not h["cfn_lint"]:
        print("  WARNING: cfn-lint is not installed - grading will not work. Re-run start.bat / start.command.")
    print("  Your browser should open by itself. Close this window (or press Quit in the page) to stop.")
    if not os.environ.get("TRAINER_NO_BROWSER"):
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        SERVER.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
