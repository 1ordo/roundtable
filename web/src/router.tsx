import { Navigate, createBrowserRouter } from 'react-router'
import { AppShell } from './app/AppShell'
import { RequireAuth } from './app/RequireAuth'
import { Login } from './pages/Login'
import { Home } from './pages/Home'
import { Browse } from './pages/Browse'
import { Search } from './pages/Search'
import { TitleDetail } from './pages/TitleDetail'
import { Lists } from './pages/Lists'
import { ListDetail } from './pages/ListDetail'
import { History } from './pages/History'
import { Notifications } from './pages/Notifications'
import { NewPage } from './pages/New'
import { NotFound } from './pages/NotFound'
import { Friends } from './pages/Friends'
import { Cinema } from './pages/Cinema'
import { Feed } from './pages/Feed'
import { Messages } from './pages/Messages'
import { Profile } from './pages/Profile'

export const router = createBrowserRouter([
  // A self-hosted instance is somebody's app, not a shop window. The root
  // goes straight to it, and RequireAuth sends anyone signed out to /login.
  // The marketing page lives in src/marketing and is not built into this
  // route table; it belongs to the hosted site.
  { path: '/', element: <Navigate to="/app" replace /> },
  { path: '/login', element: <Login /> },
  { path: '/legal', lazy: async () => ({ Component: (await import('./pages/Legal')).Legal }) },
  { path: '/legal/:doc', lazy: async () => ({ Component: (await import('./pages/Legal')).Legal }) },
  {
    path: '/app',
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Home /> },
      { path: 'new', element: <NewPage /> },
      { path: 'night', lazy: async () => ({ Component: (await import('./pages/WatchNight')).WatchNight }) },
      { path: 'friends', element: <Friends /> },
      { path: 'cinema', element: <Cinema /> },
      { path: 'feed', element: <Feed /> },
      { path: 'status', lazy: async () => ({ Component: (await import('./pages/Status')).Status }) },
      { path: 'messages', element: <Messages /> },
      { path: 'messages/:handle', element: <Messages /> },
      { path: 'u/:handle', element: <Profile /> },
      { path: 'browse', element: <Browse /> },
      // The sidebar has a section per media type; the route carries it so
      // each is its own page with its own address, not a hidden toggle.
      { path: 'browse/:media', element: <Browse /> },
      // Kept for old links. The overlay is how search is reached now.
      { path: 'search', element: <Search /> },
      { path: 'ask', lazy: async () => ({ Component: (await import('./pages/Chat')).Chat }) },
      { path: 'title/:type/:tmdbId', element: <TitleDetail /> },
      { path: 'person/:personId', lazy: async () => ({ Component: (await import('./pages/Person')).Person }) },
      { path: 'lists', element: <Lists /> },
      { path: 'lists/:listId', element: <ListDetail /> },
      { path: 'history', element: <History /> },
      { path: 'import', lazy: async () => ({ Component: (await import('./pages/ImportPage')).ImportPage }) },
      { path: 'import/:batchId', lazy: async () => ({ Component: (await import('./pages/ImportReview')).ImportReview }) },
      { path: 'notifications', element: <Notifications /> },
      { path: 'stats', lazy: async () => ({ Component: (await import('./pages/Stats')).StatsPage }) },
      { path: 'settings', lazy: async () => ({ Component: (await import('./pages/Settings')).Settings }) },
      { path: 'admin', lazy: async () => ({ Component: (await import('./pages/Admin')).Admin }) },
    ],
  },
  { path: '*', element: <NotFound /> },
])
