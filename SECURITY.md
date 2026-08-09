# Security policy

Roundtable is self-hosted: the deployments at risk belong to the people
running it, so reports are handled quietly and fixes ship before details.

## Reporting a vulnerability

Do not open a public issue. Use GitHub's private vulnerability reporting
([Security → Report a vulnerability](https://github.com/1ordo/roundtable/security/advisories/new))
and include:

- what you found and where (endpoint, page, component)
- steps to reproduce, as exactly as you can
- what an attacker gains

You will get an acknowledgement within a few days. Once a fix is released,
you are welcome to publish — credit is yours.

## Scope

The API, the web app, the browser extension, and the compose deployment as
shipped. Things worth reporting include authentication or session flaws,
visibility leaks (one user seeing another's private data), injection of any
kind, and ways a default configuration exposes an instance.

Out of scope: vulnerabilities in third-party services you connect (TMDB,
OMDb, Resend, ntfy, your OIDC provider), and instances whose admins changed
security defaults.

## Handling secrets

- `.env` is gitignored and must stay that way. Example files carry
  placeholders only.
- AI keys are stored in the database via Admin settings, so they can be
  rotated without a redeploy.
- If you find a real credential anywhere in this repository or its
  history, report it exactly like a vulnerability: the key gets rotated
  first, then removed.

## Supported versions

The `main` branch. There are no maintained release branches; update by
pulling and re-running `docker compose up -d`.
