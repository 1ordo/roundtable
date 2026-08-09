/* How to read a title out of each streaming site.
 *
 * Every adapter is a best effort at one job: turn whatever the page is
 * showing into a name a catalog would recognise. They are separated per
 * site because the sites genuinely differ, and pinned to observed
 * behaviour rather than guessed at:
 *
 *   Shahid    renders in Arabic but keeps a Latin slug in the URL, so the
 *             slug is far more matchable than anything on the page. Reading
 *             the heading would send arabic text to a catalog that indexes
 *             the romanised name.
 *   Prime     uses opaque ids in the URL and puts the real name in
 *             document.title as "Prime Video: Foo".
 *   Netflix   also uses opaque ids and also puts the name in the title.
 *
 * The order of preference is the same everywhere:
 *   1. navigator.mediaSession.metadata, when the player sets it. It is a
 *      standard, it is what the OS media keys read, and it is already the
 *      clean name.
 *   2. The site adapter.
 *   3. document.title with the site name stripped.
 *
 * When a site changes its markup an adapter goes stale. That is expected,
 * which is why the popup shows exactly what was detected: a wrong name is
 * visible immediately rather than quietly polluting a history.
 */

const SITES = [
  {
    id: 'netflix',
    label: 'Netflix',
    provider: 8,
    match: (host) => host.includes('netflix.com'),
    // Only /watch is playback. Browsing is not watching.
    playing: (path) => path.startsWith('/watch/'),
    title: () => stripSuffix(document.title, ['Netflix']),
  },
  {
    id: 'prime',
    label: 'Prime Video',
    provider: 9,
    match: (host) => host.includes('primevideo.com') || host.includes('amazon.'),
    playing: (path) => /\/(detail|watch|gp\/video)\//.test(path),
    // Observed: "Prime Video: From Old Country Bumpkin to Master Swordsman II"
    title: () => document.title.replace(/^Prime Video:\s*/i, '').trim(),
  },
  {
    id: 'shahid',
    label: 'Shahid',
    provider: 1715,
    match: (host) => host.includes('shahid.mbc.net'),
    playing: (path) => /\/(movie|series|show|episode)\//.test(path),
    /* Observed: /ar/series/Ward-Ala-Foll-Wa-Yasmeen/series-49923416471974
       The page heading is Arabic; the slug is romanised and matchable. */
    title: () => {
      const parts = location.pathname.split('/').filter(Boolean)
      const index = parts.findIndex((p) => ['movie', 'series', 'show', 'episode'].includes(p))
      let slug = index >= 0 ? parts[index + 1] : null
      /* The slug is only romanised for shows with a Latin name. An Arabic
         one is Arabic text, percent-encoded by the address bar, and the raw
         path gives "%D8%AA%D8%AD%D8%AA..." which went to the catalog as a
         title to match. Seen in a real log. Decoding gets the Arabic back,
         which at least has a chance; failing that the page heading is a far
         better guess than an escape sequence. */
      if (slug && slug.includes('%')) {
        try {
          slug = decodeURIComponent(slug)
        } catch {
          slug = null
        }
      }
      if (!slug || /^\d/.test(slug) || /%[0-9A-F]{2}/i.test(slug)) {
        return stripSuffix(document.title, ['MBC Shahid', 'Shahid'])
      }
      return slug.replace(/-/g, ' ').replace(/\s*season\s*\d+$/i, '').trim()
    },
    kind: () => (location.pathname.includes('/movie/') ? 'movie' : 'tv'),
  },
  {
    id: 'disney',
    label: 'Disney+',
    provider: 337,
    match: (host) => host.includes('disneyplus.com'),
    playing: (path) => /\/(video|play|movies|series)\//.test(path),
    title: () => stripSuffix(document.title, ['Disney+', 'DisneyPlus']),
  },
  {
    id: 'osn',
    label: 'OSN+',
    provider: 629,
    match: (host) => host.includes('osnplus.com') || host.includes('osn.com'),
    playing: (path) => /\/(watch|play|movie|series|title)\//.test(path),
    title: () => stripSuffix(document.title, ['OSN+', 'OSN']),
  },
  {
    id: 'max',
    label: 'Max',
    provider: 1899,
    match: (host) => host.includes('max.com') || host.includes('hbomax.com'),
    playing: (path) => /\/(video|play|movie|show)\//.test(path),
    title: () => stripSuffix(document.title, ['Max', 'HBO Max']),
  },
  {
    id: 'appletv',
    label: 'Apple TV+',
    provider: 350,
    match: (host) => host.includes('tv.apple.com'),
    playing: (path) => /\/(episode|movie|show)\//.test(path),
    title: () => stripSuffix(document.title, ['Apple TV', 'Apple TV+']),
  },
  {
    id: 'hulu',
    label: 'Hulu',
    provider: 15,
    match: (host) => host.includes('hulu.com'),
    playing: (path) => /\/(watch|movie|series)\//.test(path),
    title: () => stripSuffix(document.title, ['Hulu']),
  },
  {
    id: 'crunchyroll',
    label: 'Crunchyroll',
    provider: 283,
    match: (host) => host.includes('crunchyroll.com'),
    playing: (path) => /\/watch\//.test(path),
    title: () => stripSuffix(document.title, ['Crunchyroll']),
    kind: () => 'tv',
  },
  {
    id: 'paramount',
    label: 'Paramount+',
    provider: 531,
    match: (host) => host.includes('paramountplus.com'),
    playing: (path) => /\/(video|movies|shows)\//.test(path),
    title: () => stripSuffix(document.title, ['Paramount+', 'Paramount Plus']),
  },
  {
    id: 'peacock',
    label: 'Peacock',
    provider: 386,
    match: (host) => host.includes('peacocktv.com'),
    playing: (path) => /\/(watch|playback)\//.test(path),
    title: () => stripSuffix(document.title, ['Peacock', 'Peacock TV']),
  },
  {
    id: 'starzplay',
    label: 'STARZPLAY',
    provider: 630,
    match: (host) => host.includes('starzplay.com') || host.includes('starz.com'),
    playing: (path) => /\/(watch|play|movies|series)\//.test(path),
    title: () => stripSuffix(document.title, ['STARZPLAY', 'STARZ']),
  },
  {
    id: 'watchit',
    label: 'Watch It',
    provider: 2199,
    match: (host) => host.includes('watchit.com') || host.includes('watchit.movie'),
    playing: (path) => /\/(watch|play|movie|series)\//.test(path),
    title: () => stripSuffix(document.title, ['Watch It', 'WatchIt']),
  },
]

/* Titles that are the service describing itself. Without this the Prime
   home page reported "Watch movies, TV shows, sports, and live TV" as
   something being watched, which then failed to match anything. */
const GENERIC = [
  /^watch movies/i,
  /^prime video$/i,
  /^netflix$/i,
  /^home$/i,
  /^search$/i,
  /^browse$/i,
  /^your watchlist$/i,
  /^my (list|stuff)$/i,
  /tv shows, sports/i,
  /^shahid/i,
  /^disney\+?$/i,
]

function isGeneric(name) {
  return !name || GENERIC.some((pattern) => pattern.test(name.trim()))
}

/* Reading a whole saved list off a page.
 *
 * Every service calls it something different and marks it up differently,
 * so this stays generic on purpose: find the links that point at a title,
 * and take the accessible name off each one. That survives a redesign in a
 * way that a hand picked class name does not, and the review screen means a
 * wrong read is caught before anything is written. */
const LIST_PATTERNS = {
  netflix: { path: /\/(browse\/my-list|list)/, link: 'a[href*="/watch/"], a[href*="/title/"]' },
  prime: { path: /\/(watchlist|mystuff)/i, link: 'a[href*="/detail/"]' },
  // Confirmed by Mohamed: Shahid calls it favorite, not a watchlist.
  shahid: {
    path: /\/(favou?rite|my-list|watchlist|mylist)/i,
    link: 'a[href*="/movie/"], a[href*="/series/"]',
  },
  disney: { path: /\/watchlist/i, link: 'a[href*="/movies/"], a[href*="/series/"]' },
  /* Confirmed on the live signed-in page: cards are /en-eg/movie/<slug-id>
     and /en-eg/series/<slug-id>, the name is the anchor's textContent, and
     aria-label and the poster's alt are both empty. The old selector looked
     for /title/ and matched nothing at all. */
  osn: { path: /\/(watchlist|my-list)/i, link: 'a[href*="/movie/"], a[href*="/series/"]' },
  // "mylist" as well as "my-list": Max spells it without the hyphen, and a
  // pattern that does not match the address we send people to makes the
  // whole import refuse itself.
  max: { path: /\/(my-?list|watchlist)/i, link: 'a[href*="/show/"], a[href*="/movie/"]' },
  appletv: { path: /\/(up-next|watchlist)/i, link: 'a[href*="/movie/"], a[href*="/show/"]' },
  hulu: { path: /\/my-stuff/i, link: 'a[href*="/watch/"], a[href*="/series/"]' },
  crunchyroll: { path: /\/(watchlist|crunchylists)/i, link: 'a[href*="/series/"]' },
  // These four had no entry at all, which meant isListPage was false for
  // them everywhere: the on-page offer never appeared and the import refused
  // every page as "not your list". A service with an adapter and no list
  // pattern is a service the import silently does not support.
  paramount: {
    path: /\/(watchlist|my-list)/i,
    link: 'a[href*="/movies/"], a[href*="/shows/"]',
  },
  peacock: { path: /\/(watchlist|my-stuff)/i, link: 'a[href*="/watch/"]' },
  starzplay: {
    path: /\/(watchlist|my-list)/i,
    link: 'a[href*="/movies/"], a[href*="/series/"], a[href*="/play/"]',
  },
  watchit: {
    path: /\/(watchlist|my-list)/i,
    link: 'a[href*="/movie/"], a[href*="/series/"]',
  },
}

/** Whether this page looks like the saved list for its service. */
function isListPage(siteId) {
  const pattern = LIST_PATTERNS[siteId]
  return Boolean(pattern && pattern.path.test(location.pathname))
}

/* Reading a virtualised carousel.
 *
 * Prime keeps exactly five cards per row in the DOM and swaps them as you
 * scroll, so a single read of a list of twenty returns five. Reading once
 * and reporting the number found is honest about the DOM and misleading
 * about the list, which is worse.
 *
 * So this scrolls each row to the end, collecting as it goes, and returns
 * the union. Anything already off screen has been captured on an earlier
 * pass. It restores the scroll position afterwards, because moving
 * somebody's page under them is rude.
 */
async function collectList(siteId) {
  const found = new Map()
  const absorb = () => {
    for (const entry of readList(siteId)) {
      if (!found.has(entry.title.toLowerCase())) found.set(entry.title.toLowerCase(), entry)
    }
  }

  absorb()
  const rows = [...document.querySelectorAll('[data-testid="card-container-list"], ul, [class*="carousel"]')]
    .map((row) => row.closest('[data-testid="navigation-carousel-wrapper"]') || row.parentElement)
    .filter((row, index, all) => row && row.scrollWidth > row.clientWidth + 40 && all.indexOf(row) === index)

  for (const row of rows) {
    const start = row.scrollLeft
    // A bounded number of steps: a very long row is still worth reading,
    // but not at the cost of scrolling forever if the width never settles.
    for (let step = 0; step < 25; step += 1) {
      const before = row.scrollLeft
      row.scrollBy({ left: row.clientWidth || 800, behavior: 'instant' })
      await new Promise((resolve) => setTimeout(resolve, 320))
      absorb()
      if (row.scrollLeft <= before) break // reached the end
    }
    row.scrollTo({ left: start, behavior: 'instant' })
  }
  absorb()
  return [...found.values()]
}

/** Every title currently in the DOM, deduplicated, best effort. */
function readList(siteId) {
  const pattern = LIST_PATTERNS[siteId]
  if (!pattern) return []
  /* Card fragments and row headings, not titles. "Now" is the heading of a
     continue-watching strip and arrived in an import as something to match. */
  const junk =
    /^(season\s*\d+|episode\s*\d+|watch now|play|trailer|more|now|next|continue watching|top \d+|\d+)$/i
  const seen = new Set()
  const out = []
  for (const link of document.querySelectorAll(pattern.link)) {
    // The accessible name is what a screen reader would announce, which is
    // the closest thing these pages have to a reliable title.
    const label =
      link.getAttribute('aria-label') ||
      link.querySelector('img')?.alt ||
      link.textContent?.trim() ||
      ''
    const name = stripSuffix(label, ['Netflix', 'Prime Video', 'Shahid', 'MBC Shahid'])
      .replace(/\s*[,\-–]\s*(watch now|play|season \d+).*$/i, '')
      .trim()
    // "Season 2" on its own is a fragment of a card, not a title.
    if (name.length < 2 || junk.test(name) || seen.has(name.toLowerCase())) continue
    seen.add(name.toLowerCase())
    out.push({ title: name })
  }
  return out
}

/* Reading a list the worker navigated us to.
 *
 * The difference from a plain read is patience and refusal.
 *
 * Patience, because the worker has just opened the page: reading it at once
 * returns nothing, and reporting nothing as the answer would say your
 * watchlist is empty when it has simply not arrived. So it waits for rows.
 *
 * Refusal, because a watchlist URL can be wrong. Services move them, and the
 * paths for the smaller ones here were never confirmed against a live
 * account. When the address turns out to be a home page, the honest outcome
 * is "could not find your list": the alternative is importing a page of
 * recommendations as though the person had chosen every one of them.
 *
 * Timing is injectable so the wait can be tested without spending it.
 */
const HARVEST_WAIT_MS = 25000
const HARVEST_POLL_MS = 700

/* A question that answers instantly: is this the list, and has it rendered?
 *
 * The worker polls this rather than holding one long request open. A service
 * worker is shut down after thirty seconds idle, and a single await that
 * blocks for twenty-five of them while a page renders is a coin flip: when
 * the worker is killed mid-await the promise never settles, nothing is
 * recorded, nothing is shown, and the import simply evaporates. Short calls
 * keep it alive and make every step observable. */
function peekList(siteId) {
  if (!isListPage(siteId)) return { isList: false, count: 0 }
  return { isList: true, count: readList(siteId).length }
}

async function harvestList(siteId, options = {}) {
  const {
    waitMs = HARVEST_WAIT_MS,
    pollMs = HARVEST_POLL_MS,
    now = () => Date.now(),
    sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  } = options

  if (!isListPage(siteId)) {
    return { ok: false, reason: 'that is not your list page', titles: [] }
  }

  const deadline = now() + waitMs
  while (now() < deadline) {
    if (readList(siteId).length > 0) {
      return { ok: true, titles: sendable(await collectList(siteId)) }
    }
    await sleep(pollMs)
  }
  // A real answer, not a timeout: the page is the list and the list is empty.
  return { ok: true, titles: [] }
}

/* The metadata a card's accessible label carries after the title.
 *
 * Observed on a real import, and all three of these went to the catalog as
 * names to match:
 *   "Werewolf by Night in Color, Movie, 4 minutes left"
 *   "Percy Jackson & The Olympians: The Lightning Thief, Movie, 7 minutes left"
 *   "Now"
 *
 * The label is still the right thing to read: it is what a screen reader
 * announces and it survives a redesign. It just has to be cut at the point
 * where the card stops naming the thing and starts describing it.
 *
 * Anchored on the separator plus a known descriptor rather than on the first
 * comma, because plenty of titles contain one: Crouching Tiger, Hidden
 * Dragon; Sex, Lies, and Videotape; Good Night, and Good Luck.
 */
const CARD_META =
  /\s*[,\u2013\u2014-]\s*(movie|film|series|show|tv show|episode\b|season\b|s\d+\s*e\d+|watch now|play\b|trailer|resume|continue|\d+\s*(min|minute|hr|hour|sec|second)s?\b|\d+%\s*(watched|complete)).*$/i

function cleanCardLabel(label) {
  return stripSuffix(label, ['Netflix', 'Prime Video', 'Shahid', 'MBC Shahid', 'OSN+', 'OSN'])
    .replace(CARD_META, '')
    .replace(/\s*\.\.\.$/, '')
    .trim()
}

/* What the server will actually accept.
 *
 * A real import came back 422 and took the whole list with it, because the
 * match endpoint validates every entry and one bad card fails the request.
 * A single unreadable tile is normal on these pages; losing the other forty
 * titles because of it is not. So the list is cleaned here, on the way out,
 * rather than trusted and rejected wholesale.
 *
 * The limits mirror the server's own: a title is one to three hundred
 * characters, and a request carries at most four hundred of them. */
const MAX_TITLE = 300
const MAX_TITLES = 400

function sendable(entries) {
  const out = []
  const seen = new Set()
  for (const entry of entries || []) {
    const title = String(entry?.title ?? '').trim().slice(0, MAX_TITLE)
    // Percent-escapes are a failed decode, not a name. So are bare numbers.
    if (title.length < 2 || /%[0-9A-F]{2}/i.test(title)) continue
    const key = title.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push({ ...entry, title })
    if (out.length >= MAX_TITLES) break
  }
  return out
}

/** Drop a trailing or leading service name, however it is separated. */
function stripSuffix(title, names) {
  let text = (title || '').trim()
  for (const name of names) {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    text = text
      .replace(new RegExp(`\\s*[|\\-–—:]\\s*${escaped}\\s*$`, 'i'), '')
      .replace(new RegExp(`^\\s*${escaped}\\s*[|\\-–—:]\\s*`, 'i'), '')
  }
  return text.replace(/^watch\s+/i, '').trim()
}

/** Season and episode, when the page says so anywhere obvious. */
function readEpisode(text) {
  const combined = /\bS(\d{1,2})\s*[:.\s]?\s*E(\d{1,3})\b/i.exec(text)
  if (combined) return { season: +combined[1], episode: +combined[2] }
  const season = /\bseason\s*(\d{1,2})\b/i.exec(text)
  const episode = /\bepisode\s*(\d{1,3})\b/i.exec(text)
  if (season || episode) {
    return { season: season ? +season[1] : null, episode: episode ? +episode[1] : null }
  }
  return { season: null, episode: null }
}

/** The site this page belongs to, or null if it is not one we handle. */
function siteFor(host) {
  return SITES.find((s) => s.match(host)) || null
}

const API = {
  SITES, siteFor, stripSuffix, readEpisode, isListPage, readList, collectList, isGeneric,
  harvestList, peekList, LIST_PATTERNS, cleanCardLabel, sendable,
  MAX_TITLE, MAX_TITLES,
}

if (typeof window !== 'undefined') {
  window.__roundtableSites = API
}
// Node, for the tests. Content scripts have no module system, so this is
// guarded rather than a plain export.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = API
}
