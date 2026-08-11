// Minimal stand-in for the FastAPI backend so Playwright can exercise the
// SPA's golden paths without Postgres or a real identity server.
import http from 'node:http'

const PORT = 8000
const CSRF = 'test-csrf-token'

function hasSession(req) {
  return (req.headers.cookie ?? '').includes('wd_session=')
}

const COCO_CARD = {
  tmdb_id: 354912,
  type: 'movie',
  name: 'Coco',
  poster_path: '/gGEsBPAijhVUFoiNpgZXqRVWJt2.jpg',
  backdrop_path: '/askg3SMvhqEl4OL52YuvdtY40Yb.jpg',
  year: 2017,
  tmdb_rating: 8.2,
  certification: 'PG',
  match: 96,
}

// Real TMDB artwork (paths verified against image.tmdb.org) so the demo
// looks like the production app in screenshots and manual browsing. Only
// Coco has a full detail route; everything else is card-level data.
function card(tmdb_id, type, name, year, tmdb_rating, certification, poster_path, extra = {}) {
  return {
    tmdb_id,
    type,
    name,
    year,
    tmdb_rating,
    certification,
    poster_path,
    backdrop_path: null,
    ...extra,
  }
}
const F = {
  interstellar: card(157336, 'movie', 'Interstellar', 2014, 8.4, 'PG-13', '/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg', { backdrop_path: '/pbrkL804c8yAv3zBZR4QPEafpAR.jpg', match: 94 }),
  dune: card(438631, 'movie', 'Dune', 2021, 7.8, 'PG-13', '/d5NXSklXo0qyIYkgV94XAgMIckC.jpg', { backdrop_path: '/jYEW5xZkZk2WTrdbMGAPFuBqbDc.jpg', match: 91 }),
  bladerunner: card(335984, 'movie', 'Blade Runner 2049', 2017, 7.5, 'R', '/gajva2L0rPYkEWjzgFlBXCAVBE5.jpg', { backdrop_path: '/ilRyazdMJwN05exqhwK4tMKBYZs.jpg', match: 88 }),
  parasite: card(496243, 'movie', 'Parasite', 2019, 8.5, 'R', '/7IiTTgloJzvGI1TAYymCfbfl3vT.jpg', { match: 90 }),
  whiplash: card(244786, 'movie', 'Whiplash', 2014, 8.4, 'R', '/7fn624j5lj3xTme2SgiLCeuedmO.jpg', { match: 84 }),
  oppenheimer: card(872585, 'movie', 'Oppenheimer', 2023, 8.1, 'R', '/8Gxv8gSFCU0XGDykEGv7zR1n2ua.jpg', { match: 87 }),
  spiderverse: card(569094, 'movie', 'Spider-Man: Across the Spider-Verse', 2023, 8.4, 'PG', '/8Vt6mWEReuy4Of61Lnj5Xj704m8.jpg', { match: 89 }),
  pulpfiction: card(680, 'movie', 'Pulp Fiction', 1994, 8.5, 'R', '/d5iIlFn5s0ImszYzBPb8JPIfbXD.jpg'),
  budapest: card(120467, 'movie', 'The Grand Budapest Hotel', 2014, 8.0, 'R', '/eWdyYQreja6JGCzqHWXpWHDrrPo.jpg', { match: 82 }),
  furyroad: card(76341, 'movie', 'Mad Max: Fury Road', 2015, 7.6, 'R', '/hA2ple9q4qnwxp3hKVNhroipsir.jpg'),
  moodforlove: card(843, 'movie', 'In the Mood for Love', 2000, 8.1, 'PG', '/iYypPT4bhqXfq1b6EnmxvRt6b2Y.jpg', { match: 86 }),
  spirited: card(129, 'movie', 'Spirited Away', 2001, 8.5, 'PG', '/39wmItIWsg5sZMyRUHLkWBcuVCM.jpg', { match: 93 }),
  portrait: card(531428, 'movie', 'Portrait of a Lady on Fire', 2019, 8.1, 'R', '/2LquGwEhbg3soxSCs9VNyh5VJd9.jpg'),
  fightclub: card(550, 'movie', 'Fight Club', 1999, 8.4, 'R', '/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg'),
  knivesout: card(546554, 'movie', 'Knives Out', 2019, 7.9, 'PG-13', '/pThyQovXQrw2m0s9x82twj48Jq4.jpg', { match: 81 }),
  yourname: card(372058, 'movie', 'Your Name.', 2016, 8.5, 'PG', '/q719jXXEzOoYaps6babgKnONONX.jpg', { match: 92 }),
  darkknight: card(155, 'movie', 'The Dark Knight', 2008, 8.5, 'PG-13', '/qJ2tW6WMUDux911r6m7haRef0WH.jpg'),
  godfather: card(238, 'movie', 'The Godfather', 1972, 8.7, 'R', '/rSPw7tgCH9c6NqICZef4kZjFOQ5.jpg'),
  lalaland: card(313369, 'movie', 'La La Land', 2016, 7.9, 'PG-13', '/uDO8zWDhfWwoFdKS4fzkUJt0Rf0.jpg'),
  ratatouille: card(2062, 'movie', 'Ratatouille', 2007, 7.8, 'G', '/npHNjldbeTHdKKw28bJKs7lzqzj.jpg', { match: 88 }),
  everything: card(545611, 'movie', 'Everything Everywhere All at Once', 2022, 7.8, 'R', '/w3LxiVYdWWRvEVdn5RYq6jIqkb1.jpg'),
  arrival: card(329865, 'movie', 'Arrival', 2016, 7.6, 'PG-13', '/x2FJsf1ElAgr63Y3PNPtJrcmpoe.jpg', { match: 85 }),
}
const S = {
  strangerthings: card(66732, 'tv', 'Stranger Things', 2016, 8.6, 'TV-14', '/49WJfeN0moxb9IPfGn8AIqMGskD.jpg', { match: 83 }),
  andor: card(83867, 'tv', 'Andor', 2022, 8.4, 'TV-14', '/59SVNwLfoMnZPPB6ukW6dlPxAdI.jpg', { match: 90 }),
  breakingbad: card(1396, 'tv', 'Breaking Bad', 2008, 8.9, 'TV-MA', '/ggFHVNu6YYI5L9pCfOacjizRGt.jpg'),
  severance: card(95396, 'tv', 'Severance', 2022, 8.4, 'TV-MA', '/lFf6LLrQjYldcZItzOkGmMMigP7.jpg', { match: 91 }),
  lastofus: card(100088, 'tv', 'The Last of Us', 2023, 8.6, 'TV-MA', '/uKvVjHNqB5VmOrdxqAt2F7J78ED.jpg', { match: 86 }),
}
const EVERY_CARD = [COCO_CARD, ...Object.values(F), ...Object.values(S)]
function highlight(c, rating_10, loved = false) {
  return { tmdb_id: c.tmdb_id, type: c.type, name: c.name, poster_path: c.poster_path, year: c.year, rating_10, loved }
}

const COCO_DETAIL = {
  id: '00000000-0000-0000-0000-00000000c0c0',
  tmdb_id: 354912,
  type: 'movie',
  name: 'Coco',
  original_name: 'Coco',
  year: 2017,
  overview: 'Aspiring musician Miguel enters the Land of the Dead.',
  original_language: 'en',
  runtime: 105,
  genres: [{ id: 16, name: 'Animation' }],
  keywords: ['afterlife', 'music'],
  poster_path: '/gGEsBPAijhVUFoiNpgZXqRVWJt2.jpg',
  backdrop_path: '/askg3SMvhqEl4OL52YuvdtY40Yb.jpg',
  tmdb_rating: 8.2,
  tmdb_votes: 20000,
  imdb_rating: 8.4,
  rt_score: 97,
  metacritic: 81,
  trailer_youtube_key: 'xlnPHQ3TLX8',
  cast: [
    { name: 'Anthony Gonzalez', character: 'Miguel', profile_path: null },
    { name: 'Gael García Bernal', character: 'Héctor', profile_path: null },
    { name: 'Benjamin Bratt', character: 'Ernesto', profile_path: null },
    { name: 'Alanna Ubach', character: 'Mamá Imelda', profile_path: null },
  ],
  availability: {
    EG: [{ provider_name: 'Disney Plus', logo_path: null, kind: 'stream', url: 'https://www.disneyplus.com/search?q=Coco' }],
  },
  countries: ['EG'],
}

function requireSession(req, res) {
  if (hasSession(req)) return true
  res.writeHead(401, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify({ detail: 'not authenticated' }))
  return false
}

function requireCsrf(req, res) {
  if (req.headers['x-csrf-token'] === CSRF) return true
  res.writeHead(403, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify({ detail: 'csrf token missing or invalid' }))
  return false
}

function readBody(req) {
  return new Promise((resolve) => {
    let data = ''
    req.on('data', (chunk) => (data += chunk))
    req.on('end', () => {
      try {
        resolve(data ? JSON.parse(data) : {})
      } catch {
        resolve({})
      }
    })
  })
}

function json(res, status, payload) {
  res.writeHead(status, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify(payload))
}

// Stateful tracking store, reset when the mock restarts.
const store = {
  lists: [
    { id: 'list-watch', name: 'Watchlist', kind: 'watchlist', items: [] },
    { id: 'list-shared', name: 'Our list', kind: 'shared', items: [] },
  ],
  history: [],
  nextEventId: 1,
  // One aired season plus an episode still to come, so the grid shows both
  // a tickable row and a locked one.
  episodes: [
    { id: 'ep-1', season: 1, episode: 1, name: 'The one that starts it', overview: null,
      air_date: '2026-01-06', runtime: 48, still_path: null, aired: true, watched: true },
    { id: 'ep-2', season: 1, episode: 2, name: 'The one after that', overview: null,
      air_date: '2026-01-13', runtime: 51, still_path: null, aired: true, watched: false },
    { id: 'ep-3', season: 1, episode: 3, name: 'Not out yet', overview: null,
      air_date: '2099-01-20', runtime: null, still_path: null, aired: false, watched: false },
  ],
  profile: { country_code: null, services: [] },
  imports: [],
  signal: { liked: false, disliked: false },
  groups: [],
  ai: {
    enabled: true,
    base_url: 'http://localhost:11434/v1',
    chat_model: 'gemma-4-26b-a4b-it',
    embed_model: 'text-embedding-nomic-embed-text-v1.5',
  },
  notifications: [
    {
      id: 'notif-1',
      kind: 'availability',
      message: 'Coco is now streaming on Netflix in EG',
      payload: {},
      read: false,
      created_at: '2026-08-01T00:00:00Z',
      title_tmdb_id: 354912,
      title_type: 'movie',
      title_poster: '/poster-coco.jpg',
    },
  ],
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`)

  if (url.pathname === '/api/lists' && req.method === 'GET') {
    if (!requireSession(req, res)) return
    return json(res, 200, {
      lists: store.lists.map((l) => ({
        id: l.id,
        name: l.name,
        kind: l.kind,
        count: l.items.length,
        posters: l.items.map((i) => i.poster_path).filter(Boolean).slice(0, 3),
      })),
    })
  }

  const itemsMatch = url.pathname.match(/^\/api\/lists\/([^/]+)\/items$/)
  if (itemsMatch && req.method === 'GET') {
    if (!requireSession(req, res)) return
    const list = store.lists.find((l) => l.id === itemsMatch[1])
    if (!list) return json(res, 404, { detail: 'list not found' })
    return json(res, 200, {
      id: list.id,
      name: list.name,
      kind: list.kind,
      items: list.items.map((title) => ({
        title,
        note: null,
        added_by: 'Lordo',
        added_at: '2026-08-01T00:00:00Z',
      })),
    })
  }
  if (itemsMatch && req.method === 'POST') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    const list = store.lists.find((l) => l.id === itemsMatch[1])
    if (!list) return json(res, 404, { detail: 'list not found' })
    if (!list.items.some((i) => i.tmdb_id === COCO_CARD.tmdb_id)) list.items.push(COCO_CARD)
    return json(res, 201, { status: 'added' })
  }

  const removeMatch = url.pathname.match(/^\/api\/lists\/([^/]+)\/items\/movie\/(\d+)$/)
  if (removeMatch && req.method === 'DELETE') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    const list = store.lists.find((l) => l.id === removeMatch[1])
    if (list) list.items = list.items.filter((i) => String(i.tmdb_id) !== removeMatch[2])
    res.writeHead(204)
    return res.end()
  }

  if (url.pathname === '/api/titles/movie/354912/state') {
    if (!requireSession(req, res)) return
    const events = store.history
    return json(res, 200, {
      lists: store.lists.filter((l) => l.items.length > 0).map((l) => l.id),
      watched_count: events.length,
      my_rating: events.find((e) => e.rating_10 != null)?.rating_10 ?? null,
      loved: events.some((e) => e.loved),
    })
  }

  if (url.pathname === '/api/history' && req.method === 'GET') {
    if (!requireSession(req, res)) return
    return json(res, 200, { total: store.history.length, events: store.history })
  }
  if (url.pathname === '/api/history' && req.method === 'POST') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    const body = await readBody(req)
    const event = {
      id: `event-${store.nextEventId++}`,
      title: COCO_CARD,
      watched_at: '2026-08-01T00:00:00Z',
      rating_10: body.rating_10 ?? null,
      loved: body.loved ?? false,
      source: 'app',
    }
    store.history.unshift(event)
    return json(res, 201, event)
  }

  const eventMatch = url.pathname.match(/^\/api\/history\/([^/]+)$/)
  if (eventMatch && req.method === 'PATCH') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    const event = store.history.find((e) => e.id === eventMatch[1])
    if (!event) return json(res, 404, { detail: 'event not found' })
    const body = await readBody(req)
    if (body.rating_10 !== undefined && body.rating_10 !== null) event.rating_10 = body.rating_10
    if (body.loved !== undefined && body.loved !== null) event.loved = body.loved
    return json(res, 200, event)
  }
  if (eventMatch && req.method === 'DELETE') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    store.history = store.history.filter((e) => e.id !== eventMatch[1])
    res.writeHead(204)
    return res.end()
  }

  if (url.pathname === '/api/me' && req.method === 'PUT') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    const body = await readBody(req)
    if (body.country_code) store.profile.country_code = body.country_code.toUpperCase()
    if (body.services) store.profile.services = body.services
    if (typeof body.expense_alerts === 'boolean') store.profile.expense_alerts = body.expense_alerts
    return json(res, 200, { status: 'ok' })
  }

  if (url.pathname === '/api/services/idle') {
    if (!requireSession(req, res)) return
    if (!store.profile.expense_alerts) return json(res, 200, { enabled: false, services: [] })
    return json(res, 200, {
      enabled: true,
      services: [
        { id: 8, name: 'Netflix', color: '#e50914', last_used: '2026-07-01', days_idle: 34 },
      ],
    })
  }

  if (url.pathname === '/api/providers') {
    if (!requireSession(req, res)) return
    return json(res, 200, [
      { provider_id: 8, provider_name: 'Netflix', logo_path: null },
      { provider_id: 337, provider_name: 'Disney Plus', logo_path: null },
    ])
  }

  const signalMatch = url.pathname.match(/^\/api\/titles\/(movie|tv)\/(\d+)\/signal$/)
  if (signalMatch && req.method === 'GET') {
    if (!requireSession(req, res)) return
    return json(res, 200, store.signal)
  }
  if (signalMatch && req.method === 'POST') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    const body = await readBody(req)
    if (body.kind === 'like') {
      store.signal = { liked: !store.signal.liked, disliked: false }
    } else if (body.kind === 'dislike') {
      store.signal = { liked: false, disliked: !store.signal.disliked }
    }
    return json(res, 200, store.signal)
  }

  if (url.pathname === '/api/nights' && req.method === 'GET') {
    if (!requireSession(req, res)) return
    return json(res, 200, store.nights ?? [])
  }
  if (url.pathname === '/api/nights' && req.method === 'POST') {
    if (!requireSession(req, res)) return
    const body = await readBody(req)
    store.nights = store.nights ?? []
    const night = {
      id: `night-${store.nights.length + 1}`,
      name: body.name ?? 'Movie night',
      host: 'Lordo',
      status: 'planning',
      scheduled_for: null,
      survey_after_hours: body.survey_after_hours ?? 12,
      members: [
        { username: 'Lordo', avatar_path: null, status: 'accepted' },
        ...(body.invite ?? []).map((username) => ({
          username,
          avatar_path: null,
          status: 'invited',
        })),
      ],
      queue: [],
      watched: null,
      watched_at: null,
      your_status: 'accepted',
      you_host: true,
      awaiting_your_verdict: false,
    }
    store.nights.push(night)
    return json(res, 200, night)
  }
  const nightSuggest = url.pathname.match(/^\/api\/nights\/([^/]+)\/suggestions$/)
  if (nightSuggest && req.method === 'POST') {
    if (!requireSession(req, res)) return
    const pick = (c, closest_to) => ({
      tmdb_id: c.tmdb_id,
      type: c.type,
      name: c.name,
      poster_path: c.poster_path,
      year: c.year,
      tmdb_rating: c.tmdb_rating,
      closest_to,
      in_queue: false,
    })
    return json(res, 200, {
      results: [
        pick(COCO_CARD, 'Lordo'),
        pick(F.yourname, 'Nadia'),
        pick(F.dune, 'Lordo'),
        pick(F.ratatouille, 'Nadia'),
        pick(F.spirited, 'Lordo'),
        pick(F.knivesout, 'Nadia'),
      ],
      considered: ['Lordo', 'Nadia'],
      without_taste: [],
    })
  }
  const nightQueue = url.pathname.match(/^\/api\/nights\/([^/]+)\/queue$/)
  if (nightQueue && req.method === 'POST') {
    if (!requireSession(req, res)) return
    const body = await readBody(req)
    const night = (store.nights ?? []).find((n) => n.id === nightQueue[1])
    if (!night) return json(res, 404, { detail: 'no such night' })
    const picked = EVERY_CARD.find((c) => c.tmdb_id === body.tmdb_id)
    night.queue.push({
      tmdb_id: body.tmdb_id,
      type: body.type,
      name: picked?.name ?? 'Coco',
      poster_path: picked?.poster_path ?? null,
      year: picked?.year ?? null,
      suggested_by: night.queue.length % 2 === 0 ? 'Lordo' : 'Nadia',
      votes: 1 + ((night.queue.length + 1) % 3),
      you_voted: true,
    })
    return json(res, 200, night)
  }

  if (url.pathname === '/api/groups' && req.method === 'GET') {
    if (!requireSession(req, res)) return
    return json(res, 200, store.groups)
  }
  if (url.pathname === '/api/groups' && req.method === 'POST') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    const body = await readBody(req)
    const group = {
      id: `group-${store.groups.length + 1}`,
      name: body.name,
      members: ['Lordo', ...(body.member_usernames ?? [])],
      created_by: 'Lordo',
    }
    store.groups.push(group)
    return json(res, 201, group)
  }
  const suggestMatch = url.pathname.match(/^\/api\/groups\/([^/]+)\/suggestions$/)
  if (suggestMatch && req.method === 'POST') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    return json(res, 200, { results: [COCO_CARD], without_taste: [] })
  }
  const groupMatch = url.pathname.match(/^\/api\/groups\/([^/]+)$/)
  if (groupMatch && req.method === 'DELETE') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    store.groups = store.groups.filter((g) => g.id !== groupMatch[1])
    res.writeHead(204)
    return res.end()
  }

  if (url.pathname === '/api/cinema') {
    if (!requireSession(req, res)) return
    const entry = (card, opens_on, in_cinemas_now, tracked, country = 'EG') => ({
      card, opens_on, in_cinemas_now, tracked, country,
    })
    return json(res, 200, {
      country: 'EG',
      countries: ['EG', 'US'],
      now_showing: [
        entry(F.dune, null, true, true),
        entry(F.oppenheimer, null, true, false),
        entry(F.everything, null, true, false),
      ],
      coming_soon: [
        entry(F.knivesout, '2026-08-13', false, true),
        entry(F.arrival, '2026-08-27', false, false),
      ],
      tracking: [
        entry(F.dune, null, true, true),
        entry(F.knivesout, '2026-08-13', false, true),
      ],
      elsewhere: [entry(F.lalaland, '2026-09-04', false, false, 'US')],
    })
  }

  if (url.pathname === '/api/next-up') {
    if (!requireSession(req, res)) return
    return json(res, 200, [
      { title: F.spiderverse, collection_name: 'Spider-Verse collection', collection_id: 573436, reason: 'You watched Into the Spider-Verse', remaining: 1 },
      { title: F.dune, collection_name: 'Dune collection', collection_id: 726871, reason: 'Part Two is out now', remaining: 1 },
    ])
  }

  if (url.pathname === '/api/titles/movie/354912/advisory') {
    if (!requireSession(req, res)) return
    return json(res, 200, {
      summary:
        'Gentle for most ages. Death is a theme throughout, handled warmly; a few skeleton scares, and a poisoning discussed in passing.',
      source: 'imdb',
      categories: [
        {
          key: 'frightening',
          label: 'Frightening and intense',
          severity: 'mild',
          note: 'Skeleton characters and one brief chase',
          total: 3,
          items: [
            { text: 'Skeleton characters appear suddenly in the Land of the Dead', spoiler: false },
            { text: 'A dog leaps across a collapsing marigold bridge', spoiler: false },
            { text: 'A character begins to fade as the living forget him', spoiler: true },
          ],
        },
        {
          key: 'violence',
          label: 'Violence',
          severity: 'mild',
          note: 'Slapstick, no blood',
          total: 2,
          items: [
            { text: 'A guitar is smashed in anger', spoiler: false },
            { text: 'A fall from a bell tower is discussed', spoiler: true },
          ],
        },
        { key: 'profanity', label: 'Language', severity: 'none', note: 'None' },
        {
          key: 'substances',
          label: 'Alcohol and substances',
          severity: 'mild',
          note: 'Adults drink at a gathering; a poisoning is mentioned',
          total: 1,
          items: [{ text: 'A toast at a family celebration', spoiler: false }],
        },
        { key: 'nudity', label: 'Nudity', severity: 'none', note: 'None' },
      ],
    })
  }

  const mediaMatch = url.pathname.match(/^\/api\/media\/tmdb\/([^/]+)\/(.+)$/)
  if (mediaMatch) {
    // Same-origin proxy for TMDB artwork, so canvas exports are not tainted.
    try {
      const upstream = await fetch(`https://image.tmdb.org/t/p/${mediaMatch[1]}/${mediaMatch[2]}`)
      res.writeHead(upstream.status, {
        'Content-Type': upstream.headers.get('content-type') ?? 'image/jpeg',
        'Cache-Control': 'public, max-age=86400',
      })
      return res.end(Buffer.from(await upstream.arrayBuffer()))
    } catch {
      res.writeHead(502)
      return res.end()
    }
  }

  if (url.pathname === '/api/friends') {
    if (!requireSession(req, res)) return
    return json(res, 200, {
      friends: [
        {
          id: 'u-nadia',
          username: 'Nadia',
          handle: 'nadia',
          display_name: null,
          avatar_path: null,
          visibility: 'friends',
          relation: 'friends',
        },
      ],
      incoming: [],
      outgoing: [],
    })
  }

  if (url.pathname === '/api/people') {
    if (!requireSession(req, res)) return
    return json(res, 200, [
      { username: 'Lordo', avatar_path: null, is_me: true },
      { username: 'Nadia', avatar_path: null, is_me: false },
    ])
  }

  if (url.pathname === '/api/countries') {
    if (!requireSession(req, res)) return
    return json(res, 200, [
      { code: 'EG', name: 'Egypt' },
      { code: 'MA', name: 'Morocco' },
      { code: 'FR', name: 'France' },
      { code: 'JP', name: 'Japan' },
      { code: 'US', name: 'United States' },
    ])
  }

  if (url.pathname === '/api/services') {
    if (!requireSession(req, res)) return
    return json(res, 200, [
      { id: 8, name: 'Netflix', color: '#e50914', note: null, subscribed: true, logo_path: null, tracked: true },
      { id: 337, name: 'Disney+', color: '#113ccf', note: 'includes Hulu', subscribed: false, logo_path: null, tracked: true },
    ])
  }

  if (url.pathname === '/api/new') {
    if (!requireSession(req, res)) return
    return json(res, 200, {
      rows: [{ key: 'in-theaters', title: 'In theaters now', items: [F.dune, F.oppenheimer, COCO_CARD, F.everything] }],
      services: [
        {
          service: { id: 8, name: 'Netflix', color: '#e50914', note: null, subscribed: true, logo_path: null, tracked: true },
          items: [S.strangerthings, S.lastofus, COCO_CARD, F.knivesout],
          unknown: false,
        },
        {
          service: { id: 350, name: 'Apple TV+', color: '#555555', note: null, subscribed: true, logo_path: null, tracked: true },
          items: [S.severance, F.lalaland],
          unknown: false,
        },
      ],
      showing_all_services: false,
    })
  }

  if (url.pathname === '/api/admin/activity') {
    if (!requireSession(req, res)) return
    return json(res, 200, {
      by_kind_30d: { view: 4, like: 2, watched: 1 },
      per_user: [{ username: 'Lordo', view: 4, like: 2 }],
      top_viewed: [{ name: 'Coco', count: 4 }],
      top_liked: [{ name: 'Coco', count: 2 }],
    })
  }

  if (url.pathname === '/api/stats') {
    if (!requireSession(req, res)) return
    return json(res, 200, {
      totals: { watched: 214, hours: 391.5, loved: 38, rated: 173, avg_rating: 7.6, this_year: 64 },
      genres: [
        { name: 'Drama', count: 61 },
        { name: 'Animation', count: 38 },
        { name: 'Science fiction', count: 33 },
        { name: 'Thriller', count: 29 },
        { name: 'Comedy', count: 24 },
        { name: 'Crime', count: 18 },
      ],
      monthly: [
        { month: '2025-08', count: 3 },
        { month: '2025-09', count: 5 },
        { month: '2025-10', count: 2 },
        { month: '2025-11', count: 6 },
        { month: '2025-12', count: 9 },
        { month: '2026-01', count: 7 },
        { month: '2026-02', count: 5 },
        { month: '2026-03', count: 8 },
        { month: '2026-04', count: 6 },
        { month: '2026-05', count: 9 },
        { month: '2026-06', count: 11 },
        { month: '2026-07', count: 13 },
      ],
      ratings: [
        { month: '4', count: 3 },
        { month: '5', count: 9 },
        { month: '6', count: 22 },
        { month: '7', count: 48 },
        { month: '8', count: 56 },
        { month: '9', count: 27 },
        { month: '10', count: 8 },
      ],
      top_actors: [
        { name: 'Gael García Bernal', count: 4, extra: null },
        { name: 'Ryan Gosling', count: 3, extra: null },
        { name: 'Timothée Chalamet', count: 3, extra: null },
      ],
      people: [
        { name: 'Gael García Bernal', count: 4, profile_path: null, person_id: 1 },
        { name: 'Ryan Gosling', count: 3, profile_path: null, person_id: 2 },
        { name: 'Timothée Chalamet', count: 3, profile_path: null, person_id: 3 },
        { name: 'Song Kang-ho', count: 3, profile_path: null, person_id: 4 },
        { name: 'Emma Stone', count: 2, profile_path: null, person_id: 5 },
        { name: 'Adam Scott', count: 2, profile_path: null, person_id: 6 },
      ],
      directors: [
        { name: 'Denis Villeneuve', count: 5, profile_path: null, person_id: 7 },
        { name: 'Christopher Nolan', count: 4, profile_path: null, person_id: 8 },
        { name: 'Hayao Miyazaki', count: 4, profile_path: null, person_id: 9 },
        { name: 'Bong Joon-ho', count: 3, profile_path: null, person_id: 10 },
      ],
      languages: [
        { name: 'en', count: 122 },
        { name: 'ja', count: 31 },
        { name: 'es', count: 22 },
        { name: 'ko', count: 14 },
        { name: 'fr', count: 9 },
      ],
      decades: [
        { name: '2020s', count: 74 },
        { name: '2010s', count: 82 },
        { name: '2000s', count: 31 },
        { name: '1990s', count: 18 },
        { name: '1970s', count: 9 },
      ],
      highest_rated: [
        highlight(F.interstellar, 10, true),
        highlight(F.parasite, 10, true),
        highlight(COCO_CARD, 9, true),
        highlight(S.severance, 9, false),
        highlight(F.spirited, 9, true),
        highlight(F.whiplash, 9, false),
      ],
      recent: [
        highlight(F.dune, 8, false),
        highlight(S.andor, 9, true),
        highlight(F.yourname, 9, true),
        highlight(F.knivesout, 7, false),
        highlight(F.moodforlove, 8, false),
        highlight(COCO_CARD, 9, true),
      ],
      by_year: [
        { name: '2024', count: 68 },
        { name: '2025', count: 82 },
        { name: '2026', count: 64 },
      ],
      days: Array.from({ length: 366 }, (_, i) => {
        const d = new Date(Date.UTC(2026, 0, 1 + i))
        if (d > new Date('2026-08-04')) return null
        const pulse = (Math.sin(i / 3) + Math.sin(i / 7) + 2) / 4
        const count = pulse > 0.62 ? Math.round(pulse * 4) : 0
        return count > 0 ? { day: d.toISOString().slice(0, 10), count } : null
      }).filter(Boolean),
      years: [2024, 2025, 2026],
      top_ten: [
        highlight(F.interstellar, 10, true),
        highlight(F.parasite, 10, true),
        highlight(COCO_CARD, 9, true),
        highlight(F.spirited, 9, true),
        highlight(S.severance, 9, false),
        highlight(F.whiplash, 9, false),
        highlight(S.andor, 9, true),
        highlight(F.yourname, 9, true),
        highlight(F.bladerunner, 8, false),
        highlight(F.budapest, 8, false),
      ],
      longest: [
        highlight(F.oppenheimer, 8, false),
        highlight(F.godfather, 9, false),
        highlight(F.interstellar, 10, true),
        highlight(F.bladerunner, 8, false),
      ],
      collections: [
        { name: 'Spider-Verse collection', count: 3 },
        { name: 'The Godfather collection', count: 3 },
        { name: 'Dune collection', count: 2 },
      ],
      runtime_buckets: [
        { name: 'Under 100 min', count: 41 },
        { name: '100 to 140 min', count: 96 },
        { name: 'Over 140 min', count: 52 },
      ],
      streak_longest: 11,
      wrap: { year: 2026, watched: 64, hours: 118.5, favorite: 'Interstellar', top_genre: 'Drama' },
    })
  }
  if (url.pathname === '/api/tokens' && req.method === 'GET') {
    if (!requireSession(req, res)) return
    return json(res, 200, { api_enabled_globally: false, api_enabled_for_me: false, tokens: [] })
  }
  const pwMatch = url.pathname.match(/^\/api\/admin\/users\/([^/]+)\/password$/)
  if (pwMatch && req.method === 'PUT') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    res.writeHead(204)
    return res.end()
  }
  if (url.pathname === '/api/admin/users') {
    if (!requireSession(req, res)) return
    return json(res, 200, [
      {
        id: '00000000-0000-0000-0000-0000000000aa',
        username: 'Nadia',
        email: null,
        role: 'member',
        is_active: true,
        api_enabled: false,
        country_code: 'EG',
        last_login_at: null,
        has_oidc: false,
      },
    ])
  }
  if (url.pathname === '/api/admin/flags') {
    if (!requireSession(req, res)) return
    return json(res, 200, [
      { key: 'api_tokens', enabled: false, description: 'Allow personal API tokens' },
    ])
  }
  if (url.pathname === '/api/admin/audit') {
    if (!requireSession(req, res)) return
    return json(res, 200, { total: 0, rows: [], actions: [] })
  }
  if (url.pathname === '/api/admin/imports') {
    if (!requireSession(req, res)) return
    return json(res, 200, [])
  }

  if (url.pathname === '/api/ai/status') {
    if (!requireSession(req, res)) return
    // No model name: /api/ai/status does not name the model, only Admin does.
    return json(res, 200, { enabled: store.ai.enabled, embedded_titles: 42 })
  }
  if (url.pathname === '/api/ai/search' && req.method === 'POST') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    if (!store.ai.enabled) return json(res, 503, { detail: 'ai_disabled' })
    return json(res, 200, {
      parsed: { mood: 'bittersweet family story about music', types: ['movie'], runtime_max: 120 },
      results: [COCO_CARD],
    })
  }
  // Saving a whole franchise, or a set the assistant proposed. Order is
  // preserved by position, which is what makes a watch-through readable.
  if (url.pathname === '/api/lists/bulk' && req.method === 'POST') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    const body = await readBody(req)
    const target = body.name
      ? (store.lists.find((l) => l.name.toLowerCase() === String(body.name).toLowerCase()) ??
        (store.lists.push({ id: `list-${store.lists.length}`, name: body.name, kind: 'custom', items: [] }),
         store.lists[store.lists.length - 1]))
      : store.lists.find((l) => (body.shared ? l.kind === 'shared' : l.kind === 'watchlist'))
    let added = 0
    let already = 0
    for (const t of body.titles ?? []) {
      if (target.items.some((i) => i.tmdb_id === t.tmdb_id)) already += 1
      else {
        target.items.push({ tmdb_id: t.tmdb_id, type: t.type })
        added += 1
      }
    }
    return json(res, 200, { added, already_there: already, failed: 0, list_name: target.name })
  }
  if (url.pathname === '/api/titles/movie/354912/similar') {
    if (!requireSession(req, res)) return
    return json(res, 200, { results: [] })
  }
  // Episodes. One aired season and one episode still to come, which is the
  // shape that exercises both the tick box and the locked row.
  {
    const episodes = /^\/api\/titles\/tv\/(\d+)\/episodes(\/watched|\/season)?$/.exec(url.pathname)
    if (episodes) {
      if (!requireSession(req, res)) return
      if (req.method === 'POST') {
        if (!requireCsrf(req, res)) return
        const body = await readBody(req)
        if (body.season !== undefined && body.episode !== undefined) {
          const found = store.episodes.find(
            (e) => e.season === body.season && e.episode === body.episode
          )
          if (found) found.watched = Boolean(body.watched)
        } else if (body.season !== undefined) {
          for (const e of store.episodes) {
            if (e.season === body.season && e.aired) e.watched = Boolean(body.watched)
          }
        }
      }
      const aired = store.episodes.filter((e) => e.aired)
      const seasons = [...new Set(store.episodes.map((e) => e.season))].sort((a, b) => a - b)
      return json(res, 200, {
        seasons: seasons.map((s) => ({
          season: s,
          episodes: store.episodes.filter((e) => e.season === s),
        })),
        next_up: aired.find((e) => !e.watched) ?? null,
        aired: aired.length,
        watched: aired.filter((e) => e.watched).length,
        upcoming: store.episodes.filter((e) => !e.aired).length,
        complete: aired.length > 0 && aired.every((e) => e.watched),
      })
    }
  }
  if (url.pathname === '/api/titles/movie/354912/tags') {
    if (!requireSession(req, res)) return
    return json(res, 200, { tags: [{ tag: 'feel-good', score: 0.71 }] })
  }
  if (url.pathname === '/api/admin/quota') {
    if (!requireSession(req, res)) return
    return json(res, 200, {
      today: { tmdb: 12, omdb: 3 },
      omdb_daily_budget: 900,
      tmdb_configured: true,
      omdb_configured: true,
      last_30_days: [],
    })
  }
  if (url.pathname === '/api/admin/settings/ai' && req.method === 'GET') {
    if (!requireSession(req, res)) return
    return json(res, 200, { ...store.ai, has_api_key: false })
  }
  if (url.pathname === '/api/admin/settings/ai' && req.method === 'PUT') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    const body = await readBody(req)
    store.ai = {
      enabled: !!body.enabled,
      base_url: body.base_url ?? store.ai.base_url,
      chat_model: body.chat_model ?? store.ai.chat_model,
      embed_model: body.embed_model ?? store.ai.embed_model,
    }
    return json(res, 200, { ...store.ai, has_api_key: !!body.api_key })
  }

  if (url.pathname === '/api/notifications' && req.method === 'GET') {
    if (!requireSession(req, res)) return
    return json(res, 200, {
      unread: store.notifications.filter((n) => !n.read).length,
      notifications: store.notifications,
    })
  }
  const readMatch = url.pathname.match(/^\/api\/notifications\/([^/]+)\/read$/)
  if (readMatch && req.method === 'POST') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    const item = store.notifications.find((n) => n.id === readMatch[1])
    if (item) item.read = true
    res.writeHead(204)
    return res.end()
  }
  if (url.pathname === '/api/notifications/read-all' && req.method === 'POST') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    store.notifications.forEach((n) => (n.read = true))
    res.writeHead(204)
    return res.end()
  }

  if (url.pathname === '/api/imports' && req.method === 'GET') {
    if (!requireSession(req, res)) return
    return json(res, 200, store.imports)
  }
  if (url.pathname === '/api/imports' && req.method === 'POST') {
    if (!requireSession(req, res) || !requireCsrf(req, res)) return
    // Multipart parsing is overkill for the mock; accept anything.
    req.resume()
    req.on('end', () => {
      const batch = {
        id: `import-${store.imports.length + 1}`,
        service: 'json',
        target: 'watchlist',
        filename: null,
        status: 'done',
        error: null,
        stats: { total: 1, imported: 1 },
        pending_review: 0,
        created_at: '2026-08-01T00:00:00Z',
      }
      store.imports.unshift(batch)
      json(res, 201, batch)
    })
    return
  }

  const homeRows = () => [
          { key: 'for-you', title: 'Picked for you', items: [F.interstellar, COCO_CARD, F.dune, S.severance, F.bladerunner, F.spirited, F.moodforlove, S.andor, F.yourname, F.whiplash] },
          { key: 'trending-movies', title: 'Trending films', items: [COCO_CARD, F.oppenheimer, F.dune, F.everything, F.knivesout, F.spiderverse, F.furyroad, F.lalaland] },
          { key: 'because-you-watched-coco', title: 'Because you watched Coco', items: [F.ratatouille, F.spiderverse, F.yourname, F.spirited, F.lalaland, F.budapest] },
          { key: 'series-for-you', title: 'Series people stay with', items: [S.severance, S.andor, S.breakingbad, S.lastofus, S.strangerthings] },
          { key: 'acclaimed-for-you', title: 'Acclaimed, and up your street', items: [F.parasite, F.godfather, F.pulpfiction, F.darkknight, F.portrait, F.fightclub, F.arrival] },
  ]
  if (url.pathname === '/api/home/stream') {
    if (!requireSession(req, res)) return
    res.writeHead(200, { 'Content-Type': 'application/x-ndjson' })
    const rows = homeRows()
    let i = 0
    const tick = () => {
      if (i >= rows.length) {
        res.end()
        return
      }
      res.write(JSON.stringify(rows[i]) + '\n')
      i += 1
      setTimeout(tick, 25)
    }
    tick()
    return
  }
  if (url.pathname === '/api/home') {
    if (!requireSession(req, res)) return
    res.writeHead(200, { 'Content-Type': 'application/json' })
    return res.end(JSON.stringify({ rows: homeRows() }))
  }

  if (url.pathname === '/api/titles/movie/354912') {
    if (!requireSession(req, res)) return
    res.writeHead(200, { 'Content-Type': 'application/json' })
    return res.end(JSON.stringify(COCO_DETAIL))
  }

  if (url.pathname === '/api/search') {
    if (!requireSession(req, res)) return
    const q = (url.searchParams.get('q') ?? '').toLowerCase()
    res.writeHead(200, { 'Content-Type': 'application/json' })
    return res.end(
      JSON.stringify({
        results: 'coco'.includes(q) || q.includes('coco') ? [COCO_CARD] : [],
        page: 1,
        total_pages: 1,
      }),
    )
  }

  if (url.pathname === '/api/genres') {
    if (!requireSession(req, res)) return
    res.writeHead(200, { 'Content-Type': 'application/json' })
    return res.end(
      JSON.stringify({ movie: [{ id: 16, name: 'Animation' }], tv: [{ id: 18, name: 'Drama' }], combined: [{ id: 16, name: 'Animation', movie_ids: [16], tv_ids: [16] }, { id: 18, name: 'Drama', movie_ids: [18], tv_ids: [18] }] }),
    )
  }

  if (url.pathname === '/api/browse') {
    if (!requireSession(req, res)) return
    res.writeHead(200, { 'Content-Type': 'application/json' })
    return res.end(JSON.stringify({ results: EVERY_CARD, page: 1, total_pages: 3 }))
  }

  if (url.pathname === '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' })
    return res.end(JSON.stringify({ status: 'ok' }))
  }

  if (url.pathname === '/api/me') {
    if (!hasSession(req)) {
      res.writeHead(401, { 'Content-Type': 'application/json' })
      return res.end(JSON.stringify({ detail: 'not authenticated' }))
    }
    res.writeHead(200, { 'Content-Type': 'application/json' })
    return res.end(
      JSON.stringify({
        user: {
          id: '00000000-0000-0000-0000-000000000001',
          username: 'Lordo',
          email: 'lordo@example.com',
          role: 'admin',
          avatar_path: null,
          country_code: store.profile.country_code,
          services: store.profile.services,
          prefs: { parents_guide: true },
        },
        csrf: CSRF,
        needs_onboarding: false,
      }),
    )
  }

  if (url.pathname === '/auth/login') {
    const next = url.searchParams.get('next') ?? '/app'
    // A real deployment redirects to Pocket ID here; the mock goes straight
    // to the callback as if the IdP approved instantly.
    res.writeHead(302, { Location: `/auth/callback?code=ok&state=ok&next=${encodeURIComponent(next)}` })
    return res.end()
  }

  if (url.pathname === '/auth/callback') {
    const next = url.searchParams.get('next') ?? '/app'
    res.writeHead(302, {
      'Set-Cookie': 'wd_session=mock-token; Path=/; HttpOnly; SameSite=Lax',
      Location: next,
    })
    return res.end()
  }

  if (url.pathname === '/api/auth/logout' && req.method === 'POST') {
    if (!hasSession(req)) {
      res.writeHead(401, { 'Content-Type': 'application/json' })
      return res.end(JSON.stringify({ detail: 'not authenticated' }))
    }
    if (req.headers['x-csrf-token'] !== CSRF) {
      res.writeHead(403, { 'Content-Type': 'application/json' })
      return res.end(JSON.stringify({ detail: 'csrf token missing or invalid' }))
    }
    res.writeHead(204, {
      'Set-Cookie': 'wd_session=; Path=/; Max-Age=0',
    })
    return res.end()
  }

  res.writeHead(404, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify({ detail: 'not found' }))
})

server.listen(PORT, '127.0.0.1', () => {
  console.log(`mock api on ${PORT}`)
})
