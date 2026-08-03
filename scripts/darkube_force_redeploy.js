/**
 * Force Darkube redeploy by bumping a harmless env + save, or via ops UI.
 * Env: HAMRAVESH_EMAIL, HAMRAVESH_PASSWORD
 */
const { chromium } = require("playwright");

const APP_ID = "faf37c36-82fb-4989-872e-932c7b934ae7";
const BASE = `https://console.hamravesh.com/@maahedir/darkube/app/${APP_ID}`;
const EMAIL = process.env.HAMRAVESH_EMAIL || "";
const PASS = process.env.HAMRAVESH_PASSWORD || "";
const BUMP = process.env.RESTART_BUMP || String(Date.now());

async function setReactValue(page, selector, value) {
  await page.waitForSelector(selector, { state: "visible", timeout: 15000 });
  await page.evaluate(
    ({ selector, value }) => {
      const el = document.querySelector(selector);
      if (!el) throw new Error("missing " + selector);
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
      const last = el.value;
      setter.call(el, value);
      const tracker = el._valueTracker;
      if (tracker) tracker.setValue(last);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    },
    { selector, value }
  );
}

(async () => {
  const browser = await chromium.launch({
    channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
    headless: true,
  });
  const page = await browser.newPage();
  const log = {};
  try {
    await page.goto("https://console.hamravesh.com/login", {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
    if (page.url().includes("login")) {
      await page.fill("#email", EMAIL);
      await page.fill("#password", PASS);
      await page.locator('button[type="submit"]').first().click();
      await page.waitForTimeout(5000);
    }

    // 1) Try ops / build tabs by clicking sidebar from a known-good page
    await page.goto(`${BASE}/envs`, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(5000);
    log.startUrl = page.url();

    for (const label of ["عملیات‌ها", "بیلد و دیپلوی"]) {
      const link = page.locator(`a,button,div,span,li`).filter({ hasText: new RegExp(`^${label}$`) }).first();
      if (await link.isVisible().catch(() => false)) {
        await link.click();
        await page.waitForTimeout(4000);
        log[`after_${label}`] = {
          url: page.url(),
          buttons: await page.evaluate(() =>
            [...document.querySelectorAll("button")]
              .map((b) => (b.innerText || "").replace(/\s+/g, " ").trim())
              .filter(Boolean)
              .slice(0, 40)
          ),
          slice: await page.evaluate(() => document.body.innerText.replace(/\s+/g, " ").slice(0, 1200)),
        };
      }
    }

    // Try click redeploy-ish buttons if present
    for (const re of [/دیپلوی مجدد/, /Redeploy/i, /Restart/i, /ری.?استارت/, /شروع بیلد/, /Deploy/i]) {
      const b = page.getByRole("button", { name: re }).first();
      if (await b.isVisible().catch(() => false)) {
        await b.click();
        log.clicked = String(re);
        await page.waitForTimeout(2000);
        const conf = page.getByRole("button", { name: /تأیید|تایید|OK|Confirm|بله/i }).first();
        if (await conf.isVisible().catch(() => false)) await conf.click();
        await page.waitForTimeout(5000);
        break;
      }
    }

    // 2) Fallback: upsert APP_IMAGE_BUMP plain env and save (forces rollout)
    await page.goto(`${BASE}/envs`, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(5000);
    const hasBump = await page.evaluate(() => document.body.innerText.includes("APP_IMAGE_BUMP"));
    if (!hasBump) {
      await page.getByRole("button", { name: /افزودن متغیر محیطی/ }).click();
      await page.waitForTimeout(500);
      await page.getByText("افزودن متغیر محیطی", { exact: true }).first().click().catch(() => null);
      // Prefer non-secure add
      const plain = page.getByText(/افزودن متغیر محیطی(?! امن)/).first();
      if (await plain.isVisible().catch(() => false)) await plain.click().catch(() => null);
      await page.waitForTimeout(800);
      // Sometimes dropdown: first item is plain
      const items = page.locator(".ant-dropdown-menu-item, .ant-dropdown-menu-title-content");
      if ((await items.count()) > 0) await items.first().click().catch(() => null);
      await page.waitForTimeout(1000);
      if (await page.locator("#name").isVisible().catch(() => false)) {
        await setReactValue(page, "#name", "APP_IMAGE_BUMP");
        await setReactValue(page, "#value", BUMP);
        await page.locator(".ant-drawer button, .ant-drawer-open button").filter({ hasText: /^ذخیره$/ }).first().click();
        await page.waitForTimeout(1500);
        log.addedBump = true;
      } else {
        log.addedBump = "no_drawer";
      }
    } else {
      // edit existing
      const row = page.locator("tr").filter({ hasText: "APP_IMAGE_BUMP" }).first();
      const btns = row.locator("button");
      const c = await btns.count();
      if (c >= 1) await btns.nth(Math.min(1, c - 1)).click();
      await page.waitForTimeout(1000);
      if (await page.locator("#value").isVisible().catch(() => false)) {
        await setReactValue(page, "#value", BUMP);
        await page.locator(".ant-drawer button, .ant-drawer-open button").filter({ hasText: /^ذخیره$/ }).first().click();
        await page.waitForTimeout(1500);
        log.updatedBump = true;
      }
    }

    const saveAll = page.getByRole("button", { name: /^ذخیره تغییرات$/ });
    if (await saveAll.isVisible().catch(() => false)) {
      await saveAll.click();
      log.saved = true;
      await page.waitForTimeout(15000);
    }

    await page.goto(`${BASE}/general`, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(8000);
    log.afterPods = await page.evaluate(() =>
      [...document.querySelectorAll("tr")]
        .map((r) => r.innerText.replace(/\s+/g, " ").trim())
        .filter((t) => /maahed-ganjeh|RUNNING|Pending|ContainerCreating/i.test(t))
    );
    log.finalUrl = page.url();
    log.bump = BUMP;

    console.log(JSON.stringify({ ok: true, ...log }, null, 2));
  } catch (e) {
    console.log(JSON.stringify({ ok: false, detail: String(e), log }));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
