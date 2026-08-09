/* Nothing is lost because the server blinked.
 *
 * The first version fired a request and, if it failed, wrote "unreachable"
 * into a log nobody could act on. A film you actually finished was gone.
 *
 * So every write goes through here: it is queued first, then drained. A
 * failure leaves the item in the queue with a later retry, and the queue
 * survives the service worker being shut down because it lives in storage
 * rather than memory.
 *
 * Reads are not queued. A match lookup that fails can simply be asked
 * again, and holding stale ones would only produce stale answers.
 */

const KEY = 'queue'
const MAX = 200
// Doubling, capped, so a server that is down overnight is retried about
// once an hour rather than every few seconds for eight hours.
const BACKOFF_MS = [5_000, 20_000, 60_000, 300_000, 900_000, 3_600_000]

export async function enqueue(item) {
  const { [KEY]: queue = [] } = await chrome.storage.local.get(KEY)
  queue.push({ ...item, tries: 0, next: 0, id: crypto.randomUUID() })
  // Oldest first out if it ever grows unreasonably: a week old view is not
  // worth keeping at the cost of today's.
  await chrome.storage.local.set({ [KEY]: queue.slice(-MAX) })
}

export async function pending() {
  const { [KEY]: queue = [] } = await chrome.storage.local.get(KEY)
  return queue.length
}

/**
 * Try everything that is due.
 *
 * @param send an async (item) => Response. Anything it throws, or any 5xx,
 *   is treated as worth retrying. A 4xx is not: a rejected token or a
 *   malformed body will fail identically forever, so it is dropped and
 *   reported rather than retried into a loop.
 */
export async function drain(send, onResult) {
  const { [KEY]: queue = [] } = await chrome.storage.local.get(KEY)
  if (queue.length === 0) return

  const now = Date.now()
  const keep = []
  for (const item of queue) {
    if (item.next > now) {
      keep.push(item)
      continue
    }
    try {
      const response = await send(item)
      if (response.ok) {
        await onResult?.(item, await response.json().catch(() => null))
        continue // done, drop it
      }
      if (response.status >= 400 && response.status < 500) {
        // Never going to succeed. Say so once and stop.
        await onResult?.(item, null, `refused ${response.status}`)
        continue
      }
      throw new Error(`server ${response.status}`)
    } catch {
      const tries = item.tries + 1
      if (tries >= BACKOFF_MS.length) {
        await onResult?.(item, null, 'gave up')
        continue
      }
      keep.push({ ...item, tries, next: now + BACKOFF_MS[tries - 1] })
    }
  }
  await chrome.storage.local.set({ [KEY]: keep })
}
