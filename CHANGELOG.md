# Changelog

Notable changes, newest first. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[semantic versioning](https://semver.org/), with one version for the whole
repository rather than one per component.

## [Unreleased]

### Added

- **The assistant is an agent.** It has tools — the catalog, plot search,
  the franchise resolver, TMDB, web search, Reddit search, a page reader —
  and calls them itself, retrying another way when a result is thin. The
  trace above an answer is the real sequence of tool calls. Every title it
  names is verified server-side before it becomes a card, web content is
  treated as untrusted data, fetches to private addresses are refused, and
  the only write remains the Save button. Needs a chat model that supports
  tool calling.
- **A featured line on your profile.** One quote, chosen by you, as a
  full-width cover above your name, replacing the grid of every line you
  ever saved.
- **Availability honesty.** The title page reports the countries you chose,
  not the instance's; and a service you subscribe to that the data source
  does not model in your country is shown as "yours, unlisted here" rather
  than silently treated as absent.

### Fixed

- Saving an assistant-proposed franchise list works at real franchise
  sizes: the request cap now derives from what the resolver can produce,
  and a save no longer re-fetches titles the catalog already holds.
- Naming a franchise is enough for the deterministic path, however the
  question is phrased, and the collection picker no longer answers "star
  wars" with the Ewok Adventures.
- A blank `RT_DEFAULT_COUNTRY` no longer becomes a country called "",
  which made availability silently empty for anyone without a profile
  country on a fresh instance.

## [0.1.0]

First public release.

### Added

- **Episode tracking.** Season grids, per-episode logging, and next-up that
  skips specials and never points at something that has not aired. A new
  episode of a show you are watching raises one notification.
- **Prebuilt images** for amd64 and arm64 on ghcr, so self-hosting does not
  mean compiling.
- **Automatic handles.** Every account gets a profile address on signup, so
  people are clickable and messageable from the moment they exist.
- A budget on the assistant: forty calls an hour per person, so one account
  cannot spend the operator's tokens without limit.

### Changed

- **Cinema alerts fire a week before a local release**, hourly, rather than
  on the morning of, twice a day. The wording matches what is actually true.
- **Suggestions default to the services you subscribe to.** Still
  switchable, and it does nothing until you have said what you have.
- The self-hosted build no longer serves a marketing page; `/` is the app.
- The parents guide is off unless `RT_IMDB_GUIDE_ENABLED` is set. It reads
  an unofficial IMDb endpoint, and that is the operator's decision to make.
- Licence is now GNU AGPL v3. The name and logo are reserved separately, see
  `TRADEMARK.md`.

### Fixed

- **Per-panel privacy is enforced everywhere a written thing appears**, not
  only on the profile page. Four leaks closed: posts marked private still
  reaching the feed and title pages, reshares carrying a friends-only
  original to people who could not see its author, quotes shown with no
  filter at all, and the assistant's prompt reading other accounts' lists.
- **The documented install now works.** `docker compose up -d` did not
  parse, published no port, discarded the TMDB key, and left no way to make
  the first account.
- **Alert preferences no longer mute almost everything.** The settings
  screen offered four kinds, two of which nothing emitted, so saving it
  silently switched off friend requests, invites, surveys, cinema alerts and
  messages. Existing broken preferences self-heal.
- A binge records every episode rather than one watch of the whole series.
- Read-scoped API tokens can call read-only MCP tools, which they could not.
- Saving a title to a list feeds your taste vector, which it did not.
- The assistant's streaming endpoint no longer builds on a database session
  that has already been closed.
- Vibe tags say they need a real embedding model instead of silently
  producing nothing.

### Performance

- **An HNSW index on the embeddings.** There was none, so every shelf ran an
  exact scan of the whole table and sorted it.
- The poster card is animated in CSS rather than JavaScript. A home page
  renders around two hundred of them, and each carried its own tween.
- Reduced motion is honoured across the whole app, from both the system
  preference and the in-app switch.
- Shipped screenshots went from 2.8 MB to 540 kB, and show the current
  interface rather than one from three commits before a redesign.

### Security

- Content Security Policy, `frame-ancestors`, `nosniff`, referrer policy and
  HSTS on the web container.
- The signing key is generated per instance instead of falling back to a
  constant published in this repository.
- CI validates the compose file, runs CodeQL, and has a read-only default
  token.

[Unreleased]: https://github.com/1ordo/roundtable/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/1ordo/roundtable/releases/tag/v0.1.0
