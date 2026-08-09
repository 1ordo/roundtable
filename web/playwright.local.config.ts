import { defineConfig, devices } from '@playwright/test'

/* Runs the same browser checks against the real stack from
   scripts/dev.sh, rather than the mock API used by the default config:
     ./scripts/dev.sh up
     npx playwright test -c playwright.local.config.ts            */
export default defineConfig({
  testDir: 'tests/e2e',
  testMatch: 'password-auth.spec.ts',
  fullyParallel: false,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:8080',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
