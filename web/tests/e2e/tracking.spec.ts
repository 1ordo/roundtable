import { expect, test } from '@playwright/test'

// The mock API keeps in-memory state, so these steps run as one ordered flow.
test.describe.configure({ mode: 'serial' })

async function signIn(page) {
  await page.goto('/login')
  await page.getByRole('link', { name: 'Sign in with passkey' }).click()
  await expect(page).toHaveURL(/\/app/)
}

test('watchlist and shared list round trip from the title page', async ({ page }) => {
  await signIn(page)
  await page.goto('/app/title/movie/354912')

  const watchlistButton = page.getByRole('button', { name: /watchlist/i })
  await watchlistButton.click()
  await expect(page.getByRole('button', { name: 'On your watchlist' })).toBeVisible()

  await page.locator('aside').getByRole('link', { name: 'Lists' }).click()
  await expect(page.getByText('1 title', { exact: true })).toBeVisible()

  await page.getByRole('link', { name: /Watchlist/ }).click()
  await expect(page.getByRole('link', { name: 'Coco' })).toBeVisible()
})

test('mark watched with a rating lands in history', async ({ page }) => {
  await signIn(page)
  await page.goto('/app/title/movie/354912')

  await page.getByRole('button', { name: 'Mark watched' }).click()
  await page.getByRole('radio', { name: '9 out of 10' }).click()
  await page.getByLabel('Loved it').check()
  await page.getByRole('button', { name: 'Save to history' }).click()

  await expect(page.getByRole('button', { name: /log again/ })).toBeVisible()

  await page.getByRole('link', { name: 'History' }).click()
  await expect(page.getByText('1 watched')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Coco' }).first()).toBeVisible()
  await expect(page.getByText('9/10')).toBeVisible()
})

test('settings picks a country by search and toggles a service', async ({ page }) => {
  await signIn(page)
  // The booth is collapsed behind the profile button.
  await page.getByRole('button', { name: 'Your profile and settings' }).click()
  await page.getByRole('link', { name: 'Settings' }).click()
  // Settings is tabbed; the country picker lives under Watching.
  await page.getByRole('button', { name: 'Watching' }).click()

  // The picker covers every country, so it is searchable rather than a list.
  await page.getByPlaceholder(/Search \d+ countries/).fill('japa')
  // Exact, so the "Japanese" language chip elsewhere on the page is not it.
  await expect(page.getByRole('button', { name: 'Japan', exact: true })).toBeVisible()
  await page.getByPlaceholder(/Search \d+ countries/).fill('')
  await page.getByRole('button', { name: 'Egypt', exact: true }).click()

  await expect(page.getByRole('button', { name: 'Netflix' })).toBeVisible()
  await page.getByRole('button', { name: 'Netflix' }).click()
  await expect(page.getByRole('button', { name: 'Netflix' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
})

test('json import lands and shows as done', async ({ page }) => {
  await signIn(page)
  // Import lives under settings now, not in the main navigation.
  // The booth is collapsed behind the profile button.
  await page.getByRole('button', { name: 'Your profile and settings' }).click()
  await page.getByRole('link', { name: 'Settings' }).click()
  // The import entry point sits in the tabbed Data section now.
  await page.getByRole('button', { name: 'Data' }).click()
  await page.getByRole('link', { name: 'Import' }).click()
  await page.getByRole('button', { name: 'Paste a list' }).click()
  await page.getByPlaceholder('[{"title": "Coco"}]').fill('[{"title": "Coco"}]')
  await page.getByRole('button', { name: 'Import', exact: true }).click()
  await expect(page.getByText('Matching runs in the background')).toBeVisible()
  await expect(page.getByText('Your imports')).toBeVisible()
  await expect(page.getByText('Done')).toBeVisible()
})

test('notification inbox shows unread and marks all read', async ({ page }) => {
  await signIn(page)
  // Notifications live in the collapsed booth menu; the avatar carries a dot.
  await page.getByRole('button', { name: 'Your profile and settings' }).click()
  await expect(page.getByRole('link', { name: /Notifications/ })).toContainText('1')
  await page.getByRole('link', { name: /Notifications/ }).click()
  await expect(page.getByText('Coco is now streaming on Netflix in EG')).toBeVisible()
  await page.getByRole('button', { name: 'Mark all read' }).click()
  await expect(page.getByRole('button', { name: 'Mark all read' })).toBeHidden()
})

test('ask search returns ranked results with parsed summary', async ({ page }) => {
  await signIn(page)
  // The classic search page has no nav entry anymore; it lives at its address.
  await page.goto('/app/search')
  await page.getByRole('button', { name: 'Ask' }).first().click()
  await page
    .getByPlaceholder('Something like Coco but not animated, under 2 hours')
    .fill('something like coco but live action')
  await page.getByRole('button', { name: 'Ask', exact: true }).last().click()
  await expect(page.getByText(/Understood as/)).toBeVisible()
  await expect(page.getByRole('link', { name: 'Coco' })).toBeVisible()
})

test('admin page shows quota and saves AI settings', async ({ page }) => {
  await signIn(page)
  // The booth is collapsed behind the profile button.
  await page.getByRole('button', { name: 'Your profile and settings' }).click()
  await page.getByRole('link', { name: 'Admin' }).click()
  await expect(page.getByText('TMDB')).toBeVisible()
  await expect(page.getByText('/ 900 today')).toBeVisible()
  await expect(page.getByRole('switch').first()).toBeVisible()
  await page.getByRole('button', { name: 'Save AI settings' }).click()
  await expect(page.getByText('Saved')).toBeVisible()

  // Handing out a password shows it exactly once.
  await page.getByRole('button', { name: 'Set password' }).first().click()
  await expect(page.getByText('One-time password')).toBeVisible()
  await page.getByRole('button', { name: 'Done' }).click()
  await expect(page.getByText('One-time password')).toBeHidden()
})

test('like and dislike toggle on the title page', async ({ page }) => {
  await signIn(page)
  await page.goto('/app/title/movie/354912')
  const like = page.getByRole('button', { name: 'More like this, please' })
  await like.click()
  await expect(like).toHaveAttribute('aria-pressed', 'true')
  const dislike = page.getByRole('button', { name: 'Not for me' })
  await dislike.click()
  await expect(dislike).toHaveAttribute('aria-pressed', 'true')
  await expect(like).toHaveAttribute('aria-pressed', 'false')
})

test('watch night creates a group and suggests', async ({ page }) => {
  await signIn(page)
  await page.getByRole('link', { name: 'Watch night' }).click()
  // A night needs a name before it can start.
  await page.getByPlaceholder('What are you calling it?').fill('Couch premiere')
  // Friends are picked by tapping them, no typing of usernames.
  await page.getByRole('button', { name: /Nadia/ }).click()
  await page.getByRole('button', { name: 'Start it' }).click()
  await expect(page.getByText('Lordo', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Nadia', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Suggest something' }).click()
  // Suggestions are queueable tiles (buttons), not links.
  await expect(page.getByRole('button', { name: 'Coco' })).toBeVisible()
})

test('new page shows fresh rows and a section per service', async ({ page }) => {
  await signIn(page)
  await page.getByRole('link', { name: 'New arrivals' }).click()
  await expect(page.getByRole('heading', { name: 'In theaters now' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Netflix' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Coco' }).first()).toBeVisible()
  await expect(page.getByLabel('Show every service')).not.toBeChecked()
})
