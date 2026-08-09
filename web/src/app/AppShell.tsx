
import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { logout } from '../api/client'
import { useInbox } from '../api/notifications'
import { Attribution } from '../components/Attribution'
import { Icon, type IconName } from '../components/Icon'
import { LeaderBoot, useBootSequence } from '../components/LeaderBoot'
import { Onboarding } from '../components/Onboarding'
import { BeamMark, Wordmark } from '../components/Wordmark'
import { useMe } from './useMe'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { ExpenseNudge } from '../components/ExpenseNudge'
import { SearchBar, SearchOverlay } from '../components/SearchOverlay'
import { BrowserAlertsWatcher } from '../components/BrowserAlerts'

type NavEntry = { to: string; label: string; icon: IconName; end?: boolean }

// The phone bottom bar: five destinations, one thumb.
const MOBILE_TABS: NavEntry[] = [
  { to: '/app', label: 'Home', icon: 'home', end: true },
  { to: '/app/browse', label: 'Browse', icon: 'browse' },
  { to: '/app/ask', label: 'Ask', icon: 'sparkle' },
  { to: '/app/new', label: 'New', icon: 'bell' },
  { to: '/app/lists', label: 'Lists', icon: 'lists' },
]

/* The sidebar reads like a programme: what's on tonight, what there is
   to explore, who you watch with, and what you keep. */
const NAV_SECTIONS: { label: string; items: NavEntry[] }[] = [
  {
    label: 'Tonight',
    items: [
      { to: '/app', label: 'Home', icon: 'home', end: true },
      { to: '/app/ask', label: 'Ask', icon: 'sparkle' },
      { to: '/app/night', label: 'Watch night', icon: 'night' },
      { to: '/app/cinema', label: 'In cinemas', icon: 'cinema' },
      { to: '/app/new', label: 'New arrivals', icon: 'bell' },
    ],
  },
  {
    label: 'Explore',
    items: [
      { to: '/app/browse', label: 'Browse', icon: 'browse', end: true },
      { to: '/app/browse/movie', label: 'Films', icon: 'film' },
      { to: '/app/browse/tv', label: 'Series', icon: 'series' },
    ],
  },
  {
    label: 'Together',
    items: [
      { to: '/app/feed', label: 'Feed', icon: 'feed' },
      { to: '/app/friends', label: 'Friends', icon: 'friends' },
      { to: '/app/messages', label: 'Messages', icon: 'message' },
    ],
  },
  {
    label: 'Your shelf',
    items: [
      { to: '/app/lists', label: 'Lists', icon: 'lists' },
      { to: '/app/history', label: 'History', icon: 'history' },
      { to: '/app/stats', label: 'Stats', icon: 'stats' },
    ],
  },
]

function NotificationsNavItem() {
  const { data } = useInbox()
  const unread = data?.unread ?? 0
  return (
    <NavLink
      to="/app/notifications"
      className={({ isActive }) =>
        clsx(
          'relative flex items-center gap-3 rounded-[4px] px-3 py-1 text-sm transition-colors',
          isActive ? 'text-fg' : 'text-muted hover:text-fg',
        )
      }
    >
      <span className="relative">
        <Icon name="bell" />
        {unread > 0 && (
          <motion.span
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-ember px-1 font-mono text-[10px] font-medium text-ink"
          >
            {unread > 9 ? '9+' : unread}
          </motion.span>
        )}
      </span>
      <span>Notifications</span>
    </NavLink>
  )
}

function NavItem({ to, label, icon, end }: NavEntry) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        clsx(
          'group relative flex items-center gap-3 rounded-[4px] px-3 py-1 text-sm transition-colors',
          isActive ? 'text-fg' : 'text-muted hover:text-fg',
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <motion.span
              layoutId="nav-active"
              className="absolute inset-0 rounded-[4px] bg-panel-2"
              transition={{ type: 'spring', stiffness: 500, damping: 40 }}
            />
          )}
          <span className="relative"><Icon name={icon} /></span>
          <span className="relative">{label}</span>
          {/* The changeover cue: flashes twice when this becomes the
              running reel, then holds. Keyed so it replays per arrival. */}
          {isActive && (
            <span key={to} className="wd-cue relative ml-auto text-ember" aria-hidden />
          )}
        </>
      )}
    </NavLink>
  )
}

function NavSections() {
  return (
    <>
      {NAV_SECTIONS.map((section) => (
        <div key={section.label} className="mb-2">
          <p className="wd-eyebrow mb-1 px-3 !text-[9px]">{section.label}</p>
          <div className="flex flex-col gap-0.5">
            {section.items.map((item) => (
              <NavItem key={item.to} {...item} />
            ))}
          </div>
        </div>
      ))}
    </>
  )
}

export function AppShell() {
  const [searchOpen, setSearchOpen] = useState(false)
  const booting = useBootSequence()
  const [bootDone, setBootDone] = useState(!booting)

  /* Slash opens search, the way it does everywhere else. Ignored while a
     field already has focus, or typing a slash into a comment would open
     it instead of writing the character. */
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== '/' || event.metaKey || event.ctrlKey) return
      const target = event.target as HTMLElement | null
      const tag = target?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || target?.isContentEditable) return
      event.preventDefault()
      setSearchOpen(true)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  const { data: me } = useMe()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  // Pages with their own search field would show two.
  const hideSearchBar =
    location.pathname.startsWith('/app/search') || location.pathname.startsWith('/app/ask')
  const { data: inbox } = useInbox()
  const unread = inbox?.unread ?? 0
  const [menuOpen, setMenuOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)

  // Choosing a destination should close the drawer and the booth behind you.
  useEffect(() => {
    setMenuOpen(false)
    setProfileOpen(false)
  }, [location.pathname])

  async function handleLogout() {
    await logout()
    queryClient.setQueryData(['me'], null)
    navigate('/login')
  }

  const user = me?.user

  return (
    /* The sidebar is fixed, so the page is a plain block: making this a flex
       row gave main a min-width of auto, which let a wide poster row stretch
       the whole page instead of scrolling inside itself. */
    <div className="min-h-screen bg-ink">
      <AnimatePresence>
        {!bootDone && <LeaderBoot onDone={() => setBootDone(true)} />}
      </AnimatePresence>
      {me?.needs_onboarding && <Onboarding />}
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col overflow-y-auto border-r border-line bg-panel px-3 py-3 md:flex">
        <div className="mb-4 flex items-center gap-2.5 px-2">
          <BeamMark className="h-7 w-7" />
          <Wordmark className="text-lg" />
        </div>

        <nav className="flex-1">
          <NavSections />
        </nav>

        <div className="border-t border-line pt-2">
          {/* The booth lives behind your own face: press it and the room's
              controls slide up, choose one and they slide away. Keeps the
              programme above the fold on ordinary screens. */}
          <AnimatePresence initial={false}>
            {profileOpen && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                className="overflow-hidden"
              >
                <div className="flex flex-col gap-0.5 pb-1.5">
                  <p className="wd-eyebrow mb-1 px-3 !text-[9px]">The booth</p>
                  {/* Your own face goes to your own profile, the same as
                      everyone else's does. Settings when there is no handle
                      yet, since that is where you pick one. */}
                  <NavItem
                    to={user?.handle ? `/app/u/${user.handle}` : '/app/settings'}
                    label="Profile"
                    icon="friends"
                    end
                  />
                  <NotificationsNavItem />
                  <NavItem to="/app/settings" label="Settings" icon="settings" />
                  {user?.role === 'admin' && (
                    <>
                      <NavItem to="/app/status" label="Status" icon="admin" />
                      <NavItem to="/app/admin" label="Admin" icon="admin" />
                    </>
                  )}
                  <button
                    onClick={handleLogout}
                    className="flex items-center gap-3 rounded-[4px] px-3 py-1 text-sm text-muted transition-colors hover:text-fg"
                  >
                    <Icon name="logout" />
                    Sign out
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <button
            onClick={() => setProfileOpen((open) => !open)}
            aria-expanded={profileOpen}
            aria-label="Your profile and settings"
            className="flex w-full items-center gap-3 rounded-[4px] px-3 py-1.5 text-left transition-colors hover:bg-panel-2"
          >
            <span className="relative shrink-0">
              {user?.avatar_path ? (
                <img
                  src={user.avatar_path}
                  alt=""
                  className="h-8 w-8 rounded-full border border-line object-cover"
                />
              ) : (
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-panel-2 font-display text-sm font-semibold text-ember">
                  {user?.username?.slice(0, 1).toUpperCase() ?? '?'}
                </span>
              )}
              {/* Unread word gets through even with the booth closed. */}
              {!profileOpen && unread > 0 && (
                <span className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-panel bg-ember" />
              )}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm text-fg">
                {user?.display_name || user?.username}
              </span>
              {user?.handle && (
                <span className="block truncate font-mono text-[10px] text-muted">
                  @{user.handle}
                </span>
              )}
            </span>
            <svg
              viewBox="0 0 24 24"
              width="14"
              height="14"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={clsx(
                'shrink-0 text-muted transition-transform duration-200',
                profileOpen && 'rotate-180',
              )}
              aria-hidden
            >
              <path d="M6 14l6-6 6 6" />
            </svg>
          </button>
        </div>
      </aside>

      {/* Phone header: the sidebar is desktop only, so the whole navigation
          lives in a drawer behind this button. */}
      <header className="fixed inset-x-0 top-0 z-30 flex items-center justify-between border-b border-line bg-panel px-4 py-3 md:hidden">
        <div className="flex items-center gap-2">
          <BeamMark className="h-6 w-6" />
          <Wordmark className="text-base" />
        </div>
        <div className="flex items-center gap-1">
          <NavLink
            to="/app/notifications"
            aria-label="Notifications"
            className="relative p-2 text-muted transition-colors hover:text-fg"
          >
            <Icon name="bell" />
            {unread > 0 && (
              <span className="absolute top-1 right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-ember px-1 font-mono text-[10px] font-medium text-ink">
                {unread > 9 ? '9+' : unread}
              </span>
            )}
          </NavLink>
          <button
            onClick={() => setMenuOpen(true)}
            aria-label="Open menu"
            aria-expanded={menuOpen}
            className="p-2 text-muted transition-colors hover:text-fg"
          >
            <Icon name="menu" />
          </button>
        </div>
      </header>

      <AnimatePresence>
        {menuOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={() => setMenuOpen(false)}
              className="fixed inset-0 z-40 bg-ink/70 backdrop-blur-sm md:hidden"
            />
            <motion.nav
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', stiffness: 420, damping: 40 }}
              aria-label="Menu"
              className="fixed inset-y-0 right-0 z-50 flex w-72 max-w-[85vw] flex-col overflow-y-auto border-l border-line bg-panel px-3 py-5 md:hidden"
            >
              <div className="mb-4 flex items-center justify-between px-2">
                <span className="wd-eyebrow !text-[9px]">Programme</span>
                <button
                  onClick={() => setMenuOpen(false)}
                  aria-label="Close menu"
                  className="p-1 text-muted transition-colors hover:text-fg"
                >
                  <Icon name="close" />
                </button>
              </div>

              <NavSections />

              <div className="mt-1 flex flex-col gap-1 border-t border-line pt-3">
                <p className="wd-eyebrow mb-1 px-3 !text-[9px]">The booth</p>
                <NavItem to="/app/notifications" label="Notifications" icon="bell" />
                <NavItem to="/app/settings" label="Settings" icon="settings" />
                {user?.role === 'admin' && (
                  <NavItem to="/app/admin" label="Admin" icon="admin" />
                )}
              </div>

              <button
                onClick={handleLogout}
                className="mt-auto flex items-center gap-3 rounded-[4px] px-3 py-2 text-sm text-muted transition-colors hover:text-fg"
              >
                <Icon name="logout" />
                Sign out, {user?.username}
              </button>
            </motion.nav>
          </>
        )}
      </AnimatePresence>

      {/* The destinations worth one thumb tap. */}
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-panel pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {MOBILE_TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) =>
              clsx(
                'flex flex-1 flex-col items-center gap-1 py-2.5 text-[10px] transition-colors',
                isActive ? 'text-ember' : 'text-muted',
              )
            }
          >
            <Icon name={tab.icon} />
            {tab.label}
          </NavLink>
        ))}
      </nav>

      {/* min-w-0 lets wide children scroll inside themselves rather than
          widening the page and sliding under the sidebar. */}
      <main className="min-h-screen min-w-0 pt-14 md:ml-60 md:pt-0">
        {/* Enter-only transition. An exit animation needs AnimatePresence in
            wait mode, which mounts the incoming page, then swaps and remounts
            it once the outgoing one finishes: anything typed in between is
            lost. Animating just the arrival keeps the motion and the state. */}
        {/* Floats over the page rather than pushing it down, so a hero that
            bleeds to the edges runs underneath it the way it is meant to.
            Sticky rather than fixed so it stays inside the main column and
            never sits over the sidebar. */}
        {!hideSearchBar && (
          /* Zero height on purpose. Sticky does not take an element out of
             flow the way fixed does, so a bar with real height pushes
             everything below it down by that much, and the hero underneath
             starts in a black band instead of behind the bar. At h-0 it
             contributes nothing to layout and its children simply overflow,
             which is what "floats over" has to mean here. */
          <div className="pointer-events-none sticky top-14 z-30 h-0 md:top-0">
            {/* A scrim, so the bar stays readable when a bright poster runs
                underneath it. Fades to nothing rather than ending on a line. */}
            <div
              aria-hidden
              className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-32 bg-gradient-to-b from-ink via-ink/70 to-transparent"
            />
            <div className="pointer-events-auto px-6 pt-4 md:px-10 md:pt-6 lg:max-w-xl">
              <SearchBar onOpen={() => setSearchOpen(true)} />
            </div>
          </div>
        )}
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          className={clsx(
            'min-w-0 px-6 pb-8 md:px-10',
            // Enough room to clear the floating bar. A full bleed hero
            // cancels exactly this much to run up behind it.
            hideSearchBar ? 'pt-8' : 'pt-24',
          )}
        >
          {/* Scoped to the page, so a crash keeps the shell and the
              navigation alive instead of whiting out the whole app. Keyed by
              path so moving to another page clears a stuck error. */}
          <ErrorBoundary key={location.pathname} label="This page">
            <Outlet />
          </ErrorBoundary>
          <SearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} />
          <BrowserAlertsWatcher />
        </motion.div>

        <footer className="border-t border-line px-6 py-6 pb-24 md:px-10 md:pb-6">
          <Attribution />
        </footer>
        {/* Outside the page transition: a fixed card inside a transformed
            ancestor would anchor to the page, not the screen. */}
        <ExpenseNudge />
      </main>
    </div>
  )
}
