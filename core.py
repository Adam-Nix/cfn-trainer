"""Trainer engine: sessions, grading, flashcards, stats. No printing, no CLI - used by app.py (the web UI)."""
import difflib
import importlib.util
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import bonus as B
import cfnutil as U
from cards import CARDS
from challenges import BY_ID, CHALLENGES, build
from snippets import SNIPPETS

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
STATE = ROOT / "progress.json"
LOCK = threading.RLock()
MAX_TEXT = 300_000


class UserError(Exception):
    pass


# ------------------------------------------------------------------ state
def _load():
    try:
        s = json.loads(STATE.read_text())
    except Exception:  # noqa: BLE001
        s = {}
    s.setdefault("sessions", {})
    s.setdefault("history", [])
    s.setdefault("cards", {})
    return s


def _save(s):
    STATE.write_text(json.dumps(s, indent=1))


def health():
    return {"cfn_lint": bool(shutil.which("cfn-lint") or importlib.util.find_spec("cfnlint")),
            "moto": importlib.util.find_spec("moto") is not None}


def _ch(cid):
    if cid not in BY_ID:
        raise UserError("Unknown drill")
    return BY_ID[cid]


def _file(key):
    if key not in BY_ID and key not in ("exam", "free"):
        raise UserError("Bad session key")
    WORK.mkdir(exist_ok=True)
    return WORK / (key + ".yaml")


def _clip(text):
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise UserError("Template missing or too large")
    return text


# ------------------------------------------------------------------ drills + sessions
def list_drills():
    st = _load()
    done, best = {}, {}
    for h in st["history"]:
        if not h.get("exam"):
            done[h["id"]] = done.get(h["id"], 0) + 1
            best[h["id"]] = max(best.get(h["id"], 0), h.get("bonus", 0))
    out = []
    for ch in CHALLENGES:
        s = st["sessions"].get(ch["id"])
        out.append({"id": ch["id"], "title": ch["title"], "level": ch["level"], "kind": ch["kind"], "lab": ch["lab"],
                    "minutes": ch["minutes"], "brief": ch["brief"],
                    "blanks": len(build(ch)[2]) if ch["kind"] == "fill" else 0,
                    "done": done.get(ch["id"], 0), "best_bonus": best.get(ch["id"], 0),
                    "in_progress": bool(s and not s.get("done"))})
    ex = st["sessions"].get("exam")
    exam = None
    if ex and not ex.get("ended"):
        exam = {"id": ex["id"], "title": BY_ID[ex["id"]]["title"], "deadline": ex["deadline"]}
    return {"drills": out, "exam": exam}


def _payload(key):
    st = _load()
    s = st["sessions"][key]
    ch = BY_ID[s["id"]]
    exam = key == "exam"
    now = time.time()
    locked = exam and not s.get("ended") and now < s["deadline"]
    return {"key": key, "id": ch["id"], "title": ch["title"], "brief": ch["brief"], "kind": ch["kind"],
            "lab": ch["lab"], "level": ch["level"], "target_minutes": ch["minutes"],
            "text": _file(key).read_text(), "blank_count": len(build(ch)[2]) if ch["kind"] == "fill" else 0,
            "bonus_ideas": ch.get("bonus", []), "start": s["start"], "deadline": s.get("deadline"), "now": now,
            "exam": exam, "ended": bool(s.get("ended")), "done": bool(s.get("done")),
            "hints_used": bool(s.get("hints")), "revealed": bool(s.get("revealed")), "locked": locked,
            "exam_minutes": s.get("minutes")}


def open_session(cid=None, exam=False, minutes=120, restart=False):
    with LOCK:
        st = _load()
        key = "exam" if exam else cid
        if exam:
            cur = st["sessions"].get("exam")
            if cur and not cur.get("ended") and not restart and (cid is None or cid == cur["id"]):
                return _payload("exam")
            if cid is None:
                pool = [c for c in CHALLENGES if c["kind"] == "fill" and c["level"] >= 3]
                seen = {h["id"] for h in st["history"] if h.get("exam")}
                cid = random.choice([c for c in pool if c["id"] not in seen] or pool)["id"]
            minutes = max(10, min(int(minutes), 240))
        ch = _ch(cid)
        cur = st["sessions"].get(key)
        if cur and cur["id"] == cid and not restart and not exam and _file(key).exists():
            return _payload(key)
        now = time.time()
        _file(key).write_text(build(ch)[0])
        st["sessions"][key] = {"id": cid, "start": now, "exam": exam, "hints": False, "revealed": False,
                               "done": False, "ended": False, "minutes": minutes if exam else None,
                               "deadline": now + minutes * 60 if exam else None}
        _save(st)
        return _payload(key)


def exam_session():
    st = _load()
    if "exam" not in st["sessions"]:
        raise UserError("No exam started")
    return _payload("exam")


def restart_timer(key):
    with LOCK:
        st = _load()
        if key not in st["sessions"] or key == "exam":
            raise UserError("No timer to reset")
        st["sessions"][key]["start"] = time.time()
        _save(st)
        return {"start": st["sessions"][key]["start"]}


def save_text(key, text):
    _clip(text)
    with LOCK:
        if key != "free" and key not in _load()["sessions"]:
            raise UserError("Session not started")
        _file(key).write_text(text)
    return {"ok": True}


def get_free():
    f = _file("free")
    return {"text": f.read_text() if f.exists() else ""}


def hints(key):
    with LOCK:
        st = _load()
        s = st["sessions"].get(key)
        if not s:
            raise UserError("Session not started")
        if key == "exam" and not s.get("ended") and time.time() < s["deadline"]:
            raise UserError("Hints are locked during the exam. Finish the exam first.")
        s["hints"] = True
        _save(st)
        return {"hints": build(BY_ID[s["id"]])[2]}


def reveal(key, text):
    _clip(text)
    with LOCK:
        st = _load()
        s = st["sessions"].get(key)
        if not s:
            raise UserError("Session not started")
        if key == "exam" and not s.get("ended") and time.time() < s["deadline"]:
            raise UserError("The solution is locked during the exam. Finish the exam first.")
        s["revealed"] = True
        _save(st)
    sol = build(BY_ID[s["id"]])[1]
    diff = list(difflib.unified_diff(text.splitlines(), sol.splitlines(), "yours", "solution", lineterm="", n=2))
    return {"solution": sol, "diff": diff}


# ------------------------------------------------------------------ grading
def _lint(text):
    exe = shutil.which("cfn-lint")
    cmd = [exe] if exe else [sys.executable, "-m", "cfnlint"]
    WORK.mkdir(exist_ok=True)
    tmpdir = WORK / ".tmp"
    tmpdir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", dir=tmpdir, delete=False) as f:
        f.write(text)
        path = f.name
    try:
        # "--" ends the option list: --regions takes many values and would otherwise swallow the file path
        r = subprocess.run(cmd + ["-f", "json", "--regions", "us-east-1", "--", path], capture_output=True, text=True,
                           timeout=90, stdin=subprocess.DEVNULL)
        if not r.stdout.strip():
            raise ValueError("cfn-lint produced no output (rc=%s): %s" % (r.returncode, r.stderr.strip()[-250:]))
        data = json.loads(r.stdout)
    except Exception as e:  # noqa: BLE001
        data = [{"Rule": {"Id": "E0000"}, "Message": "cfn-lint could not run: %s" % e, "Level": "Error",
                 "Location": {"Start": {"LineNumber": 0}}}]
    finally:
        Path(path).unlink(missing_ok=True)
    items = []
    for m in data:
        lvl = m.get("Level", "Error")
        if lvl.startswith("Info"):
            continue
        items.append({"level": lvl, "rule": m["Rule"]["Id"], "message": m["Message"],
                      "line": m["Location"]["Start"]["LineNumber"]})
    return {"errors": sum(1 for i in items if i["level"] == "Error"),
            "warnings": sum(1 for i in items if i["level"] == "Warning"), "items": items}


def _moto(text, ch):
    WORK.mkdir(exist_ok=True)
    tmpdir = WORK / ".tmp"
    tmpdir.mkdir(exist_ok=True)
    files = []
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", dir=tmpdir, delete=False) as f:
            f.write(text)
            files.append(f.name)
        cmd = [sys.executable, str(ROOT / "moto_deploy.py"), files[0]]
        if ch and ch.get("prestack"):
            with tempfile.NamedTemporaryFile("w", suffix=".yaml", dir=tmpdir, delete=False) as f:
                f.write(build(BY_ID[ch["prestack"]])[1])
                files.append(f.name)
            cmd.append(files[1])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90, stdin=subprocess.DEVNULL)
        return json.loads(r.stdout.strip().splitlines()[-1])
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "error": "mock deploy took more than 90s"}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "error": str(e)[:200]}
    finally:
        for p in files:
            Path(p).unlink(missing_ok=True)


def grade(text, ch=None, full=True):
    res = {"blanks": sorted(set(re.findall(r"____\d+____", text)), key=lambda b: int(b.strip("_"))),
           "yaml_error": None, "lint": None, "reqs": [], "moto": None, "bonus": None, "passed": False}
    try:
        t = U.load(text)
    except Exception as e:  # noqa: BLE001
        res["yaml_error"] = " / ".join(str(e).strip().splitlines()[:3])
        return res
    if res["blanks"]:
        return res
    res["lint"] = _lint(text)
    for desc, fn in (ch["reqs"] if ch else []):
        try:
            r = fn(t)
            okv, msg = (r if isinstance(r, tuple) else (bool(r), ""))
        except Exception:  # noqa: BLE001
            okv, msg = False, "not satisfied yet"
        res["reqs"].append({"desc": desc, "ok": bool(okv), "msg": "" if okv else msg})
    if full and res["lint"]["errors"] == 0:
        res["moto"] = _moto(text, ch)
    got, total, missing = B.score(t, res["lint"])
    have = []
    for f in B.FEATURES:
        try:
            if f[5](t, res["lint"]):
                have.append(f[1])
        except Exception:  # noqa: BLE001
            pass
    res["bonus"] = {"got": got, "total": total, "have": have,
                    "missing": [{"points": w, "effort": e, "label": lab, "snippet": sn} for _, w, e, lab, sn in missing]}
    res["passed"] = res["lint"]["errors"] == 0 and all(r["ok"] for r in res["reqs"])
    return res


def check(key, text, full=True):
    _clip(text)
    with LOCK:
        st = _load()
        s = st["sessions"].get(key)
        if not s:
            raise UserError("Session not started")
        _file(key).write_text(text)
        ch = BY_ID[s["id"]]
    res = grade(text, ch, full)
    with LOCK:
        st = _load()
        s = st["sessions"][key]
        if full and res["passed"] and not s.get("done"):
            minutes = round(min((time.time() - s["start"]) / 60, 240), 1)
            st["history"].append({"id": s["id"], "ts": int(time.time()), "minutes": minutes, "hints": s.get("hints"),
                                  "revealed": s.get("revealed"), "exam": key == "exam",
                                  "bonus": res["bonus"]["got"],
                                  "timeup": bool(s.get("deadline") and time.time() > s["deadline"])})
            s["done"] = True
            _save(st)
        res["done"] = bool(s.get("done"))
    return res


def finish_exam(text):
    res = check("exam", text, True)
    with LOCK:
        st = _load()
        s = st["sessions"].get("exam")
        if s:
            if not s.get("done"):  # record failed / unfinished exams too
                st["history"].append({"id": s["id"], "ts": int(time.time()), "exam": True, "passed": False,
                                      "minutes": round(min((time.time() - s["start"]) / 60, 240), 1),
                                      "hints": False, "revealed": False,
                                      "bonus": (res.get("bonus") or {}).get("got", 0),
                                      "timeup": bool(s.get("deadline") and time.time() > s["deadline"])})
            s["ended"] = True
            _save(st)
    res["payload"] = _payload("exam")
    return res


def check_free(text, full=True):
    _clip(text)
    _file("free").write_text(text)
    return grade(text, None, full)


# ------------------------------------------------------------------ flashcards / snippets / stats
def cards_next(n=10, tag=None):
    st = _load()
    boxes = st["cards"]
    idx = [i for i, c in enumerate(CARDS) if not tag or c[0] == tag]
    pool = idx[:]
    wts = [{1: 6, 2: 3, 3: 1}[boxes.get(str(i), 1)] for i in pool]
    chosen = []
    while len(chosen) < min(n, len(idx)) and pool:
        j = random.choices(range(len(pool)), weights=wts)[0]
        chosen.append(pool.pop(j))
        wts.pop(j)
    return {"cards": [{"i": i, "tag": CARDS[i][0], "q": CARDS[i][1], "a": CARDS[i][2], "box": boxes.get(str(i), 1)}
                      for i in chosen],
            "tags": sorted({c[0] for c in CARDS}), "total": len(CARDS)}


def card_answer(i, correct):
    with LOCK:
        st = _load()
        if not isinstance(i, int) or not 0 <= i < len(CARDS):
            raise UserError("Bad card")
        cur = st["cards"].get(str(i), 1)
        st["cards"][str(i)] = min(cur + 1, 3) if correct else 1
        _save(st)
    return {"box": st["cards"][str(i)]}


def snippets():
    return {"snippets": [{"name": k, "title": t, "body": b} for k, (t, b) in SNIPPETS.items()]}


def stats():
    st = _load()
    b = st["cards"]
    return {"history": st["history"][-30:][::-1],
            "titles": {c["id"]: c["title"] for c in CHALLENGES},
            "cards": {"known": sum(1 for v in b.values() if v == 3), "learning": sum(1 for v in b.values() if v < 3),
                      "untouched": len(CARDS) - len(b), "total": len(CARDS)}}
