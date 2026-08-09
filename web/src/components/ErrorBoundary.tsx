import { Component, type ErrorInfo, type ReactNode } from 'react'

/* Without this, one undefined access anywhere in the tree blanks the whole
   app to white with no message and no way back. On a self-hosted app, where
   the person running it is also the person supporting it, that turns every
   small frontend bug into "the site is down".
 *
 * A class component because getDerivedStateFromError has no hook form. */
export class ErrorBoundary extends Component<
  { children: ReactNode; label?: string },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // The console is the only place this can go on a self-hosted instance
    // with no error reporting service wired up.
    console.error('render failed', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div className="mx-auto max-w-lg py-16">
        <p className="wd-eyebrow text-danger">Something broke</p>
        <h1 className="mt-3 font-display text-2xl font-semibold uppercase tracking-[0.02em]">
          {this.props.label ?? 'This page'} could not be drawn
        </h1>
        <p className="mt-3 text-sm text-muted">
          The rest of the app is still fine. Going back or reloading usually clears it.
        </p>
        <pre className="wd-scroller mt-4 max-h-40 overflow-auto rounded-[6px] border border-line bg-panel p-3 font-mono text-[11px] break-all whitespace-pre-wrap text-muted">
          {error.message || String(error)}
        </pre>
        <div className="mt-5 flex flex-wrap gap-3">
          <button
            onClick={() => this.setState({ error: null })}
            className="rounded-[4px] bg-ember px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-ember/90"
          >
            Try again
          </button>
          <button
            onClick={() => window.location.reload()}
            className="rounded-[4px] border border-line px-4 py-2 text-sm text-muted transition-colors hover:border-ember hover:text-ember"
          >
            Reload
          </button>
        </div>
      </div>
    )
  }
}
