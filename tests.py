"""Hosting tests: login, per-user isolation, host/origin guards, rate limit. Run: python tests.py
Fast (no cfn-lint / moto). The full grader check is selftest.py."""
import http.client
import json
import tempfile
import threading
import unittest
from base64 import b64encode
from pathlib import Path

import app
import auth
import core


def basic(u, p):
    return {"Authorization": "Basic " + b64encode(("%s:%s" % (u, p)).encode()).decode()}


class Base(unittest.TestCase):
    env = {}
    host = "cfn.test"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls._old = core.DATA
        core.DATA = Path(cls.tmp.name)
        cls.srv = app.make_server(app.Config(cls.env), port=0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        core.DATA = cls._old
        cls.tmp.cleanup()

    def req(self, method, path, body=None, headers=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or self.host}
        h.update(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body)
            h.setdefault("Content-Type", "application/json")
        c.request(method, path, data, h)
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw), r
        except ValueError:
            return r.status, raw, r


class Hosted(Base):
    env = {"TRAINER_USERS": "alice:pw1,Bob:p:w2", "TRAINER_HOST": "cfn.test", "TRAINER_BIND": "127.0.0.1"}

    def test_login(self):
        self.assertEqual(self.req("GET", "/api/drills")[0], 401)
        st, _, r = self.req("GET", "/api/drills", headers=basic("alice", "wrong"))
        self.assertEqual(st, 401)
        self.assertIn("Basic", r.getheader("WWW-Authenticate"))
        self.assertEqual(self.req("GET", "/api/drills", headers=basic("alice", "pw1"))[0], 200)
        self.assertEqual(self.req("GET", "/api/drills", headers=basic("bob", "p:w2"))[0], 200)  # name case + colon in pw
        self.assertEqual(self.req("GET", "/")[0], 401)  # the page itself is behind the login too

    def test_progress_isolated(self):
        a, b = basic("alice", "pw1"), basic("bob", "p:w2")
        st, _, _ = self.req("POST", "/api/open", {"id": "ec2-basic"}, a)
        self.assertEqual(st, 200)
        self.assertEqual(self.req("POST", "/api/save", {"key": "ec2-basic", "text": "ALICE-ONLY"}, a)[0], 200)
        da = {d["id"]: d for d in self.req("GET", "/api/drills", headers=a)[1]["drills"]}
        db = {d["id"]: d for d in self.req("GET", "/api/drills", headers=b)[1]["drills"]}
        self.assertTrue(da["ec2-basic"]["in_progress"])
        self.assertFalse(db["ec2-basic"]["in_progress"])
        # bob has no session, so he cannot read or write alice's template
        self.assertEqual(self.req("POST", "/api/save", {"key": "ec2-basic", "text": "x"}, b)[0], 400)
        root = Path(self.tmp.name) / "users"
        self.assertEqual((root / "alice" / "work" / "ec2-basic.yaml").read_text(), "ALICE-ONLY")
        self.assertFalse((root / "bob" / "progress.json").exists() and
                         "ec2-basic" in json.loads((root / "bob" / "progress.json").read_text())["sessions"])
        self.assertFalse((Path(self.tmp.name) / "progress.json").exists())  # nothing leaked to the local store

    def test_host_and_origin(self):
        a = basic("alice", "pw1")
        self.assertEqual(self.req("GET", "/api/drills", headers=a, host="evil.example")[0], 403)
        self.assertEqual(self.req("GET", "/api/drills", headers=a, host="localhost")[0], 403)
        ok = dict(a, Origin="https://cfn.test")
        self.assertEqual(self.req("POST", "/api/open", {"id": "ec2-basic"}, ok)[0], 200)
        bad = dict(a, Origin="https://evil.example")
        self.assertEqual(self.req("POST", "/api/open", {"id": "ec2-basic"}, bad)[0], 403)

    def test_post_rules_kept(self):
        a = basic("alice", "pw1")
        self.assertEqual(self.req("POST", "/api/open", {"id": "ec2-basic"}, dict(a, **{"Content-Type": "text/plain"}))[0], 415)
        self.assertEqual(self.req("POST", "/api/save", {"key": "free", "text": "x" * 700_000}, a)[0], 413)
        self.assertEqual(self.req("GET", "/..%2f..%2fcore.py", headers=a)[0], 404)
        self.assertEqual(self.req("GET", "/../core.py", headers=a)[0], 404)

    def test_quit_disabled(self):
        st, _, _ = self.req("POST", "/api/quit", {}, basic("alice", "pw1"))
        self.assertEqual(st, 404)
        hh = self.req("GET", "/api/health", headers=basic("alice", "pw1"))[1]
        self.assertTrue(hh["hosted"])
        self.assertEqual(hh["user"], "alice")

    def test_healthz_open(self):
        self.assertEqual(self.req("GET", "/healthz", host="localhost")[0], 200)


class RateLimit(Base):
    env = {"TRAINER_USERS": "alice:pw1", "TRAINER_HOST": "cfn.test"}

    def test_lockout(self):
        for _ in range(auth.FAIL_LIMIT):
            self.assertEqual(self.req("GET", "/api/drills", headers=basic("alice", "bad"))[0], 401)
        st, _, r = self.req("GET", "/api/drills", headers=basic("alice", "pw1"))  # even the right password
        self.assertEqual(st, 429)
        self.assertTrue(int(r.getheader("Retry-After")) > 0)


class LocalMode(Base):
    env = {}
    host = "localhost"

    def test_no_login_needed(self):
        self.assertEqual(self.req("GET", "/api/drills")[0], 200)
        self.assertEqual(self.req("GET", "/api/drills", host="evil.example")[0], 403)
        self.assertFalse(self.req("GET", "/api/health")[1]["hosted"])
        self.req("POST", "/api/open", {"id": "ec2-basic"})
        self.assertTrue((Path(self.tmp.name) / "progress.json").exists())  # old layout


class ConfigChecks(unittest.TestCase):
    def test_refuses_open_bind_without_users(self):
        with self.assertRaises(SystemExit):
            app.Config({"TRAINER_BIND": "0.0.0.0"})

    def test_user_validation(self):
        for bad in ("../x:pw", "a b:pw", "local:pw", "alice:", "alice", "a:1,a:2"):
            with self.assertRaises(ValueError, msg=bad):
                auth.parse_users(bad)
        with self.assertRaises(core.UserError):
            core.clean_user("../etc")

    def test_users_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "users.txt"
            f.write_text("# classmates\nalice:a,b\ncarol:pw\n")
            u = auth.load_users({"TRAINER_USERS_FILE": str(f)})
            self.assertEqual(u, {"alice": b"a,b", "carol": b"pw"})


class Concurrency(unittest.TestCase):
    def test_job_cap_and_per_user_locks(self):
        import time
        from unittest import mock
        live, peak, guard = [0], [0], threading.Lock()

        def fake_run(cmd, **kw):
            with guard:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            time.sleep(0.15)
            with guard:
                live[0] -= 1
        with mock.patch.object(core.subprocess, "run", fake_run):
            ts = [threading.Thread(target=core._run, args=(["x"],)) for _ in range(8)]
            [x.start() for x in ts]
            [x.join() for x in ts]
        self.assertLessEqual(peak[0], core.MAX_JOBS)
        self.assertGreaterEqual(peak[0], 1)
        # one user's lock does not block another user
        got = []

        def other():
            core.USER.set("bob")
            with core._lock():
                got.append(1)
        core.USER.set("alice")
        with core._lock():
            th = threading.Thread(target=other)
            th.start()
            th.join(2)
        core.USER.set(core.LOCAL_USER)
        self.assertEqual(got, [1])


if __name__ == "__main__":
    unittest.main()
