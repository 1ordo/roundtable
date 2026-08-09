import { enqueue, drain, pending } from './queue.js'
import { BY_ID, listUrls, serviceForUrl } from './services.js'

/* Talks to your Roundtable, and keeps a short log of what it sent.
 *
 * The content script never holds the token and never calls the API: it
 * reports what it saw and this decides what to do with it. That way the
 * token exists in one place, and a compromised streaming page cannot read
 * it out of the page context.
 *
 * Every write goes through the queue first. A server that is briefly down
 * costs a retry rather than the record of something you actually watched.
 */

const RECENT_MAX = 25

/* How long a sync stands before the same service is worth reading again.
 *
 * A watchlist is something you change a few times a week, so re-reading it
 * because you opened a second tab is pure cost: a page load on their
 * connection and a match run on the server, to learn nothing. Ten minutes is
 * long enough that normal browsing syncs once, and short enough that adding
 * something on the service and looking in the app shortly after finds it. */
const SYNC_GRACE_MS = 10 * 60 * 1000

// How long to wait for a navigated tab to be ready to talk to us.
const TAB_READY_MS = 30000

async function settings() {
  const stored = await chrome.storage.local.get([
    'baseUrl',
    'token',
    'paused',
    'providers',
    'autoSync',
  ])
  return {
    baseUrl: (stored.baseUrl || '').replace(/\/+$/, ''),
    token: stored.token || '',
    paused: Boolean(stored.paused),
    // Which services the person actually subscribes to, from their profile.
    providers: stored.providers || [],
    // Undefined means never set, which is a fresh install, and this is the
    // behaviour that was asked for. Only an explicit false turns it off.
    autoSync: stored.autoSync !== false,
  }
}

async function remember(entry) {
  const { recent = [] } = await chrome.storage.local.get('recent')
  recent.unshift({ ...entry, at: Date.now() })
  await chrome.storage.local.set({ recent: recent.slice(0, RECENT_MAX) })
}

/** Only from services they said they have. No list means report everything. */
function subscribed(providers, provider) {
  return !providers.length || !provider || providers.includes(provider)
}

async function post(path, payload) {
  const { baseUrl, token } = await settings()
  return fetch(`${baseUrl}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  })
}

/** What the server decided, recorded and surfaced. */
async function onWritten(payload, result) {
  await remember({
    title: result.name || payload.title,
    site: payload.site,
    action: result.action,
    matched: result.matched,
    poster: result.poster_path || null,
  })

  if (result.action !== 'watched') return

  await chrome.action.setBadgeText({ text: '1' })
  await chrome.action.setBadgeBackgroundColor({ color: '#ec6a3f' })
  // Held so the popup can ask what they thought. Right after the credits is
  // the only moment anyone actually remembers.
  await chrome.storage.local.set({
    pendingRating: {
      name: result.name,
      tmdb_id: result.tmdb_id,
      type: result.type,
      poster: result.poster_path || null,
      at: Date.now(),
    },
  })
  chrome.notifications?.create(`roundtable-${result.tmdb_id}`, {
    type: 'basic',
    iconUrl: 'icon128.png',
    title: `Logged ${result.name}`,
    message: 'Open Roundtable to say what you thought of it.',
  })
}

async function flush() {
  const { baseUrl, token } = await settings()
  if (!baseUrl || !token) return

  await drain(
    (item) => post(item.path, item.payload),
    async (item, result, failure) => {
      if (failure) {
        await remember({ title: item.payload.title, site: item.payload.site, action: failure })
        if (failure.includes('401')) {
          await chrome.action.setBadgeText({ text: '!' })
          await chrome.action.setBadgeBackgroundColor({ color: '#e0505c' })
        }
        return
      }
      if (result) await onWritten(item.payload, result)
    },
  )

  // Something is still waiting: come back for it.
  if ((await pending()) > 0) {
    chrome.alarms.create('roundtable-flush', { delayInMinutes: 1 })
  }
}

async function queueWrite(path, payload) {
  const { baseUrl, token, paused, providers } = await settings()
  if (paused) return
  if (!subscribed(providers, payload.provider)) return
  if (!baseUrl || !token) {
    await remember({ title: payload.title, site: payload.site, action: 'not set up' })
    return
  }
  await enqueue({ path, payload })
  await flush()
}

/* The import flow: match first, show the result, write only on confirm.
   Not queued, because a match that failed can simply be asked again and a
   stale one would only produce a stale review screen. */
async function matchList(payload) {
  const { baseUrl, token } = await settings()
  if (!baseUrl || !token) {
    await chrome.runtime.openOptionsPage()
    return
  }
  try {
    const response = await post('/api/extension/match', payload)
    if (!response.ok) {
      await remember({ title: 'list import', site: payload.site, action: `error ${response.status}` })
      return
    }
    const result = await response.json()
    await chrome.storage.local.set({
      pendingImport: { ...result, site: payload.site, at: Date.now() },
    })
    await chrome.action.setBadgeText({ text: String(result.matched) })
    await chrome.action.setBadgeBackgroundColor({ color: '#4cbaa4' })
    await chrome.tabs.create({ url: chrome.runtime.getURL('import.html') })
  } catch {
    await remember({ title: 'list import', site: payload.site, action: 'unreachable' })
  }
}

/* Fetching a whole list without needing the person to be looking at it.
 *
 * The old import only worked if you had already navigated to your watchlist
 * yourself, which meant the button in the popup was usually a note telling
 * you to go somewhere else. This drives the browser instead: open the list,
 * wait for the content script to read it, act on what came back.
 *
 * A tab is always a NEW one rather than the tab they are using. Navigating
 * somebody off the thing they are watching to read their watchlist would be
 * a strange trade.
 */

/* Tabs this worker opened. A tab we are driving must never be treated as
   the person arriving at a service, or reading a list would schedule reading
   the same list. */
const ours = new Set()

/* Wait until a tab has finished loading the page we asked for.
 *
 * The URL check is not decoration. A tab created with a URL can report
 * "complete" for the blank page it starts on, before navigation begins, and
 * a harvest fired at that moment talks to nothing and burns its retries on a
 * page that was never the list. Waiting for the address as well as the
 * status makes "ready" mean what it says.
 */
function whenReady(tabId, expectUrl) {
  const arrived = (tab) =>
    tab?.status === 'complete' && (!expectUrl || sameOrigin(tab.url, expectUrl))

  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener)
      reject(new Error('timed out loading the page'))
    }, TAB_READY_MS)

    function done() {
      clearTimeout(timer)
      chrome.tabs.onUpdated.removeListener(listener)
      resolve()
    }
    function listener(id, info, tab) {
      if (id === tabId && arrived({ ...tab, status: info.status ?? tab?.status })) done()
    }
    chrome.tabs.onUpdated.addListener(listener)
    // It may already be there: check once rather than wait for an event that
    // has been and gone.
    chrome.tabs.get(tabId).then((tab) => {
      if (arrived(tab)) done()
    }, () => {})
  })
}

/* Whether the tab landed somewhere that could be the page we asked for.
   Compared by host rather than exactly, because these services redirect: a
   locale gets added, a ref parameter gets appended, /watchlist becomes
   /mystuff/watchlist. Any of those is still the right place. */
function sameOrigin(actual, wanted) {
  try {
    return new URL(actual).host === new URL(wanted).host
  } catch {
    return false
  }
}

/* Ask a tab for its list.
 *
 * Polled in short calls rather than one long one, and this is the whole
 * point of it. A service worker is shut down after thirty seconds idle. The
 * previous version opened the tab and then held a single await while the
 * content script waited up to twenty-five seconds for the page to render;
 * when the worker was killed inside that window the promise never settled,
 * so nothing was recorded, nothing was shown, and the import evaporated
 * without an error anywhere. That is exactly what "it does nothing and there
 * are no errors" looks like from outside.
 *
 * Now every message returns in milliseconds and the waiting happens here,
 * where each round of it is fresh activity that keeps the worker alive.
 */
/* Overridable so the test suite does not spend thirty real seconds per case
   waiting for a list that a fake browser is never going to render. Six such
   cases turned a suite with no real work in it into the slowest job in CI.
   Nothing in the extension sets this; only the tests do, before importing. */
const TIMING = globalThis.__roundtableTiming ?? {}
const LIST_WAIT_MS = TIMING.listWaitMs ?? 30000
const LIST_POLL_MS = TIMING.listPollMs ?? 1000

async function askForList(tabId, siteId) {
  const deadline = Date.now() + LIST_WAIT_MS
  let sawPage = false
  let sawList = false

  while (Date.now() < deadline) {
    let peek = null
    try {
      peek = await chrome.tabs.sendMessage(tabId, { type: 'roundtable:peek', siteId })
    } catch {
      // "Receiving end does not exist" while the content script boots.
    }

    if (peek) {
      sawPage = true
      if (peek.adapters === false) {
        return { ok: false, reason: 'the page reader did not load', titles: [] }
      }
      sawList = sawList || peek.isList
      if (peek.isList && peek.count > 0) {
        // Rendered. Collecting is its own short call, because it scrolls.
        return await chrome.tabs.sendMessage(tabId, {
          type: 'roundtable:harvest',
          siteId,
          waitMs: 0,
        })
      }
    }
    await new Promise((resolve) => setTimeout(resolve, LIST_POLL_MS))
  }

  if (!sawPage) return { ok: false, reason: 'the page never answered', titles: [] }
  if (!sawList) return { ok: false, reason: 'that is not your list page', titles: [] }
  return { ok: true, titles: [] } // it is the list, and it is empty
}

/**
 * Open a service's saved list and read it.
 *
 * `auto` decides what happens either side: an automatic sync opens the tab
 * in the background, writes the confident matches straight away and closes
 * the tab again, while a sync somebody asked for happens in front of them
 * and ends on the review screen so nothing is written they did not see.
 */
async function syncService(siteId, { auto = false } = {}) {
  const service = BY_ID[siteId]
  if (!service) return { ok: false, reason: 'unknown service' }

  const { baseUrl, token } = await settings()
  if (!baseUrl || !token) {
    if (!auto) await chrome.runtime.openOptionsPage()
    return { ok: false, reason: 'not set up' }
  }

  // Claimed up front, not on success. This is also what stops the tab we
  // are about to open from tripping the automatic sync for the same service
  // the moment it finishes loading.
  await markSynced(siteId)

  // Only to read which locale they are browsing in. Every tab is fetched and
  // filtered here rather than asked for by match pattern, because a wildcard
  // in the middle of a host is not a legal pattern and chrome.tabs.query
  // throws on one rather than returning nothing.
  //
  // Line comments, not a block: writing a match pattern inside a block
  // comment ends the comment at the pattern's own closing slash-star.
  const open = (await chrome.tabs.query({})).filter(
    (candidate) => candidate.url && serviceForUrl(candidate.url)?.id === siteId,
  )
  const urls = listUrls(service, open[0]?.url || null)

  let tab
  try {
    // Every page of the list, in one tab, unioned. Prime splits films and
    // series across two, and reading one of them imports half a watchlist
    // and reports it as the whole thing.
    const collected = new Map()
    let refusal = null

    for (const [index, url] of urls.entries()) {
      if (index === 0) {
        tab = await chrome.tabs.create({ url, active: !auto })
        ours.add(tab.id)
      } else {
        await chrome.tabs.update(tab.id, { url })
      }
      await whenReady(tab.id, url)
      const page = await askForList(tab.id, siteId)

      if (!page?.ok) {
        // One page of several failing is worth noting but not fatal: the
        // others may still hold most of the list.
        refusal = page?.reason || 'could not read'
        continue
      }
      for (const entry of page.titles) {
        const key = (entry.title || '').toLowerCase()
        if (key && !collected.has(key)) collected.set(key, entry)
      }
    }

    const titles = [...collected.values()]
    if (!titles.length) {
      if (refusal) {
        await remember({
          title: `${service.label} list`,
          site: siteId,
          action: refusal,
          matched: false,
        })
        await release(tab, auto)
        return { ok: false, reason: refusal, service }
      }
      await remember({ title: `${service.label} list`, site: siteId, action: 'nothing on it' })
      await release(tab, auto)
      return { ok: true, titles: 0, service }
    }

    const result = await matchTitles(siteId, titles)
    if (!result) {
      await release(tab, auto)
      return { ok: false, reason: 'unreachable', service }
    }

    if (auto) {
      const added = await importMatched(result, service)
      await release(tab, true)
      return { ok: true, added, matched: result.matched, service }
    }

    // Asked for, so it ends where they can see what it found. The same tab
    // becomes the review screen rather than leaving two open.
    await chrome.storage.local.set({
      pendingImport: { ...result, site: siteId, at: Date.now() },
    })
    await chrome.action.setBadgeText({ text: String(result.matched) })
    await chrome.action.setBadgeBackgroundColor({ color: '#4cbaa4' })
    ours.delete(tab.id)
    await chrome.tabs.update(tab.id, { url: chrome.runtime.getURL('import.html') })
    return { ok: true, matched: result.matched, service }
  } catch (error) {
    await release(tab, auto)
    await remember({
      title: `${service.label} list`,
      site: siteId,
      action: String(error?.message || error),
      matched: false,
    })
    return { ok: false, reason: String(error?.message || error), service }
  }
}

/** Ask the server what a scraped list actually is. Read only. */
async function matchTitles(siteId, titles) {
  try {
    const response = await post('/api/extension/match', { site: siteId, titles })
    if (!response.ok) {
      await remember({ title: 'list import', site: siteId, action: `error ${response.status}` })
      return null
    }
    return await response.json()
  } catch {
    await remember({ title: 'list import', site: siteId, action: 'unreachable' })
    return null
  }
}

/* An automatic sync writes without a review screen, so it writes only what
   the server actually recognised and has not already got. Anything it could
   not identify is left alone rather than guessed at: an unattended import is
   the wrong place to be brave. */
async function importMatched(result, service) {
  const wanted = (result.results || []).filter((row) => row.matched && !row.already)
  if (!wanted.length) {
    await remember({ title: `${service.label} list`, site: service.id, action: 'already in sync' })
    return 0
  }
  try {
    const response = await post('/api/extension/import', {
      titles: wanted.map((row) => ({ type: row.type, tmdb_id: row.tmdb_id })),
    })
    if (!response.ok) {
      await remember({
        title: `${service.label} list`,
        site: service.id,
        action: `error ${response.status}`,
        matched: false,
      })
      return 0
    }
    const written = await response.json()
    await remember({
      title: `${service.label} list`,
      site: service.id,
      action: written.added ? `synced ${written.added}` : 'already in sync',
    })
    if (written.added) {
      chrome.notifications?.create(`roundtable-sync-${service.id}`, {
        type: 'basic',
        iconUrl: 'icon128.png',
        title: `${written.added} from ${service.label}`,
        message: 'Added to your Roundtable watchlist.',
      })
    }
    return written.added
  } catch {
    await remember({ title: `${service.label} list`, site: service.id, action: 'unreachable' })
    return 0
  }
}

/** Close a tab we opened for a background sync, or hand it back. */
async function release(tab, auto) {
  if (!tab?.id) return
  ours.delete(tab.id)
  if (auto) await chrome.tabs.remove(tab.id).catch(() => {})
}

async function markSynced(siteId) {
  const { syncedAt = {} } = await chrome.storage.local.get('syncedAt')
  await chrome.storage.local.set({ syncedAt: { ...syncedAt, [siteId]: Date.now() } })
}

/** Whether this service is due, given the grace period. */
async function dueForSync(siteId) {
  const { syncedAt = {} } = await chrome.storage.local.get('syncedAt')
  return Date.now() - (syncedAt[siteId] || 0) > SYNC_GRACE_MS
}

/* Opening a service is the trigger.
 *
 * Not every page load: the grace period means normal browsing syncs once and
 * then leaves you alone. Not a service they do not subscribe to either, and
 * never while paused, because paused has to mean paused.
 *
 * Deliberately skipped when the tab is already the list page. The person is
 * looking at it, the on-page banner covers that case, and opening a second
 * copy of the page they are on would be absurd.
 */
async function maybeAutoSync(tabUrl) {
  const { paused, providers, autoSync, baseUrl, token } = await settings()
  if (paused || !autoSync || !baseUrl || !token) return
  const service = serviceForUrl(tabUrl)
  if (!service) return
  if (!subscribed(providers, service.provider)) return
  if (!(await dueForSync(service.id))) return
  // Claim the slot before the work, not after: two tabs opening together
  // would otherwise both pass the check and both sync.
  await markSynced(service.id)
  await syncService(service.id, { auto: true })
}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message?.type === 'roundtable:activity') {
    queueWrite('/api/extension/activity', message.payload).finally(() => reply({ ok: true }))
    return true // the reply is async
  }
  if (message?.type === 'roundtable:watchlist') {
    queueWrite('/api/extension/watchlist', message.payload).finally(() => reply({ ok: true }))
    return true
  }
  if (message?.type === 'roundtable:import') {
    matchList(message.payload).finally(() => reply({ ok: true }))
    return true
  }
  if (message?.type === 'roundtable:sync') {
    syncService(message.siteId, { auto: false }).then(reply, (error) =>
      reply({ ok: false, reason: String(error?.message || error) }),
    )
    return true
  }
  return false
})

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status !== 'complete' || !tab?.url || ours.has(tabId)) return
  maybeAutoSync(tab.url)
})

// Anything still queued gets another go, and the browser wakes the worker
// for it even after it has been shut down.
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'roundtable-flush') flush()
})
chrome.runtime.onStartup.addListener(() => flush())
chrome.runtime.onInstalled.addListener(() => flush())
