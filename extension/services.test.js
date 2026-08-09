/* The service table, and whether every service is actually wired end to end.
 *
 * A service is supported when four separate files agree about it: the
 * adapter that reads its pages, the list pattern that recognises its
 * watchlist, the service entry that says where that watchlist lives, and the
 * app's own provider id. Any one of those missing produces a service that
 * looks supported and quietly does nothing.
 *
 * That is not hypothetical. Before these tests: four services had no list
 * pattern at all, so the import refused every page as "not your list"; Max's
 * pattern wanted my-list while its address is /mylist, so the import refused
 * the very page it had just opened; and Hulu and Crunchyroll claimed to have
 * no provider id when the catalog has both, which disabled the subscription
 * filter for them.
 */
const test = require('node:test')
const assert = require('node:assert')

// sites.js reads these lazily, inside functions, so a bare stub is enough to
// require it. Individual tests set location as they need it.
global.window = undefined
global.navigator = { mediaSession: null }
global.location = { host: '', pathname: '' }
global.document = { title: '', querySelectorAll: () => [] }

const sites = require('./sites.js')

async function services() {
  return await import('./services.js')
}

test('every adapter has a service entry, and the reverse', async () => {
  const { SERVICES } = await services()
  const adapters = sites.SITES.map((s) => s.id).sort()
  const listed = SERVICES.map((s) => s.id).sort()
  assert.deepEqual(listed, adapters, 'sites.js and services.js disagree about which services exist')
})

test('the two files agree on every label and provider id', async () => {
  const { BY_ID } = await services()
  for (const adapter of sites.SITES) {
    const service = BY_ID[adapter.id]
    assert.equal(service.label, adapter.label, `${adapter.id} label`)
    assert.equal(service.provider, adapter.provider, `${adapter.id} provider id`)
  }
})

test('provider ids match the ones the app stores on a profile', async () => {
  /* Checked against the catalog's own availability rows, not remembered. A
     wrong id here silently disables the subscription filter for that
     service, which looks like nothing at all until the wrong things start
     being logged. */
  const { BY_ID } = await services()
  const fromTheCatalog = {
    netflix: 8, prime: 9, hulu: 15, crunchyroll: 283, disney: 337, appletv: 350,
    peacock: 386, paramount: 531, osn: 629, starzplay: 630, shahid: 1715,
    max: 1899, watchit: 2199,
  }
  for (const [id, provider] of Object.entries(fromTheCatalog)) {
    assert.equal(BY_ID[id]?.provider, provider, `${id} provider id`)
  }
  assert.equal(
    Object.keys(fromTheCatalog).length,
    Object.keys(BY_ID).length,
    'a service was added without checking its provider id against the catalog',
  )
})

test('EVERY LIST URL WE OPEN IS ONE THE HARVESTER RECOGNISES', async () => {
  /* The single most important invariant here. The import navigates to each
     path in `service.lists` and then asks isListPage whether it arrived
     somewhere sensible; if the answer is no it refuses, correctly, and the
     feature is dead for that page. Two services failed this when it was
     written. */
  const { SERVICES } = await services()
  for (const service of SERVICES) {
    for (const path of service.lists) {
      global.location = { host: '', pathname: path }
      assert.ok(
        sites.isListPage(service.id),
        `${service.id}: navigating to ${path} lands on a page its own ` +
          'list pattern does not recognise, so the import would refuse it',
      )
    }
  }
})

test('a service whose list is split across pages says so', async () => {
  /* Prime keeps films and series on separate tabs. Reading one of them
     imports half a watchlist and reports success, which is worse than
     failing. Confirmed signed in: /mystuff/watchlist/movie held 5 films and
     /mystuff/watchlist/tv held 5 series, and neither page shows the other. */
  const { BY_ID } = await services()
  assert.deepEqual(BY_ID.prime.lists, ['/mystuff/watchlist/movie', '/mystuff/watchlist/tv'])
  for (const service of Object.values(BY_ID)) {
    assert.ok(Array.isArray(service.lists) && service.lists.length, `${service.id} lists`)
  }
})

test('every service says how to find titles on its list', async () => {
  const { SERVICES } = await services()
  for (const service of SERVICES) {
    const pattern = sites.LIST_PATTERNS[service.id]
    assert.ok(pattern, `${service.id} has no list pattern, so importing it can never work`)
    assert.match(pattern.link, /^a\[href/, `${service.id} link selector`)
  }
})

test('a list URL is absolute and points at the right service', async () => {
  const { SERVICES, serviceForUrl } = await services()
  for (const service of SERVICES) {
    for (const path of service.lists) {
      const url = `${service.origin}${path}`
      assert.doesNotThrow(() => new URL(url), `${service.id} builds a valid URL`)
      assert.equal(serviceForUrl(url)?.id, service.id, `${service.id} recognises its own list URL`)
    }
  }
})

test('the service keeps its own origin, whatever tab is open', async () => {
  const { BY_ID, listUrls } = await services()
  /* An earlier version preferred the origin they were already browsing, on
     the theory that a regional domain was a better bet. It is not: Prime's
     watchlist is on primevideo.com even while you are on an amazon
     storefront, and rewriting the origin sent people somewhere that does not
     hold their list. */
  assert.deepEqual(listUrls(BY_ID.prime, 'https://www.amazon.co.uk/gp/video/storefront'), [
    'https://www.primevideo.com/mystuff/watchlist/movie',
    'https://www.primevideo.com/mystuff/watchlist/tv',
  ])
  assert.deepEqual(listUrls(BY_ID.netflix), ['https://www.netflix.com/browse/my-list'])
})

test('a locale in the path is kept, because it selects a catalog', async () => {
  const { BY_ID, listUrls } = await services()
  // OSN's locale segment is a different catalog, not a translation.
  assert.deepEqual(listUrls(BY_ID.osn), ['https://osnplus.com/en-eg/my-list'])
  assert.deepEqual(listUrls(BY_ID.osn, 'https://osnplus.com/fr-fr/home'), [
    'https://osnplus.com/fr-fr/my-list',
  ])
  assert.deepEqual(listUrls(BY_ID.osn, 'https://osnplus.com/ar/series/foo'), [
    'https://osnplus.com/ar/my-list',
  ])
  // A service with no locale is untouched by a locale-looking path.
  assert.deepEqual(listUrls(BY_ID.netflix, 'https://www.netflix.com/fr/browse'), [
    'https://www.netflix.com/browse/my-list',
  ])
  // Rubbish in, default out, rather than a throw on the way to a page load.
  assert.deepEqual(listUrls(BY_ID.netflix, 'not a url'), [
    'https://www.netflix.com/browse/my-list',
  ])
})

test('serviceForUrl matches hosts and refuses everything else', async () => {
  const { serviceForUrl } = await services()
  assert.equal(serviceForUrl('https://www.netflix.com/browse')?.id, 'netflix')
  assert.equal(serviceForUrl('https://shahid.mbc.net/ar')?.id, 'shahid')
  assert.equal(serviceForUrl('https://play.max.com/mylist')?.id, 'max')
  assert.equal(serviceForUrl('https://example.com'), null)
  assert.equal(serviceForUrl('chrome://extensions'), null)
  assert.equal(serviceForUrl(''), null)
  assert.equal(serviceForUrl(undefined), null)
})

test('an unverified list address is admitted rather than implied', async () => {
  /* Honesty about what was checked against a live account and what was read
     off a public URL scheme. The popup surfaces the failure either way, so
     this is documentation rather than behaviour, but a flag that drifts out
     of date is worse than none. */
  const { BY_ID } = await services()
  // Confirmed against a live signed-in account.
  assert.equal(BY_ID.netflix.verified, true)
  assert.equal(BY_ID.prime.verified, true)
  assert.equal(BY_ID.osn.verified, true)
  for (const service of Object.values(BY_ID)) {
    assert.equal(typeof service.verified, 'boolean', `${service.id} must say either way`)
  }
})


/* Permission to be on the page we send the browser to.
 *
 * The content script only runs where the manifest says it may. A list URL
 * outside that set loads fine, answers nothing, and the import waits out its
 * whole timeout before reporting a failure that looks like the service being
 * slow. The manifest is the fix, and this is how it stays in step. */
const manifest = JSON.parse(require('node:fs').readFileSync('./manifest.json', 'utf8'))

function covers(pattern, url) {
  const parsed = new URL(url)
  const [, rest] = pattern.split('://')
  const patternHost = rest.split('/')[0]
  const path = '/' + rest.split('/').slice(1).join('/')
  const hostOk = patternHost.startsWith('*.')
    ? parsed.host === patternHost.slice(2) || parsed.host.endsWith('.' + patternHost.slice(2))
    : parsed.host === patternHost
  if (!hostOk) return false
  // Only the /* and /prefix/* shapes appear here.
  const prefix = path.replace(/\*$/, '')
  return parsed.pathname.startsWith(prefix)
}

test('the manifest grants access to every list URL we navigate to', async () => {
  const { SERVICES } = await services()
  for (const service of SERVICES) {
    for (const path of service.lists) {
      const url = `${service.origin}${path}`
      assert.ok(
        manifest.host_permissions.some((pattern) => covers(pattern, url)),
        `${service.id}: no host permission covers ${url}`,
      )
      assert.ok(
        manifest.content_scripts[0].matches.some((pattern) => covers(pattern, url)),
        `${service.id}: the content script does not run on ${url}, so nothing can read it`,
      )
    }
  }
})

test('the manifest asks for the permissions the sync needs', () => {
  // tabs, to open the list page and to read the URL of a tab that just
  // finished loading, which is what triggers an automatic sync.
  for (const needed of ['tabs', 'storage', 'alarms', 'notifications']) {
    assert.ok(manifest.permissions.includes(needed), `manifest is missing "${needed}"`)
  }
})
