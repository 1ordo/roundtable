import { useEffect, useRef, useState } from 'react'
import { motion } from 'motion/react'
import clsx from 'clsx'
import { currentCsrf } from '../api/client'
import type { TitleCard } from '../api/catalog'
import { PosterCard } from '../components/PosterCard'
import { ChatTrace, type Considered, type Step } from '../components/ChatTrace'
import { BeamMark } from '../components/Wordmark'

type Turn = {
  role: 'user' | 'assistant'
  content: string
  results?: TitleCard[]
  steps?: Step[]
  considered?: Considered[]
}

const OPENERS = [
  'Something tense and smart, under two hours',
  'A comfort film for a bad day',
  'Arabic cinema I have probably not seen',
  'What should we watch together tonight?',
]

export function Chat() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [running, setRunning] = useState(false)
  // Two lists: what has arrived, and what has been shown. The server
  // finishes the early steps in milliseconds, so revealing them the instant
  // they land makes four lines flash past as one. The queue drips them out
  // instead, which is the only way the trace is actually readable.
  const [arrived, setArrived] = useState<Step[]>([])
  const [steps, setSteps] = useState<Step[]>([])
  const [considered, setConsidered] = useState<Considered[]>([])
  const [error, setError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)
  // Read inside the stream loop, which closes over the first render's state.
  const stepsShownRef = useRef(0)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [turns.length, steps.length, running])

  /* Reveal one step at a time. The pace is deliberate rather than tied to
     how fast the work happened: a step that took 4ms still needs long
     enough on screen to read. */
  useEffect(() => {
    if (steps.length >= arrived.length) return
    const gap = steps.length === 0 ? 250 : 900
    const timer = setTimeout(() => {
      setSteps(arrived.slice(0, steps.length + 1))
    }, gap)
    return () => clearTimeout(timer)
  }, [arrived, steps])

  /* Server-sent events rather than one request that returns at the end, so
     the trace above the answer is the real sequence of work and not a
     loading animation. Read by hand rather than with EventSource because
     this is a POST with a CSRF header and a body. */
  async function send(message: string) {
    const text = message.trim()
    if (!text || running) return
    const history = turns.map(({ role, content }) => ({ role, content }))
    setTurns((current) => [...current, { role: 'user', content: text }])
    setInput('')
    setArrived([])
    setSteps([])
    setConsidered([])
    setError(null)
    setRunning(true)

    const collected: Step[] = []
    let shortlist: Considered[] = []

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': currentCsrf() ?? '' },
        credentials: 'same-origin',
        body: JSON.stringify({ message: text, history }),
      })
      if (!response.ok || !response.body) throw new Error(String(response.status))

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        // Events are separated by a blank line; a chunk can split one.
        const chunks = buffer.split('\n\n')
        buffer = chunks.pop() ?? ''
        for (const chunk of chunks) {
          const line = chunk.trim()
          if (!line.startsWith('data:')) continue
          const event = JSON.parse(line.slice(5).trim())
          if (event.type === 'step') {
            collected.push(event)
            setArrived([...collected])
          } else if (event.type === 'candidates') {
            shortlist = event.titles
            setConsidered(shortlist)
          } else if (event.type === 'done') {
            // Hold the answer back until the trace has finished playing, or
            // the reply lands on top of steps still appearing beneath it.
            const remaining = Math.max(0, collected.length - stepsShownRef.current) * 900
            await new Promise((resolve) => setTimeout(resolve, remaining))
            setTurns((current) => [
              ...current,
              {
                role: 'assistant',
                content: event.reply,
                results: event.results,
                steps: [...collected],
                considered: shortlist,
              },
            ])
          } else if (event.type === 'error') {
            setError(event.detail)
          }
        }
      }
    } catch {
      setError('connection lost')
    } finally {
      setRunning(false)
      setArrived([])
      setSteps([])
      setConsidered([])
    }
  }

  useEffect(() => {
    stepsShownRef.current = steps.length
  }, [steps])

  const disabled = error === 'ai_disabled'

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-3xl flex-col">
      <header className="flex items-start gap-3">
        <BeamMark className="mt-1.5 h-7 w-7" />
        <div>
          <p className="wd-eyebrow wd-eyebrow--nitrate">Tonight</p>
          <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
            Ask
          </h1>
          <p className="mt-2 max-w-xl text-sm text-muted">
            It knows your lists, your history, and the whole catalog.
          </p>
        </div>
      </header>

      {turns.length === 0 && (
        <div className="mt-10">
          <p className="wd-eyebrow">Try one</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {OPENERS.map((opener) => (
              <motion.button
                key={opener}
                whileTap={{ scale: 0.97 }}
                onClick={() => send(opener)}
                className="rounded-full border border-line bg-panel px-4 py-2 text-sm text-muted transition-colors hover:border-nitrate hover:text-nitrate"
              >
                {opener}
              </motion.button>
            ))}
          </div>
        </div>
      )}

      <div className="mt-8 flex flex-1 flex-col gap-6">
        {turns.map((turn, index) => (
          <motion.div
            key={index}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            className={clsx('min-w-0', turn.role === 'user' && 'flex justify-end')}
          >
            {turn.role === 'user' ? (
              <p className="max-w-lg rounded-lg rounded-br-sm bg-ember px-4 py-2.5 text-ink">
                {turn.content}
              </p>
            ) : (
              <div className="min-w-0">
                {turn.steps && turn.steps.length > 0 && (
                  <div className="mb-3 max-w-xl">
                    <ChatTrace
                      steps={turn.steps}
                      considered={turn.considered ?? []}
                      running={false}
                      collapsible
                    />
                  </div>
                )}
                <p className="wd-plate max-w-xl px-4 py-3 leading-relaxed whitespace-pre-wrap">
                  {turn.content}
                </p>
                {turn.results && turn.results.length > 0 && (
                  <div className="wd-scroller mt-4 flex gap-4 pb-3">
                    {turn.results.map((title, i) => (
                      <PosterCard
                        key={`${title.type}-${title.tmdb_id}`}
                        title={title}
                        index={i}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}
          </motion.div>
        ))}

        {running && (
          <div className="max-w-xl">
            <ChatTrace steps={steps} considered={considered} running />
          </div>
        )}

        {disabled && (
          <p className="wd-plate px-4 py-3 text-sm text-muted">
            AI features are turned off. An admin can enable them under Admin, AI settings.
          </p>
        )}
        {error && !disabled && (
          <p className="rounded-md border border-danger/40 bg-danger/5 px-4 py-3 text-sm text-danger">
            {/* The actual reason. An empty reply from a free model and a
                missing API key are different problems and need different
                fixes. */}
            The assistant stopped: {error}
          </p>
        )}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          send(input)
        }}
        className="sticky bottom-0 mt-8 flex gap-2 bg-ink py-4"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="What are you in the mood for?"
          className="min-w-0 flex-1 rounded-[4px] border border-line bg-panel px-4 py-3 text-fg placeholder:text-muted focus:border-ember focus:outline-none"
        />
        <motion.button
          type="submit"
          whileTap={{ scale: 0.97 }}
          disabled={!input.trim() || running}
          className="rounded-[4px] bg-ember px-5 py-3 font-medium text-ink transition-colors hover:bg-ember/90 disabled:opacity-40"
        >
          Send
        </motion.button>
      </form>
    </div>
  )
}
