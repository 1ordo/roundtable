# Roadmap

What is being worked on and what is wanted, so a contributor can pick
something up without asking first. Anything marked **help wanted** is
genuinely open, not a polite way of saying somebody is already on it.

For what does and does not work today, see
[What works](README.md#what-works) in the README. That table is kept honest
on purpose.

## Next

**Make the browser extension real.** *help wanted, and the best place to start.*
The watchlist import works on Netflix, Prime Video and OSN+. Automatic play
logging is written for eight services and confirmed on none, including
Netflix. Ten of the thirteen adapters carry `verified: false` in
`extension/services.js`, set by their own author.

What is needed is not clever code, it is somebody with an account on a
service, watching one thing, and reporting what happened. One issue per
service. If detection is broken, the fix is usually a few lines in
`extension/sites.js`, and the tests run with `node --test` and no backend.

Two known structural problems, both good issues on their own:
`manifest.json` sets `all_frames: false`, so a player inside an iframe is
invisible; and `_match` searches only the local catalog with no TMDB
fallback, so on a fresh instance most watches come back unmatched.

**Split the watchlist import from the play detection.** *help wanted.*
Passive play detection is what Trakt scrobblers have done for a decade. The
unattended watchlist read is a different thing: it opens a page the user did
not ask for, on a timer, and reads it. That is what Netflix's terms prohibit
by name, and it is the part most likely to fail store review. Passive
detection should ship as the default; the import should be user-initiated
only.

**Chrome Web Store and AMO listings.** Blocked on the two items above, plus
a published privacy policy and store assets. The manifest declares a Gecko
id but the extension will not load in Firefox as written: Firefox MV3 uses
an event page rather than a service worker, so `background.scripts` has to
be declared alongside `background.service_worker`.

**Native applications.** A phone app first, then desktop. Not started. The
API is ready for a non-browser client: personal tokens already work and are
scoped. Genuinely large, and worth talking about before anyone starts.

## Wanted, unclaimed

- **Internationalisation.** *help wanted.* The strongest thing about this
  project is that it serves markets the big trackers do not, and it ships in
  English only with no RTL support. The plumbing is the work: a light i18n
  layer, `lang` and `dir` on the document, and Tailwind's logical properties
  (`ms-`, `ps-`, `start-`) in place of the directional ones.
- **A public demo.** The mock API in `web/tests/mock-api.mjs` is a complete
  believable backend with no database. Deployed as a static site plus that
  mock, it would be a demo anyone could touch, for about an hour of work.
- **Contract tests between the API and the mock.** Three hand-maintained
  descriptions of one API surface: the Pydantic models, the TypeScript
  client, and the mock. A field rename passes every check and breaks the
  app. Dumping the OpenAPI schema in CI and generating the client types from
  it would close this.
- **Export everything.** History and lists export; posts, quotes, messages
  and watch nights do not. There is no self-service account deletion either.
- **Vibe tags without an external model.** They currently need a real
  embedding endpoint; the bundled lexical encoder cannot do zero-shot
  labels. A small local classifier would work and would keep the "no AI
  service required" promise whole.
- **Backup and restore, documented.** Self-hosters ask for it first and it
  is not written down anywhere.

## Deliberately not doing

- **Playing anything.** Watchpile never touches a stream. It tells you where
  something is and hands you off. That keeps it out of DRM entirely and it
  is not going to change.
- **Telemetry.** No analytics, no phoning home, no "anonymous usage
  statistics". The instance belongs to whoever runs it.
- **An account with us.** There is no us. Self-hosted means the operator is
  the only party.

## How to pick something up

Comment on the issue, or open one if it does not exist. For anything larger
than a bug fix, say what you intend to do before writing it, so nobody
spends a weekend on something that was going the other way.
[CONTRIBUTING.md](CONTRIBUTING.md) has the dev environment, which is one
command, and the design rules, which are worth reading before touching the
interface.
