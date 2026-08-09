# Privacy policy for the Roundtable browser extension

Published at <https://roundtable.watch/privacy.html>, which is the URL the
Chrome Web Store listing points at. This file and that page say the same
thing; edit both, or edit `site/privacy.html` and copy it here.

Last updated: 10 August 2026

## The short version

The extension sends what you watch to **your own Roundtable instance**, at
the address you typed into its options page. It does not send anything to
the author of Roundtable, or to anyone else, because there is nowhere else
for it to go. There is no analytics, no tracking, no advertising, and no
third-party service of any kind.

## What it collects

Only on the streaming sites listed in its permissions, and only while you
are on them:

- **The page address**, to recognise which service you are on and whether
  you are on a playback page.
- **The title the page reports**, from the document title or the browser's
  media-session metadata, plus the season and episode number when the page
  states them.
- **How far through you are**, as a fraction, read from the page's video
  element.
- **Your watchlist**, when you press the import button in the extension
  popup: the titles listed on that service's own list page.

It does not read anything else on those pages. It does not touch any other
site. It has no access to your streaming account, your password, your
payment details or your viewing history on the service itself.

## Where it goes

To the Roundtable instance URL you configured, authenticated with a personal
API token you generated there. Nowhere else.

Roundtable is self-hosted software. That instance is a server you or someone
you know runs. Whoever operates it controls that data, and the extension's
author has no access to it and no way to obtain it.

## What is stored in the browser

- The instance address and your API token, in extension storage.
- A short queue of events not yet delivered, so nothing is lost when the
  network drops or the instance is briefly unreachable. It is emptied as
  soon as delivery succeeds.

Clearing the extension's storage, or removing the extension, removes both.

## What it never does

- Send anything to the extension author or any third party.
- Run remote code. Everything the extension executes ships in the package.
- Read pages other than the streaming services it declares.
- Sell, share or otherwise pass on your information. There is nobody to
  pass it to.

## Removing your data

The data lives on your Roundtable instance. Delete individual entries from
your history in the app, or export everything from Settings and then ask
the operator to remove your account. Uninstalling the extension stops
anything further being sent.

## Permissions, and why

| Permission | Why |
|---|---|
| `storage` | Remembering your instance address, token, and the pending queue |
| `tabs` | Knowing which service page is open, and opening a list page when you press import |
| `notifications` | Telling you when something was logged, or could not be matched |
| Host access to the streaming sites | Reading the title and playback position on pages you are already watching |

Host access is requested for the specific services listed in the manifest
and for nothing else.

## Contact

Open an issue at <https://github.com/1ordo/roundtable/issues>, or email
mohemed4442003@gmail.com.

Changes to this policy are made in the repository, and its history is
public, so you can see exactly what changed and when.
