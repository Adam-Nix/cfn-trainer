# CloudFormation Practical Trainer (web version)

Practice for the 2-hour "fill in the CloudFormation template" practical.
Runs in your browser. No AWS sandbox, no sign-up, no typing commands.

---

## Start it

- **Windows:** double-click `start.bat`
- **Mac:** double-click `start.command`. If macOS says it is from an unidentified developer, right-click it, choose **Open**, then **Open** again (first time only).
- **Linux:** run `./start.command`

First run installs what it needs (about a minute).
Then your browser opens at `http://localhost:47651` (it picks the next free port automatically if that one is busy; the black window shows the exact address).

Needs **Python 3.9+** installed ([python.org](https://www.python.org/downloads/)).
On Windows, tick **"Add python.exe to PATH"** in the installer.

To stop: press **Quit** in the page, or close the black window.

---

## What's in it

- **Drills** - 8 fill-in-the-blank templates from your labs, plus 3 bug hunts
- **Exam** - random template, real countdown, hints and solution locked until you finish
- **Free practice** - paste any template to lint and score it
- **Flashcards** - 60 cards, missed ones come back more often
- **Snippets** - tested blocks for the "extra complexity" marks
- **Stats** - your completed drills and times

---

## Using a drill

1. Pick a drill
2. Fill every `____N____` in the editor
3. Pause typing and a quick check runs (lint + requirements)
4. Press **Check** (or Ctrl+Enter) for the full grade, including the mock deploy
5. Click any lint message to jump to its line
6. Once it passes, open the **Complexity** tab for what to add next

Your work saves automatically. Closing the page and coming back resumes it.

---

## How grading works

- **cfn-lint** - the real linter. Errors must be zero.
- **Requirements** - drill-specific logic (e.g. "NAT sits in a public subnet")
- **Mock deploy** - deploys into moto, a fake AWS, as a smoke test
- **Complexity score** - my own checklist out of 100

---

## Honest limits

- **cfn-lint is the strong check.** A mock-deploy failure with clean lint may be moto's fault.
- **The complexity score is not your lecturer's rubric.** Use it for ideas.
- **I haven't seen your real exam template.** These drills match the lab style.
- **Nothing here checks that an AMI id or key pair really exists.** Use the AMI your lecturer gives you, or an SSM reference.
- **IAM roles are likely blocked in the Learner Lab.** Don't plan your extra marks around creating one.
- **A pass here is not a real deploy.** If you get sandbox time, deploy your final stack once.
- **`Fn::Sub isn't needed` warnings are harmless.** The labs use `!Sub` in UserData without variables.

---

## Rule for the real thing

- Get the **base template deploying first**
- Add **one** extra at a time
- Re-check after each
- A broken ambitious template scores worse than a clean plain one

---

## Hosting for classmates (Docker, HTTPS)

Needs the Python backend (cfn-lint + moto), so it cannot run on GitHub Pages.

**Logins.** Set `TRAINER_USERS="alice:pw1,bob:pw2"` or `TRAINER_USERS_FILE=/path/users.txt` (one `name:password` per line, `#` comments).
Usernames: `a-z 0-9 _ -`. With no users configured it behaves as before: local only, no login.
Each user gets `DATA/users/<name>/progress.json` and `work/`. Failed logins: 5 per 5 min per IP, then HTTP 429.
Basic auth sends the password with every request, so **only expose it over HTTPS**.

| Env | Meaning |
|---|---|
| `TRAINER_USERS` / `TRAINER_USERS_FILE` | logins (above) |
| `TRAINER_HOST` | allowed Host header(s), e.g. `cfn.adamnix.com` (comma separated; add `localhost` to also allow it) |
| `TRAINER_BIND` | default `127.0.0.1`; `0.0.0.0` in Docker. The server refuses a non-loopback bind with no users |
| `TRAINER_DATA` | state directory (default: the app folder; `/data` in Docker) |
| `TRAINER_TRUST_PROXY=1` | take the client IP from `CF-Connecting-IP` / `X-Forwarded-For` (only if the proxy is the only way in) |
| `TRAINER_MAX_JOBS` | concurrent cfn-lint/moto runs (default 2) |

Quit button and `/api/quit` are disabled when hosted. `/healthz` is the only page without a login.

### TrueNAS + Docker Compose
1. Make a dataset, e.g. `/mnt/tank/apps/cfn-trainer`, and `chown 568:568` it (TrueNAS apps user).
2. Copy this repo to the box. `cp .env.example .env` and set real passwords and `TRAINER_HOST=cfn.adamnix.com`.
3. In `docker-compose.yml`: set `UID: 568` and swap the volume for `/mnt/tank/apps/cfn-trainer:/data`.
4. `docker compose up -d --build`. Check `docker compose ps` shows `healthy`.
5. Add a user later: edit `.env`, `docker compose up -d`. Progress stays in the volume.

### HTTPS
- **Cloudflare Tunnel** (easiest, no open ports): add a public hostname `cfn.adamnix.com` -> `http://<truenas-ip>:47651`
  (or `http://trainer:47651` if `cloudflared` joins the same compose network). Set `TRAINER_TRUST_PROXY=1`.
- **Reverse proxy** (Nginx Proxy Manager / Caddy / Traefik): proxy `cfn.adamnix.com` -> `<truenas-ip>:47651`, with a
  Let's Encrypt certificate, and pass the original Host header. Caddy: `cfn.adamnix.com { reverse_proxy trainer:47651 }`.
- Don't forward port 47651 itself to the internet.

### Tests
`python tests.py` (login, user isolation, guards; seconds) and `python selftest.py` (every drill; ~1-2 min). CI runs both in the image.

## Known limits
- Fake-but-valid-looking AMI ids pass the grader (it cannot check them offline).
- The complexity score is a personal checklist, not the lecturer's rubric.
- Never tested against real AWS; the mock deploy is moto only.
- Basic auth + rate limiting suits a few trusted classmates; it is not a hardened multi-tenant service. Templates run through cfn-lint/moto in subprocesses with a 90 s timeout and a job cap, but with no per-user CPU/memory limits beyond the container's.

## Privacy

By default the server only listens on your own computer (`127.0.0.1`).
Nothing is sent anywhere. Progress is stored in `progress.json` and `work/` (hosted: `DATA/users/<name>/`).
