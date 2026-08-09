import { expect, test } from '@playwright/test'

async function signIn(page) {
  await page.goto('/login')
  await page.getByRole('link', { name: 'Sign in with passkey' }).click()
  await expect(page).toHaveURL(/\/app/)
}

test('the ledger speaks only when asked, and a dismissal holds', async ({ page }) => {
  await signIn(page)
  // Off by default: no opinion about money until the switch is flipped.
  await expect(page.getByText('Netflix has been quiet')).toBeHidden()

  await page.getByRole('button', { name: 'Your profile and settings' }).click()
  await page.getByRole('link', { name: 'Settings' }).click()
  await page.getByRole('button', { name: 'Alerts' }).click()
  await page.getByRole('switch', { name: 'Unused subscription reminders' }).click()

  await page.goto('/app')
  await expect(page.getByText('Netflix has been quiet')).toBeVisible()

  await page.getByRole('button', { name: 'Not now' }).click()
  await expect(page.getByText('Netflix has been quiet')).toBeHidden()

  // A dismissal is an answer: it holds across a reload, not just a render.
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Trending films' })).toBeVisible()
  await expect(page.getByText('Netflix has been quiet')).toBeHidden()
})
