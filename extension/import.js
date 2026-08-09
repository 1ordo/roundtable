/* Review before anything is written. Every match is shown with its poster
   so a wrong one is obvious, and the titles that matched nothing are listed
   plainly rather than dropped silently. */
const grid = document.getElementById('grid')
const summary = document.getElementById('summary')
const misses = document.getElementById('misses')
const chosen = new Set()

function draw(data) {
  const hits = data.results.filter((r) => r.matched && !r.already)
  const already = data.results.filter((r) => r.already)
  const unmatched = data.results.filter((r) => !r.matched)

  summary.textContent =
    `${hits.length} to add, ${already.length} already on your watchlist, ` +
    `${unmatched.length} not recognised.`

  for (const item of hits) {
    chosen.add(`${item.type}:${item.tmdb_id}`)
    const card = document.createElement('button')
    card.className = 'card on'
    card.innerHTML = `
      ${item.poster_path
        ? `<img src="https://image.tmdb.org/t/p/w185${item.poster_path}" alt="" />`
        : '<span class="blank"></span>'}
      <span class="t">${item.name}</span>
      <span class="y">${item.year || ''}</span>`
    card.addEventListener('click', () => {
      const key = `${item.type}:${item.tmdb_id}`
      if (chosen.has(key)) { chosen.delete(key); card.classList.remove('on') }
      else { chosen.add(key); card.classList.add('on') }
    })
    card.dataset.key = `${item.type}:${item.tmdb_id}`
    grid.append(card)
  }

  if (unmatched.length) {
    misses.innerHTML =
      '<h2>Not recognised</h2><p class="fine">' +
      'These are not in the catalog yet, or the page called them something else. ' +
      'You can add them by hand in Watchpile.</p><ul class="plain">' +
      unmatched.map((u) => `<li>${u.given}</li>`).join('') +
      '</ul>'
  }
}

document.getElementById('all').addEventListener('click', () => {
  document.querySelectorAll('.card').forEach((c) => {
    c.classList.add('on'); chosen.add(c.dataset.key)
  })
})
document.getElementById('none').addEventListener('click', () => {
  document.querySelectorAll('.card').forEach((c) => c.classList.remove('on'))
  chosen.clear()
})

document.getElementById('save').addEventListener('click', async (event) => {
  const button = event.currentTarget
  button.disabled = true
  button.textContent = 'Adding'
  const { baseUrl, token } = await chrome.storage.local.get(['baseUrl', 'token'])
  const titles = [...chosen].map((key) => {
    const [type, id] = key.split(':')
    return { type, tmdb_id: Number(id) }
  })
  try {
    const response = await fetch(`${baseUrl}/api/extension/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ titles }),
    })
    const result = await response.json()
    summary.textContent = `Added ${result.added}. ${result.already} were already there.`
    grid.innerHTML = ''
    button.textContent = 'Done'
    await chrome.storage.local.remove('pendingImport')
    await chrome.action.setBadgeText({ text: '' })
  } catch {
    button.disabled = false
    button.textContent = 'Try again'
  }
})

chrome.storage.local.get('pendingImport').then(({ pendingImport }) => {
  if (!pendingImport) {
    summary.textContent = 'Nothing waiting to import.'
    return
  }
  draw(pendingImport)
})
