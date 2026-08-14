// The marketing page. Not part of the self-hosted build and not routed by
// src/router.tsx: a private instance for one household has no use for a page
// that sells the product to strangers, and serving one means every visitor
// lands on an advert before they can reach their own app.
//
// Kept here, and kept building, because it is the page the hosted site will
// use. When that exists it should be a separate static site rather than a
// route inside this SPA, so a crawler sees real HTML instead of an empty div.
import { useEffect, useState } from 'react'
import { MotionConfig, motion, useReducedMotion } from 'motion/react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'
import { Attribution } from '../components/Attribution'
import { BeamMark, Wordmark } from '../components/Wordmark'
import { Atmosphere, Hairline } from '../components/Atmosphere'
import { Counter } from './parts/Counter'
import { DeviceFrame } from './parts/DeviceFrame'
import { ExploreDemo } from './parts/ExploreDemo'

type Showcase = {
  posters: string[]
  titles: number
  services: number
  countries: number
}

const OUT = [0.22, 1, 0.36, 1] as const
const VIEW = { once: true, amount: 0.15 } as const

function useShowcase() {
  return useQuery({
    queryKey: ['showcase'],
    queryFn: () => api.get<Showcase>('/api/public/showcase'),
    staleTime: 60 * 60_000,
    retry: false,
  })
}

/* The heading face carries the page now that every panel is gone: Big
   Shoulders set tall and condensed, like a marquee letterboard. */
const DISPLAY = 'uppercase font-semibold tracking-[0.01em] leading-[0.92]'

function Header() {
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header
      className={clsx(
        'sticky top-0 z-30 transition-colors duration-300',
        // A class toggle, never a tween on backdrop-filter, which would
        // repaint the whole viewport every frame.
        scrolled && 'bg-ink/70 backdrop-blur-xl',
      )}
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-2.5">
          <BeamMark className="h-7 w-7" />
          <Wordmark className="text-xl" />
        </div>
        <nav className="hidden items-center gap-8 text-sm text-muted md:flex">
          <a href="#product" className="transition-colors hover:text-fg">
            Recommendations
          </a>
          <a href="#together" className="transition-colors hover:text-fg">
            Watch nights
          </a>
          <a href="#cinema" className="transition-colors hover:text-fg">
            Cinemas
          </a>
          <a href="#free" className="transition-colors hover:text-fg">
            Free
          </a>
          <a href="#install" className="transition-colors hover:text-fg">
            Self-hosted
          </a>
        </nav>
        <div className="flex items-center gap-3">
          <Link to="/app" className="hidden text-sm text-muted transition-colors hover:text-fg sm:block">
            Sign in
          </Link>
          <Link
            to="/app"
            className="rounded-[4px] bg-ember px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-ember/90"
          >
            Open Roundtable
          </Link>
        </div>
      </div>
      {scrolled && <Hairline />}
    </header>
  )
}

/* The h1, one line per span so each can rise out of its own clip. Two lines
   only, so it stays a gesture rather than an effect. */
function Rise({ children, delay = 0 }: { children: string; delay?: number }) {
  const still = useReducedMotion()
  // Reduced motion gets the words with no gesture at all, rather than a
  // damped one: the point is stillness, not slower movement.
  if (still) return <span className="block">{children}</span>
  /* The old version rose out of an overflow-hidden clip, which meant the
     headline was invisible until the animation ran. Anything that stalls
     frames, a background tab or a throttled renderer, left the most
     important sentence on the page hidden. It rises a short distance with
     no clip now, so the worst case is a headline sitting a few pixels low
     rather than one that is not there. */
  return (
    <span className="block">
      <motion.span
        initial={{ y: 18 }}
        animate={{ y: 0 }}
        transition={{ duration: 0.6, delay, ease: OUT }}
        className="block"
      >
        {children}
      </motion.span>
    </span>
  )
}

type Row = {
  id?: string
  kicker: string
  title: string
  body: string
  shot: string
  label: string
  points?: string[]
}

const ROWS: Row[] = [
  {
    id: 'product',
    kicker: 'The engine',
    title: 'It learns from every click',
    body: 'Opening a title, saving it, rating it, clicking through to play it: all of it feeds one taste vector per person. Shelves are re-ranked for quality, popularity and how recent something is, then spread across genres so you do not end up in a corridor of the same four films.',
    shot: '/shots/home.webp',
    label: 'roundtable.local / home',
    points: ['Picked for you', 'Next up in a franchise you started', 'Because you follow someone in it'],
  },
  {
    id: 'together',
    kicker: 'Everyone in the room',
    title: 'A watch night you all create',
    body: 'Invite two people or five. Everyone who accepts suggests into the same queue and votes on it. The suggestions are blended from all of your tastes, with a dial for who leans hardest tonight. Whatever wins lands in every history at once. A while later you are each asked what you thought, so the next set knows how the evening went.',
    shot: '/shots/night.webp',
    label: 'roundtable.local / nights',
  },
  {
    id: 'cinema',
    kicker: 'Out of the house',
    title: 'Never miss a premiere again',
    body: 'Put a film on the cinema list and Roundtable follows its theatrical date for where you actually are, whether that is Cairo or Chicago, then sends one notification the morning it opens, in time to book. One alert per film. No countdown, no daily nagging.',
    shot: '/shots/cinema.webp',
    label: 'roundtable.local / cinema',
  },
  {
    kicker: 'Before you press play',
    title: 'Skip the extra checks',
    body: 'Five categories, each with a severity other viewers voted on and itemised entries describing what happens and roughly where, with spoilers folded away until you ask for them. Enough to decide before you press play, rather than twenty minutes in. Off by default, and set per profile.',
    shot: '/shots/guide.webp',
    label: 'roundtable.local / title',
  },
  {
    kicker: 'The receipts',
    title: 'A year worth posting',
    body: 'Hours, titles, how you rate, your longest daily streak, and your top genres, directors and actors. At the end of it there are four cards drawn from your own year, posters and faces and all, sized for a story. You see them before you save them. Export the raw numbers as CSV or JSON whenever you like, because it is your history and it leaves when you do.',
    shot: '/shots/cards.webp',
    label: 'roundtable.local / stats',
  },
]

function FeatureRow({ row, index }: { row: Row; index: number }) {
  // Alternating sides, and the copy enters from the side it lives on.
  const shotRight = index % 2 === 0
  return (
    <section
      id={row.id}
      className="relative mx-auto max-w-6xl scroll-mt-20 px-6 py-14 md:py-20"
    >
      <div
        className={clsx(
          'grid items-center gap-10 lg:grid-cols-2 lg:gap-16',
          !shotRight && 'lg:[&>*:first-child]:order-2',
        )}
      >
        <motion.div
          initial={{ x: shotRight ? -18 : 18 }}
          whileInView={{ x: 0 }}
          viewport={VIEW}
          transition={{ duration: 0.4, ease: OUT }}
          className="min-w-0"
        >
          <p className="wd-eyebrow wd-eyebrow--ember">{row.kicker}</p>
          <h2 className={`mt-4 font-display text-4xl md:text-5xl ${DISPLAY}`}>
            {row.title}
          </h2>
          <p className="mt-5 max-w-lg text-[15px] leading-[1.7] text-muted">{row.body}</p>
          {row.points && (
            <ul className="mt-6 flex flex-col gap-2.5">
              {row.points.map((point, i) => (
                <motion.li
                  key={point}
                  initial={{ opacity: 0, x: -8 }}
                  whileInView={{ x: 0 }}
                  viewport={VIEW}
                  transition={{ delay: 0.1 + i * 0.06, duration: 0.4 }}
                  className="flex items-center gap-3 font-mono text-[13px] text-fg/80"
                >
                  <span aria-hidden className="h-px w-6 shrink-0 bg-ember" />
                  {point}
                </motion.li>
              ))}
            </ul>
          )}
        </motion.div>

        <DeviceFrame
          src={row.shot}
          alt={row.title}
          label={row.label}
          parallax={24}
          className="min-w-0"
        />
      </div>
    </section>
  )
}

function Prose({
  id,
  kicker,
  title,
  children,
  wide = false,
}: {
  id?: string
  kicker: string
  title: string
  children: React.ReactNode
  wide?: boolean
}) {
  return (
    <section
      id={id}
      className={clsx(
        'relative mx-auto scroll-mt-20 px-6 py-14 md:py-20',
        wide ? 'max-w-6xl' : 'max-w-3xl',
      )}
    >
      <motion.div
        initial={{ y: 14 }}
        whileInView={{ y: 0 }}
        viewport={VIEW}
        transition={{ duration: 0.4, ease: OUT }}
      >
        <p className="wd-eyebrow wd-eyebrow--ember">{kicker}</p>
        <h2 className={`mt-4 font-display text-4xl md:text-5xl ${DISPLAY}`}>
          {title}
        </h2>
        <div className="mt-5 text-[15px] leading-[1.7] text-muted">{children}</div>
      </motion.div>
    </section>
  )
}

const REST = [
  {
    term: 'Follow people',
    detail:
      'Follow an actor or a director and their new work turns up in New, and weighs on your suggestions.',
  },
  {
    term: 'Availability by country',
    detail:
      'See what is streaming where you actually are, and add as many countries as you split your time between.',
  },
  {
    term: 'Passkey or password',
    detail: 'Sign in with either, or both, and switch either one off.',
  },
  {
    term: 'One search box',
    detail:
      'Titles and the people in them, in the same set of results, from any page. Press the slash key.',
  },
  {
    term: 'A feed, and messages',
    detail:
      "Post about what you watched, reply, share someone else's post with your own take, and write to a friend directly.",
  },
  {
    term: 'Bring your history',
    detail:
      'Import years of Netflix history from their own CSV, review what matched before it lands, then carry on.',
  },
  {
    term: 'Audit logged',
    detail:
      'Every action is recorded in plain words, and everything you own comes back out as CSV or JSON.',
  },
]

export function Landing() {
  const { data } = useShowcase()

  return (
    <MotionConfig reducedMotion="user">
      <div className="wd-landing relative isolate min-h-screen overflow-x-clip bg-ink text-fg">
        <Atmosphere />
        <Header />

        {/* Hero: the only centred thing on the page. Everything below is left
            aligned, which is what stops it reading as a template. */}
        <section className="relative mx-auto max-w-6xl px-6 pt-16 pb-12 text-center md:pt-24">
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8 }}
            className="wd-eyebrow wd-eyebrow--ember justify-center"
          >
            Free &middot; Self-hosted &middot; Film and series discovery
          </motion.p>
          <h1
            className={`mx-auto mt-6 max-w-3xl font-display text-[clamp(2.75rem,7vw,5.5rem)] ${DISPLAY}`}
          >
            <Rise delay={0.1}>Stop scrolling.</Rise>
            <Rise delay={0.18}>Start watching.</Rise>
          </h1>
          <motion.p
            initial={{ y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35, duration: 0.7, ease: OUT }}
            className="mx-auto mt-7 max-w-2xl text-lg leading-[1.7] text-muted"
          >
            Roundtable learns your taste from what you actually do, tells you which of your
            services has it in your country, warns you the morning a film opens in your
            cinemas, and settles what to put on when there are two of you. Free, on your own
            machine.
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.45, duration: 0.6, ease: OUT }}
            className="mt-9 flex flex-wrap items-center justify-center gap-3"
          >
            <Link
              to="/app"
              className="rounded-[4px] bg-ember px-8 py-3.5 font-medium text-ink transition-colors hover:bg-ember/90"
            >
              Open Roundtable
            </Link>
            <a
              href="#product"
              className="rounded-[4px] border border-line px-6 py-3.5 text-sm text-muted transition-colors hover:border-ember hover:text-ember"
            >
              See it working
            </a>
          </motion.div>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.6, duration: 0.6 }}
            className="mt-6 font-mono text-[11px] text-muted"
          >
            Your server. Your keys. Passkey or password.
          </motion.p>
        </section>

        {/* The hero shot, tilted and settling flat. */}
        <div className="relative mx-auto max-w-[1180px] px-6">
          <DeviceFrame
            src="/shots/home.webp"
            alt="The Roundtable home page, with a hero carousel and shelves of suggestions"
            label="roundtable.local / home"
            priority
            tilt
          />
        </div>

        {/* Proof, from this instance rather than from a brochure. */}
        {data && data.titles > 0 && (
          <section className="mx-auto max-w-3xl px-6 py-16 text-center">
            <div className="grid grid-cols-3 gap-6">
              <Counter to={data.titles} label="titles indexed" />
              <Counter to={data.countries} label="countries covered" />
              <Counter to={data.services} label="services tracked" />
            </div>
            <p className="mt-6 font-mono text-[11px] text-muted">
              Live from this instance, not from a brochure.
            </p>
          </section>
        )}

        {ROWS.slice(0, 1).map((row, i) => (
          <FeatureRow key={row.title} row={row} index={i} />
        ))}

        {/* The exploration setting, shown rather than claimed. */}
        <section className="relative mx-auto max-w-6xl px-6 py-14 md:py-20">
          <motion.div
            initial={{ y: 14 }}
            whileInView={{ y: 0 }}
            viewport={VIEW}
            transition={{ duration: 0.4, ease: OUT }}
          >
            <p className="wd-eyebrow wd-eyebrow--ember">Not a bubble</p>
            <h2 className={`mt-4 max-w-2xl font-display text-4xl md:text-5xl ${DISPLAY}`}>
              You control the variety
            </h2>
            <p className="mt-5 max-w-2xl text-[15px] leading-[1.7] text-muted">
              Comfort keeps close to what you already like. Balanced is the default. Bold pulls
              about a third of every shelf from outside your cluster, chosen from things well
              enough liked to be a fair bet. It is a setting you can see and change, not a
              hidden dial someone else turns.
            </p>
          </motion.div>
          <div className="mt-10">
            <ExploreDemo posters={data?.posters ?? []} />
          </div>
        </section>

        <Prose kicker="Just ask" title="An assistant that researches, not one that guesses">
          <p>
            Ask for everything connected to The Nun and it resolves the franchise, searches
            the web, reads what it finds, and checks every film it intends to name against
            the database before it answers, in order, with one press to save the whole run
            as a list. The trace above the answer is the real sequence of tool calls, shown
            as they happen, and when it cannot ground an answer it says so rather than
            dressing up a guess.
          </p>
          <p className="mt-4">
            It knows your history too, so the answer includes what you have already seen.
            And it ships an MCP server, so your own AI assistant can use it: ask Claude
            what to watch tonight and the answer comes from your taste rather than from
            the internet's.
          </p>
        </Prose>

        {ROWS.slice(1).map((row, i) => (
          <FeatureRow key={row.title} row={row} index={i + 1} />
        ))}

        <Prose
          kicker="Not just Hollywood's internet"
          title="Works where you live"
        >
          <p>
            Streaming lookups that know Shahid and OSN, not only Netflix. Cinema listings for
            the city you are actually in. Add every country you split your time between and
            see availability for all of them at once, with the age rating from the one you
            call home.
          </p>
          <p className="mt-4">
            The big tools serve three markets properly. This one serves yours.
          </p>
        </Prose>

        <Prose id="free" kicker="No catch" title="Free, actually">
          <p>
            Roundtable is free. Not free until funding, not free with your data. It is free
            because it was built for one household and it costs nothing extra when you run it
            on your own machine.
          </p>
          <p className="mt-4">
            If it earns a place in your Friday nights you can donate, and donors get API
            access as a thank you. That is the whole business model.
          </p>
        </Prose>

        <Prose kicker="The itch" title="Built because I needed it">
          <p>
            Five streaming subscriptions and still nothing to watch. Films opening and leaving
            the cinemas here before I heard about them. Where to watch it in one app, what it
            is rated in another, my list in a third, and none of them working properly in my
            country.
          </p>
          <p className="mt-4">
            So this is the one I wanted. It is free, it runs on your own hardware, and it gets
            better every evening you use it.
          </p>
          <p className="mt-5 font-display text-lg text-fg">Mohamed</p>
        </Prose>

        {/* Where the six squares used to be: hairlines that draw themselves
            in, and nothing else. */}
        <section id="yours" className="relative mx-auto max-w-6xl scroll-mt-20 px-6 py-14 md:py-20">
          <motion.div
            initial={{ y: 14 }}
            whileInView={{ y: 0 }}
            viewport={VIEW}
            transition={{ duration: 0.4, ease: OUT }}
          >
            <p className="wd-eyebrow wd-eyebrow--ember">Also in the box</p>
            <h2 className={`mt-4 font-display text-4xl md:text-5xl ${DISPLAY}`}>
              The rest of it
            </h2>
          </motion.div>

          <dl className="mt-12">
            {REST.map((item, i) => (
              <div key={item.term}>
                <motion.div
                  aria-hidden
                  initial={{ scaleX: 0 }}
                  whileInView={{ scaleX: 1 }}
                  viewport={{ once: true, amount: 0.8 }}
                  transition={{ delay: i * 0.05, duration: 0.6, ease: OUT }}
                  style={{ originX: 0 }}
                  className="h-px w-full bg-line"
                />
                <motion.div
                  initial={{ y: 10 }}
                  whileInView={{ y: 0 }}
                  viewport={{ once: true, amount: 0.8 }}
                  transition={{ delay: i * 0.05 + 0.1, duration: 0.5, ease: OUT }}
                  className="grid gap-2 py-6 md:grid-cols-[minmax(0,18rem)_1fr] md:gap-10"
                >
                  <dt className="font-display text-lg font-semibold uppercase tracking-[0.02em]">
                    {item.term}
                  </dt>
                  <dd className="max-w-2xl text-[15px] leading-[1.7] text-muted">
                    {item.detail}
                  </dd>
                </motion.div>
              </div>
            ))}
          </dl>
        </section>

        <Prose id="install" kicker="Up in one command" title="It runs on your machine">
          <p>
            One compose file, a free TMDB key and a browser. It is happy on a small box in a
            cupboard.
          </p>
          <pre className="wd-scroller wd-plate mt-5 overflow-x-auto p-4 font-mono text-sm text-fg">
            <code>{'git clone https://github.com/1ordo/roundtable\ncd roundtable\ndocker compose up -d'}</code>
          </pre>
          <div className="mt-5 flex flex-wrap gap-3">
            <a
              href="https://github.com/1ordo/roundtable"
              target="_blank"
              rel="noreferrer noopener"
              className="rounded-[4px] border border-line px-4 py-2 text-sm text-muted transition-colors hover:border-ember hover:text-ember"
            >
              GitHub
            </a>
            <a
              href="https://github.com/1ordo/roundtable#readme"
              target="_blank"
              rel="noreferrer noopener"
              className="rounded-[4px] border border-line px-4 py-2 text-sm text-muted transition-colors hover:border-ember hover:text-ember"
            >
              Install guide
            </a>
          </div>
          <p className="mt-6 text-sm">
            <span className="font-mono text-[10px] tracking-[0.2em] text-ember uppercase">
              Coming
            </span>{' '}
            a browser extension that logs what you watch automatically, phone apps, and a
            public API for donors first.
          </p>
        </Prose>

        {/* Close. No band, no border: the atmosphere carries it. */}
        <section className="relative mx-auto max-w-3xl px-6 py-24 text-center md:py-32">
          <motion.h2
            initial={{ y: 14 }}
            whileInView={{ y: 0 }}
            viewport={VIEW}
            transition={{ duration: 0.4, ease: OUT }}
            className={`font-display text-4xl md:text-5xl ${DISPLAY}`}
          >
            It gets better the evening you start
          </motion.h2>
          <motion.p
            initial={false}
            whileInView={{ opacity: 1 }}
            viewport={VIEW}
            transition={{ delay: 0.15, duration: 0.6 }}
            className="mx-auto mt-5 max-w-xl text-[15px] leading-[1.7] text-muted"
          >
            Import years of history in two files, or just start clicking. Either way the picks
            sharpen from the first night.
          </motion.p>
          <motion.div
            initial={false}
            whileInView={{ opacity: 1 }}
            viewport={VIEW}
            transition={{ delay: 0.25, duration: 0.6 }}
          >
            <Link
              to="/app"
              className="mt-9 inline-block rounded-[4px] bg-ember px-8 py-3.5 font-medium text-ink transition-colors hover:bg-ember/90"
            >
              Open Roundtable
            </Link>
          </motion.div>
        </section>

        <footer className="relative mx-auto max-w-6xl px-6 pb-12">
          <Hairline />
          <div className="flex flex-wrap items-start justify-between gap-6 pt-8">
            <div>
              <div className="flex items-center gap-2">
                <BeamMark className="h-5 w-5" />
                <span className="font-display text-sm font-semibold uppercase tracking-[0.02em]">
                  Roundtable
                </span>
              </div>
              <p className="mt-2 font-mono text-[11px] text-muted">
                Free, and runs on your own hardware.
              </p>
              <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
                <a
                  href="https://github.com/1ordo/roundtable"
                  target="_blank"
                  rel="noreferrer noopener"
                  className="transition-colors hover:text-ember"
                >
                  GitHub
                </a>
                <a
                  href="https://github.com/1ordo/roundtable#readme"
                  target="_blank"
                  rel="noreferrer noopener"
                  className="transition-colors hover:text-ember"
                >
                  Docs
                </a>
                <a href="#free" className="transition-colors hover:text-ember">
                  Why it is free
                </a>
                <Link to="/legal/privacy" className="transition-colors hover:text-ember">
                  Privacy
                </Link>
                <Link to="/legal/terms" className="transition-colors hover:text-ember">
                  Terms
                </Link>
              </div>
            </div>
            <Attribution className="max-w-md" />
          </div>
        </footer>
      </div>
    </MotionConfig>
  )
}
