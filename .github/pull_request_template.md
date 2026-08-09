<!-- One concern per PR. The why matters more than the what. -->

## What this changes

## Why

## Checks

- [ ] `pytest` green (api), `npm run test:e2e` green (web), `node --test` green (extension) — whichever apply
- [ ] `ruff check`, `ruff format --check`, `mypy app` clean if the api changed
- [ ] Anything user-visible has a screenshot below, and stays inside the design system (CONTRIBUTING.md, "The Projection Booth")
- [ ] The mock API (`web/tests/mock-api.mjs`) still matches any API shape this touches
- [ ] No secrets, no personal hostnames, placeholders only in examples
