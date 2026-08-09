/* Regenerates the landing-page product screenshots in public/shots.
 *
 * Drives the real app against the mock API, the same pair the e2e suite
 * uses, so the shots always show the current design with believable data.
 *
 *   node tests/mock-api.mjs &          # port 8000
 *   npm run dev &                      # port 5173
 *   node tests/make-shots.mjs
 *
 * Writes webp, not png. The conversion used to be a manual step described
 * in this comment, which meant the repo shipped two and a half megabytes of
 * png that nothing rendered. It happens automatically at the end now.
 */
import { chromium } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { mkdirSync, rmSync } from 'node:fs'

const BASE = 'http://127.0.0.1:5173'
const OUT = new URL('../public/shots/', import.meta.url).pathname

async function signIn(page) {
  await page.goto(`${BASE}/login`)
  await page.getByRole('link', { name: 'Sign in with passkey' }).click()
  await page.waitForURL(/\/app/)
}

async function settle(page, extra = 1200) {
  await page.waitForLoadState('networkidle')
  // Let entrance animations finish and images decode.
  await page.waitForTimeout(extra)
}

async function newPage(browser, deviceScaleFactor = 1) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor,
    colorScheme: 'dark',
  })
  // The leader countdown is for people, not screenshots.
  await context.addInitScript(() => sessionStorage.setItem('wd-booted', '1'))
  return context.newPage()
}

const browser = await chromium.launch()
mkdirSync(OUT, { recursive: true })

{
  // Home: hero, Next up, and the personalized shelves.
  const page = await newPage(browser)
  await signIn(page)
  await settle(page, 1800)
  await page.screenshot({ path: `${OUT}home.png` })
  await page.close()
}

{
  // Watch night: create one, blend suggestions, queue a couple of picks.
  const page = await newPage(browser)
  await signIn(page)
  await page.goto(`${BASE}/app/night`)
  await page.getByPlaceholder('What are you calling it?').fill('Friday premiere')
  await page.getByRole('button', { name: /Nadia/ }).click()
  await page.getByRole('button', { name: 'Start it' }).click()
  await page.getByRole('button', { name: 'Suggest something' }).click()
  await page.getByRole('button', { name: 'Your Name.' }).waitFor()
  await page.getByRole('button', { name: 'Your Name.' }).click()
  await page.getByRole('button', { name: /Dune/ }).first().click()
  await settle(page)
  // Frame the night card just under the floating search bar.
  const nightCard = page.locator('section').filter({ hasText: 'Friday premiere' }).first()
  const cardBox = await nightCard.boundingBox()
  await page.evaluate((y) => window.scrollBy(0, y - 88), cardBox.y)
  await page.waitForTimeout(400)
  await page.screenshot({ path: `${OUT}night.png` })
  await page.close()
}

{
  // Cinema: tracked, showing now, coming soon.
  const page = await newPage(browser)
  await signIn(page)
  await page.goto(`${BASE}/app/cinema`)
  await settle(page)
  await page.screenshot({ path: `${OUT}cinema.png` })
  await page.close()
}

{
  // Parents guide, expanded on the title page.
  const page = await newPage(browser)
  await signIn(page)
  await page.goto(`${BASE}/app/title/movie/354912`)
  await page.getByRole('button', { name: 'What is in it?' }).click()
  await page.getByText('Frightening and intense').waitFor()
  await page.getByText('Frightening and intense').click()
  await settle(page)
  await page.getByRole('heading', { name: 'Parents guide' }).scrollIntoViewIfNeeded()
  await page.mouse.wheel(0, -80)
  await page.waitForTimeout(400)
  await page.screenshot({ path: `${OUT}guide.png` })
  await page.close()
}

{
  // The four share cards, crisp at 2x.
  const page = await newPage(browser, 2)
  await signIn(page)
  await page.goto(`${BASE}/app/stats`)
  await settle(page, 2500)
  const section = page.locator('section').filter({ hasText: 'Share your year' }).last()
  await section.scrollIntoViewIfNeeded()
  // Card previews rasterize posters through the media proxy; give them room.
  await page.waitForTimeout(4000)
  // Clip the dead column to the section's right; keep the cards and actions.
  const box = await section.boundingBox()
  await page.screenshot({
    path: `${OUT}cards.png`,
    clip: { x: box.x, y: box.y, width: Math.min(box.width, 1352), height: box.height },
  })
  await page.close()
}

{
  // A dedicated Open Graph image at the size every unfurler expects, rather
  // than a 1440x900 app screenshot cropped by whoever is displaying it.
  const context = await browser.newContext({
    viewport: { width: 1200, height: 630 },
    deviceScaleFactor: 1,
    colorScheme: 'dark',
  })
  await context.addInitScript(() => sessionStorage.setItem('wd-booted', '1'))
  const page = await context.newPage()
  await signIn(page)
  await settle(page, 1800)
  await page.screenshot({ path: `${OUT}og.png`, quality: undefined })
  await page.close()
}

await browser.close()

/* webp at quality 82 is visually indistinguishable from the png here and
   roughly a tenth of the size. The png is removed once converted so there
   is only ever one copy of each shot in the repo.

   The Open Graph image becomes jpeg rather than webp: it is the one image
   whose whole job is being read by someone else's unfurler, and not all of
   them take webp. As a png it was 670 kB, which is heavier than every other
   asset put together. */
for (const name of ['home', 'night', 'cinema', 'guide', 'cards']) {
  execFileSync('cwebp', ['-quiet', '-q', '82', `${OUT}${name}.png`, '-o', `${OUT}${name}.webp`])
  rmSync(`${OUT}${name}.png`)
}
execFileSync('sips', [
  '-s', 'format', 'jpeg', '-s', 'formatOptions', '82',
  `${OUT}og.png`, '--out', `${OUT}og.jpg`,
], { stdio: 'ignore' })
rmSync(`${OUT}og.png`)

console.log('shots written to public/shots')
