/* The retry queue. This is the piece that decides whether a film you
   actually finished survives the server being down for a minute. */
const test = require('node:test')
const assert = require('node:assert')

// A tiny stand-in for chrome.storage.local, which is all queue.js touches.
function fakeChrome() {
  const store = {}
  return {
    storage: {
      local: {
        get: async (key) => ({ [key]: store[key] }),
        set: async (patch) => Object.assign(store, patch),
      },
    },
    _store: store,
  }
}

async function load() {
  global.chrome = fakeChrome()
  global.crypto = { randomUUID: () => Math.random().toString(36).slice(2) }
  // Fresh module each time, since the queue lives in storage.
  delete require.cache[require.resolve('./queue.js')]
  return await import(`./queue.js?${Math.random()}`)
}

test('a successful write leaves nothing behind', async () => {
  const q = await load()
  await q.enqueue({ path: '/a', payload: { title: 'Inception' } })
  assert.equal(await q.pending(), 1)

  await q.drain(async () => ({ ok: true, status: 200, json: async () => ({ action: 'watched' }) }))
  assert.equal(await q.pending(), 0)
})

test('a server that is down keeps the item for later', async () => {
  const q = await load()
  await q.enqueue({ path: '/a', payload: { title: 'Whiplash' } })

  await q.drain(async () => { throw new Error('offline') })
  assert.equal(await q.pending(), 1, 'the watch is still queued')
})

test('a 500 is retried, a 400 is not', async () => {
  const q = await load()
  await q.enqueue({ path: '/a', payload: { title: 'Retry me' } })
  await q.drain(async () => ({ ok: false, status: 503 }))
  assert.equal(await q.pending(), 1, 'a server error is worth another go')

  const q2 = await load()
  await q2.enqueue({ path: '/a', payload: { title: 'Drop me' } })
  let told = null
  await q2.drain(
    async () => ({ ok: false, status: 401 }),
    async (item, result, failure) => { told = failure },
  )
  assert.equal(await q2.pending(), 0, 'a rejected token will never succeed')
  assert.match(told, /refused 401/)
})

test('a failed item is not retried immediately', async () => {
  const q = await load()
  await q.enqueue({ path: '/a', payload: { title: 'Backoff' } })
  await q.drain(async () => { throw new Error('offline') })

  let attempts = 0
  await q.drain(async () => { attempts += 1; throw new Error('offline') })
  assert.equal(attempts, 0, 'it waits before trying again')
  assert.equal(await q.pending(), 1)
})

test('it gives up eventually rather than queueing forever', async () => {
  const q = await load()
  await q.enqueue({ path: '/a', payload: { title: 'Hopeless' } })
  let failure = null
  // Walk past every backoff step by clearing the wait each round.
  for (let i = 0; i < 8; i += 1) {
    const { queue = [] } = await global.chrome.storage.local.get('queue')
    await global.chrome.storage.local.set({ queue: queue.map((x) => ({ ...x, next: 0 })) })
    await q.drain(
      async () => { throw new Error('offline') },
      async (item, result, reason) => { failure = reason },
    )
  }
  assert.equal(await q.pending(), 0)
  assert.equal(failure, 'gave up')
})

test('the queue does not grow without bound', async () => {
  const q = await load()
  for (let i = 0; i < 260; i += 1) {
    await q.enqueue({ path: '/a', payload: { title: `Film ${i}` } })
  }
  assert.ok((await q.pending()) <= 200, 'old entries are dropped, not accumulated')
})
