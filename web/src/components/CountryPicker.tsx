import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'
import { Icon } from './Icon'

type CountryOption = { code: string; name: string }

// The ones most likely wanted here, offered before the long list.
const SUGGESTED = ['EG', 'MA', 'AE', 'SA', 'FR', 'GB', 'US']

function flag(code: string): string {
  // Regional indicator letters render the flag without shipping any images.
  return code
    .toUpperCase()
    .replace(/./g, (char) => String.fromCodePoint(127397 + char.charCodeAt(0)))
}

export function CountryPicker({
  value,
  onChange,
}: {
  value: string | null
  onChange: (code: string) => void
}) {
  const [term, setTerm] = useState('')
  const { data: countries } = useQuery({
    queryKey: ['countries'],
    queryFn: () => api.get<CountryOption[]>('/api/countries'),
    staleTime: 24 * 60 * 60_000,
  })

  const selected = countries?.find((c) => c.code === value)

  const results = useMemo(() => {
    if (!countries) return []
    const needle = term.trim().toLowerCase()
    if (!needle) {
      const suggested = SUGGESTED.map((code) => countries.find((c) => c.code === code)).filter(
        (c): c is CountryOption => Boolean(c),
      )
      // Keep the current choice visible even when it is not a suggestion.
      if (selected && !suggested.some((c) => c.code === selected.code)) {
        suggested.unshift(selected)
      }
      return suggested
    }
    return countries
      .filter(
        (c) =>
          c.name.toLowerCase().includes(needle) || c.code.toLowerCase() === needle,
      )
      .slice(0, 40)
  }, [countries, term, selected])

  return (
    <div>
      <div className="relative mt-4 max-w-sm">
        <span className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted">
          <Icon name="search" width={18} height={18} />
        </span>
        <input
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          placeholder={
            countries ? `Search ${countries.length} countries` : 'Loading countries'
          }
          className="w-full rounded-[4px] border border-line bg-panel py-2.5 pr-4 pl-10 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
        />
      </div>

      <p className="wd-eyebrow mt-3">
        {term.trim() ? `${results.length} matching` : 'Common choices'}
      </p>

      <div className="mt-2 flex flex-wrap gap-2">
        <AnimatePresence initial={false}>
          {results.map((country) => (
            <motion.button
              key={country.code}
              layout
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{ duration: 0.15 }}
              onClick={() => onChange(country.code)}
              aria-pressed={value === country.code}
              className={clsx(
                'flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm transition-colors',
                value === country.code
                  ? 'border-ember bg-ember/15 text-ember'
                  : 'border-line text-muted hover:text-fg',
              )}
            >
              <span aria-hidden>{flag(country.code)}</span>
              {country.name}
            </motion.button>
          ))}
        </AnimatePresence>
      </div>

      {term.trim() && results.length === 0 && (
        <p className="mt-3 text-sm text-muted">No country matches that.</p>
      )}
    </div>
  )
}
