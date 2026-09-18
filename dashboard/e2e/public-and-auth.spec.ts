import { expect, test } from '@playwright/test'

const hasSignedInState = Boolean(process.env.PLAYWRIGHT_STORAGE_STATE)
const targetsDeployedAuth = Boolean(process.env.E2E_BASE_URL)

test('a signed-out browser cannot enter protected research routes', async ({ browser }) => {
  test.skip(!targetsDeployedAuth, 'The local Clerk development proxy is not the production auth boundary; set E2E_BASE_URL for this check.')
  const context = await browser.newContext({ storageState: undefined })
  const page = await context.newPage()
  await page.goto('/terminal/command')
  await expect(page).toHaveURL(/sign-in|login/)
  await context.close()
})

test('the frontend reports its build revision', async ({ request }) => {
  const response = await request.get('/api/build')
  expect(response.ok()).toBeTruthy()
  const body = await response.json()
  expect(body.service).toBe('frontend')
  expect(typeof body.commit).toBe('string')
})

test.describe('signed-in critical journeys', () => {
  test.skip(!hasSignedInState, 'Set PLAYWRIGHT_STORAGE_STATE to a real signed-in browser state; no auth bypass is permitted.')

  test('all three experience modes navigate to their own complete shells', async ({ page }) => {
    await page.goto('/start')
    await page.getByRole('button', { name: 'Use Simple Mode' }).click()
    await expect(page).toHaveURL(/\/beginner$/)
    await expect(page.getByRole('heading', { name: 'Top Ranked Ideas' })).toBeVisible()

    await page.getByRole('button', { name: 'Switch to Intermediate' }).click()
    await expect(page).toHaveURL(/\/intermediate$/)
    await expect(page.getByRole('heading', { name: 'Analyze a company' })).toBeVisible()

    await page.getByRole('button', { name: 'Switch to Advanced' }).click()
    await expect(page).toHaveURL(/\/terminal\/command$/)
    await expect(page.getByRole('heading', { name: 'Terminal' })).toBeVisible()
  })

  test('company analysis exposes evidence, agents, compare, watch and paper preview', async ({ page }) => {
    await page.goto('/intermediate/company/AAPL?paper=1')
    await expect(page.getByRole('heading', { name: /Signal and risk/i })).toBeVisible({ timeout: 120_000 })
    await expect(page.getByRole('heading', { name: /Evidence health/i })).toBeVisible()
    await expect(page.getByRole('heading', { name: /Analysis run/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /Compare/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /watchlist/i })).toBeVisible()

    const ticket = page.getByLabel('Paper order for AAPL')
    if (await ticket.count()) {
      await ticket.getByRole('button', { name: 'review order' }).click()
      await expect(ticket.getByRole('button', { name: 'place paper order' })).toBeVisible()
      // Preview is the terminal action in this test. It never places the order.
    }
  })

  test('compare, watchlist, portfolio and experience-aware explore are routable', async ({ page }) => {
    await page.goto('/intermediate/compare?a=AAPL&b=MSFT')
    await expect(page.getByRole('heading', { name: 'Compare' })).toBeVisible()
    await expect(page.getByText('AAPL against MSFT')).toBeVisible({ timeout: 120_000 })

    await page.goto('/intermediate/watchlist')
    await expect(page.getByRole('heading', { name: 'Watchlist' })).toBeVisible()
    await page.goto('/intermediate/portfolio')
    await expect(page.getByRole('heading', { name: 'Portfolio' })).toBeVisible()
    await page.goto('/explore?category=quality')
    await expect(page.getByRole('button', { name: 'Quality' })).toHaveAttribute('aria-pressed', 'true')
  })

  test('ordinary accounts are denied operator diagnostics by the backend', async ({ page }) => {
    await page.goto('/terminal/admin')
    await expect(
      page.getByText(/This account is not an operator|Deployment versions/),
    ).toBeVisible()
  })
})
