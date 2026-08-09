/* Loads the worker for real and drives it end to end.
 *
 * This exists because `node --check` passes on a file that calls functions
 * which were never defined. A bad edit left background.js with two `send`
 * declarations and no `flush` or `onWritten` at all: syntactically perfect,
 * and it threw ReferenceError on the first thing anyone watched. Nothing
 * caught it until the file was read by eye.
 *
 * So: fake enough of chrome, load the module, fire the messages it handles,
 * and assert what came out the other side.
 */
const test = require('node:test')
const assert = require('node:assert')

/* Enough of chrome.tabs to drive the import: the worker opens a tab, waits
   for it to load, asks the page for its list and then either closes the tab
   or turns it into the review screen. All four of those have to be real
   here, because the bug this guards against is the flow falling over
   somewhere in the middle and leaving a tab open on somebody's watchlist. */
function tabApi(calls, tabs) {
  let nextId = 100
  return {
    create: async ({ url, active }) => {
      const tab = { id: (nextId += 1), url, active, status: 'complete' }
      // A snapshot, not the live object: `update` mutates the tab, and a
      // record of what was opened has to survive being navigated afterwards.
      tabs.opened.push({ ...tab })
      tabs.live.set(tab.id, tab)
      return tab
    },
    get: async (id) => tabs.live.get(id) || null,
    query: async () => [...tabs.live.values()],
    update: async (id, patch) => {
      const tab = tabs.live.get(id)
      if (tab) Object.assign(tab, patch)
      tabs.updated.push({ id, ...patch })
      return tab
    },
    remove: async (id) => {
      tabs.removed.push(id)
      tabs.live.delete(id)
    },
    sendMessage: async (id, message) => {
      const url = tabs.live.get(id)?.url
      tabs.asked.push({ id, message, url })
      if (tabs.page instanceof Error) throw tabs.page
      const answer = (tabs.pages ? tabs.pages[url] : tabs.page) || { ok: true, titles: [] }
      // Peek is the cheap "is it there yet" question the worker polls.
      if (message.type === 'roundtable:peek') {
        if (answer.adapters === false) return { adapters: false }
        return {
          adapters: true,
          isList: answer.ok !== false,
          count: (answer.titles || []).length,
        }
      }
      return answer
    },
    onUpdated: { addListener: (fn) => tabs.updateListeners.push(fn), removeListener: () => {} },
  }
}

function harness({ respond } = {}) {
  const store = {}
  const listeners = { message: [], alarm: [], startup: [], installed: [] }
  const calls = []
  const badges = []
  const notes = []
  const tabs = {
    opened: [], removed: [], updated: [], asked: [], live: new Map(),
    updateListeners: [],
    // What the content script answers when asked to harvest.
    page: { ok: true, titles: [{ title: 'Inception' }] },
  }

  global.chrome = {
    storage: {
      local: {
        get: async (keys) => {
          const wanted = Array.isArray(keys) ? keys : [keys]
          return Object.fromEntries(wanted.map((k) => [k, store[k]]))
        },
        set: async (patch) => Object.assign(store, patch),
      },
    },
    runtime: {
      onMessage: { addListener: (fn) => listeners.message.push(fn) },
      onStartup: { addListener: (fn) => listeners.startup.push(fn) },
      onInstalled: { addListener: (fn) => listeners.installed.push(fn) },
      openOptionsPage: async () => {},
      getURL: (p) => `chrome-extension://x/${p}`,
    },
    alarms: { create: () => {}, onAlarm: { addListener: (fn) => listeners.alarm.push(fn) } },
    action: {
      setBadgeText: async (o) => badges.push(o.text),
      setBadgeBackgroundColor: async () => {},
    },
    notifications: { create: (id, o) => notes.push(o) },
    tabs: tabApi(calls, tabs),
  }
  global.crypto = { randomUUID: () => Math.random().toString(36).slice(2) }
  global.fetch = async (url, init) => {
    calls.push({ url, body: JSON.parse(init.body) })
    return (
      respond?.(url) ?? {
        ok: true,
        status: 200,
        json: async () => ({ matched: true, name: 'Inception', tmdb_id: 27205, type: 'movie', action: 'watched' }),
      }
    )
  }
  return { store, listeners, calls, badges, notes, tabs }
}

async function load() {
  // The worker waits up to thirty seconds for a watchlist page to render.
  // A fake browser never renders one, so every case that exercises the
  // import path would sit out the whole deadline for real. Milliseconds
  // here; the production defaults are in background.js.
  globalThis.__roundtableTiming = { listWaitMs: 40, listPollMs: 5 }
  return await import(`./background.js?${Math.random()}`)
}

/** Fire a message and wait for the handler to settle. */
function fire(listeners, message) {
  return new Promise((resolve) => {
    listeners.message[0](message, {}, resolve)
  })
}

test('a watch report reaches the server and is recorded', async () => {
  const h = harness()
  Object.assign(h.store, { baseUrl: 'http://x', token: 'wdk_1', providers: [] })
  await load()

  await fire(h.listeners, {
    type: 'roundtable:activity',
    payload: { title: 'Inception', site: 'prime', provider: 9, progress: 0.95 },
  })

  assert.equal(h.calls.length, 1, 'it actually called the API')
  assert.match(h.calls[0].url, /\/api\/extension\/activity$/)
  assert.equal(h.store.recent[0].action, 'watched')
  assert.ok(h.notes.length, 'and told them it was logged')
  assert.ok(h.store.pendingRating, 'and offered a rating')
})

test('a watchlist click reaches the watchlist endpoint', async () => {
  const h = harness({
    respond: () => ({
      ok: true, status: 200,
      json: async () => ({ matched: true, name: 'Get Out', tmdb_id: 419430, type: 'movie', action: 'saved' }),
    }),
  })
  Object.assign(h.store, { baseUrl: 'http://x', token: 'wdk_1', providers: [] })
  await load()

  await fire(h.listeners, {
    type: 'roundtable:watchlist',
    payload: { title: 'Get Out', site: 'prime', provider: 9, add: true },
  })

  assert.match(h.calls[0].url, /\/api\/extension\/watchlist$/)
  assert.equal(h.store.recent[0].action, 'saved')
})

test('a service they do not subscribe to is not reported', async () => {
  const h = harness()
  // Netflix only.
  Object.assign(h.store, { baseUrl: 'http://x', token: 'wdk_1', providers: [8] })
  await load()

  await fire(h.listeners, {
    type: 'roundtable:activity',
    payload: { title: 'Something', site: 'prime', provider: 9, progress: 0.95 },
  })
  assert.equal(h.calls.length, 0)
})

test('paused means nothing is sent', async () => {
  const h = harness()
  Object.assign(h.store, { baseUrl: 'http://x', token: 'wdk_1', providers: [], paused: true })
  await load()
  await fire(h.listeners, {
    type: 'roundtable:activity',
    payload: { title: 'Inception', site: 'prime', provider: 9, progress: 0.95 },
  })
  assert.equal(h.calls.length, 0)
})

test('with no server configured it says so instead of throwing', async () => {
  const h = harness()
  await load()
  await fire(h.listeners, {
    type: 'roundtable:activity',
    payload: { title: 'Inception', site: 'prime', progress: 0.95 },
  })
  assert.equal(h.calls.length, 0)
  assert.equal(h.store.recent[0].action, 'not set up')
})

test('a server that is down keeps the watch for later', async () => {
  const h = harness({ respond: () => { throw new Error('offline') } })
  Object.assign(h.store, { baseUrl: 'http://x', token: 'wdk_1', providers: [] })
  await load()

  await fire(h.listeners, {
    type: 'roundtable:activity',
    payload: { title: 'Whiplash', site: 'prime', provider: 9, progress: 0.95 },
  })
  assert.equal(h.store.queue.length, 1, 'still queued, not lost')
})

test('a rejected token is reported and flagged', async () => {
  const h = harness({ respond: () => ({ ok: false, status: 401 }) })
  Object.assign(h.store, { baseUrl: 'http://x', token: 'bad', providers: [] })
  await load()

  await fire(h.listeners, {
    type: 'roundtable:activity',
    payload: { title: 'Inception', site: 'prime', provider: 9, progress: 0.95 },
  })
  assert.equal(h.store.queue.length, 0, 'not retried forever')
  assert.match(h.store.recent[0].action, /401/)
  assert.ok(h.badges.includes('!'))
})


/* Importing a watchlist without standing on it.
 *
 * This is the flow the popup button drives: open the service's list, wait
 * for the page, ask it what is there, match it, and either show the result
 * or write it. Each test below is one way that can go wrong. */

/** Reply to whichever endpoint is being called. */
function api(routes) {
  return (url) => {
    for (const [fragment, body] of Object.entries(routes)) {
      if (url.includes(fragment)) {
        return { ok: true, status: 200, json: async () => body }
      }
    }
    return { ok: false, status: 404 }
  }
}

const TWO_MATCHES = {
  matched: 2,
  already: 1,
  results: [
    { given: 'Inception', matched: true, name: 'Inception', tmdb_id: 27205, type: 'movie', already: false },
    { given: 'Arrival', matched: true, name: 'Arrival', tmdb_id: 329865, type: 'movie', already: true },
    { given: 'Something Odd', matched: false },
  ],
}

function connected(h, extra = {}) {
  Object.assign(h.store, { baseUrl: 'http://x', token: 'wdk_1', providers: [], ...extra })
}

async function sync(h, siteId) {
  return new Promise((resolve) => {
    h.listeners.message[0]({ type: 'roundtable:sync', siteId }, {}, resolve)
  })
}

test('asking to import opens the list, reads it, and shows what it found', async () => {
  const h = harness({ respond: api({ '/match': TWO_MATCHES }) })
  connected(h)
  await load()

  const result = await sync(h, 'netflix')

  assert.equal(result.ok, true)
  assert.equal(h.tabs.opened.length, 1, 'it opened exactly one tab')
  assert.equal(h.tabs.opened[0].url, 'https://www.netflix.com/browse/my-list')
  assert.equal(h.tabs.opened[0].active, true, 'a sync you asked for happens in front of you')
  assert.ok(
    h.tabs.asked.some((a) => a.message.type === 'roundtable:peek'),
    'it polls a cheap question first',
  )
  assert.ok(h.tabs.asked.some((a) => a.message.type === 'roundtable:harvest'))

  // Nothing written: the review screen is the confirm step.
  assert.ok(!h.calls.some((c) => c.url.includes('/import')), 'it must not write before review')
  assert.equal(h.store.pendingImport.matched, 2)
  // The same tab becomes the review screen rather than leaving two open.
  assert.match(h.tabs.updated[0].url, /import\.html$/)
  assert.deepEqual(h.tabs.removed, [])
})

test('an automatic sync writes quietly and cleans up after itself', async () => {
  const h = harness({ respond: api({ '/match': TWO_MATCHES, '/import': { added: 1, already: 1, failed: 0 } }) })
  connected(h)
  await load()

  // Arriving at Netflix is the trigger.
  const onUpdated = h.tabs.updateListeners.at(-1)
  await onUpdated(1, { status: 'complete' }, { id: 1, url: 'https://www.netflix.com/browse' })
  // The worker's own work is async; let it finish.
  await new Promise((resolve) => setTimeout(resolve, 50))

  assert.equal(h.tabs.opened[0].active, false, 'a sync nobody asked for stays out of the way')
  const wrote = h.calls.find((c) => c.url.includes('/import'))
  assert.ok(wrote, 'an automatic sync does write')
  assert.deepEqual(
    wrote.body.titles,
    [{ type: 'movie', tmdb_id: 27205 }],
    'only what matched and is not already on the list',
  )
  assert.equal(h.tabs.removed.length, 1, 'the tab it opened is closed again')
  assert.ok(h.notes.some((n) => /Netflix/.test(n.title)))
})

test('the same service is not read again inside the grace period', async () => {
  const h = harness({ respond: api({ '/match': TWO_MATCHES, '/import': { added: 1, already: 0, failed: 0 } }) })
  connected(h)
  await load()
  const onUpdated = h.tabs.updateListeners.at(-1)

  const visit = async () => {
    await onUpdated(1, { status: 'complete' }, { id: 1, url: 'https://www.netflix.com/browse' })
    await new Promise((resolve) => setTimeout(resolve, 50))
  }

  await visit()
  assert.equal(h.tabs.opened.length, 1)

  // Opening a second tab minutes later must not re-read the whole list.
  await visit()
  assert.equal(h.tabs.opened.length, 1, 'a second visit inside the grace period is free')

  // Once it has aged out, it is due again.
  h.store.syncedAt = { netflix: Date.now() - 11 * 60 * 1000 }
  await visit()
  assert.equal(h.tabs.opened.length, 2, 'past the grace period it syncs again')
})

test('a service they do not subscribe to is never synced', async () => {
  const h = harness({ respond: api({ '/match': TWO_MATCHES }) })
  connected(h, { providers: [9] }) // Prime only
  await load()
  const onUpdated = h.tabs.updateListeners.at(-1)

  await onUpdated(1, { status: 'complete' }, { id: 1, url: 'https://www.netflix.com/browse' })
  await new Promise((resolve) => setTimeout(resolve, 30))
  assert.equal(h.tabs.opened.length, 0)
})

test('paused means paused, and the toggle turns it off', async () => {
  for (const off of [{ paused: true }, { autoSync: false }]) {
    const h = harness({ respond: api({ '/match': TWO_MATCHES }) })
    connected(h, off)
    await load()
    const onUpdated = h.tabs.updateListeners.at(-1)
    await onUpdated(1, { status: 'complete' }, { id: 1, url: 'https://www.netflix.com/browse' })
    await new Promise((resolve) => setTimeout(resolve, 30))
    assert.equal(h.tabs.opened.length, 0, `${JSON.stringify(off)} should stop the sync`)
  }
})

test('the tab the worker opens does not trigger another sync', async () => {
  /* The tab it opens lands on the watchlist, which is a page on that
     service, which is the trigger. Without a guard this reads the list,
     which opens a tab, which reads the list. */
  const h = harness({ respond: api({ '/match': TWO_MATCHES, '/import': { added: 0, already: 2, failed: 0 } }) })
  connected(h)
  await load()
  const onUpdated = h.tabs.updateListeners.at(-1)

  await onUpdated(1, { status: 'complete' }, { id: 1, url: 'https://www.netflix.com/browse' })
  await new Promise((resolve) => setTimeout(resolve, 50))

  const own = h.tabs.opened[0]
  await onUpdated(own.id, { status: 'complete' }, own)
  await new Promise((resolve) => setTimeout(resolve, 50))

  assert.equal(h.tabs.opened.length, 1, 'it must not chase its own tab')
})

test('a watchlist address that turns out to be wrong says so, and writes nothing', async () => {
  const h = harness({ respond: api({ '/match': TWO_MATCHES }) })
  connected(h)
  await load()
  // What the content script answers when the URL lands on a home page.
  h.tabs.page = { ok: false, reason: 'that is not your list page', titles: [] }

  const result = await sync(h, 'starzplay')

  assert.equal(result.ok, false)
  assert.match(result.reason, /not your list/)
  assert.ok(!h.calls.some((c) => c.url.includes('/import')), 'nothing may be written')
  assert.ok(!h.calls.some((c) => c.url.includes('/match')), 'and nothing sent to be matched')
  assert.match(h.store.recent[0].action, /not your list/)
})

test('an empty list is reported as empty, not as a failure', async () => {
  const h = harness({ respond: api({ '/match': TWO_MATCHES }) })
  connected(h)
  await load()
  h.tabs.page = { ok: true, titles: [] }

  const result = await sync(h, 'netflix')
  assert.equal(result.ok, true)
  assert.equal(result.titles, 0)
  assert.equal(h.store.recent[0].action, 'nothing on it')
})

test('a page that never answers gives up rather than hanging', async () => {
  const h = harness({ respond: api({ '/match': TWO_MATCHES }) })
  connected(h)
  await load()
  h.tabs.page = new Error('Receiving end does not exist')

  const result = await sync(h, 'netflix')
  assert.equal(result.ok, false)
  assert.match(result.reason, /never answered/)
})

test('importing without a server configured opens settings instead of failing', async () => {
  const h = harness()
  await load()
  const result = await sync(h, 'netflix')
  assert.equal(result.ok, false)
  assert.equal(result.reason, 'not set up')
  assert.equal(h.tabs.opened.length, 0)
})


test('a watchlist split across two pages is read in full', async () => {
  /* Prime keeps films and series on separate tabs and neither shows the
     other. These are the real contents of both, read while signed in. A
     single-page import returned five of the ten and called it done. */
  const h = harness({ respond: api({ '/match': { matched: 0, already: 0, results: [] } }) })
  connected(h)
  await load()
  h.tabs.pages = {
    'https://www.primevideo.com/mystuff/watchlist/movie': {
      ok: true,
      titles: [
        { title: 'Get Out' },
        { title: 'Apocalypse Z: The Beginning of the End' },
        { title: 'Legally Blonde 2: Red, White And Blonde' },
      ],
    },
    'https://www.primevideo.com/mystuff/watchlist/tv': {
      ok: true,
      titles: [{ title: 'The Boys - Season 2' }, { title: 'The Mentalist - Season 2' }],
    },
  }

  await sync(h, 'prime')

  assert.equal(h.tabs.opened.length, 1, 'one tab, walked through both pages')
  assert.equal(
    h.tabs.asked.filter((a) => a.message.type === 'roundtable:harvest').length,
    2,
    'both pages were read',
  )
  const sent = h.calls.find((c) => c.url.includes('/match')).body.titles.map((t) => t.title)
  assert.deepEqual(sent, [
    'Get Out',
    'Apocalypse Z: The Beginning of the End',
    'Legally Blonde 2: Red, White And Blonde',
    'The Boys - Season 2',
    'The Mentalist - Season 2',
  ])
})

test('one page of several failing does not lose the rest', async () => {
  const h = harness({ respond: api({ '/match': { matched: 0, already: 0, results: [] } }) })
  connected(h)
  await load()
  h.tabs.pages = {
    'https://www.primevideo.com/mystuff/watchlist/movie': { ok: true, titles: [{ title: 'Get Out' }] },
    'https://www.primevideo.com/mystuff/watchlist/tv': { ok: false, reason: 'that is not your list page', titles: [] },
  }

  const result = await sync(h, 'prime')
  assert.equal(result.ok, true)
  const sent = h.calls.find((c) => c.url.includes('/match')).body.titles.map((t) => t.title)
  assert.deepEqual(sent, ['Get Out'], 'the page that worked still counts')
})

test('every page failing is a failure, not an empty list', async () => {
  const h = harness({ respond: api({ '/match': { matched: 0, already: 0, results: [] } }) })
  connected(h)
  await load()
  h.tabs.page = { ok: false, reason: 'that is not your list page', titles: [] }

  const result = await sync(h, 'prime')
  assert.equal(result.ok, false)
  assert.match(result.reason, /not your list/)
  assert.ok(!h.calls.some((c) => c.url.includes('/match')))
})


test('a tab that reports complete before it has navigated is not harvested', async () => {
  /* chrome.tabs.create resolves with a tab that can say "complete" for the
     blank page it starts on. Firing the harvest then talks to nothing and
     burns every retry on a page that was never the list, which surfaces as
     "the page never answered" and looks like the service being slow. */
  const h = harness({ respond: api({ '/match': { matched: 0, already: 0, results: [] } }) })
  connected(h)
  await load()

  // The tab starts blank and only becomes the list a moment later.
  const realCreate = global.chrome.tabs.create
  global.chrome.tabs.create = async ({ url, active }) => {
    const tab = await realCreate({ url, active })
    const target = tab.url
    tab.url = 'about:blank'
    tab.status = 'complete'
    setTimeout(() => {
      tab.url = target
      h.tabs.updateListeners.forEach((fn) => fn(tab.id, { status: 'complete' }, tab))
    }, 60)
    return tab
  }
  h.tabs.pages = { 'https://www.netflix.com/browse/my-list': { ok: true, titles: [{ title: 'Get Out' }] } }

  await sync(h, 'netflix')

  assert.ok(
    h.tabs.asked.every((a) => a.url === 'https://www.netflix.com/browse/my-list'),
    'nothing was asked of the blank page it started on',
  )
  global.chrome.tabs.create = realCreate
})

test('a redirect to the same service still counts as arrived', async () => {
  /* These services redirect constantly: a locale is added, a ref parameter
     is appended, /watchlist becomes /mystuff/watchlist. Comparing the whole
     address would make every one of those a timeout. */
  const h = harness({ respond: api({ '/match': { matched: 0, already: 0, results: [] } }) })
  connected(h)
  await load()
  const realCreate = global.chrome.tabs.create
  global.chrome.tabs.create = async ({ url, active }) => {
    const tab = await realCreate({ url, active })
    tab.url = 'https://osnplus.com/en-eg/my-list?ref_=nav'
    tab.status = 'complete'
    return tab
  }
  h.tabs.pages = { 'https://osnplus.com/en-eg/my-list?ref_=nav': { ok: true, titles: [{ title: 'The Shining' }] } }

  const result = await sync(h, 'osn')
  assert.equal(result.ok, true)
  global.chrome.tabs.create = realCreate
})
