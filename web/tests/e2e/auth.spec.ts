import { expect, test } from '@playwright/test'

test('unauthenticated visit to the app redirects to login', async ({ page }) => {
  await page.goto('/app')
  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByRole('link', { name: 'Sign in with passkey' })).toBeVisible()
})

test('login page presents the Roundtable identity', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByText('Roundtable')).toBeVisible()
  await expect(page.getByText('Your private screening room')).toBeVisible()
})

test('sign-in golden path lands in the app shell', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('link', { name: 'Sign in with passkey' }).click()
  await expect(page).toHaveURL(/\/app/)
  await expect(page.getByRole('complementary').getByText('Lordo')).toBeVisible()
  // Admin entry lives in the collapsed booth menu.
  await page.getByRole('button', { name: 'Your profile and settings' }).click()
  await expect(page.getByRole('link', { name: 'Admin' })).toBeVisible()
})

test('sign out returns to the login screen', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('link', { name: 'Sign in with passkey' }).click()
  await expect(page).toHaveURL(/\/app/)
  // Wait for /api/me to resolve so the client holds the CSRF token.
  await expect(page.getByRole('complementary').getByText('Lordo')).toBeVisible()
  // Sign out lives in the collapsed booth menu.
  await page.getByRole('button', { name: 'Your profile and settings' }).click()
  await page.getByRole('button', { name: 'Sign out' }).first().click()
  await expect(page).toHaveURL(/\/login/)
})

test('protected navigation keeps the requested destination', async ({ page }) => {
  await page.goto('/app/stats')
  await expect(page).toHaveURL(/\/login\?next=%2Fapp%2Fstats/)
  await page.getByRole('link', { name: 'Sign in with passkey' }).click()
  await expect(page).toHaveURL(/\/app\/stats/)
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Stats')
})
