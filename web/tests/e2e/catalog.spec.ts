import { expect, test } from '@playwright/test'

async function signIn(page) {
  await page.goto('/login')
  await page.getByRole('link', { name: 'Sign in with passkey' }).click()
  await expect(page).toHaveURL(/\/app/)
}

test('home shows trending row and opens a title', async ({ page }) => {
  await signIn(page)
  await expect(page.getByRole('heading', { name: 'Trending films' })).toBeVisible()
  await page.getByRole('link', { name: 'Coco' }).first().click()
  await expect(page).toHaveURL(/\/app\/title\/movie\/354912/)
  await expect(page.getByRole('heading', { name: 'Coco' })).toBeVisible()
  await expect(page.getByText('Where to watch')).toBeVisible()
  await expect(page.getByText('Disney Plus')).toBeVisible()
})

test('search finds a title', async ({ page }) => {
  await signIn(page)
  // Search lives in an overlay now, opened from the floating bar.
  await page.getByRole('button', { name: 'Search films, series and people' }).click()
  await page.getByPlaceholder('Films, series, people').fill('coco')
  // Results are buttons inside the dialog; the shelves behind it also show Coco.
  await expect(
    page.getByRole('dialog', { name: 'Search' }).getByRole('button', { name: /Coco/ }),
  ).toBeVisible()
})

test('browse renders genre chips and results', async ({ page }) => {
  await signIn(page)
  await page.getByRole('link', { name: 'Browse' }).click()
  await expect(page.getByRole('button', { name: 'Animation' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Coco' })).toBeVisible()
})
