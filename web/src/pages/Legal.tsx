import { motion } from 'motion/react'
import { Link, useParams } from 'react-router'
import { Atmosphere, Hairline } from '../components/Atmosphere'
import { BeamMark, Wordmark } from '../components/Wordmark'

const DISPLAY = 'uppercase font-semibold tracking-[0.01em] leading-[0.92]'

function H2({ children }: { children: React.ReactNode }) {
  return <h2 className={`mt-10 font-display text-2xl ${DISPLAY}`}>{children}</h2>
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="mt-4 text-[15px] leading-[1.75] text-muted">{children}</p>
}

function Points({ items }: { items: string[] }) {
  return (
    <ul className="mt-4 flex flex-col gap-2.5">
      {items.map((item) => (
        <li key={item} className="flex gap-3 text-[15px] leading-[1.7] text-muted">
          <span aria-hidden className="mt-2.5 h-1 w-1 shrink-0 rounded-full bg-ember" />
          <span className="min-w-0">{item}</span>
        </li>
      ))}
    </ul>
  )
}

/* Written for what this actually is: software you run yourself. Most of the
   usual clauses do not apply, and saying so plainly is more useful than
   pasting a template that talks about "our servers" when there are none. */
function Privacy() {
  return (
    <>
      <p className="mt-6 text-lg text-fg/90">
        Watchpile runs on a machine somebody chose to run it on. Whoever set it up holds the
        data. If that is you, nothing here leaves your hardware except the requests listed
        below.
      </p>

      <H2>What is stored, and where</H2>
      <P>
        Everything the app knows about you lives in the database on the machine running it:
        your account, what you have watched and rated, your lists, your posts and messages,
        your settings, and an audit log of actions taken on the account. There is no central
        Watchpile service, no analytics, no telemetry and no third-party trackers in the
        page.
      </P>

      <H2>What leaves the machine</H2>
      <P>
        The app talks to a small number of outside services to do its job. Each one receives
        only what that request needs, never your identity or your history.
      </P>
      <Points
        items={[
          'TMDB, for the catalog: titles, artwork, cast and where things are streaming. It sees the title being looked up, not who is looking.',
          'OMDb, optionally, for IMDb, Rotten Tomatoes and Metacritic scores.',
          'An AI provider, only if the operator turned the AI features on. It receives the question you asked and a shortlist of catalog titles. It is not sent your account, your history or anything you have written.',
          'An email or push provider, only if the operator configured one, and only for alerts you switched on.',
        ]}
      />
      <P>
        If the operator sets no keys beyond the catalog, nothing else is contacted at all.
        Recommendations are computed on the machine itself.
      </P>

      <H2>Who can see your things</H2>
      <P>
        You choose, per part of your profile. Public means anyone signed in to this
        instance. Friends means people whose friend request you accepted. Private means
        nobody but you. Nothing is ever visible to the open internet at any setting, and
        direct messages are only ever between two people who are friends.
      </P>
      <P>
        The person who runs the instance has database access, as anyone hosting anything
        does. They can see that accounts exist and can read the database directly. Trust the
        operator the way you would trust anyone hosting your files.
      </P>

      <H2>Getting it out, and getting rid of it</H2>
      <P>
        Everything you own exports as CSV or JSON from Settings, at any time, without asking
        anyone. Ask the operator to delete your account and the data goes with it: posts,
        messages, history, lists and all.
      </P>

      <H2>Cookies</H2>
      <P>
        One, holding your session so you stay signed in. It is not used for tracking and
        there is nothing to consent to.
      </P>

      <H2>Children</H2>
      <P>
        The parents guide exists because households have children in them. The app is not
        designed for children to hold their own accounts, and the operator decides who gets
        one.
      </P>
    </>
  )
}

function Terms() {
  return (
    <>
      <p className="mt-6 text-lg text-fg/90">
        Watchpile is free software you run yourself. This copy is operated by whoever
        set it up, and you have no account with anyone else.
      </p>

      <H2>The software</H2>
      <P>
        Watchpile is released under the GNU Affero General Public License, version 3.
        You may run it, change it and share it, and if you offer a modified version to
        other people over a network you have to publish your changes too. The name and
        the logo are not covered by that licence. It comes with no warranty of any kind:
        if it loses your watch history, misses a cinema date or recommends something
        dreadful, that is on you and on me equally, which is to say nobody is liable.
      </P>

      <H2>Cost</H2>
      <P>
        The software is free, and stays free: that is what the licence means, and it is
        not a promise anyone can quietly withdraw. Running it costs whatever your server
        and your own API keys cost, which is a matter between you and them.
      </P>

      <H2>Your instance</H2>
      <P>
        Whoever runs the instance sets its rules: who may register, what is acceptable to
        post, and whether an account stays. They can remove content or accounts on their own
        machine. Take that up with them rather than with the project.
      </P>

      <H2>What you post</H2>
      <P>
        Your posts, comments, quotes and messages stay yours. Posting them here grants the
        instance nothing beyond showing them to the people you chose. Do not post anything
        you do not have the right to post, and do not use the messages to harass anyone.
      </P>

      <H2>Catalog data</H2>
      <P>
        Film and series information comes from TMDB, and scores from OMDb. This product uses
        the TMDB API but is not endorsed or certified by TMDB. Their terms govern that data,
        and it is provided here for personal use.
      </P>

      <H2>The AI features</H2>
      <P>
        Ask, the content advisories and the quote suggestions are generated by a language
        model. They are labelled as estimates where they are estimates, because they can be
        wrong. Do not treat an advisory as a substitute for checking something yourself when
        it matters.
      </P>

      <H2>Changes</H2>
      <P>
        This document lives in the repository with the code. When it changes, the change is
        in the history along with everything else.
      </P>
    </>
  )
}

export function Legal() {
  const { doc } = useParams()
  const privacy = doc !== 'terms'

  return (
    <div className="wd-landing relative isolate min-h-screen overflow-x-clip bg-ink text-fg">
      <Atmosphere />

      <header className="mx-auto flex max-w-3xl items-center justify-between px-6 py-6">
        <Link to="/" className="flex items-center gap-2.5">
          <BeamMark className="h-7 w-7" />
          <Wordmark className="text-xl" />
        </Link>
        <div className="flex gap-4 text-sm">
          <Link
            to="/legal/privacy"
            className={privacy ? 'text-ember' : 'text-muted transition-colors hover:text-fg'}
          >
            Privacy
          </Link>
          <Link
            to="/legal/terms"
            className={!privacy ? 'text-ember' : 'text-muted transition-colors hover:text-fg'}
          >
            Terms
          </Link>
        </div>
      </header>

      <motion.main
        key={privacy ? 'privacy' : 'terms'}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="mx-auto max-w-3xl px-6 pb-24"
      >
        <p className="wd-eyebrow wd-eyebrow--ember">
          {privacy ? 'What happens to your data' : 'The deal'}
        </p>
        <h1 className={`mt-1 font-display text-5xl ${DISPLAY}`}>
          {privacy ? 'Privacy' : 'Terms'}
        </h1>

        {privacy ? <Privacy /> : <Terms />}

        <Hairline className="mt-14" />
        <p className="mt-6 text-xs text-muted">
          Written in plain words on purpose. It describes how the software behaves, which you
          can check against the source rather than take on trust. If you are running an
          instance for other people, read it over and adjust it for your situation.
        </p>
        <Link
          to="/"
          className="mt-6 inline-block text-sm text-muted transition-colors hover:text-ember"
        >
          Back to the start
        </Link>
      </motion.main>
    </div>
  )
}
