/* TMDB terms of use require attribution wherever their data or images
   appear, using their own logo. Keep this visible; do not restyle the
   logo itself. https://www.themoviedb.org/about/logos-attribution */
export function Attribution({ className }: { className?: string }) {
  return (
    <div className={className}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <a
          href="https://www.themoviedb.org/"
          target="_blank"
          rel="noreferrer"
          aria-label="The Movie Database"
        >
          <img src="/tmdb-logo.svg" alt="TMDB" className="h-4 w-auto" />
        </a>
        <p className="text-xs text-muted">
          This product uses the TMDB API but is not endorsed or certified by TMDB.
        </p>
      </div>
      <p className="mt-1.5 text-xs text-muted">
        Ratings from{' '}
        <a
          href="https://www.omdbapi.com/"
          target="_blank"
          rel="noreferrer"
          className="underline-offset-4 hover:text-fg hover:underline"
        >
          OMDb
        </a>
        , which sources IMDb, Rotten Tomatoes, and Metacritic scores.
      </p>
    </div>
  )
}
