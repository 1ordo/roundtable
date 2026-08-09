import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useInbox } from '../api/notifications'
import { Row, Toggle } from './SettingsSections'

const STORAGE_KEY = 'wd-browser-alerts'
const SEEN_KEY = 'wd-alerts-seen'

function enabled(): boolean {
  return localStorage.getItem(STORAGE_KEY) === 'on'
}

/* Notifications the browser shows even when the tab is in the background.
 *
 * Permission is asked for on the click that turns this on, never on load:
 * a permission prompt nobody asked for is the fastest way to get denied
 * permanently, and a denied permission cannot be asked for again.
 */
export function BrowserAlertsSection() {
  const [on, setOn] = useState(enabled)
  const [state, setState] = useState<NotificationPermission | 'unsupported'>(
    typeof Notification === 'undefined' ? 'unsupported' : Notification.permission,
  )

  async function toggle(next: boolean) {
    if (!next) {
      localStorage.setItem(STORAGE_KEY, 'off')
      setOn(false)
      return
    }
    if (typeof Notification === 'undefined') return
    const granted =
      Notification.permission === 'granted'
        ? 'granted'
        : await Notification.requestPermission()
    setState(granted)
    if (granted !== 'granted') return
    localStorage.setItem(STORAGE_KEY, 'on')
    setOn(true)
    new Notification('Watchpile', {
      body: 'That worked. You will hear about new alerts here.',
    })
  }

  if (state === 'unsupported') {
    return (
      <Row label="Browser notifications" hint="This browser does not offer them.">
        <span className="font-mono text-[11px] text-muted">unavailable</span>
      </Row>
    )
  }

  return (
    <Row
      label="Browser notifications"
      hint={
        state === 'denied'
          ? 'Blocked for this site. Allow notifications in your browser settings first.'
          : 'Shows alerts on your desktop even when Watchpile is in another tab.'
      }
    >
      <Toggle
        on={on && state === 'granted'}
        onChange={toggle}
        label="Browser notifications"
      />
    </Row>
  )
}

/* Watches the inbox and raises a browser notification for anything new.
 *
 * Mounted once in the shell. It compares against the last id it announced
 * rather than the unread count, so marking something read elsewhere does
 * not cause the next poll to re-announce older rows. */
export function BrowserAlertsWatcher() {
  const { data } = useInbox()
  const queryClient = useQueryClient()
  const primed = useRef(false)

  useEffect(() => {
    if (!data?.notifications || typeof Notification === 'undefined') return
    if (!enabled() || Notification.permission !== 'granted') return

    const seen = new Set<string>(JSON.parse(localStorage.getItem(SEEN_KEY) || '[]'))

    // The first load after opening the app is not news: without this every
    // unread row from the past week would arrive at once.
    if (!primed.current) {
      primed.current = true
      localStorage.setItem(
        SEEN_KEY,
        JSON.stringify(data.notifications.slice(0, 60).map((n) => n.id)),
      )
      return
    }

    const fresh = data.notifications.filter((n) => !n.read && !seen.has(n.id))
    for (const item of fresh.slice(0, 3)) {
      const note = new Notification('Watchpile', { body: item.message, tag: item.id })
      note.onclick = () => {
        window.focus()
        queryClient.invalidateQueries({ queryKey: ['inbox'] })
      }
      seen.add(item.id)
    }
    if (fresh.length > 0) {
      localStorage.setItem(SEEN_KEY, JSON.stringify([...seen].slice(-60)))
    }
  }, [data, queryClient])

  return null
}
