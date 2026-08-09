import { SERVICES } from './services.js'

/* What it has done lately, so a wrong match is obvious straight away
   rather than discovered in your history a week later. */
const ago = (ms) => {
  const s = Math.round((Date.now() - ms) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  return `${Math.floor(s / 86400)}d`
}

const LABEL = {
  watched: 'logged',
  viewed: 'seen',
  saved: 'on your list',
  removed: 'taken off',
  ignored: 'already',
  unmatched: 'no match',
}

/* Asked right after the credits, which is the only time anyone actually
   remembers what they thought. Skipping is a real option: a prompt you
   cannot dismiss is a prompt people learn to ignore. */
async function drawRating() {
  const box = document.getElementById('rate-box')
  const { pendingRating, baseUrl, token } = await chrome.storage.local.get([
    'pendingRating', 'baseUrl', 'token',
  ])
  // Stale after a day: rating something you finished on Tuesday on Thursday
  // is worse data than no rating.
  if (!pendingRating || Date.now() - pendingRating.at > 86400000) {
    box.hidden = true
    if (pendingRating) await chrome.storage.local.remove('pendingRating')
    return
  }

  box.hidden = false
  box.innerHTML = `
    <div style="display:flex;gap:9px;align-items:center;margin-bottom:7px">
      ${pendingRating.poster
        ? `<img src="https://image.tmdb.org/t/p/w92${pendingRating.poster}"
             style="width:30px;height:45px;border-radius:4px;object-fit:cover" alt="" />`
        : ''}
      <div style="min-width:0">
        <div style="font-size:12px;color:var(--muted)">You just finished</div>
        <div style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          ${pendingRating.name}</div>
      </div>
    </div>
    <div class="rate" id="stars"></div>
    <div class="row">
      <button id="loved" class="ghost" style="margin:0">loved it</button>
      <span style="flex:1"></span>
      <button id="skip" class="ghost" style="margin:0">skip</button>
    </div>
    <hr />`

  const stars = box.querySelector('#stars')
  let picked = null
  for (let n = 1; n <= 10; n++) {
    const b = document.createElement('button')
    b.textContent = n
    b.addEventListener('click', () => {
      picked = n
      stars.querySelectorAll('button').forEach((x, i) => x.classList.toggle('on', i < n))
      send(false)
    })
    stars.append(b)
  }

  async function send(loved) {
    try {
      await fetch(`${baseUrl}/api/extension/rate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          type: pendingRating.type,
          tmdb_id: pendingRating.tmdb_id,
          rating_10: picked,
          loved,
        }),
      })
    } catch {
      // The watch is already logged; a lost rating is not worth a retry loop.
    }
    await chrome.storage.local.remove('pendingRating')
    await chrome.action.setBadgeText({ text: '' })
    box.hidden = true
  }

  box.querySelector('#loved').addEventListener('click', () => send(true))
  box.querySelector('#skip').addEventListener('click', async () => {
    await chrome.storage.local.remove('pendingRating')
    await chrome.action.setBadgeText({ text: '' })
    box.hidden = true
  })
}

async function draw() {
  const { recent = [], baseUrl, token, paused } = await chrome.storage.local.get([
    'recent',
    'baseUrl',
    'token',
    'paused',
  ])
  const state = document.getElementById('state')
  const pause = document.getElementById('pause')
  pause.textContent = paused ? 'resume' : 'pause'

  if (!baseUrl || !token) {
    state.textContent = 'Not set up yet. Open settings to connect it.'
  } else if (paused) {
    state.textContent = 'Paused. Nothing is being logged.'
  } else {
    state.textContent = 'Watching for what you play.'
  }

  const list = document.getElementById('recent')
  list.innerHTML = ''
  const collapsed = []
  for (const item of recent) {
    const previous = collapsed[collapsed.length - 1]
    // Same title and same outcome in a row is one thing that happened.
    if (previous && previous.title === item.title && previous.action === item.action) continue
    collapsed.push(item)
  }
  for (const item of collapsed.slice(0, 8)) {
    const li = document.createElement('li')
    if (item.poster) {
      const img = document.createElement('img')
      img.src = `https://image.tmdb.org/t/p/w92${item.poster}`
      img.alt = ''
      li.append(img)
    }
    const name = document.createElement('span')
    name.className = 'name'
    name.textContent = item.title
    const tag = document.createElement('span')
    const label = LABEL[item.action] || item.action
    tag.className =
      'tag' + (item.action === 'watched' ? ' watched' : item.matched === false ? ' bad' : '')
    tag.textContent = `${label} ${ago(item.at)}`
    li.append(name, tag)
    list.append(li)
  }
}

/* Importing a watchlist, without having to be standing on it.
 *
 * The first version only offered an import when you had already navigated to
 * your watchlist yourself, so the usual state of this box was a note telling
 * you to go somewhere else. That is not a feature, it is an instruction.
 *
 * Now the button does the navigating. Pressing one opens that service's list,
 * waits for it to render, reads it and lands on the review screen. The
 * already-on-the-list-page case is still handled first, because when it
 * applies it is one page load cheaper.
 */
async function drawImport() {
  const box = document.getElementById('import-box')
  box.innerHTML = ''

  const { providers = [], baseUrl, token } = await chrome.storage.local.get([
    'providers',
    'baseUrl',
    'token',
  ])
  if (!baseUrl || !token) return

  // Standing on a list already: read this one, no navigation needed.
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  if (tab?.id) {
    let page = null
    try {
      page = await chrome.tabs.sendMessage(tab.id, { type: 'roundtable:scrape' })
    } catch {
      // Not a streaming page, or the content script has not loaded here.
    }
    /* The one failure that is worth interrupting for: the page reader did
       not load, so nothing on any streaming page can be read and no amount
       of waiting fixes it. Said first, and said plainly. */
    if (page && page.adapters === false) {
      const bad = document.createElement('p')
      bad.className = 'fine'
      bad.style.cssText = 'margin:0 0 10px;color:#e0505c'
      bad.textContent =
        'The page reader did not load on this tab. Reload Roundtable at ' +
        'chrome://extensions, then reload the page.'
      box.append(bad)
      return
    }

    if (page?.site && page.isList && page.titles?.length) {
      box.append(
        action(`Import ${page.titles.length} from your ${page.label} list`, (button) => {
          button.textContent = 'Matching'
          chrome.runtime.sendMessage(
            { type: 'roundtable:import', payload: { site: page.site, titles: page.titles } },
            () => window.close(),
          )
        }),
      )
      return
    }

    /* Say what it saw, whenever it is on a service at all.
     *
     * Without this the popup shows the same list of buttons whether the page
     * is unrecognised, recognised but not a list, or a list it could not
     * read, and every one of those looks identical from the outside. The
     * only conclusion available was "it does not work", which is true and
     * says nothing about which of the three it is. */
    if (page?.site) {
      const seen = document.createElement('p')
      seen.className = 'fine'
      seen.style.margin = '0 0 9px'
      seen.textContent = page.isList
        ? `On your ${page.label} list, but nothing readable on it yet. Give it a moment and reopen this.`
        : `On ${page.label}, though ${page.path || 'this page'} is not your list.`
      box.append(seen)
    }
  }

  /* Otherwise, offer the services they actually pay for. Ticking nothing in
     the app means "I have not said", not "I have none", so that shows
     everything rather than an empty box. */
  const mine = providers.length
    ? SERVICES.filter((s) => providers.includes(s.provider))
    : SERVICES

  const heading = document.createElement('p')
  heading.className = 'fine'
  heading.style.margin = '0 0 7px'
  heading.textContent = 'Import a watchlist'
  box.append(heading)

  const wrap = document.createElement('div')
  wrap.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;margin-bottom:11px'
  for (const service of mine) {
    const button = document.createElement('button')
    button.className = 'ghost'
    button.style.margin = '0'
    button.textContent = service.label
    button.addEventListener('click', async () => {
      wrap.querySelectorAll('button').forEach((b) => (b.disabled = true))
      button.textContent = 'Opening'
      const result = await chrome.runtime.sendMessage({
        type: 'roundtable:sync',
        siteId: service.id,
      })
      if (result?.ok) {
        window.close()
        return
      }
      // A wrong list address is the likely cause, and it is worth saying so
      // rather than leaving a dead button: the paths for the smaller
      // services are the ones least likely to have been confirmed.
      heading.textContent = `Could not read your ${service.label} list: ${
        result?.reason || 'no answer'
      }. Open it yourself and press import.`
      wrap.querySelectorAll('button').forEach((b) => (b.disabled = false))
      button.textContent = service.label
    })
    wrap.append(button)
  }
  box.append(wrap)
}

function action(label, onClick) {
  const button = document.createElement('button')
  button.className = 'primary'
  button.style.cssText = 'width:100%;margin-bottom:10px'
  button.textContent = label
  button.addEventListener('click', () => {
    button.disabled = true
    onClick(button)
  })
  return button
}

document.getElementById('pause').addEventListener('click', async () => {
  const { paused } = await chrome.storage.local.get('paused')
  await chrome.storage.local.set({ paused: !paused })
  drawRating()
draw()
drawImport()
})

document.getElementById('settings').addEventListener('click', (event) => {
  event.preventDefault()
  chrome.runtime.openOptionsPage()
})

drawRating()
draw()
drawImport()
