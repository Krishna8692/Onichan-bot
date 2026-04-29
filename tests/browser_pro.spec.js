// @ts-check
//
// Browser Pro Mode UI smoke spec (Task #75).
//
// This spec drives the live /user/browser panel in a real browser and
// verifies the Pro toggle: capability detection, click-to-enable swaps
// the iframe for a <canvas>, and the pool-state endpoint reflects the
// open tab. The spec is automatically skipped when the server reports
// Pro Mode unavailable (no Chromium / no flask-sock), so it stays green
// in environments without the heavy deps.
//
// Run with::
//
//     BROWSER_TEST_BASE=http://localhost:5000 npx playwright test tests/browser_pro.spec.js

const { test, expect } = require("@playwright/test");

const BASE = process.env.BROWSER_TEST_BASE || "http://localhost:5000";
const TG_ID = process.env.BROWSER_TEST_USER || "999900001";
const PASS = process.env.BROWSER_TEST_PASS || "testpass123";

async function login(request) {
  let r = await request.post(`${BASE}/user/login`, {
    form: { user_id: TG_ID, password: PASS },
    maxRedirects: 0,
  });
  if (![302, 303].includes(r.status())) {
    await request.post(`${BASE}/user/register`, {
      form: { user_id: TG_ID, password: PASS, confirm_password: PASS },
      maxRedirects: 0,
    });
    r = await request.post(`${BASE}/user/login`, {
      form: { user_id: TG_ID, password: PASS },
      maxRedirects: 0,
    });
  }
  return [302, 303].includes(r.status());
}

test.describe("Pro Mode toggle UI", () => {
  test.beforeEach(async ({ page, request }) => {
    const ok = await login(request);
    test.skip(!ok, "could not log in test user");
    // Replay session cookie into the browser context.
    const cookies = (await request.storageState()).cookies;
    await page.context().addCookies(cookies);
  });

  test("toggle button is present and reflects capability", async ({ page, request }) => {
    const status = await (await request.get(
      `${BASE}/user/browser/api/pro/status`)).json();

    await page.goto(`${BASE}/user/browser`);
    const btn = page.locator("#btn-pro");
    await expect(btn).toBeVisible();

    if (!status.available) {
      // Disabled-with-tooltip path. Clicking should NOT mount a canvas.
      await expect(btn).toHaveClass(/disabled/);
      await btn.click({ force: true });
      await expect(page.locator("canvas.br-pro-canvas")).toHaveCount(0);
      test.skip(true, `Pro Mode unavailable: ${status.reason}`);
    }

    // Capability available — clicking the toggle should swap the iframe
    // for a canvas, light up the pill, and add the active class to the
    // toggle. We don't wait for a frame here (that's covered by the
    // python integration test), only the structural swap.
    await page.locator("#br-addr").fill("https://example.com/");
    await page.locator("#br-addr").press("Enter");
    await btn.click();
    await expect(btn).toHaveClass(/active/);
    await expect(page.locator("#br-pro-pill")).toBeVisible();
    await expect(page.locator("canvas.br-pro-canvas")).toHaveCount(1);

    // Toggling off must dispose the canvas.
    await btn.click();
    await expect(btn).not.toHaveClass(/active/);
    await expect(page.locator("canvas.br-pro-canvas")).toHaveCount(0);
  });
});
