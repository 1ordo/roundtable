import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { SERIES, languageName, type NameCount, type PersonCount, type TitleHighlight } from './StatsViews'

/* A set of share cards rather than one.
 *
 * Posters are drawn through the app's own image proxy, not straight from
 * the catalog host: a cross-origin image with no CORS header taints the
 * canvas, and toBlob then throws instead of producing a file. Same origin
 * keeps the canvas clean, so the export cannot silently fail.
 */

const WIDTH = 1080
const HEIGHT = 1350

/* Exported PNG cards always use the dark ("house lights down") palette,
   whatever theme the app is in — the cards are made for feeds, and feeds
   are dark. */
const INK = '#181114'
const FG = '#f2ebe4'
const MUTED = '#a2938e'
const EMBER = '#ec6a3f'
const NITRATE = '#4cbaa4'
const LINE = '#3d3034'

export type CardData = {
  username: string
  year: number
  watched: number
  hours: number
  loved: number
  avgRating: number | null
  streak: number
  topGenres: NameCount[]
  topLanguages: NameCount[]
  favorite: string | null
  people: PersonCount[]
  highest: TitleHighlight[]
  decades: NameCount[]
}

function proxied(path: string | null, size = 'w342'): string | null {
  if (!path) return null
  // Absolute urls (OMDb) cannot be proxied by filename, so they are left
  // out of the card rather than drawn from another origin.
  if (path.startsWith('http')) return null
  return `/api/media/tmdb/${size}/${path.replace(/^\//, '')}`
}

function escapeText(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function chrome(title: string, subtitle: string): string {
  return `
  <rect width="${WIDTH}" height="${HEIGHT}" fill="${INK}"/>
  <rect width="${WIDTH}" height="${HEIGHT}" fill="url(#beam)"/>
  <circle cx="108" cy="116" r="34" fill="none" stroke="${EMBER}" stroke-width="8.5"/>
  <circle cx="117" cy="107" r="34" fill="none" stroke="${NITRATE}" stroke-width="8.5" opacity="0.9"/>
  <text x="182" y="134" font-family="Big Shoulders Variable, Arial Narrow, sans-serif" font-size="44" font-weight="600" letter-spacing="3" fill="${FG}">ROUNDTABLE</text>
  <text x="72" y="252" font-family="monospace" font-size="24" letter-spacing="8" fill="${EMBER}">${escapeText(subtitle)}</text>
  <text x="72" y="330" font-family="Big Shoulders Variable, Arial Narrow, sans-serif" font-size="60" fill="${FG}">${escapeText(title)}</text>`
}

const DEFS = `
  <defs>
    <linearGradient id="beam" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="${EMBER}" stop-opacity="0.20"/>
      <stop offset="55%" stop-color="${INK}" stop-opacity="0"/>
      <stop offset="100%" stop-color="${NITRATE}" stop-opacity="0.16"/>
    </linearGradient>
    <clipPath id="round"><rect x="0" y="0" width="200" height="300" rx="12"/></clipPath>
  </defs>`

/* Each card is described as SVG plus a list of images to paint underneath,
   because an <image> inside an SVG blob cannot reference a same-origin URL
   once that blob is loaded as an image itself. */
type Card = {
  name: string
  svg: string
  images: { url: string; x: number; y: number; w: number; h: number; radius: number }[]
}

function topTenCard(data: CardData): Card | null {
  const picks = data.highest.slice(0, 10).filter((t) => proxied(t.poster_path))
  if (picks.length < 3) return null

  const images = picks.map((title, i) => ({
    url: proxied(title.poster_path)!,
    x: 72 + (i % 5) * 192,
    y: 430 + Math.floor(i / 5) * 330,
    w: 176,
    h: 264,
    radius: 12,
  }))

  const labels = picks
    .map((title, i) => {
      const x = 72 + (i % 5) * 192
      const y = 430 + Math.floor(i / 5) * 330
      return `
        <text x="${x}" y="${y - 12}" font-family="monospace" font-size="22" fill="${EMBER}">${i + 1}</text>
        <text x="${x}" y="${y + 292}" font-family="Big Shoulders Variable, Arial Narrow, sans-serif" font-size="18" fill="${FG}">${escapeText(
          title.name.length > 18 ? `${title.name.slice(0, 17)}…` : title.name,
        )}</text>`
    })
    .join('')

  return {
    name: 'top-ten',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${HEIGHT}" viewBox="0 0 ${WIDTH} ${HEIGHT}">
      ${DEFS}${chrome(`${data.username}, ranked`, `TOP ${picks.length} OF ${data.year}`)}
      ${labels}
      <text x="72" y="1290" font-family="monospace" font-size="20" fill="${MUTED}">Rated and loved, most first</text>
    </svg>`,
    images,
  }
}

function peopleCard(data: CardData): Card | null {
  const picks = data.people.slice(0, 8).filter((p) => proxied(p.profile_path, 'w185'))
  if (picks.length < 3) return null

  const images = picks.map((person, i) => ({
    url: proxied(person.profile_path, 'w185')!,
    x: 96 + (i % 4) * 232,
    y: 460 + Math.floor(i / 4) * 400,
    w: 180,
    h: 180,
    radius: 90,
  }))

  const labels = picks
    .map((person, i) => {
      const x = 96 + (i % 4) * 232
      const y = 460 + Math.floor(i / 4) * 400
      return `
        <text x="${x + 90}" y="${y + 224}" text-anchor="middle" font-family="Big Shoulders Variable, Arial Narrow, sans-serif" font-size="21" fill="${FG}">${escapeText(
          person.name.length > 16 ? `${person.name.slice(0, 15)}…` : person.name,
        )}</text>
        <text x="${x + 90}" y="${y + 254}" text-anchor="middle" font-family="monospace" font-size="18" fill="${MUTED}">${person.count} titles</text>`
    })
    .join('')

  return {
    name: 'people',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${HEIGHT}" viewBox="0 0 ${WIDTH} ${HEIGHT}">
      ${DEFS}${chrome('Faces of the year', 'WHO YOU WATCHED')}
      ${labels}
    </svg>`,
    images,
  }
}

function tasteCard(data: CardData): Card {
  const genres = data.topGenres.slice(0, 5)
  const max = Math.max(1, ...genres.map((g) => g.count))
  const bars = genres
    .map((genre, i) => {
      const y = 470 + i * 96
      const width = Math.round((genre.count / max) * 600)
      return `
        <text x="72" y="${y}" font-family="Big Shoulders Variable, Arial Narrow, sans-serif" font-size="30" fill="${FG}">${escapeText(genre.name)}</text>
        <rect x="360" y="${y - 26}" width="600" height="32" rx="16" fill="${LINE}"/>
        <rect x="360" y="${y - 26}" width="${width}" height="32" rx="16" fill="${SERIES[i % SERIES.length]}"/>
        <text x="${360 + width + 16}" y="${y}" font-family="monospace" font-size="22" fill="${MUTED}">${genre.count}</text>`
    })
    .join('')

  const decades = data.decades
    .slice(-5)
    .map((d, i) => {
      const x = 72 + i * 190
      return `
        <text x="${x}" y="1120" font-family="Big Shoulders Variable, Arial Narrow, sans-serif" font-size="34" fill="${NITRATE}">${escapeText(d.name)}</text>
        <text x="${x}" y="1156" font-family="monospace" font-size="20" fill="${MUTED}">${d.count}</text>`
    })
    .join('')

  const languages = data.topLanguages
    .slice(0, 4)
    .map((l) => languageName(l.name))
    .join('  ·  ')

  return {
    name: 'taste',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${HEIGHT}" viewBox="0 0 ${WIDTH} ${HEIGHT}">
      ${DEFS}${chrome('What you went for', 'YOUR TASTE')}
      ${bars}
      <text x="72" y="1060" font-family="monospace" font-size="20" letter-spacing="6" fill="${MUTED}">ACROSS THE DECADES</text>
      ${decades}
      ${
        languages
          ? `<text x="72" y="1250" font-family="monospace" font-size="20" letter-spacing="6" fill="${MUTED}">IN</text>
             <text x="72" y="1296" font-family="Big Shoulders Variable, Arial Narrow, sans-serif" font-size="32" fill="${FG}">${escapeText(languages)}</text>`
          : ''
      }
    </svg>`,
    images: [],
  }
}

/* The original card, kept as the last of the set. */
function numbersCard(data: CardData): Card {
  const genres = data.topGenres.slice(0, 4)
  const max = Math.max(1, ...genres.map((g) => g.count))
  const bars = genres
    .map((genre, i) => {
      const y = 800 + i * 84
      const width = Math.round((genre.count / max) * 600)
      return `
        <text x="72" y="${y}" font-family="Big Shoulders Variable, Arial Narrow, sans-serif" font-size="28" fill="${FG}">${escapeText(genre.name)}</text>
        <rect x="340" y="${y - 24}" width="600" height="28" rx="14" fill="${LINE}"/>
        <rect x="340" y="${y - 24}" width="${width}" height="28" rx="14" fill="${SERIES[i % SERIES.length]}"/>`
    })
    .join('')

  return {
    name: 'numbers',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${HEIGHT}" viewBox="0 0 ${WIDTH} ${HEIGHT}">
      ${DEFS}${chrome(data.username, `${data.year} IN FILM`)}

      <text x="72" y="490" font-family="Big Shoulders Variable, Arial Narrow, sans-serif" font-size="96" fill="${EMBER}">${data.watched}</text>
      <text x="72" y="536" font-family="monospace" font-size="22" fill="${MUTED}">TITLES</text>

      <text x="400" y="490" font-family="Big Shoulders Variable, Arial Narrow, sans-serif" font-size="96" fill="${FG}">${data.hours}</text>
      <text x="400" y="536" font-family="monospace" font-size="22" fill="${MUTED}">HOURS</text>

      <text x="700" y="490" font-family="Big Shoulders Variable, Arial Narrow, sans-serif" font-size="96" fill="${FG}">${data.loved}</text>
      <text x="700" y="536" font-family="monospace" font-size="22" fill="${MUTED}">LOVED</text>

      <text x="72" y="640" font-family="Big Shoulders Variable, Arial Narrow, sans-serif" font-size="70" fill="${NITRATE}">${data.streak}</text>
      <text x="72" y="678" font-family="monospace" font-size="22" fill="${MUTED}">DAY STREAK</text>
      ${
        data.avgRating != null
          ? `<text x="400" y="640" font-family="Big Shoulders Variable, Arial Narrow, sans-serif" font-size="70" fill="${NITRATE}">${data.avgRating}</text>
             <text x="400" y="678" font-family="monospace" font-size="22" fill="${MUTED}">AVERAGE SCORE</text>`
          : ''
      }

      <text x="72" y="740" font-family="monospace" font-size="20" letter-spacing="6" fill="${MUTED}">MOSTLY</text>
      ${bars}
      ${
        data.favorite
          ? `<text x="72" y="1210" font-family="monospace" font-size="20" letter-spacing="6" fill="${MUTED}">FAVOURITE</text>
             <text x="72" y="1264" font-family="Big Shoulders Variable, Arial Narrow, sans-serif" font-size="42" fill="${FG}">${escapeText(
               data.favorite.slice(0, 32),
             )}</text>`
          : ''
      }
    </svg>`,
    images: [],
  }
}

async function loadImage(url: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new Image()
    image.onload = () => resolve(image)
    // A missing poster loses one tile, never the whole card.
    image.onerror = () => resolve(null)
    image.src = url
  })
}

function roundedPath(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  const radius = Math.min(r, w / 2, h / 2)
  context.beginPath()
  context.moveTo(x + radius, y)
  context.arcTo(x + w, y, x + w, y + h, radius)
  context.arcTo(x + w, y + h, x, y + h, radius)
  context.arcTo(x, y + h, x, y, radius)
  context.arcTo(x, y, x + w, y, radius)
  context.closePath()
}

async function render(card: Card): Promise<Blob> {
  const canvas = document.createElement('canvas')
  canvas.width = WIDTH
  canvas.height = HEIGHT
  const context = canvas.getContext('2d')
  if (!context) throw new Error('no canvas')

  // Background and text first, then the photographs on top of it.
  const blob = new Blob([card.svg], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const base = await loadImage(url)
  URL.revokeObjectURL(url)
  if (!base) throw new Error('could not draw the card')
  context.drawImage(base, 0, 0)

  const loaded = await Promise.all(card.images.map((spec) => loadImage(spec.url)))
  loaded.forEach((image, i) => {
    if (!image) return
    const spec = card.images[i]
    context.save()
    roundedPath(context, spec.x, spec.y, spec.w, spec.h, spec.radius)
    context.clip()
    // Cover, not stretch: posters and portraits have different ratios.
    const scale = Math.max(spec.w / image.width, spec.h / image.height)
    const drawWidth = image.width * scale
    const drawHeight = image.height * scale
    context.drawImage(
      image,
      spec.x + (spec.w - drawWidth) / 2,
      spec.y + (spec.h - drawHeight) / 2,
      drawWidth,
      drawHeight,
    )
    context.restore()
  })

  const png = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'))
  if (!png) throw new Error('could not encode the image')
  return png
}

const LABELS: Record<string, string> = {
  'top-ten': 'Top ten',
  people: 'Faces',
  taste: 'Taste',
  numbers: 'Numbers',
}

export function StatsCards({ data }: { data: CardData }) {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [previews, setPreviews] = useState<{ name: string; url: string }[]>([])
  const [zoomed, setZoomed] = useState<string | null>(null)

  // Order matters: the numbers card the app has always made goes last.
  const cards = useMemo(
    () =>
      [topTenCard(data), peopleCard(data), tasteCard(data), numbersCard(data)].filter(
        (card): card is Card => card !== null,
      ),
    [data],
  )

  /* Draw them all as soon as the data is there. Asking someone to download
     a file to find out what it looks like is the wrong way round, and these
     are the thing people actually want to post. */
  useEffect(() => {
    let cancelled = false
    const made: string[] = []
    ;(async () => {
      const out: { name: string; url: string }[] = []
      for (const card of cards) {
        try {
          const png = await render(card)
          const url = URL.createObjectURL(png)
          made.push(url)
          out.push({ name: card.name, url })
        } catch {
          // One card failing must not cost the others their preview.
        }
      }
      if (!cancelled) setPreviews(out)
    })()
    return () => {
      cancelled = true
      made.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [cards])

  function download(name: string, url: string) {
    const link = document.createElement('a')
    link.href = url
    link.download = `roundtable-${data.year}-${name}.png`
    link.click()
  }

  async function saveAll() {
    setBusy('all')
    setError(null)
    try {
      for (const preview of previews) {
        download(preview.name, preview.url)
        // A pause between clicks, or the browser blocks the later ones as
        // an unrequested batch of downloads.
        await new Promise((resolve) => setTimeout(resolve, 350))
      }
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'export failed')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="mt-4">
      {previews.length === 0 ? (
        <div className="flex gap-4">
          {cards.map((card) => (
            <div
              key={card.name}
              className="h-64 w-52 shrink-0 animate-pulse rounded-md bg-panel"
            />
          ))}
        </div>
      ) : (
        <div className="wd-scroller flex gap-4 overflow-x-auto pb-3">
          {previews.map((preview, i) => (
            <motion.div
              key={preview.name}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(i * 0.06, 0.3), duration: 0.4 }}
              className="w-52 shrink-0"
            >
              <button
                onClick={() => setZoomed(preview.url)}
                className="group block w-full"
                aria-label={`Look at the ${LABELS[preview.name]} card`}
              >
                <img
                  src={preview.url}
                  alt={`${LABELS[preview.name]} card for ${data.year}`}
                  className="w-full rounded-md border border-line transition-colors group-hover:border-ember"
                />
              </button>
              <div className="mt-2 flex items-center justify-between gap-2">
                <span className="truncate text-xs">{LABELS[preview.name]}</span>
                <button
                  onClick={() => download(preview.name, preview.url)}
                  className="shrink-0 rounded-[4px] border border-line px-2 py-1 font-mono text-[10px] text-muted transition-colors hover:border-ember hover:text-ember"
                >
                  save
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-3">
        <motion.button
          whileTap={{ scale: 0.97 }}
          onClick={saveAll}
          disabled={busy !== null || previews.length === 0}
          className="rounded-[4px] bg-ember px-5 py-2.5 text-sm font-medium text-ink transition-colors hover:bg-ember/90 disabled:opacity-50"
        >
          {busy ? 'Saving' : `Save all ${previews.length}`}
        </motion.button>
        <span className="text-xs text-muted">
          Each one is 1080 by 1350, sized for a story. Tap one to see it full size.
        </span>
      </div>
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}

      {/* Full size, because the point of these is how they look. */}
      <AnimatePresence>
        {zoomed && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setZoomed(null)}
            className="fixed inset-0 z-50 flex items-center justify-center bg-ink/90 p-6 backdrop-blur-sm"
          >
            <motion.img
              initial={{ scale: 0.94 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0.94 }}
              src={zoomed}
              alt="Your year, full size"
              className="max-h-full rounded-lg border border-line"
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
