"""HTTP Basic auth helpers: user loading, constant-time check, per-IP failure rate limit.
Passwords are never logged or written anywhere."""
import base64
import hmac
import threading
import time

import core

FAIL_LIMIT = 5      # failed attempts allowed ...
FAIL_WINDOW = 300   # ... per this many seconds, per IP


def _entry(item):
    name, sep, pw = item.strip().partition(":")  # split on the FIRST colon
    if not sep or not pw:
        raise ValueError("user entries must look like name:password")
    try:
        name = core.clean_user(name)
    except core.UserError:
        raise ValueError("usernames may only use a-z 0-9 _ - (max 32)") from None
    if name == core.LOCAL_USER:
        raise ValueError("the username 'local' is reserved")
    return name, pw.encode()


def _add(users, item):
    name, pw = _entry(item)
    if name in users:
        raise ValueError("duplicate user %r" % name)
    users[name] = pw


def parse_users(text):
    """'alice:pw1,bob:pw2' (comma separated; use a users file if a password contains a comma)."""
    users = {}
    for item in text.split(","):
        if item.strip():
            _add(users, item)
    return users


def load_users(env):
    users = {}
    path = env.get("TRAINER_USERS_FILE")
    if path:
        with open(path, encoding="utf-8") as f:  # one name:password per line, '#' comments
            for line in f.read().splitlines():
                if line.strip() and not line.lstrip().startswith("#"):
                    _add(users, line)
    for name, pw in parse_users(env.get("TRAINER_USERS", "")).items():
        if name in users:
            raise ValueError("duplicate user %r" % name)
        users[name] = pw
    return users


def credentials(header):
    """Return (user, password) bytes from an Authorization header, or None."""
    if not header or not header.lower().startswith("basic "):
        return None
    try:
        raw = base64.b64decode(header[6:].strip(), validate=True)
    except Exception:  # noqa: BLE001
        return None
    u, sep, p = raw.partition(b":")
    return (u.strip().lower(), p) if sep else None


def verify(users, creds):
    """Constant-time check against every user (no early exit). Returns the username or None."""
    u, p = creds
    found = None
    for name, pw in users.items():
        ok_u = hmac.compare_digest(name.encode(), u)
        ok_p = hmac.compare_digest(pw, p)
        if ok_u and ok_p:
            found = name
    if not users:
        hmac.compare_digest(b"x", p)
    return found


class RateLimiter:
    def __init__(self, limit=FAIL_LIMIT, window=FAIL_WINDOW, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._fails = {}
        self._lock = threading.Lock()

    def _recent(self, ip):
        now = self.clock()
        v = [t for t in self._fails.get(ip, []) if now - t < self.window]
        if v:
            self._fails[ip] = v
        else:
            self._fails.pop(ip, None)
        return v

    def blocked(self, ip):
        """Seconds until this IP may try again, or 0."""
        with self._lock:
            v = self._recent(ip)
            return int(self.window - (self.clock() - v[0])) + 1 if len(v) >= self.limit else 0

    def fail(self, ip):
        with self._lock:
            if len(self._fails) > 10_000:  # bound memory
                for k in list(self._fails):
                    self._recent(k)
            self._fails.setdefault(ip, []).append(self.clock())
