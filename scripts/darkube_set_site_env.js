/**
 * Permanently set MAAHED_SITE_* on Darkube ganjeh app.
 * Requires: HAMRAVESH_EMAIL, HAMRAVESH_PASSWORD, MAAHED_SITE_USERNAME, MAAHED_SITE_PASSWORD
 */
const { chromium } = require("playwright");

const APP_ENVS =
  "https://console.hamravesh.com/@maahedir/darkube/app/faf37c36-82fb-4989-872e-932c7b934ae7/envs";
const EMAIL = process.env.HAMRAVESH_EMAIL || "";
const PASS = process.env.HAMRAVESH_PASSWORD || "";
const SITE_USER = process.env.MAAHED_SITE_USERNAME || "";
const SITE_PASS = process.env.MAAHED_SITE_PASSWORD || "";

if (!EMAIL || !PASS || !SITE_USER || !SITE_PASS) {
  console.log(
    JSON.stringify({
      ok: false,
      detail: "Set HAMRAVESH_EMAIL, HAMRAVESH_PASSWORD, MAAHED_SITE_USERNAME, MAAHED_SITE_PASSWORD",
    })
  );
  process.exit(1);
}

async function setReactValue(page, selector, value) {
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

async function upsertEnv(page, key, value) {
  const hasKey = await page.evaluate((key) => document.body.innerText.includes(key), key);
  if (hasKey) {
    await page.evaluate((key) => {
      const row = Array.from(document.querySelectorAll("tr")).find((r) => r.innerText.includes(key));
      if (!row) throw new Error("row not found " + key);
      const buttons = Array.from(row.querySelectorAll("button"));
      (buttons[1] || buttons[0]).click();
    }, key);
    await page.waitForTimeout(700);
    await setReactValue(page, "#value, textarea#value, input#value", value);
    await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll("button")).find((b) => b.textContent.trim() === "ذخیره");
      if (btn) btn.click();
    });
    await page.waitForTimeout(900);
    return "updated";
  }

  // Add via menu
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll("button")).find((b) =>
      (b.textContent || "").includes("افزودن متغیر محیطی")
    );
    if (!btn) throw new Error("add button missing");
    btn.click();
  });
  await page.waitForTimeout(400);
  const secure = /PASSWORD|TOKEN|SECRET/i.test(key);
  await page.evaluate((secure) => {
    const items = Array.from(document.querySelectorAll('[role="menuitem"]'));
    const want = secure ? "افزودن متغیر محیطی امن" : "افزودن متغیر محیطی";
    const item = items.find((i) => i.textContent.trim() === want) || items.find((i) => i.textContent.includes("افزودن متغیر محیطی"));
    if (!item) throw new Error("menu item missing");
    item.click();
  }, secure);
  await page.waitForSelector("#name, input#name", { timeout: 15000 });
  await setReactValue(page, "#name, input#name", key);
  await setReactValue(page, "#value, textarea#value, input#value", value);
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll("button")).find((b) => b.textContent.trim() === "ذخیره");
    if (btn) btn.click();
  });
  await page.waitForTimeout(1000);
  return "added";
}

(async () => {
  const browser = await chromium.launch({
    channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
    headless: true,
  });
  const page = await browser.newPage();
  try {
    await page.goto("https://console.hamravesh.com/login", { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(1000);
    if (page.url().includes("login")) {
      await page.fill("#email", EMAIL);
      await page.fill("#password", PASS);
      await page.locator('button[type="submit"]').first().click();
      await page.waitForTimeout(4000);
    }

    await page.goto(APP_ENVS, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(3500);

    const actions = {
      MAAHED_SITE_USERNAME: await upsertEnv(page, "MAAHED_SITE_USERNAME", SITE_USER),
      MAAHED_SITE_PASSWORD: await upsertEnv(page, "MAAHED_SITE_PASSWORD", SITE_PASS),
      MAAHED_SITE_BASE_URL: await upsertEnv(page, "MAAHED_SITE_BASE_URL", "https://maahed.ir"),
      MAAHED_SITE_ADMIN_LOGIN_PATH: await upsertEnv(page, "MAAHED_SITE_ADMIN_LOGIN_PATH", "/admin-panel/login"),
    };

    await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll("button")).find((b) =>
        b.textContent.trim() === "ذخیره تغییرات"
      );
      if (btn) btn.click();
    });
    await page.waitForTimeout(8000);

    const text = await page.locator("body").innerText();
    console.log(
      JSON.stringify({
        ok: text.includes("MAAHED_SITE_USERNAME") && text.includes("MAAHED_SITE_PASSWORD"),
        actions,
        hasUser: text.includes("MAAHED_SITE_USERNAME"),
        hasPassMasked: text.includes("MAAHED_SITE_PASSWORD"),
        hasBase: text.includes("MAAHED_SITE_BASE_URL"),
        hasPath: text.includes("MAAHED_SITE_ADMIN_LOGIN_PATH"),
        url: page.url(),
      })
    );
  } catch (e) {
    console.log(JSON.stringify({ ok: false, detail: String(e) }));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
