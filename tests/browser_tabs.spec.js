// @ts-check
/**
 * Playwright end-to-end test for /user/browser — Chrome-style multi-tab
 * UI + true Incognito mode (Task #74 spec).
 *
 * Run from project root with the bot running on port 5000:
 *   npx playwright test tests/browser_tabs.spec.js
 *
 * The test deliberately exercises every observable outcome from the
 * task spec's "Done looks like" section so reviewers can replay the
 * full scenario without a human in the loop.
 */
const { test, expect } = require('@playwright/test');

const BASE = process.env.BROWSER_TEST_BASE || 'http://localhost:5000';
const TG_ID = process.env.BROWSER_TEST_USER || '999900001';
const PASS = process.env.BROWSER_TEST_PASS || 'testpass123';

async function login(page) {
  await page.goto(`${BASE}/user/login`);
  await page.fill('input[name="telegram_id"]', TG_ID);
  await page.fill('input[name="password"]', PASS);
  await Promise.all([
    page.waitForURL(/\/user\/(home|dashboard)/),
    page.click('button[type="submit"]'),
  ]);
}

async function openBrowser(page) {
  await page.goto(`${BASE}/user/browser`);
  await page.waitForSelector('#br-shell', { timeout: 8000 });
  await page.waitForSelector('#br-tabstrip .br-tab', { timeout: 8000 });
}

async function tabCount(page) {
  return await page.locator('#br-tabstrip .br-tab').count();
}

async function activeTabHasClass(page, cls) {
  return await page.evaluate((c) => {
    const t = document.querySelector('#br-tabstrip .br-tab.active');
    return t ? t.classList.contains(c) : false;
  }, cls);
}

/**
 * Open a new tab via the "+" menu. Uses the stable
 * `[data-mode="normal|incognito"]` attribute on the menu item, which is
 * the contract the test relies on (see tests/browser_tabs.spec.js).
 */
async function openNewTab(page, mode /* 'normal' | 'incognito' */) {
  await page.click('.br-newtab-btn');
  await page.waitForSelector('#br-newtab-menu.open', { state: 'visible' });
  const sel = `.br-newtab-menu-item[data-mode="${mode}"]`;
  await page.click(sel);
  // give the TabManager a tick to update the strip
  await page.waitForTimeout(150);
}

test.describe('/user/browser — Chrome-style multi-tab + Incognito', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await openBrowser(page);
  });

  test('opens 3 normal + 2 incognito tabs and switches between them', async ({ page }) => {
    // Start state: 1 tab. Open 2 more normal tabs → 3 normal total.
    await openNewTab(page, 'normal');
    await openNewTab(page, 'normal');
    expect(await tabCount(page)).toBe(3);

    // Open 2 incognito tabs → 5 total.
    await openNewTab(page, 'incognito');
    await openNewTab(page, 'incognito');
    expect(await tabCount(page)).toBe(5);

    // Active tab should be the latest incognito one.
    expect(await activeTabHasClass(page, 'incognito')).toBe(true);

    // Click first tab to switch back to normal.
    await page.locator('#br-tabstrip .br-tab').first().click();
    await page.waitForTimeout(100);
    expect(await activeTabHasClass(page, 'incognito')).toBe(false);

    // Shell should NOT have incognito class while a normal tab is active.
    const shellHasIncognito = await page.evaluate(() =>
      document.getElementById('br-shell').classList.contains('incognito'));
    expect(shellHasIncognito).toBe(false);
  });

  test('close button is hover-only on inactive tabs', async ({ page }) => {
    await openNewTab(page, 'normal');
    await openNewTab(page, 'normal');
    const inactive = page.locator('#br-tabstrip .br-tab:not(.active)').first();
    const closeBtn = inactive.locator('.br-tab-close');
    // before hover: opacity should be 0
    const opacityBefore = await closeBtn.evaluate((el) =>
      getComputedStyle(el).opacity);
    expect(parseFloat(opacityBefore)).toBeLessThan(0.1);
    await inactive.hover();
    await page.waitForTimeout(100);
    const opacityAfter = await closeBtn.evaluate((el) =>
      getComputedStyle(el).opacity);
    expect(parseFloat(opacityAfter)).toBeGreaterThan(0.5);
  });

  test('closes tabs and removes them from the strip', async ({ page }) => {
    await openNewTab(page, 'normal');
    await openNewTab(page, 'incognito');
    expect(await tabCount(page)).toBe(3);
    // Close the middle tab via its × button (force-click since it's hidden).
    const middleClose = page.locator('#br-tabstrip .br-tab').nth(1)
      .locator('.br-tab-close');
    await middleClose.click({ force: true });
    await page.waitForTimeout(150);
    expect(await tabCount(page)).toBe(2);
  });

  test('Incognito visits do NOT appear in browsing history', async ({ page, request }) => {
    await openNewTab(page, 'incognito');
    // Navigate the active (incognito) tab to a unique example.org path.
    const probe = `https://example.org/?probe-${Date.now()}`;
    await page.fill('#br-addr', probe);
    await page.press('#br-addr', 'Enter');
    await page.waitForTimeout(2500);

    const cookies = await page.context().cookies();
    const cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join('; ');
    const res = await request.get(`${BASE}/user/browser/api/history`, {
      headers: { Cookie: cookieHeader },
    });
    const body = await res.json();
    const items = body.items || body.history || [];
    const leaked = items.some(it => (it.url || '').includes('probe-'));
    expect(leaked).toBe(false);
  });

  test('Bookmark button is visually disabled in Incognito', async ({ page }) => {
    await openNewTab(page, 'incognito');
    const btn = page.locator('#btn-bookmark');
    await expect(btn).toHaveClass(/disabled/);
    await expect(btn).toHaveAttribute('aria-disabled', 'true');
    const text = await btn.textContent();
    expect(text.trim()).toBe('🔒');
    const tip = await btn.getAttribute('title');
    expect(tip).toMatch(/Incognito/i);

    // Programmatically click — handler must short-circuit with an alert.
    page.once('dialog', async d => {
      expect(d.message()).toMatch(/Incognito|disabled/i);
      await d.dismiss();
    });
    await btn.evaluate(el => el.click());
  });

  test('Tracking parameters are stripped in Incognito tabs', async ({ page }) => {
    // Per spec: tracking-param stripping is an Incognito-only privacy
    // feature. Open an incognito tab and verify the cleaned URL.
    await openNewTab(page, 'incognito');
    const dirty = 'https://example.com/?utm_source=foo&utm_campaign=bar' +
                  '&fbclid=xyz&gclid=abc&keep=ok';
    await page.fill('#br-addr', dirty);
    await page.press('#br-addr', 'Enter');
    await page.waitForTimeout(2500);
    const addrValue = await page.inputValue('#br-addr');
    expect(addrValue).not.toMatch(/utm_/i);
    expect(addrValue).not.toMatch(/fbclid/i);
    expect(addrValue).not.toMatch(/gclid/i);
    // Non-tracking params are preserved.
    expect(addrValue).toMatch(/keep=ok/);
  });
});
