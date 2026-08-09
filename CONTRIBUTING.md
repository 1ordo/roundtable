# Contributing to Watchpile

Glad you are here. This document is the whole book: how to get running, how
the code is laid out, the rules the interface follows, and what a good pull
request looks like. If something in here is wrong or missing, that is a bug
in this file — fix it in the same PR.

## The shape of the project

Watchpile is a self-hosted app with four moving parts:

```
api/        FastAPI + SQLAlchemy 2 (async) + Alembic + Pydantic v2.
            An arq worker on Redis runs the crawler, alerts and imports.
web/        React 19 + Vite + TypeScript + Tailwind v4 + TanStack Query.
extension/  A Manifest V3 browser extension. Plain files, no bundler.
db          Postgres 17 with pgvector.
```

Principles that outrank any local preference:

- **Self-hosted means private.** Nothing leaves the user's machine except
  the API calls they configured. No telemetry, no phoning home.
- **Visibility is decided in one place.** Anything that shows one user's
  data to another goes through `api/app/social/visibility.py`.
- **Features degrade, they do not gate.** No TMDB key means a setup notice,
  not a crash. No AI endpoint means fewer features, not a broken page.
- **The interface follows the design system.** See "The Projection Booth"
  below before you touch a component.

## Getting a dev environment

Requirements: Docker, Python 3.12, Node 22.

### Everything at once

```bash
./scripts/dev.sh up      # Postgres, Redis, API, worker, web, seeded accounts
./scripts/dev.sh logs    # follow logs; also: down, reset, seed
```

### Piece by piece

```bash
# infrastructure
docker compose -f compose.dev.yaml up -d

# backend
cd api
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000

# frontend (proxies /api and /auth to :8000)
cd web
npm install && npm run dev
```

### Frontend only, no backend at all

The Playwright suite ships a mock API with believable data — real TMDB
artwork, a populated home page, a watch night, stats. It needs nothing but
Node:

```bash
cd web
node tests/mock-api.mjs &   # port 8000
npm run dev                 # port 5173, click "Sign in with passkey"
```

This is the fastest loop for design work, and it is what the screenshot
generator and e2e tests run against.

## A tour of the code

### api/

- `app/routers/` one file per surface: catalog, discovery, tracking, stats,
  friends, messages, nights, quotes, comments, profiles, cinema,
  notifications, admin, ai, extension, me.
- `app/models/` SQLAlchemy models; `social.py` is the whole social graph.
- `app/social/` visibility, handles, mentions — shared social logic.
- `app/ai/` the taste engine (`taste.py`), chat, local embeddings, and
  `rails.py`, the guard rails around model output.
- `app/catalog/` TMDB client, local catalog cache, services, genre map,
  the IMDb parents-guide scraper.
- `app/notifications/` inbox, ntfy push, Resend email.
- `app/worker.py` the arq jobs: crawler, alerts, imports.
- `alembic/versions/` migrations. Read anything autogenerate writes.

### web/

- `src/pages/` one file per route. Every page opens with the standard
  header: an eyebrow naming its section, then the display title.
- `src/components/` shared pieces. The flagship ones are `Hero`,
  `PosterCard`, `Row`, `SearchOverlay`, `LeaderBoot` (the launch
  animation) and `ScreenLoader`.
- `src/api/` typed fetch wrappers per domain; `client.ts` is the base.
- `src/index.css` the entire design system: tokens, both themes, and the
  `wd-*` devices. There is no other stylesheet.
- `tests/` the e2e specs, the mock API, and `make-shots.mjs`, which
  regenerates the README and landing screenshots from the live app.

### extension/

Plain JS with `node --test` unit tests next to each file. `build.js` packs
the zip. No bundler, no dependencies — keep it that way.

## The Projection Booth (design system rules)

The interface has one identity and every change stays inside it. The
tokens live in `web/src/index.css`; these are the rules that are not
obvious from reading it:

1. **Two accents, never a third.** `ember` (red-orange) is films, actions,
   selection, links. `nitrate` (blue-green) is series, the system's own
   voice — AI trace, success copy — and origin/language filters. `danger`
   is only for destructive and failing things. If you are reaching for a
   new color, the answer is one of these three.
2. **Type has three jobs.** `font-display` (Big Shoulders, uppercase) for
   page titles and section headings. `font-sans` (Archivo) for everything
   people read. `font-mono` (Spline Sans Mono) for edge-code labels,
   timestamps and numbers. Do not uppercase body copy.
3. **Use the devices, not their ingredients.** A card is `wd-plate`
   (`wd-plate--hover` if clickable). A kicker is `wd-eyebrow`
   (`--ember`/`--nitrate` variants). Horizontal strips are `wd-scroller`.
   The active-marker dot is `wd-cue`. Buttons are `rounded-[4px]`; only
   pills, dots and avatars are fully round.
4. **Every page header is the same shape.** Eyebrow with the route group
   (Tonight, Explore, Together, Your shelf, The booth), then
   `font-display text-5xl font-semibold uppercase tracking-[0.01em]`.
5. **Motion respects the off switch.** Anything animated must be inert
   under `prefers-reduced-motion` and the in-app setting — JS-driven
   motion checks `motionOff()` from `src/lib/motion.ts`. No full-screen
   flashes, ever.
6. **Both themes, always.** Dark is the house lights down; light is the
   silver screen. If you add a color, validate contrast in both (the
   palette is documented AA or better — keep it that way).
7. **Third-party marks stay theirs.** IMDb yellow, Rotten Tomatoes,
   Metacritic, TMDB, and API-provided service colors are deliberately not
   tokenized.

If a change moves the design visibly, regenerate the screenshots so the
README and landing page keep telling the truth:

```bash
cd web
node tests/mock-api.mjs &
npm run dev &
node tests/make-shots.mjs
```

## Tests, and what green means

```bash
# backend: real Postgres with pgvector in a disposable container
cd api && .venv/bin/python -m pytest

# lint and types
cd api && .venv/bin/ruff check app tests \
  && .venv/bin/ruff format --check app tests \
  && .venv/bin/mypy app
cd web && npm run lint && npx tsc -b

# frontend e2e: Playwright drives the real app against the mock API
cd web && npm run test:e2e

# extension
cd extension && node --test
```

Backend tests run against real Postgres so migrations and vector queries
are covered — if your feature adds an endpoint, add a test that walks it
the way a person would. Frontend behavior belongs in an e2e spec; keep the
mock API (`web/tests/mock-api.mjs`) in step with any API shape you change,
because a stale mock fails the suite for the next person. The mock keeps
its state in memory — if you leave one running while repeating the suite,
restart it for a clean slate before blaming a spec.

## Database changes

```bash
cd api
.venv/bin/alembic revision --autogenerate -m "what changed"
```

Then read what it wrote. Autogenerate will happily emit a `NOT NULL`
column with no server default, which aborts on any table that already has
rows. Migrations are append-only once merged.

## Commits and pull requests

- **Conventional Commits**, imperative mood: `feat(scope): summary`,
  `fix:`, `chore:`, `refactor:`, `docs:`, `test:`, `perf:`, `ci:`.
  Summary under ~72 characters; add a body explaining *why* when the
  change is not self-explanatory.
- One concern per PR. A redesign and a schema change are two PRs.
- Before opening: the four test blocks above pass, and anything
  user-visible got a screenshot in the PR description.
- The interface copy follows the product voice: sentence case, plain
  verbs, controls say exactly what they do ("Save changes", not
  "Submit"). Errors say what went wrong and how to fix it.

## Secrets

- Real keys live in `.env`, which is gitignored. `.env.example` files
  carry placeholders only — if you add a config variable, add it there
  and to the README table with an empty or obviously-fake value.
- Defaults in code must be generic: `localhost`, `example.com`, empty.
  Never a real hostname, email, username or key — yours or anyone
  else's.
- If a secret ever lands in a commit, do not just delete it in the next
  one: rotate the key first, then clean up. History remembers.
- Found a vulnerability? [SECURITY.md](SECURITY.md), not the issue
  tracker.

## Licensing of contributions

Watchpile is under the GNU AGPL v3, and your contribution is too. You keep
your copyright: there is no assignment and no CLA to sign.

What is asked instead is a sign-off, the
[Developer Certificate of Origin](https://developercertificate.org/). It is
one line, and it says you wrote the patch or otherwise have the right to
submit it under this licence:

```bash
git commit -s -m "fix(web): a thing"
```

which appends `Signed-off-by: Your Name <you@example.com>` to the message.
That is the whole ceremony. It exists because a project that cannot say
where its code came from cannot be safely used by anyone, and because the
alternative, a CLA that hands one person the right to relicense everyone
else's work, asks contributors for far more than this project needs.

## Getting help

Open an issue with what you tried and what happened, including the exact
command and error. For questions that are not bugs, open a discussion.
There is no wrong question — the docs failed first.
