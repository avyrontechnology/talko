# Single-VM Deployment Runbook (dev-blr1)

Three backend services on one DigitalOcean droplet, deployed Sep 2026.
Status: working dev/demo environment. See §5 for open follow-ups.

## 1. Architecture

**Droplet:** `dev-blr1` — Basic $24/mo (2 vCPU / 4 GB RAM / 80 GB SSD),
Ubuntu 24.04 LTS, region BLR1 (Bangalore), public IP `143.110.255.238`.
Extras: 2 GB swap file, UFW allowing only 22/80/443, Docker CE + Compose v2
(from Docker's official apt repo — Ubuntu's default repos lack
`docker-compose-plugin`).

**Layout on the VM:** everything lives in `/opt/prod` (one compose project,
one `prod` bridge network).

| Container | Image | Port | Env file |
|---|---|---|---|
| talko-api | built from `./talko` (branch `main`) | 8003 | `.env.talko` |
| talko-worker | same image, celery worker cmd | — | `.env.talko` |
| talko-beat | same image, celery beat cmd (replicas: 1) | — | `.env.talko` |
| voiceai-engine | built from `./voiceai` (branch `master`) | 5001 | `.env.voiceai` |
| voiceai-trunk | same image, trunk cmd | 8004 | `.env.trunk` |
| caddy | `caddy:2-alpine` | 80/443 | `Caddyfile` |

**External managed services (NOT on the VM):** MongoDB Atlas, Upstash Redis
(TLS), console-gRPC, Cloudinary, Tata Tele SmartFlo, Vercel UIs.

**Networking rules that matter:**

- Inter-service URLs use Docker DNS names, never public domains:
  `http://talko-api:8003/talko-service/v1`,
  `http://voiceai-engine:5001`, `ws://voiceai-engine:5001`.
- Public entry is Caddy with automatic Let's Encrypt TLS (via `sslip.io`,
  no DNS purchase needed for dev):
  `api.143-110-255-238.sslip.io` → talko-api:8003,
  `engine.143-110-255-238.sslip.io` → voiceai-engine:5001.
- Tata Tele voice-streaming endpoint (Static type in SmartFlo portal):
  `wss://api.143-110-255-238.sslip.io/talko-service/v1/pstn/tata/stream`
  (call context such as `callSid` arrives inside stream events, not the URL).
- Env files are `chmod 600`, never committed. `VOICE_STREAM_SECRET` must be
  identical in `.env.talko` and `.env.voiceai`/`.env.trunk`.

## 2. Deploy steps (fresh rebuild)

```bash
# 1. base
apt update && apt upgrade -y
# Docker from official repo (see §3.4 if compose plugin is missing)
apt install -y docker.io docker-compose-plugin curl git ufw  # else use docker-ce path
systemctl enable --now docker

# 2. swap + firewall + workspace
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
ufw allow 22/tcp && ufw allow 80,443/tcp && ufw --force enable
mkdir -p /opt/prod && cd /opt/prod

# 3. code (note the different default branches + talko submodule)
git clone --branch main --recurse-submodules https://github.com/avyrontechnology/talko.git talko
git clone --branch master https://github.com/avyrontechnology/voiceai.git voiceai
ls talko/src/components/digital_assets  # MUST be non-empty (startup import)

# 4. env files (.env.talko / .env.voiceai / .env.trunk, chmod 600).
# Copy Render values verbatim EXCEPT cross-service URLs -> internal hostnames.
# Add ALLOWED_HOSTS_EXTRA=<droplet-ip>,<api-host>,<engine-host>.

# 5. docker-compose.yml (+ docker-compose.override.yml for caddy, auto-loaded)

# 6. boot in stages (talko first: fast build, validates Atlas/Upstash)
docker compose build talko-api && docker compose up -d talko-api
curl -s localhost:8003/talko-service/v1/health
docker compose up -d talko-worker talko-beat
docker compose build voiceai-engine voiceai-trunk   # slow: torch/ffmpeg (~4-25 min)
docker compose up -d voiceai-engine && curl -s localhost:5001/health
docker compose up -d voiceai-trunk && curl -s localhost:8004/talko/health
# trunk /talko/health calls talko-api internally: healthy == full chain proven

# 7. public edge
docker compose up -d caddy   # first HTTPS hit fetches LE certs (seconds)
curl -s https://api.143-110-255-238.sslip.io/talko-service/v1/health
curl -s https://engine.143-110-255-238.sslip.io/health
```

Health = healthy on all five + `talko_reachable:true` from trunk means done.
Snapshot the droplet at that point (known-good checkpoint).

## 3. Issues hit and fixes

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | Considered $4 droplet (1 vCPU/512 MB/10 GB) | Stack needs ~5 GB RAM; Mongo alone won't boot; images alone exceed 10 GB | $24 plan (2 vCPU/4 GB/80 GB). $18 viable for test-only with trims (celery concurrency 2, api workers 1, mongo cache 0.25 GB) |
| 2 | `~/.ssh/id_rsa.pub: Permission denied` | Tried to execute the key file | `cat` it, paste into DO dashboard |
| 3 | $42 CPU-Optimized plan preselected | Wrong tab; dedicated CPU, less disk, no benefit for this workload | Basic/Shared-CPU $24 tab |
| 4 | `Unable to locate package docker-compose-plugin` | Missing from Ubuntu default repos | Docker official apt repo (docker-ce, compose v2, buildx) |
| 5 | SSH `Connection refused` after kernel-upgrade reboot | Machine still booting | Wait + retry loop |
| 6 | UI API calls blocked (no response data) | `CORS_EXTRA_ORIGINS` empty in new env (Render had Vercel URLs) | Set both Vercel origins, restart talko-api (env loads at startup only) |
| 7 | ALL UI requests fail, "provisional headers" | Caddy never started → nothing on 443 (DNS was fine) | Created Caddyfile + override file, `up -d caddy`, certs auto-issued |
| 8 | `/vendors` 403, 84-byte body | `TalkoAllowedHostsMiddleware` 403s unknown Hosts (only `/health` exempt; runs before request logger, hence no log lines) | `ALLOWED_HOSTS_EXTRA=<ip>,<api-host>,<engine-host>` + restart |
| 9 | Engine `/auth/me` 401, fresh install | New volume = zero users; first user becomes owner, then signup closes | Created `demo@otoba.ai` (member) via owner invite + accept. Found users/sessions live in shared Upstash Redis, so Render accounts carried over — no migration needed |
| 10 | Login 200 → instant logout loop (`/login?clear_session=1`) | Chrome blocks third-party cookies; `otoba_session` is set by engine host while page is vercel.app → dropped on every later call | Same-origin proxy: `/api/*` rewrites to engine (`next.config.ts` + server-only `ENGINE_URL`), UI env `NEXT_PUBLIC_API_BASE_URL=/api`. WS untouched (ticket-token auth, not cookies) |
| 11 | `/api/*` → 404 `DNS_HOSTNAME_RESOLVED_PRIVATE` | `ENGINE_URL` missing on Vercel → rewrite fell back to `localhost:5001`, which Vercel edge refuses to proxy | Set server-only (non-`NEXT_PUBLIC_`) `ENGINE_URL`, redeploy |
| 12 | `POST /api/auth/login` → 405 | Middleware page-gate hijacked API POSTs into `/login?next=...` (same-site guard misfires on relative `/api`) | `/api/*` bypass in UI `src/proxy.ts` |
| 13 | "Invalid email or password" + HTTP 429 | Wrong email (`demo@` before it existed); retries tripped login rate limit (5/60s/IP) | Wait out window, use `owner@otoba.ai` |
| 14 | Tata portal needs websocket URL | Stream path lives in code | `wss://<api-host>/talko-service/v1/pstn/tata/stream`, Static type |

Recurring diagnostic pattern: browser DevTools (request URL + status + response
body) paired with `docker logs <container>` server-side. Every row above was
identified that way. Engine also keeps a queryable auth audit trail
(`GET /auth/events` as owner: every login/login_failed with timestamps).

## 4. UI wiring (Vercel)

Talko-ui (API-key auth, no cookies — unaffected by §3.10):

- `NEXT_PUBLIC_TALKO_API_BASE_URL=https://<api-host>/talko-service/v1`
- `NEXT_PUBLIC_AUTH_LOGIN_URL=https://<api-host>/talko-service/v1/auth`

Obota-ui (cookie session — needs the §3.10 proxy):

- `NEXT_PUBLIC_API_BASE_URL=/api` (relative! old validator required absolute
  URLs — `src/lib/env.ts` now accepts site-relative paths)
- `ENGINE_URL=https://<engine-host>` (server-only, no `NEXT_PUBLIC_` prefix)
- `NEXT_PUBLIC_WS_BASE_URL=wss://<engine-host>` (unchanged; ticket auth)

`NEXT_PUBLIC_*` bakes at build time: any change needs a Vercel **Redeploy**,
then a hard refresh (Ctrl+Shift+R) to drop the cached bundle.

## 5. Open follow-ups

- [ ] `CLOUDINARY_*` keys empty in `.env.talko` → file uploads fail until added.
- [ ] Rotate secrets that transited through chat (Atlas, Upstash, OpenAI,
      owner password, demo temp password after first login).
- [ ] console-service not migrated — anything needing console gRPC fails;
      don't demo those flows (`CONSOLE_GRPC_HOST` still points at legacy host).
- [ ] Snapshot the droplet at known-good state.
- [ ] Real domain later: replace `sslip.io` hostnames in Caddyfile,
      `ALLOWED_HOSTS_EXTRA`, and the 4 Vercel vars. Prefer sibling subdomains
      (`app.` + `engine.`) so session cookies stay same-site permanently.
- [ ] Re-apply the reverted talko code cleanup (makunai defaults, hardcoded
      JWT in `call_management/controllers.py`) — harmless while envs override,
      but shouldn't drift.
