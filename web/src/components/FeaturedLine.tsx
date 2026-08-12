import { Link } from 'react-router'
import { img } from '../api/catalog'

export type FeaturedLine = {
  id: string
  body: string
  character: string | null
  title: {
    tmdb_id: number
    type: string
    name: string
    backdrop_path: string | null
    poster_path: string | null
    year: number | null
  }
}

/* The one line somebody put above their name.
 *
 * This replaced a grid of every line they had ever saved. A list of saved
 * lines is an inventory; one line, chosen, at full width, is a statement
 * about the person, which is what the feature was always reaching for.
 *
 * Two things carry it and both have to be right. The image is the film's
 * backdrop at w1280 rather than the poster, because a poster is portrait and
 * a cover is not, and at that width it is sharp on a retina display without
 * being an original-size download. And the line itself is set in the display
 * face at a size that assumes it is the loudest thing on the page, because
 * it is.
 */
export function FeaturedLineCover({ line }: { line: FeaturedLine }) {
  // Backdrop first. The poster is a fallback for the handful of titles that
  // have no backdrop, cropped hard so it still reads as a band rather than
  // a portrait stretched sideways.
  const backdrop = img(line.title.backdrop_path, 'w1280')
  const poster = img(line.title.poster_path, 'w500')
  const image = backdrop ?? poster

  // Long lines need to come down in size or they wrap into a wall.
  const long = line.body.length > 90

  return (
    <figure className="relative -mx-4 mb-8 overflow-hidden sm:mx-0 sm:rounded-[6px] sm:border sm:border-line">
      {image ? (
        <img
          src={image}
          alt=""
          aria-hidden
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : (
        <span className="absolute inset-0 bg-panel-2" aria-hidden />
      )}

      {/* Two layers, not one. A flat scrim dulls the image everywhere; a
          gradient keeps the picture readable at the top and buys contrast
          exactly where the text sits. */}
      <span
        aria-hidden
        className="absolute inset-0 bg-gradient-to-t from-ink via-ink/80 to-ink/25"
      />
      <span aria-hidden className="absolute inset-0 bg-ink/25" />

      <blockquote className="relative px-5 py-10 sm:px-8 sm:py-14">
        <p
          className={
            long
              ? 'font-display text-2xl leading-tight font-semibold text-balance sm:text-3xl'
              : 'font-display text-3xl leading-tight font-semibold text-balance sm:text-4xl'
          }
        >
          <span aria-hidden className="text-ember">
            “
          </span>
          {line.body}
          <span aria-hidden className="text-ember">
            ”
          </span>
        </p>
        <figcaption className="mt-4 flex flex-wrap items-baseline gap-x-2 font-mono text-xs tracking-wide text-muted uppercase">
          {line.character && <span className="text-fg/80">{line.character}</span>}
          {line.character && <span aria-hidden>·</span>}
          <Link
            to={`/app/title/${line.title.type}/${line.title.tmdb_id}`}
            className="transition-colors hover:text-ember"
          >
            {line.title.name}
            {line.title.year ? ` (${line.title.year})` : ''}
          </Link>
        </figcaption>
      </blockquote>
    </figure>
  )
}
