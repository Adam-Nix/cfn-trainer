"""Web server for the trainer. Run via start.bat / start.command (or: python app.py).

Default: binds to 127.0.0.1 only, no login - nothing is exposed to your network.
Hosted mode (set TRAINER_USERS or TRAINER_USERS_FILE): HTTP Basic auth, one progress store per user.
Env: TRAINER_BIND, TRAINER_PORT, TRAINER_HOST (allowed Host header(s), comma separated), TRAINER_DATA,
     TRAINER_USERS / TRAINER_USERS_FILE, TRAINER_TRUST_PROXY=1 (take client IP from CF-Connecting-IP /
     X-Forwarded-For), TRAINER_MAX_JOBS (concurrent cfn-lint/moto runs, default 2)."""
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

import auth
import core

STATIC = Path(__file__).resolve().parent / "static"
SERVER = None

LOOPBACK = ("localhost", "127.0.0.1", "::1")


class Config:
    def __init__(self, env=os.environ):
        self.bind = env.get("TRAINER_BIND") or "127.0.0.1"
        self.port = int(env.get("TRAINER_PORT") or "47651")
        self.users = auth.load_users(env)
        hosts = [h for h in (env.get("TRAINER_HOST") or "").split(",") if h.strip()]
        self.hosts = {_hostname(h) for h in hosts} or set(LOOPBACK)
        self.trust_proxy = env.get("TRAINER_TRUST_PROXY") == "1"
        self.hosted = bool(self.users or hosts or self.bind not in LOOPBACK)
        if self.bind not in LOOPBACK and not self.users:
            raise SystemExit("Refusing to listen on %s without logins. Set TRAINER_USERS or TRAINER_USERS_FILE." % self.bind)
        self.limiter = auth.RateLimiter()


def _hostname(value):
    """'Cfn.Example.com:443' -> 'cfn.example.com'; '[::1]:80' -> '::1'."""
    v = value.strip().lower()
    if v.startswith("["):
        return v[1:].split("]")[0]
    return v.split(":")[0] if v.count(":") <= 1 else v


CFG = Config.__new__(Config)  # replaced by main() / tests via make_server()

GET_ROUTES = {
    "health": lambda q: dict(core.health(), hosted=CFG.hosted, user=core.USER.get()),
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

    def _ip(self):
        if CFG.trust_proxy:
            ip = self.headers.get("CF-Connecting-IP")
            if not ip:  # rightmost entry = the one our own proxy appended
                ip = (self.headers.get("X-Forwarded-For") or "").split(",")[-1]
            if ip.strip():
                return ip.strip()
        return self.client_address[0]

    def _guard(self):
        """Host allow-list, then login. On success sets the per-request user and returns True."""
        host = _hostname(self.headers.get("Host") or "")
        if host not in CFG.hosts:
            self._send(403, {"error": "forbidden"})
            return False
        if not CFG.users:
            core.USER.set(core.LOCAL_USER)
            return True
        ip = self._ip()
        wait = CFG.limiter.blocked(ip)
        if wait:
            self.send_response(429)
            self.send_header("Retry-After", str(wait))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False
        creds = auth.credentials(self.headers.get("Authorization"))
        user = auth.verify(CFG.users, creds) if creds else None
        if not user:
            if creds:
                CFG.limiter.fail(ip)
                print("login failed from %s" % ip, file=sys.stderr, flush=True)  # never the password
            data = b'{"error": "login required"}'
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="CFN trainer", charset="UTF-8"')
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return False
        core.USER.set(user)
        return True

    def do_GET(self):
        if self.path == "/healthz":  # for Docker healthcheck: no login, no data
            return self._send(200, b"ok", "text/plain")
        if self._guard():
            self._get()

    def do_POST(self):
        if self._guard():
            self._post()

    def _get(self):
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

    def _post(self):
        # Block cross-site requests: a page on another site can send a "simple" POST to localhost.
        origin = self.headers.get("Origin")
        if origin and _hostname(urlparse(origin).hostname or "") not in CFG.hosts:
            return self._send(403, {"error": "cross-origin request blocked"})
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            return self._send(415, {"error": "JSON required"})
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return self._send(404, {"error": "not found"})
        name = path[5:]
        if name == "quit" and not CFG.hosted:
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


def make_server(cfg, port=None):
    global CFG
    CFG = cfg
    port = cfg.port if port is None else port
    if cfg.hosted:  # fixed port: a container / reverse proxy expects exactly this one
        return Server((cfg.bind, port), Handler)
    for p in range(port, port + 50):
        if port_in_use(p):
            continue
        try:
            return Server((cfg.bind, p), Handler)
        except OSError:
            continue
    sys.exit("No free port found near %d. Set TRAINER_PORT to another number." % port)


def main():
    global SERVER
    try:
        cfg = Config()
    except ValueError as e:
        sys.exit("Bad login config: %s" % e)
    SERVER = make_server(cfg)
    url = "http://localhost:%d/" % SERVER.server_address[1]
    h = core.health()
    print("CloudFormation practical trainer", flush=True)
    if cfg.hosted:
        print("  Hosted mode on %s:%d, %d user(s), hosts: %s" % (cfg.bind, SERVER.server_address[1], len(cfg.users),
                                                                 ", ".join(sorted(cfg.hosts))), flush=True)
    else:
        print("  Running at %s" % url, flush=True)
    if not h["cfn_lint"]:
        print("  WARNING: cfn-lint is not installed - grading will not work. Re-run start.bat / start.command.")
    if not cfg.hosted:
        print("  Your browser should open by itself. Close this window (or press Quit in the page) to stop.")
        if not os.environ.get("TRAINER_NO_BROWSER"):
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        SERVER.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
