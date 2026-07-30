/**
 * Upsert BALE_BOT_TOKEN + TELEGRAM_BOT_TOKEN as secure Darkube env vars.
 * Env: HAMRAVESH_EMAIL, HAMRAVESH_PASSWORD, BALE_BOT_TOKEN, TELEGRAM_BOT_TOKEN
 */
const { chromium } = require("playwright");

const APP_ENVS =
  "https://console.hamravesh.com/@maahedir/darkube/app/faf37c36-82fb-4989-872e-932c7b934ae7/envs";
const EMAIL = process.env.HAMRAVESH_EMAIL || "";
const PASS = process.env.HAMRAVESH_PASSWORD || "";
const BALE = process.env.BALE_BOT_TOKEN || "";
const TG = process.env.TELEGRAM_BOT_TOKEN || "";

if (!EMAIL || !PASS || !BALE || !TG) {
  console.log(JSON.stringify({ ok: false, detail: "missing env credentials/tokens" }));
  process.exit(1);
}

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

async function closeDrawerIfOpen(page) {
  const close = page.locator(".ant-drawer-open .ant-drawer-close, .ant-drawer .ant-drawer-close").first();
  if (await close.isVisible().catch(() => false)) {
    await close.click();
    await page.waitForTimeout(600);
  }
}

async function clickDrawerSave(page) {
  const btn = page.locator(".ant-drawer-open button, .ant-drawer button").filter({ hasText: /^ذخیره$/ }).first();
  await btn.click({ timeout: 10000 });
  await page.waitForTimeout(1500);
}

async function openAddSecure(page) {
  await closeDrawerIfOpen(page);
  await page.getByRole("button", { name: /افزودن متغیر محیطی/ }).click();
  await page.waitForTimeout(400);
  // dropdown items
  const secure = page.getByText("افزودن متغیر محیطی امن", { exact: true }).first();
  await secure.click({ timeout: 10000 });
  await page.waitForSelector(".ant-drawer #name, #name", { state: "visible", timeout: 15000 });
}

async function addSecure(page, key, value) {
  await openAddSecure(page);
  await setReactValue(page, "#name", key);
  await setReactValue(page, "#value", value);
  await clickDrawerSave(page);
  await closeDrawerIfOpen(page);
  return "added";
}

async function updateExisting(page, key, value) {
  await closeDrawerIfOpen(page);
  const row = page.locator("tr").filter({ hasText: key }).first();
  await row.waitFor({ timeout: 10000 });
  // Prefer edit icon button inside row (usually 2nd or titled)
  const buttons = row.locator("button");
  const count = await buttons.count();
  let clicked = false;
  for (let i = 0; i < count; i++) {
    const b = buttons.nth(i);
    const label = ((await b.getAttribute("aria-label")) || "") + (await b.innerText());
    if (/edit|ویرایش|pencil/i.test(label)) {
      await b.click();
      clicked = true;
      break;
    }
  }
  if (!clicked) {
    // Heuristic: skip first (often eye/reveal), click second; else last-but-one
    if (count >= 2) await buttons.nth(1).click();
    else if (count >= 1) await buttons.first().click();
    else throw new Error("no row buttons for " + key);
  }
  await page.waitForTimeout(1200);
  // Secure edit may only expose value, or require replace flow
  const hasValue = await page.locator("#value").isVisible().catch(() => false);
  if (!hasValue) {
    // try clicking "تغییر مقدار" / similar
    const change = page.getByText(/تغییر|ویرایش مقدار|Replace|Update/i).first();
    if (await change.isVisible().catch(() => false)) await change.click();
    await page.waitForTimeout(800);
  }
  const still = await page.locator("#value").isVisible().catch(() => false);
  if (!still) {
    await closeDrawerIfOpen(page);
    return "skipped_no_value_field";
  }
  await setReactValue(page, "#value", value);
  await clickDrawerSave(page);
  await closeDrawerIfOpen(page);
  return "updated";
}

async function upsert(page, key, value) {
  const has = await page.evaluate((k) => document.body.innerText.includes(k), key);
  if (has) return updateExisting(page, key, value);
  return addSecure(page, key, value);
}

(async () => {
  const browser = await chromium.launch({
    channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
    headless: true,
  });
  const page = await browser.newPage();
  try {
    await page.goto("https://console.hamravesh.com/login", { waitUntil: "domcontentloaded", timeout: 60000 });
    if (page.url().includes("login")) {
      await page.fill("#email", EMAIL);
      await page.fill("#password", PASS);
      await page.locator('button[type="submit"]').first().click();
      await page.waitForTimeout(4500);
    }
    await page.goto(APP_ENVS, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(4500);

    const before = {
      bale: await page.evaluate(() => document.body.innerText.includes("BALE_BOT_TOKEN")),
      tg: await page.evaluate(() => document.body.innerText.includes("TELEGRAM_BOT_TOKEN")),
    };

    // Add missing Telegram first (cleaner), then refresh Bale value if possible
    const actions = {};
    if (!before.tg) actions.TELEGRAM_BOT_TOKEN = await addSecure(page, "TELEGRAM_BOT_TOKEN", TG);
    else actions.TELEGRAM_BOT_TOKEN = await updateExisting(page, "TELEGRAM_BOT_TOKEN", TG);

    if (before.bale) actions.BALE_BOT_TOKEN = await updateExisting(page, "BALE_BOT_TOKEN", BALE);
    else actions.BALE_BOT_TOKEN = await addSecure(page, "BALE_BOT_TOKEN", BALE);

    const saveAll = page.getByRole("button", { name: /^ذخیره تغییرات$/ });
    if (await saveAll.isVisible().catch(() => false)) {
      await saveAll.click();
      await page.waitForTimeout(10000);
    }

    await page.goto(APP_ENVS, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(4500);
    const after = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll("tr"))
        .map((r) => r.innerText.replace(/\s+/g, " ").trim())
        .filter((t) => /BALE_BOT_TOKEN|TELEGRAM_BOT_TOKEN/.test(t));
      return {
        bale: document.body.innerText.includes("BALE_BOT_TOKEN"),
        tg: document.body.innerText.includes("TELEGRAM_BOT_TOKEN"),
        rows,
      };
    });

    console.log(JSON.stringify({ ok: after.bale && after.tg, before, actions, after }, null, 2));
    if (!(after.bale && after.tg)) process.exitCode = 1;
  } catch (e) {
    console.log(JSON.stringify({ ok: false, detail: String(e) }));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
