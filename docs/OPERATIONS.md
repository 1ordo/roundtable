# Running an instance

For getting started, see [Running it](../README.md#running-it) in the
README. This is the rest: what the moving parts are, how to back it up, how
to upgrade it, and what to look at when something is wrong.

## The parts

Five containers. Only one is exposed.

| Container | What it is | Exposed |
|---|---|---|
| `web` | nginx serving the built app, proxying `/api` and `/auth` | Yes, `RT_PORT` (8080) |
| `api` | FastAPI. Runs migrations on start, then uvicorn | No |
| `worker` | arq. Crawler, alerts, imports, embeddings | No |
| `db` | Postgres 17 with pgvector | No |
| `redis` | Job queue and rate-limit counters | No |

Put a reverse proxy in front of `web` for HTTPS and set
`RT_COOKIE_SECURE=true` once you have. The database and Redis stay on the
internal network; nothing needs to reach them from outside.

The API runs `alembic upgrade head` before it starts serving, so an upgrade
is a pull and a restart. The worker does not migrate: on a first boot give
the API a moment before expecting scheduled jobs to do anything.

## Backups

Everything that matters is in two volumes: `db-data` (all your data) and
`app-data` (avatars, uploads, and the generated signing key). Docker
prefixes both with the compose project name, which defaults to the
directory you cloned into, so run `docker volume ls` if the names below do
not match yours.

The Postgres role and database are both named `roundtable`, the project's
former name. They are internal to the compose network and renaming them
would strand existing data volumes, so they were left alone.

```bash
# Database
docker compose exec -T db pg_dump -U roundtable roundtable \
  | gzip > roundtable-$(date +%F).sql.gz

# Uploads and the signing key
docker run --rm -v "$(basename "$PWD")_app-data":/data -v "$PWD":/backup alpine \
  tar czf /backup/roundtable-files-$(date +%F).tar.gz -C /data .
```

Keep the `app-data` copy. It holds the signing key, and restoring without it
invalidates every session and makes the stored AI key undecryptable.

To restore:

```bash
docker compose up -d db
gunzip -c roundtable-2026-08-09.sql.gz \
  | docker compose exec -T db psql -U roundtable roundtable
docker run --rm -v "$(basename "$PWD")_app-data":/data -v "$PWD":/backup alpine \
  tar xzf /backup/roundtable-files-2026-08-09.tar.gz -C /data
docker compose up -d
```

Test a restore before you need one. A backup nobody has restored is a guess.

## Upgrading

```bash
docker compose pull && docker compose up -d
```

Migrations run automatically. Pin a version with `RT_VERSION=0.2.0` in
`.env` if you would rather upgrade deliberately; the default is `latest`.
Take a database snapshot first, because migrations are one-way: `downgrade`
exists but is not something to rely on with real data in the table.

## Signing in

Two methods, both switchable in Admin, and the API refuses to leave both
off. It also refuses to switch off passkeys for an admin who has no password
of their own, which would lock them out.

- **Password.** argon2id, minimum ten characters, eight attempts per account
  per fifteen minutes, and a wrong password is indistinguishable from an
  unknown user. Enabled automatically when no OIDC client is configured.
- **OIDC.** Tested against Pocket ID. PKCE, with the callback at
  `RT_PUBLIC_BASE_URL/auth/callback`.

Open registration is off by default. The exception is an instance with no
accounts at all, which always accepts its first: that account becomes the
admin, and the door closes behind it.

`RT_DEV_LOGIN=true` turns `/auth/login` into an instant local sign-in. It
requires `RT_ENV=dev`, and the app refuses to start if it is set anywhere
else. Never set it on a machine anyone else can reach.

## Scheduled work

All times UTC. Everything is in `api/app/worker.py`.

| Job | When | What |
|---|---|---|
| `sweep_catalog` | :05 :25 :45 hourly | Walks TMDB discovery, grows the catalog |
| `refresh_catalog` | :15 :50 hourly | Refreshes the oldest records, embeds stragglers |
| `poll_cinema` | :20 hourly | Cinema alerts, a week before local release |
| `ai_maintenance` | :35 hourly | Embeddings and vibe tags |
| `poll_episodes` | :40 hourly | New episodes of shows people are watching |
| `ask_night_verdicts` | :00 :20 :40 hourly | Asks what people thought after a watch night |
| `poll_availability` | 05:15 daily | Diffs provider rows, alerts on new appearances |
| `poll_followed_people` | 06:10 daily | New credits for people someone follows |
| `expense_reminders` | 08:40 daily | A paid service unused for a month |

Jobs are cancelled after fifteen minutes and are not retried. If a sweep is
timing out on a large instance, that is the number to raise.

## The assistant

Configured at runtime in Admin, AI settings, so a key rotates without a
redeploy. Any OpenAI-compatible base URL works, including OpenRouter and a
local Ollama or LM Studio. The key is encrypted at rest with a key derived
from the instance signing key.

With AI off the app is fully functional: embeddings are generated by a local
encoder, so recommendations work with no external service. What needs a real
embedding endpoint is vibe tags, which skip rather than guess. What needs a
chat endpoint is Ask and natural-language search, which return a clear
disabled state.

Each person can make forty assistant calls an hour. That is a ceiling on
what one account can spend of yours, not a quality setting.

## Personal API and MCP

Enable the `api_tokens` flag in Admin, then API access per user. People
create their own tokens under Settings; the token is shown once and stored
only as a SHA-256 hash.

```json
{
  "mcpServers": {
    "roundtable": {
      "type": "http",
      "url": "https://your-instance.example/api/mcp/",
      "headers": { "Authorization": "Bearer wdk_..." }
    }
  }
}
```

Ten tools, covering search, lists, availability, history, recommendations
and logging a watch. Read-scoped tokens can call the read-only ones; the
three that change something need a write token.

## Quotas

TMDB responses cache in Postgres, so the catalog costs a request once rather
than per view. OMDb is capped at `RT_OMDB_DAILY_BUDGET` (900 of the free
tier's 1000) and refreshes a title's scores monthly at most. Both are
visible in Admin, along with how much of the catalog was refreshed recently.

## When something is wrong

**Sign-in works then bounces back to the login page.** `RT_COOKIE_SECURE` is
true over plain HTTP. Browsers exempt `localhost` but not a LAN or tailnet
address, so the cookie is dropped silently. Set it false until you are
behind HTTPS.

**Every page says the catalog is not configured.** No TMDB key reached the
container. Check `docker compose exec api env | grep TMDB`.

**The home page is empty on a new install.** The catalog fills in the
background; the crawler runs three times an hour. Importing a history or
picking five titles in onboarding seeds it immediately.

**Alerts stopped arriving.** Check Admin, status: it pings Redis for real.
If Redis is down the worker is not running, and nothing scheduled has fired.

**Logs.** `docker compose logs api --tail 100` and
`docker compose logs worker --tail 100`. The worker logs a line per job that
did something and stays quiet otherwise.
