/* The pure half of the extension, tested without a browser.
 *
 * These cover the things that actually broke in use: a service tagline
 * reported as a title, an Arabic heading sent instead of a romanised slug,
 * and card fragments like "Season 2" arriving as titles of their own. */
const test = require('node:test')
const assert = require('node:assert')

// The content script reads globals off window; give it enough of one.
global.window = undefined
global.navigator = { mediaSession: null }
global.location = { host: '', pathname: '' }
global.document = { title: '', querySelectorAll: () => [] }

const { siteFor, stripSuffix, readEpisode, isGeneric, isListPage } = require('./sites.js')

test('recognises the services it supports', () => {
  assert.equal(siteFor('www.netflix.com')?.id, 'netflix')
  assert.equal(siteFor('www.primevideo.com')?.id, 'prime')
  assert.equal(siteFor('shahid.mbc.net')?.id, 'shahid')
  assert.equal(siteFor('www.osnplus.com')?.id, 'osn')
  assert.equal(siteFor('example.com'), null)
})

test('every service states its provider id, or states that it has none', () => {
  /* The subscription filter skips any site whose provider is undefined, so
     forgetting an id silently disables the filter for that service. Hulu
     and Crunchyroll used to declare null here on the grounds that the app
     did not track them; the catalog carries availability for both, so that
     was an omission wearing a decision's clothes. */
  const { SITES } = require('./sites.js')
  const undeclared = SITES.filter((s) => !('provider' in s)).map((s) => s.id)
  assert.deepEqual(undeclared, [], `these never mention a provider id: ${undeclared}`)

  // The ones the app does track must match the ids it stores on a profile.
  const expected = {
    netflix: 8, prime: 9, hulu: 15, crunchyroll: 283, disney: 337,
    appletv: 350, peacock: 386, paramount: 531, osn: 629, starzplay: 630,
    shahid: 1715, max: 1899, watchit: 2199,
  }
  for (const [id, provider] of Object.entries(expected)) {
    assert.equal(SITES.find((s) => s.id === id)?.provider, provider, `${id} provider id`)
  }
})

test('strips the service name however it is attached', () => {
  assert.equal(stripSuffix('Chernobyl | Netflix', ['Netflix']), 'Chernobyl')
  assert.equal(stripSuffix('Netflix - Chernobyl', ['Netflix']), 'Chernobyl')
  assert.equal(stripSuffix('Watch Chernobyl', []), 'Chernobyl')
  assert.equal(stripSuffix('Chernobyl', ['Netflix']), 'Chernobyl')
})

test('refuses the service talking about itself', () => {
  // Observed in the wild: this went to the catalog as a title to match.
  assert.ok(isGeneric('Watch movies, TV shows, sports, and live TV'))
  assert.ok(isGeneric('Prime Video'))
  assert.ok(isGeneric('Your Watchlist'))
  assert.ok(isGeneric(''))
  assert.ok(!isGeneric('Project Hail Mary'))
  assert.ok(!isGeneric('The Boys'))
})

test('reads season and episode when the page says so', () => {
  assert.deepEqual(readEpisode('The Bear S01E03'), { season: 1, episode: 3 })
  assert.deepEqual(readEpisode('Breaking Bad Season 2 Episode 5'), { season: 2, episode: 5 })
  assert.deepEqual(readEpisode('Inception'), { season: null, episode: null })
})

test('knows a saved list page from a title page', () => {
  global.location = { host: 'www.primevideo.com', pathname: '/mystuff/watchlist' }
  assert.ok(isListPage('prime'))
  global.location = { host: 'www.primevideo.com', pathname: '/detail/0ABC' }
  assert.ok(!isListPage('prime'))
})

test('shahid uses the romanised slug, not the arabic heading', () => {
  // The page renders in Arabic. Sending that to a catalog indexed under the
  // romanised name matches nothing, which is why the slug wins.
  global.location = {
    host: 'shahid.mbc.net',
    pathname: '/ar/series/Ward-Ala-Foll-Wa-Yasmeen/series-49923416471974',
  }
  global.document = { title: 'شاهد ورد على فل وياسمين - الموسم 1 | MBC شاهد', querySelectorAll: () => [] }
  const site = siteFor('shahid.mbc.net')
  assert.equal(site.title(), 'Ward Ala Foll Wa Yasmeen')
  assert.equal(site.kind(), 'tv')
})

test('prime takes the name out of the document title', () => {
  global.location = { host: 'www.primevideo.com', pathname: '/detail/0ABC' }
  global.document = { title: 'Prime Video: Project Hail Mary', querySelectorAll: () => [] }
  assert.equal(siteFor('www.primevideo.com').title(), 'Project Hail Mary')
})


/* Every adapter, not just the two that were debugged in anger.
 *
 * Each row is a page that service really serves: a path that is playback, a
 * path that is not, and the document title as that site writes it. An
 * adapter whose `playing` matches the home page reports the home page as
 * something you watched, which is how "Watch movies, TV shows, sports and
 * live TV" ended up in a history. */
const PAGES = [
  { id: 'netflix', host: 'www.netflix.com', playing: '/watch/80100172', idle: '/browse',
    title: 'Chernobyl | Netflix', expect: 'Chernobyl' },
  { id: 'prime', host: 'www.primevideo.com', playing: '/detail/0ABCDEF', idle: '/storefront',
    title: 'Prime Video: Project Hail Mary', expect: 'Project Hail Mary' },
  { id: 'shahid', host: 'shahid.mbc.net', playing: '/ar/series/Al-Hayba/series-771', idle: '/ar',
    title: 'الهيبة | MBC شاهد', expect: 'Al Hayba' },
  { id: 'disney', host: 'www.disneyplus.com', playing: '/movies/moana/1Cx3', idle: '/home',
    title: 'Moana | Disney+', expect: 'Moana' },
  { id: 'osn', host: 'www.osnplus.com', playing: '/en/watch/the-wire', idle: '/en',
    title: 'The Wire - OSN+', expect: 'The Wire' },
  { id: 'max', host: 'play.max.com', playing: '/video/watch/abc-123', idle: '/home',
    title: 'Dune | Max', expect: 'Dune' },
  { id: 'appletv', host: 'tv.apple.com', playing: '/episode/umc.cmc.1', idle: '/browse',
    title: 'Severance | Apple TV+', expect: 'Severance' },
  { id: 'hulu', host: 'www.hulu.com', playing: '/watch/9c1e', idle: '/hub/movies',
    title: 'The Bear | Hulu', expect: 'The Bear' },
  { id: 'crunchyroll', host: 'www.crunchyroll.com', playing: '/watch/GRDV0019R', idle: '/videos/popular',
    title: 'Frieren | Crunchyroll', expect: 'Frieren' },
  { id: 'paramount', host: 'www.paramountplus.com', playing: '/shows/yellowstone/', idle: '/home/',
    title: 'Yellowstone - Paramount+', expect: 'Yellowstone' },
  { id: 'peacock', host: 'www.peacocktv.com', playing: '/watch/playback/abc', idle: '/stream',
    title: 'Poker Face | Peacock', expect: 'Poker Face' },
  { id: 'starzplay', host: 'www.starzplay.com', playing: '/movies/john-wick', idle: '/home',
    title: 'John Wick | STARZPLAY', expect: 'John Wick' },
  { id: 'watchit', host: 'www.watchit.com', playing: '/movie/el-feel-el-azraq', idle: '/home',
    title: 'El Feel El Azraq | Watch It', expect: 'El Feel El Azraq' },
]

test('every adapter is covered by a page test', () => {
  const { SITES } = require('./sites.js')
  assert.deepEqual(
    PAGES.map((p) => p.id).sort(),
    SITES.map((s) => s.id).sort(),
    'an adapter was added without a page to test it against',
  )
})

for (const page of PAGES) {
  test(`${page.id}: reads the title and knows playback from browsing`, () => {
    const site = siteFor(page.host)
    assert.ok(site, `${page.host} is not recognised`)
    assert.equal(site.id, page.id)

    assert.ok(site.playing(page.playing), `${page.playing} should count as playback`)
    assert.ok(!site.playing(page.idle), `${page.idle} is browsing, not watching`)

    global.location = { host: page.host, pathname: page.playing }
    global.document = { title: page.title, querySelectorAll: () => [] }
    assert.equal(site.title(), page.expect)
    // Whatever it read must survive the self-description filter, or the
    // adapter works and the report is dropped anyway.
    assert.ok(!isGeneric(site.title()), `${page.id} title was rejected as generic`)
  })
}


/* Harvesting: what happens when the worker opens a list page for you. */
function pageWith(names, selectorMatches = true) {
  const links = names.map((name) => ({
    getAttribute: (attribute) => (attribute === 'aria-label' ? name : null),
    querySelector: () => null,
    textContent: '',
  }))
  return {
    title: '',
    // Only the list selector returns links; the carousel probe finds no
    // scrollable rows, so collectList reads once and stops.
    querySelectorAll: (selector) =>
      selectorMatches && selector.startsWith('a[href') ? links : [],
  }
}

test('harvest refuses a page that is not the list', async () => {
  const { harvestList } = require('./sites.js')
  global.location = { host: 'www.netflix.com', pathname: '/browse' }
  global.document = pageWith(['Some Recommendation', 'Another One'])

  const result = await harvestList('netflix', { waitMs: 10, pollMs: 1 })
  assert.equal(result.ok, false)
  assert.deepEqual(result.titles, [])
  assert.match(result.reason, /not your list/)
})

test('harvest waits for a list that has not rendered yet', async () => {
  const { harvestList } = require('./sites.js')
  global.location = { host: 'www.netflix.com', pathname: '/browse/my-list' }
  global.document = pageWith([], false)

  let slept = 0
  const result = await harvestList('netflix', {
    waitMs: 1000,
    pollMs: 100,
    now: () => slept,
    sleep: async (ms) => {
      slept += ms
      // Arrives on the third look, the way a real page does.
      if (slept >= 300) global.document = pageWith(['Inception', 'Arrival'])
    },
  })
  assert.equal(result.ok, true)
  assert.deepEqual(result.titles.map((t) => t.title), ['Inception', 'Arrival'])
  assert.ok(slept >= 300, 'it should have waited rather than answered immediately')
})

test('an empty list is an answer, not a timeout', async () => {
  const { harvestList } = require('./sites.js')
  global.location = { host: 'www.netflix.com', pathname: '/browse/my-list' }
  global.document = pageWith([], false)

  let clock = 0
  const result = await harvestList('netflix', {
    waitMs: 500,
    pollMs: 100,
    now: () => clock,
    sleep: async (ms) => {
      clock += ms
    },
  })
  // Nothing on it, and it says so plainly rather than reporting a failure
  // the popup would show as "could not read your list".
  assert.equal(result.ok, true)
  assert.deepEqual(result.titles, [])
})


/* Card labels, from a real import that went wrong.
 *
 * These three arrived in the "Not recognised" column of the review screen,
 * which is where the accessible label of a continue-watching card ends up
 * when it is read as a title. The label is still the right thing to read;
 * it just has to be cut where the card stops naming the thing and starts
 * describing it. */
test('a card label is cut where the title ends', () => {
  const { cleanCardLabel } = require('./sites.js')
  const real = {
    'Werewolf by Night in Color, Movie, 4 minutes left': 'Werewolf by Night in Color',
    'Percy Jackson & The Olympians: The Lightning Thief, Movie, 7 minutes left':
      'Percy Jackson & The Olympians: The Lightning Thief',
    'The Boys - Season 2': 'The Boys',
    'The Mentalist: The Complete First Season': 'The Mentalist: The Complete First Season',
    'Dune, Movie': 'Dune',
    'Severance, Series, S2 E4': 'Severance',
    'Arcane - Watch now': 'Arcane',
    'Inception, 2 hours 28 minutes': 'Inception',
    'Shogun, 45% watched': 'Shogun',
  }
  for (const [label, expected] of Object.entries(real)) {
    assert.equal(cleanCardLabel(label), expected, `cleaning ${label!== undefined ? JSON.stringify(label) : ''}`)
  }
})

test('a title with a comma in it survives the cut', () => {
  /* Anchoring on the first comma would have been simpler and wrong. These
     are all real films. */
  const { cleanCardLabel } = require('./sites.js')
  for (const title of [
    'Crouching Tiger, Hidden Dragon',
    'Sex, Lies, and Videotape',
    'Good Night, and Good Luck',
    'Hello, Dolly!',
    'Paris, Texas',
  ]) {
    assert.equal(cleanCardLabel(title), title)
  }
})

test('a row heading is not a title', () => {
  /* "Now" is the heading of a continue-watching strip. It was sent to the
     catalog to be matched. */
  global.location = { host: 'www.primevideo.com', pathname: '/mystuff/watchlist' }
  const links = ['Now', 'Continue watching', 'Top 10', 'Season 3', 'Inception'].map((name) => ({
    getAttribute: (a) => (a === 'aria-label' ? name : null),
    querySelector: () => null,
    textContent: '',
  }))
  global.document = {
    title: '',
    querySelectorAll: (selector) => (selector.startsWith('a[href') ? links : []),
  }
  const { readList } = require('./sites.js')
  assert.deepEqual(
    readList('prime').map((t) => t.title),
    ['Inception'],
    'only the one that is actually a title should survive',
  )
})


test('a declined offer comes back later instead of never', () => {
  /* "Not now" used to set a session flag with no expiry, so one press killed
     the offer on that service until the browser restarted, silently. Anyone
     trying the feature twice hit it, and the second attempt was
     indistinguishable from the extension having stopped working. */
  const store = {}
  global.localStorage = {
    getItem: (k) => store[k] ?? null,
    setItem: (k, v) => { store[k] = String(v) },
    removeItem: (k) => { delete store[k] },
  }
  const QUIET = 60 * 60 * 1000
  const recentlyDeclined = (now) => {
    const until = Number(store['watchpile-declined'] || 0)
    if (!until) return false
    if (now > until) { delete store['watchpile-declined']; return false }
    return true
  }

  const t0 = 1_000_000
  assert.equal(recentlyDeclined(t0), false, 'nothing declined yet')
  store['watchpile-declined'] = String(t0 + QUIET)
  assert.equal(recentlyDeclined(t0 + 60_000), true, 'a minute later it stays quiet')
  assert.equal(recentlyDeclined(t0 + QUIET + 1), false, 'an hour later it offers again')
  assert.equal(store['watchpile-declined'], undefined, 'and forgets it, rather than checking forever')
})


test('walking away from the list and back offers again', () => {
  /* These services are single page apps, so arriving at your list is a route
     change, not a page load. The "already offered" flag only used to clear
     on a full reload, so the second visit in a session was silent and looked
     like the extension had stopped working. */
  let offered = false
  let onListPage = false
  const shown = []

  // The loop from content.js, with the page state as a parameter.
  function tick(isList, rendered = true) {
    if (onListPage && !isList) {
      onListPage = false
      offered = false
      return
    }
    onListPage = isList
    if (!isList || !rendered) return
    if (!offered) {
      offered = true
      shown.push('bar')
    }
  }

  tick(true)                       // arrive at the list
  assert.equal(shown.length, 1)
  tick(true)                       // still there: not shown twice
  assert.equal(shown.length, 1)
  tick(false)                      // browse away, still no page load
  tick(false)
  tick(true)                       // come back
  assert.equal(shown.length, 2, 'a second visit must get its own offer')
})


test('an unusable card does not take the whole import with it', () => {
  /* A real import came back 422 and lost the entire list, because the match
     endpoint validates every entry and one bad one fails the request. A
     single unreadable tile is normal on these pages. */
  const { sendable, MAX_TITLE } = require('./sites.js')
  const out = sendable([
    { title: 'Inception' },
    { title: '' },
    { title: ' ' },
    { title: 'x' },
    { title: null },
    undefined,
    // A failed decode is an escape sequence, not a name. Seen in a real log.
    { title: '%D8%AA%D8%AD%D8%AA%20%D8%A7%D9%84%D8%B3%D9%86' },
    { title: 'A'.repeat(500) },
    { title: 'Inception' },
    { title: 'INCEPTION' },
  ])
  assert.deepEqual(
    out.map((t) => t.title.slice(0, 12)),
    ['Inception', 'AAAAAAAAAAAA'],
    'the good ones survive, the rest are dropped rather than sent',
  )
  assert.equal(out[1].title.length, MAX_TITLE, 'over-long is trimmed, not discarded')
})

test('shahid decodes an arabic slug instead of sending escapes', () => {
  /* The slug is only romanised for shows with a Latin name. An Arabic one is
     percent-encoded in the path, and the raw value went to the catalog as a
     title: "%D8%AA%D8%AD%D8%AA..." appeared in a real popup log. */
  const { siteFor } = require('./sites.js')
  const site = siteFor('shahid.mbc.net')

  global.location = {
    host: 'shahid.mbc.net',
    pathname: '/ar/series/' + encodeURIComponent('تحت السن') + '/season-49923752756763',
  }
  global.document = { title: 'تحت السن | MBC شاهد', querySelectorAll: () => [] }
  assert.equal(site.title(), 'تحت السن')

  // A Latin slug still wins, unchanged.
  global.location = { host: 'shahid.mbc.net', pathname: '/ar/series/Al-Hayba/series-771' }
  assert.equal(site.title(), 'Al Hayba')
})

test('shahid calls its saved list favorite', () => {
  const { isListPage } = require('./sites.js')
  global.location = { host: 'shahid.mbc.net', pathname: '/ar/favorite' }
  assert.ok(isListPage('shahid'))
  global.location = { host: 'shahid.mbc.net', pathname: '/ar/series/Al-Hayba/series-771' }
  assert.ok(!isListPage('shahid'))
})
