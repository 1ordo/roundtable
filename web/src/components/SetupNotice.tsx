export function SetupNotice() {
  return (
    <div className="wd-plate p-6">
      <p className="font-display text-lg font-semibold uppercase">
        The catalog is not connected yet
      </p>
      <p className="mt-2 max-w-lg text-sm text-muted">
        Add a TMDB API key to the server environment (RT_TMDB_API_KEY) and restart.
        Keys are free at themoviedb.org under Settings, then API.
      </p>
    </div>
  )
}

export function LoadError({ message }: { message?: string }) {
  return (
    <div className="rounded-[6px] border border-danger/40 bg-danger/10 p-6">
      <p className="font-display text-lg font-semibold uppercase">
        Could not load this right now
      </p>
      <p className="mt-2 text-sm text-muted">{message ?? 'Check the server logs and try again.'}</p>
    </div>
  )
}
