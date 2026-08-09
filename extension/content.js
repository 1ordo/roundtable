/* Watches the page, and says so.
 *
 * The first version reported only while a video was actually playing, and
 * showed nothing at all until a title reached 88 percent. That is
 * indistinguishable from broken: you open something, nothing visible
 * happens, and there is no way to tell whether the extension is even
 * running. So it now also:
 *   - marks the document, so "is it loaded" has an answer
 *   - reports a title you opened, not only one you played
 *   - says once, quietly, when it starts following something
 */

const SAMPLE_MS = 4000
// Report again once progress has moved this much, so a two hour film sends
// a handful of updates rather than hundreds.
const PROGRESS_STEP = 0.1

let lastKey = null
let lastProgress = -1
let toldAbout = null

/* Visible from the page and from devtools, so whether it loaded is a
   question with an answer that does not involve the extensions page.
 *
 * The REAL version, not a string that gets forgotten. It sat at "0.2.0"
 * through six releases, which meant the one diagnostic the extension has
 * could confirm that something was running and never which something. When
 * a fix appears not to work, the first question is whether the copy in the
 * browser contains it, and this is the only thing that can answer it. */
document.documentElement.dataset.roundtable = chrome.runtime.getManifest().version

function findVideo() {
  // The largest playing video, because players leave hidden ones around for
  // trailers and previews.
  const videos = [...document.querySelectorAll('video')]
    .filter((v) => v.duration > 60 && !v.paused && v.currentTime > 0)
    .sort((a, b) => b.duration - a.duration)
  return videos[0] || null
}

function detect() {
  const { siteFor, readEpisode, isGeneric } = window.__roundtableSites || {}
  if (!siteFor) return null
  const site = siteFor(location.host)
  if (!site) return null

  if (!site.playing(location.pathname)) return null

  // The player's own metadata first: it is a standard, and it is already
  // the clean name.
  const fromSession = navigator.mediaSession?.metadata?.title?.trim() || null
  const name = fromSession || site.title()
  if (!name || name.length < 2) return null
  /* The service talking about itself, or a title that has not caught up
     with a navigation yet. Reporting either is how "Watch movies, TV shows,
     sports" ended up in the log as something being watched. */
  if (isGeneric(name)) return null

  // Opening a title counts. Nothing playing yet simply means no progress,
  // and the server records interest separately from watching.
  const video = findVideo()
  const { season, episode } = readEpisode(
    `${document.title} ${navigator.mediaSession?.metadata?.artist || ''}`,
  )

  return {
    title: name,
    site: site.id,
    // So the worker can honour "I subscribe to this" without another lookup.
    provider: site.provider || null,
    kind: site.kind ? site.kind() : null,
    season,
    episode,
    progress: video && video.duration ? Math.min(1, video.currentTime / video.duration) : null,
  }
}

/* Said once per title, small, bottom left, gone in a few seconds. Enough to
   know it is working, not enough to become something to close. */
function toast(text) {
  document.getElementById('roundtable-toast')?.remove()
  const box = document.createElement('div')
  box.id = 'roundtable-toast'
  box.textContent = text
  box.style.cssText = [
    'position:fixed', 'z-index:2147483647', 'left:18px', 'bottom:18px',
    'padding:9px 14px', 'border-radius:10px', 'background:#221a1d',
    'color:#f2ebe4', 'border:1px solid #3d3034', 'pointer-events:none',
    'box-shadow:0 12px 34px rgba(0,0,0,.5)', 'opacity:0',
    'transition:opacity .25s', 'font:12.5px/1.4 system-ui,-apple-system,sans-serif',
  ].join(';')
  document.body.append(box)
  requestAnimationFrame(() => (box.style.opacity = '1'))
  setTimeout(() => {
    box.style.opacity = '0'
    setTimeout(() => box.remove(), 300)
  }, 3600)
}

function sample() {
  let payload
  try {
    payload = detect()
  } catch (error) {
    // A site changing its markup must never break the page it is on.
    console.debug('roundtable: could not read this page', error)
    return
  }
  if (!payload) return

  const key = `${payload.site}:${payload.title}:${payload.season}:${payload.episode}`

  // Once per title, whether or not it is playing yet.
  if (key !== toldAbout) {
    toldAbout = key
    toast(`Roundtable is following ${payload.title}`)
  }

  const progress = payload.progress ?? 0
  const moved = Math.abs(progress - lastProgress) >= PROGRESS_STEP
  const finishing = progress >= 0.88 && lastProgress < 0.88
  if (key === lastKey && !moved && !finishing) return

  lastKey = key
  lastProgress = progress
  chrome.runtime.sendMessage({ type: 'roundtable:activity', payload }, () => {
    // The worker may be asleep. Swallowing this keeps the page clean; the
    // next sample will try again.
    void chrome.runtime.lastError
  })
}

// A new title resets the throttle, or finishing one film would suppress the
// first report of the next.
let lastPath = location.pathname
setInterval(() => {
  if (location.pathname !== lastPath) {
    lastPath = location.pathname
    lastKey = null
    lastProgress = -1
  }
  sample()
}, SAMPLE_MS)
// Do not wait a whole interval to notice the page you just opened.
setTimeout(sample, 1200)


/* Offering to import a saved list.
 *
 * Only when you are actually looking at your list, only once per visit, and
 * it never reads anything until you say yes. An extension that silently
 * hoovered up a list the moment a page loaded would be doing something
 * nobody asked for. */
let offered = false
// How long "Not now" holds. See the note where it is set.
const DECLINE_QUIET_MS = 60 * 60 * 1000

function recentlyDeclined() {
  const until = Number(localStorage.getItem('roundtable-declined') || 0)
  if (!until) return false
  if (Date.now() > until) {
    localStorage.removeItem('roundtable-declined')
    return false
  }
  return true
}

function offerImport(site) {
  const { readList } = window.__roundtableSites
  if (offered || document.getElementById('roundtable-offer')) return
  offered = true

  const bar = document.createElement('div')
  bar.id = 'roundtable-offer'
  bar.style.cssText = [
    'position:fixed', 'z-index:2147483647', 'right:18px', 'bottom:18px',
    'max-width:320px', 'padding:14px 16px', 'border-radius:12px',
    'background:#221a1d', 'color:#f2ebe4', 'border:1px solid #3d3034',
    'box-shadow:0 18px 50px rgba(0,0,0,.55)',
    'font:13px/1.5 system-ui,-apple-system,sans-serif',
  ].join(';')

  const count = readList(site.id).length
  bar.innerHTML = `
    <div style="font-weight:600;margin-bottom:4px">Import this list?</div>
    <div style="color:#a2938e;margin-bottom:11px">
      ${count} titles on your ${site.label} list. You will see what matched before
      anything is saved.
    </div>
    <div style="display:flex;gap:8px">
      <button id="roundtable-yes" style="flex:1;padding:7px 12px;border-radius:8px;border:none;
        background:#ec6a3f;color:#181114;font:inherit;font-weight:600;cursor:pointer">Have a look</button>
      <button id="roundtable-no" style="padding:7px 12px;border-radius:8px;
        border:1px solid #3d3034;background:none;color:#a2938e;font:inherit;cursor:pointer">Not now</button>
    </div>`
  document.body.append(bar)

  bar.querySelector('#roundtable-no').addEventListener('click', () => {
    bar.remove()
    /* Quiet for an hour, not for the whole session.
     *
     * This used to set a session flag with no expiry, so one "Not now"
     * killed the offer on that service until the browser restarted, with
     * nothing to say it had happened. Anyone trying the feature twice hit
     * it, and the second attempt looked like the extension had stopped
     * working. An hour is long enough not to nag and short enough that
     * coming back later just works. */
    localStorage.setItem('roundtable-declined', String(Date.now() + DECLINE_QUIET_MS))
  })
  bar.querySelector('#roundtable-yes').addEventListener('click', async () => {
    bar.querySelector('#roundtable-yes').textContent = 'Reading your list'
    /* collectList, not readList. The rows are virtualised on most of these
       services, so a plain read returns the five cards currently in the DOM
       and silently imports a fraction of the list. This scrolls them. */
    const titles = await window.__roundtableSites.collectList(site.id)
    bar.remove()
    chrome.runtime.sendMessage(
      { type: 'roundtable:import', payload: { site: site.id, titles } },
      () => void chrome.runtime.lastError,
    )
  })
}

/* Every one of these services is a single page app, so arriving at your list
 * is usually a route change rather than a page load. `offered` is set the
 * first time the bar appears and only a full reload used to clear it, which
 * meant: open the service, look at your list once, go and browse, come back
 * to your list, and nothing happens. The route never navigated, so the flag
 * never reset, and the second visit looked like the extension had died.
 *
 * Leaving the list page is what clears it. */
let onListPage = false
let adapterChecks = 0

setInterval(() => {
  const { siteFor, isListPage, readList } = window.__roundtableSites || {}
  /* sites.js and this file are two content scripts in one isolated world,
     and this reads what that one exports. If it is missing then nothing
     works: no banner, no toast, no click detection, and every one of those
     fails silently while the marker above still says the extension loaded.
     That combination is indistinguishable from the extension being broken,
     so it gets said out loud instead. */
  if (!siteFor) {
    adapterChecks += 1
    if (adapterChecks === 3) {
      document.documentElement.dataset.roundtableError = 'adapters-missing'
      console.warn(
        'Roundtable: sites.js did not load, so nothing on this page can be read. ' +
          'Reload the extension at chrome://extensions and reload this page.',
      )
    }
    return
  }
  if (adapterChecks) {
    adapterChecks = 0
    delete document.documentElement.dataset.roundtableError
  }
  const site = siteFor(location.host)
  const here = Boolean(site && isListPage(site.id))

  if (onListPage && !here) {
    // Walked away from the list. The next arrival is a fresh chance to ask.
    onListPage = false
    offered = false
    document.getElementById('roundtable-offer')?.remove()
    return
  }
  onListPage = here
  if (!here || recentlyDeclined()) return
  // Wait until the list has actually rendered, since these pages fill in late.
  if (readList(site.id).length >= 3) offerImport(site)
}, 3000)


/* The popup can ask this page to scrape on demand, so importing never
   depends on having noticed a banner appear. */
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message?.type !== 'roundtable:scrape') return false
  const { siteFor, collectList, isListPage } = window.__roundtableSites || {}
  /* Told apart from "not a streaming page", because they are different
     problems with different answers and they used to look identical in the
     popup. Missing adapters means the page reader never loaded, which no
     amount of waiting or navigating will fix; reloading the extension will. */
  if (!siteFor) {
    reply({ site: null, label: null, isList: false, titles: [], adapters: false })
    return true
  }
  const site = siteFor(location.host)
  if (!site) {
    reply({ site: null, label: null, isList: false, titles: [], adapters: true })
    return true
  }
  // Async, because collecting means scrolling the rows.
  collectList(site.id).then((titles) =>
    reply({
      site: site.id,
      label: site.label,
      isList: isListPage(site.id),
      titles,
      adapters: true,
      // So the popup can say what it sees rather than showing nothing and
      // leaving "it does not work" as the only available conclusion.
      path: location.pathname,
    }),
  )
  return true
})


/* Reading a list the worker navigated this tab to.

   The waiting and the refusal both live in sites.js, so they can be tested
   without a browser; this is only the wiring. */
/* Answered immediately, so the worker can poll instead of holding one long
   request open across its own shutdown. */
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message?.type !== 'roundtable:peek') return false
  const { peekList } = window.__roundtableSites || {}
  reply(peekList ? { ...peekList(message.siteId), adapters: true } : { adapters: false })
  return true
})

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message?.type !== 'roundtable:harvest') return false
  const { harvestList } = window.__roundtableSites || {}
  if (!harvestList) {
    reply({ ok: false, reason: 'not ready', titles: [] })
    return true
  }
  // waitMs 0 when the worker has already waited by polling peek.
  harvestList(message.siteId, message.waitMs != null ? { waitMs: message.waitMs } : {}).then(reply, (error) =>
    reply({ ok: false, reason: String(error?.message || error), titles: [] }),
  )
  return true
})


/* Following what you press.
 *
 * Two clicks matter, and waiting for a poll to notice them is what made the
 * extension feel like it was doing nothing. Both are matched on the
 * accessible label rather than a class, because every service words it
 * slightly differently and labels are the one thing they all set:
 *   "Add to Watchlist", "Add to My List", "Remove from Watchlist"
 *   "Play", "Resume", "Watch now"
 */
const ADD_LABEL = /\b(add to (my )?(watch)?list|save to (watch)?list|\+ ?watchlist)\b/i
const REMOVE_LABEL = /\b(remove from (my )?(watch)?list|remove from list)\b/i
const PLAY_LABEL = /\b(play|resume|watch now)\b/i

function labelOf(element) {
  return (
    element.getAttribute?.('aria-label') ||
    element.getAttribute?.('title') ||
    element.textContent ||
    ''
  ).trim()
}

document.addEventListener(
  'click',
  (event) => {
    const { siteFor, isGeneric } = window.__roundtableSites || {}
    const site = siteFor?.(location.host)
    if (!site) return

    // Walk up a few levels: the click usually lands on an icon inside the
    // button rather than on the button itself.
    let node = event.target
    let label = ''
    for (let depth = 0; node && depth < 5; depth += 1) {
      label = labelOf(node)
      if (label && (ADD_LABEL.test(label) || REMOVE_LABEL.test(label) || PLAY_LABEL.test(label))) {
        break
      }
      node = node.parentElement
      label = ''
    }
    if (!label) return

    const name = navigator.mediaSession?.metadata?.title?.trim() || site.title()
    if (!name || isGeneric(name)) return

    if (ADD_LABEL.test(label) || REMOVE_LABEL.test(label)) {
      const adding = !REMOVE_LABEL.test(label)
      chrome.runtime.sendMessage(
        {
          type: 'roundtable:watchlist',
          payload: {
            title: name,
            site: site.id,
            provider: site.provider || null,
            kind: site.kind ? site.kind() : null,
            add: adding,
          },
        },
        () => void chrome.runtime.lastError,
      )
      toast(adding ? `Saving ${name} to Roundtable` : `Removing ${name} from Roundtable`)
      return
    }

    // Pressing play should register straight away rather than on the next
    // poll, which is up to four seconds later.
    toldAbout = null
    setTimeout(sample, 600)
    setTimeout(sample, 2500)
  },
  true, // capture, so a player that stops propagation is still seen
)
