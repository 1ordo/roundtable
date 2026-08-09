/* Save the address and token, then prove they work before saying so. A
   settings page that accepts anything and fails silently later is worse
   than one that refuses. */
const baseUrl = document.getElementById('baseUrl')
const token = document.getElementById('token')
const status = document.getElementById('status')

const autoSync = document.getElementById('autoSync')

chrome.storage.local.get(['baseUrl', 'token', 'autoSync']).then((s) => {
  baseUrl.value = s.baseUrl || 'http://localhost:8080'
  token.value = s.token || ''
  // Never set means a fresh install, which starts on.
  autoSync.checked = s.autoSync !== false
})

/* Saved on the click rather than with the address, so turning it off takes
   effect without also having to re-verify a token that was already fine. */
autoSync.addEventListener('change', () =>
  chrome.storage.local.set({ autoSync: autoSync.checked }),
)

function show(text, ok) {
  status.textContent = text
  status.className = ok === undefined ? '' : ok ? 'ok' : 'bad'
}

document.getElementById('save').addEventListener('click', async () => {
  const url = baseUrl.value.trim().replace(/\/+$/, '')
  const key = token.value.trim()
  if (!url || !key) return show('Both are needed.', false)

  show('Checking')
  /* Ask for access to this one address rather than shipping a blanket
     permission for every site. Nothing is granted until the person says so,
     and the request is tied to the address they just typed. */
  try {
    const origin = new URL(url).origin + '/*'
    const granted = await chrome.permissions.request({ origins: [origin] })
    if (!granted) return show('Access to that address was declined.', false)
  } catch {
    return show('That does not look like a valid address.', false)
  }

  try {
    const response = await fetch(`${url}/api/extension/hello`, {
      headers: { Authorization: `Bearer ${key}` },
    })
    if (response.status === 401) return show('That token was refused.', false)
    if (!response.ok) return show(`The server answered ${response.status}.`, false)
    const who = await response.json()
    // Cache the subscriptions so the worker can filter without a round trip
    // on every report.
    await chrome.storage.local.set({
      baseUrl: url,
      token: key,
      providers: who.providers || [],
    })
    const count = (who.providers || []).length
    show(
      count
        ? `Saved. Logging as ${who.username}, from your ${count} services.`
        : `Saved. Logging as ${who.username}, from every service.`,
      true,
    )
  } catch {
    show('Could not reach that address.', false)
  }
})
