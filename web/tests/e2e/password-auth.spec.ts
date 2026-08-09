import { expect, test } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

test('login page offers both sign-in methods', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByPlaceholder('Username')).toBeVisible()
  await expect(page.getByPlaceholder('Password')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Sign in with passkey' })).toBeVisible()
})

test('wrong password shows one generic message', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('Username').fill('Lordo')
  await page.getByPlaceholder('Password').fill('definitely-wrong')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('alert')).toContainText('do not match')
  await expect(page).toHaveURL(/\/login/)
})

test('password sign-in reaches the app', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('Username').fill('Lordo')
  await page.getByPlaceholder('Password').fill('watchpile-local')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/app/)
  await expect(page.getByRole('complementary').getByText('Lordo')).toBeVisible()
})
