/* The services this extension knows, and where each one keeps your list.
 *
 * Separate from sites.js on purpose. sites.js is DOM behaviour and runs as a
 * classic content script; this is plain data and is imported as a module by
 * the worker and the popup, which are the two places that need to navigate
 * somewhere without a page already being open. A test asserts the two agree
 * on every id, label and provider, so the split cannot quietly drift.
 *
 * `provider` is the TMDB provider id, which is what the app stores when
 * someone ticks a service in Settings. These are checked against the
 * catalog's own availability rows rather than remembered: a wrong id here
 * silently disables the subscription filter for that service, which looks
 * like nothing at all until you notice the wrong things being logged.
 *
 * `list` is the path to the saved list. `verified` says whether it was
 * confirmed against the live site or is a best guess from the service's
 * public URL scheme. A guess that turns out wrong costs a page load and an
 * honest "could not find your list there", never a bad import: the harvest
 * only proceeds if the page it lands on actually looks like a list.
 */

export const SERVICES = [
  {
    id: 'netflix',
    label: 'Netflix',
    provider: 8,
    hosts: ['netflix.com'],
    origin: 'https://www.netflix.com',
    lists: ['/browse/my-list'],
    verified: true,
  },
  {
    id: 'prime',
    label: 'Prime Video',
    provider: 9,
    hosts: ['primevideo.com', 'amazon.'],
    // primevideo.com, never the amazon.* storefront, even when that is where
    // they are browsing. The watchlist lives here.
    origin: 'https://www.primevideo.com',
    /* Two pages, confirmed signed in: the watchlist is tabbed, and each tab
       shows only its own kind. Reading one of them and reporting the count
       is how you import half a list and call it done. */
    lists: ['/mystuff/watchlist/movie', '/mystuff/watchlist/tv'],
    verified: true,
  },
  {
    id: 'disney',
    label: 'Disney+',
    provider: 337,
    hosts: ['disneyplus.com'],
    origin: 'https://www.disneyplus.com',
    lists: ['/watchlist'],
    verified: false,
  },
  {
    id: 'max',
    label: 'Max',
    provider: 1899,
    hosts: ['max.com', 'hbomax.com'],
    origin: 'https://play.max.com',
    lists: ['/mylist'],
    verified: false,
  },
  {
    id: 'appletv',
    label: 'Apple TV+',
    provider: 350,
    hosts: ['tv.apple.com'],
    origin: 'https://tv.apple.com',
    lists: ['/up-next'],
    verified: false,
  },
  {
    id: 'shahid',
    label: 'Shahid',
    provider: 1715,
    hosts: ['shahid.mbc.net'],
    origin: 'https://shahid.mbc.net',
    // Confirmed by Mohamed: it is /ar/favorite.
    lists: ['/ar/favorite'],
    locale: /^\/[a-z]{2}(-[a-z]{2})?(?=\/|$)/,
    verified: true,
  },
  {
    id: 'osn',
    label: 'OSN+',
    provider: 629,
    hosts: ['osnplus.com', 'osn.com'],
    origin: 'https://osnplus.com',
    // Confirmed: it is my-list, not watchlist, and the locale is part of the
    // path rather than a subdomain. `locale` keeps whichever one the person
    // is actually browsing, since /en-eg is not where a viewer in France
    // wants to land.
    lists: ['/en-eg/my-list'],
    locale: /^\/[a-z]{2}(-[a-z]{2})?(?=\/|$)/,
    verified: true,
  },
  {
    id: 'starzplay',
    label: 'STARZPLAY',
    provider: 630,
    hosts: ['starzplay.com', 'starz.com'],
    origin: 'https://www.starzplay.com',
    lists: ['/watchlist'],
    verified: false,
  },
  {
    id: 'paramount',
    label: 'Paramount+',
    provider: 531,
    hosts: ['paramountplus.com'],
    origin: 'https://www.paramountplus.com',
    lists: ['/account/watchlist/'],
    verified: false,
  },
  {
    id: 'peacock',
    label: 'Peacock',
    provider: 386,
    hosts: ['peacocktv.com'],
    origin: 'https://www.peacocktv.com',
    lists: ['/watchlist'],
    verified: false,
  },
  {
    id: 'hulu',
    label: 'Hulu',
    provider: 15,
    hosts: ['hulu.com'],
    origin: 'https://www.hulu.com',
    lists: ['/my-stuff'],
    verified: false,
  },
  {
    id: 'crunchyroll',
    label: 'Crunchyroll',
    provider: 283,
    hosts: ['crunchyroll.com'],
    origin: 'https://www.crunchyroll.com',
    lists: ['/watchlist'],
    verified: false,
  },
  {
    id: 'watchit',
    label: 'Watch It',
    provider: 2199,
    hosts: ['watchit.com', 'watchit.movie'],
    origin: 'https://www.watchit.com',
    lists: ['/watchlist'],
    verified: false,
  },
]

export const BY_ID = Object.fromEntries(SERVICES.map((s) => [s.id, s]))

/** The service a URL belongs to, or null. */
export function serviceForUrl(url) {
  let host
  try {
    host = new URL(url).host
  } catch {
    return null
  }
  return SERVICES.find((s) => s.hosts.some((h) => host.includes(h))) || null
}

/* Every page this person's saved list is spread across.
 *
 * The origin is the service's own, not whichever one they happen to have a
 * tab on. An earlier version preferred their current host on the theory that
 * a regional domain was a better bet; it is not. Prime's watchlist lives on
 * primevideo.com even when you are browsing an amazon storefront, and
 * rewriting the origin sent people to a page that does not hold their list.
 *
 * The locale is different, and is kept when a service has one, because on
 * OSN the locale segment selects a different catalog rather than a
 * translation.
 */
export function listUrls(service, currentUrl = null) {
  let locale = null
  if (currentUrl && service.locale) {
    try {
      const url = new URL(currentUrl)
      if (service.hosts.some((h) => url.host.includes(h))) {
        locale = service.locale.exec(url.pathname)?.[0] || null
      }
    } catch {
      // Not a URL we can read: the service's own locale is the fallback.
    }
  }

  return service.lists.map((path) => {
    if (locale) {
      const ours = service.locale.exec(path)
      if (ours) path = path.replace(ours[0], locale)
    }
    return `${service.origin}${path}`
  })
}
