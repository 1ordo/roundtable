# The Roundtable extension

Logs what you watch on streaming sites to your own Roundtable, offers to
import your saved list, and asks what you thought when the credits roll.

## Installing it

It is not in a store yet, so load it directly. Chrome, Edge, Brave and Arc
all take the same steps.

1. Open `chrome://extensions`
2. Turn on **Developer mode**, top right
3. **Load unpacked**, and pick this folder

Then open the extension's options and give it two things:

- **Where your Roundtable is**, for example `http://localhost:8080`
- **An API token**, from Settings, Account, Tokens in Roundtable. It needs
  write scope.

It checks both before saving, so a wrong address or a refused token is
visible immediately rather than a week later.

## What it does

**Logs what you finish.** It samples the page every few seconds and reports
the title with how far through you are. Past 88 percent counts as watched,
because nobody watches the last of the credits. The same title inside six
hours is one sitting, however many times the page reports it.

**Asks for a rating.** When something is logged, the toolbar icon marks it
and the popup offers one to ten, or loved. Right after the credits is the
only time anyone remembers what they thought. Skipping is a real option.

**Imports your list, without you having to find it.** Open the popup and
press a service. It opens that service's watchlist, waits for it to render,
reads it, and lands on a review screen showing every match with its poster,
what was already on your watchlist, and what it could not recognise. Nothing
is written until you confirm. If you happen to be standing on your list
already it reads that page instead, which is one page load cheaper.

**Keeps them in sync.** Opening a service you subscribe to re-reads its list
and adds anything new, at most once every ten minutes per service. That one
runs in a background tab which closes itself, and it only writes what the
catalog actually recognised and you do not already have: an unattended
import is the wrong place to guess. Turn it off in the options.

**Only from services you have.** It reads the services you ticked in
Roundtable and ignores the rest. If you have not ticked any, it reports from
all of them.

## Services

Netflix, Prime Video, Disney+, Max, Apple TV+, Shahid, OSN+, STARZPLAY,
Paramount+, Peacock, Hulu, Crunchyroll and Watch It.

Each one needs four things to agree: an adapter that reads its pages, a
pattern that recognises its watchlist, an address to find that watchlist at,
and the provider id the app stores when you tick the service in Settings.
`services.test.js` asserts all four for every service, because any one of
them missing produces a service that looks supported and quietly does
nothing. That is not hypothetical: writing those tests found four services
with no list pattern at all, one whose pattern did not match its own
watchlist address, and two claiming to have no provider id when the catalog
has both.

Netflix, Prime and OSN+ have been confirmed against a live signed-in
account; the rest are read off each service's public URL scheme and are
marked `verified: false`. Two things that only came out by looking: OSN+
keeps its list at `/en-eg/my-list` rather than a watchlist path, with the
locale in the path selecting a different catalog, and **Prime splits its
watchlist across a films tab and a series tab**, so a service's list is
modelled as a set of pages rather than one. A wrong one costs a page load and an honest "could
not find your list", never a bad import, because the extension refuses to
read a page that does not look like a list.

## When something reads wrong

Streaming sites change their markup, and an adapter goes stale when they do.
That is expected, which is why the popup lists exactly what was detected and
what happened to it. A wrong name is visible straight away rather than
quietly filling your history.

The fix is usually one line in `sites.js`. Each service has an entry saying
how to find the title on that site, and the order of preference is the same
everywhere:

1. `navigator.mediaSession.metadata`, when the player sets it. It is a
   standard, it is what the OS media keys read, and it is already clean.
2. The site's own rule.
3. `document.title` with the service name stripped.

Two that are worth knowing, because they are not obvious:

- **Shahid** renders in Arabic but keeps a romanised slug in the URL, so the
  slug is used. Reading the heading would send Arabic text to a catalog that
  indexes the romanised name.
- **Prime Video** uses opaque ids in the URL and puts the real name in
  `document.title` as `Prime Video: Foo`.

## What it does not do

It reads the title and how far through you are. It does not read the video,
the page beyond that, your account, or anything else. Nothing is sent
anywhere except the address you configured. The token lives in the
background worker and never enters a streaming page, so a compromised page
cannot read it.

## Following what you press

Two clicks are followed directly rather than waited for:

- **Add to Watchlist**, on any service, saves it to your Roundtable watchlist
  straight away. Removing it there removes it here. Matched on the button's
  accessible label, because every service words it differently but they all
  set one.
- **Play**, so a title registers immediately instead of on the next sample.

## If the server is down

Nothing is lost. Every write goes into a queue in storage before it is sent,
and a failure leaves it there to be retried, backing off from five seconds
to an hour. The queue survives the service worker being shut down. A
rejected token is the exception: that will fail identically forever, so it
is reported once rather than retried into a loop.

## Developing

```bash
cd extension
node --test        # the logic, no browser needed
node build.js      # dist/roundtable-extension-<version>.zip
```

The tests cover the things that actually broke in use: a service tagline
being reported as a title, an Arabic heading being sent instead of the
romanised slug, card fragments like "Season 2" arriving as titles, and the
queue dropping something it should have kept. Every adapter has a page test
with a real path and a real document title, so a service is never supported
in name only.

`background.test.js` loads the worker for real against a fake `chrome` and
drives the whole import: open the tab, wait, read, match, write, close. It
exists because `node --check` passes a file that calls functions which were
never defined, and a bad edit once shipped exactly that.

There is no bundler on purpose. What runs in your browser is what is in the
repository, which matters for something that reads pages you are signed in
to.

## Permissions, and why each one

- The streaming sites listed above, to read the title on the page.
- **Your instance**, requested when you save its address rather than
  declared up front, so the extension never holds blanket access to
  everything.
- **storage** for your settings and the retry queue, **alarms** to retry,
  **notifications** to tell you something was logged, **tabs** to open the
  import review screen.

## Firefox

The manifest declares a Gecko id and a minimum version, but it has not been
tested there yet.
