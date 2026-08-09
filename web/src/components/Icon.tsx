import type { SVGProps } from 'react'

const PATHS: Record<string, string> = {
  home: 'M4 12.5 12 5l8 7.5M6 11v8h4.5v-4.5h3V19H18v-8',
  browse: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm3.5 5.5-2 5-5 2 2-5 5-2Z',
  search: 'M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Zm9.5 16-4.4-4.4',
  lists: 'M6 4h12a1 1 0 0 1 1 1v15l-7-4-7 4V5a1 1 0 0 1 1-1Z',
  history: 'M12 8v4.5l3 2M12 3a9 9 0 1 1-8.7 6.5M3 4v5h5',
  stats: 'M4 20V10m5.5 10V4M15 20v-7m5.5 7V8',
  settings:
    'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Zm7.5 3a7.5 7.5 0 0 0-.1-1.2l2-1.5-2-3.5-2.4 1a7.6 7.6 0 0 0-2-1.2L14.6 3h-4l-.4 2.6a7.6 7.6 0 0 0-2 1.2l-2.4-1-2 3.5 2 1.5a7.7 7.7 0 0 0 0 2.4l-2 1.5 2 3.5 2.4-1a7.6 7.6 0 0 0 2 1.2l.4 2.6h4l.4-2.6a7.6 7.6 0 0 0 2-1.2l2.4 1 2-3.5-2-1.5c.06-.4.1-.8.1-1.2Z',
  admin: 'M12 3l8 3v6c0 4.5-3.5 8-8 9-4.5-1-8-4.5-8-9V6l8-3Zm-3 9 2.2 2.2L15.5 10',
  logout: 'M14 4h-8a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h8M10 12h10m0 0-3.5-3.5M20 12l-3.5 3.5',
  bell: 'M12 4a5.5 5.5 0 0 0-5.5 5.5c0 4-1.5 5.5-2.5 6.5h16c-1-1-2.5-2.5-2.5-6.5A5.5 5.5 0 0 0 12 4Zm-2.5 15a2.5 2.5 0 0 0 5 0',
  import: 'M12 3v10m0 0 4-4m-4 4-4-4M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4',
  sparkle: 'M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.4L12 3Zm7 11 .9 2.6 2.6.9-2.6.9-.9 2.6-.9-2.6-2.6-.9 2.6-.9.9-2.6Z',
  menu: 'M4 7h16M4 12h16M4 17h16',
  close: 'M6 6l12 12M18 6L6 18',
  feed: 'M4 6h16M4 12h16M4 18h10M18 16v5m2.5-2.5h-5',
  message: 'M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9l-5 4V6a1 1 0 0 1 1-1Z',
  // A film strip and a screen: the two halves of the catalog.
  film: 'M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Zm3 0v14m10-14v14M3 9.5h4m10 0h4M3 14.5h4m10 0h4',
  series: 'M4 8h16a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Zm4.5-4L12 8l3.5-4',
  cinema: 'M4 9h16a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1Zm2.5-5.5 2 4m3-4.5 2 4.5m3-5 2 4.5M3 9l18-2.5',
  friends: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm-6 9c.6-3.2 2.9-5 6-5s5.4 1.8 6 5m1.5-15a3.5 3.5 0 0 1 0 7m2 3c2 .6 3.4 2.2 3.9 5',
  night: 'M8 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm8 0a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM2.5 20c.6-3.2 2.8-5 5.5-5s4.9 1.8 5.5 5m1-5c2.3.3 4 2 4.5 5',
}

export type IconName = keyof typeof PATHS

export function Icon({ name, ...props }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...props}
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
