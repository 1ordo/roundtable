import { Link } from 'react-router'

export function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-ink px-6">
      <p className="wd-eyebrow">404</p>
      <h1 className="text-center font-display text-5xl font-semibold uppercase tracking-[0.01em]">
        This reel does not exist
      </h1>
      <Link to="/app" className="text-ember underline-offset-4 hover:underline">
        Back to the screening room
      </Link>
    </div>
  )
}
