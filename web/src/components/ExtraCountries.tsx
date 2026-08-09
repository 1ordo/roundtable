import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'
import { useUpdateProfile } from '../api/tracking'
import { useMe } from '../app/useMe'

type CountryOption = { code: string; name: string }

function flag(code: string): string {
  return code
    .toUpperCase()
    .replace(/./g, (char) => String.fromCodePoint(127397 + char.charCodeAt(0)))
}

/* Countries beyond the main one. Availability, cinema listings and release
   alerts all widen to cover these; the main country still decides which age
   rating is shown, because that has to be one answer. */
export function ExtraCountries() {
  const { data: me } = useMe()
  const update = useUpdateProfile()
  const [term, setTerm] = useState('')
  const { data: countries } = useQuery({
    queryKey: ['countries'],
    queryFn: () => api.get<CountryOption[]>('/api/countries'),
    staleTime: 24 * 60 * 60_000,
  })

  const main = me?.user?.country_code ?? null
  const extras = (me?.user?.prefs?.countries as string[] | undefined) ?? []

  const byCode = useMemo(
    () => new Map((countries ?? []).map((c) => [c.code, c.name])),
    [countries],
  )

  const results = useMemo(() => {
    const needle = term.trim().toLowerCase()
    if (!countries || needle.length < 1) return []
    return countries
      .filter(
        (c) =>
          c.code !== main &&
          !extras.includes(c.code) &&
          (c.name.toLowerCase().includes(needle) || c.code.toLowerCase() === needle),
      )
      .slice(0, 8)
  }, [countries, term, main, extras])

  function add(code: string) {
    update.mutate({ countries: [...extras, code] })
    setTerm('')
  }

  function remove(code: string) {
    update.mutate({ countries: extras.filter((c) => c !== code) })
  }

  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Anywhere else</h2>
      <p className="mt-1 text-sm text-muted">
        Add every country you actually watch in. Streaming availability, cinema listings and
        release alerts cover all of them. Your main country still decides which age rating is
        shown.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        {main && (
          <span className="flex items-center gap-2 rounded-full border border-ember/50 bg-ember/10 px-3 py-1.5 text-sm text-ember">
            <span aria-hidden>{flag(main)}</span>
            {byCode.get(main) ?? main}
            <span className="font-mono text-[10px] text-muted">main</span>
          </span>
        )}
        <AnimatePresence initial={false}>
          {extras.map((code) => (
            <motion.button
              key={code}
              layout
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.2 }}
              onClick={() => remove(code)}
              className="flex items-center gap-2 rounded-full border border-line px-3 py-1.5 text-sm transition-colors hover:border-danger hover:text-danger"
            >
              <span aria-hidden>{flag(code)}</span>
              {byCode.get(code) ?? code}
              <span aria-hidden className="text-muted">
                ×
              </span>
              <span className="sr-only">Remove {byCode.get(code) ?? code}</span>
            </motion.button>
          ))}
        </AnimatePresence>
      </div>

      <input
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        placeholder="Add a country"
        className="mt-3 w-full rounded-[4px] border border-line bg-panel px-4 py-2.5 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
      />

      {results.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1">
          {results.map((country) => (
            <li key={country.code}>
              <button
                onClick={() => add(country.code)}
                className={clsx(
                  'flex w-full items-center gap-2.5 rounded-[4px] px-3 py-2 text-left text-sm',
                  'transition-colors hover:bg-panel-2',
                )}
              >
                <span aria-hidden>{flag(country.code)}</span>
                <span className="min-w-0 flex-1 truncate">{country.name}</span>
                <span className="font-mono text-[11px] text-muted">{country.code}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
