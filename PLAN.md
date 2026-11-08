# Plan: deploy cfn-trainer at https://cfn.adamnix.com

Repo: https://github.com/Adam-Nix/cfn-trainer (private). Code is done and pushed. This is what's left.

## 0. Check CI (5 min)
- [ ] GitHub -> Actions: first run of CI is green (builds the image, runs `tests.py`, `selftest.py`, smoke test).
      The Docker build has NOT been run locally (no Docker on the dev PC), so fix any failure here first.

## 1. Optional code tweak: avoid Cloudflare 524 timeouts
- [ ] Lower `JOB_WAIT` in `core.py` from 120 to ~45 s, so a busy server answers "try again"
      before Cloudflare's ~100 s limit. (Ask Claude: "lower JOB_WAIT to 45".)
- [ ] `python tests.py`, commit, push.

## 2. Prepare the TrueNAS box
- [ ] Create dataset, e.g. `/mnt/tank/apps/cfn-trainer`; `chown 568:568` it.
- [ ] Get the code onto the box: `git clone https://github.com/Adam-Nix/cfn-trainer` (needs a deploy key or token).
- [ ] `cp .env.example .env`, then edit:
  - `TRAINER_HOST=cfn.adamnix.com`
  - `TRAINER_USERS=name:password,...` (long, random, different per person)
  - `TRAINER_TRUST_PROXY=1`
- [ ] `docker-compose.yml`: set `UID: 568`; volume -> `/mnt/tank/apps/cfn-trainer-data:/data`.

## 3. Cloudflare Tunnel
- [ ] Zero Trust -> Networks -> Tunnels -> create tunnel, copy the token.
- [ ] Add `cloudflared` as a second service in the compose file (same network), e.g.
      `image: cloudflare/cloudflared:latest`, `command: tunnel --no-autoupdate run`,
      `environment: TUNNEL_TOKEN=...` (put the token in `.env`, never commit it).
- [ ] Public hostname: `cfn.adamnix.com` -> `http://trainer:47651`. Leave "HTTP Host Header" override EMPTY.
- [ ] Delete the `ports:` section from the trainer service, so the only way in is the tunnel
      (required, because `TRAINER_TRUST_PROXY=1` trusts the `CF-Connecting-IP` header).
- [ ] Do not port-forward 47651 on the router.

## 4. Start and verify
- [ ] `docker compose up -d --build`; `docker compose ps` shows trainer `healthy`.
- [ ] `https://cfn.adamnix.com` shows a login popup (not the app, not a 403).
- [ ] Log in as one user: drills load, a check grades, Quit button is gone.
- [ ] Log in as a second user (private window): progress is separate.
- [ ] 5 wrong passwords -> 429. Wait ~5 min, or restart the container.
- [ ] `docker compose logs trainer` shows "login failed from <real IP>" and no passwords.

## 5. Give access
- [ ] Send each classmate the URL + their own username/password via a private message.
- [ ] Tell them: progress is tied to their username; they cannot change their password.

## 6. Optional extras
- [ ] Cloudflare Access (email-code login) in front of the hostname, to keep bots away.
- [ ] Back up the data dir (`users/` holds everyone's progress).
- [ ] Update later: `git pull && docker compose up -d --build`.
- [ ] Add/remove user: edit `.env`, `docker compose up -d` (progress is kept).

## Known limits (also in README)
- Fake-but-valid-looking AMI ids pass the grader (cannot check offline).
- Complexity score is a personal checklist, not the lecturer's rubric.
- Never tested against real AWS.
- Basic auth: HTTPS only; no password change UI; rate limit is per IP.
