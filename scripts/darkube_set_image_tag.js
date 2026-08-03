/**
 * Set Darkube docker image tag (forces pull of a specific build).
 * Env: HAMRAVESH_EMAIL, HAMRAVESH_PASSWORD, IMAGE_TAG
 */
const { chromium } = require("playwright");

const APP =
  "https://console.hamravesh.com/@maahedir/darkube/app/faf37c36-82fb-4989-872e-932c7b934ae7/general";
const EMAIL = process.env.HAMRAVESH_EMAIL || "";
const PASS = process.env.HAMRAVESH_PASSWORD || "";
const TAG = process.env.IMAGE_TAG || "";

if (!EMAIL || !PASS || !TAG) {
  console.log(JSON.stringify({ ok: false, detail: "missing EMAIL/PASS/IMAGE_TAG" }));
  process.exit(1);
}

async function setReactValue(page, selector, value) {
  await page.waitForSelector(selector, { state: "visible", timeout: 15000 });
  await page.evaluate(
    ({ selector, value }) => {
      const el = document.querySelector(selector);
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
    await page.goto(APP, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(6000);

    // Click the current tag (often "latest") near docker image section
    const tagBtn = page.getByText("latest", { exact: true }).first();
    if (await tagBtn.isVisible().catch(() => false)) {
      await tagBtn.click();
      await page.waitForTimeout(1500);
    }

    // Prefer an input for tag
    let set = false;
    for (const sel of ["#tag", "input[name='tag']", "input[id*='tag']", ".ant-select-selection-search-input"]) {
      if (await page.locator(sel).first().isVisible().catch(() => false)) {
        try {
          await setReactValue(page, sel, TAG);
          set = true;
          break;
        } catch {
          await page.locator(sel).first().fill(TAG).catch(() => null);
          set = true;
          break;
        }
      }
    }

    // Ant Design select: type tag and enter
    if (!set) {
      const search = page.locator(".ant-select-open input, .ant-select-focused input").first();
      if (await search.isVisible().catch(() => false)) {
        await search.fill(TAG);
        await page.keyboard.press("Enter");
        set = true;
      }
    }

    // Sometimes a free-text field appears after clicking edit on image
    const anyInput = page.locator("input").filter({ hasText: "" });
    // Save
    const save = page.getByRole("button", { name: /^ذخیره تغییرات$/ });
    if (await save.isVisible().catch(() => false)) {
      await save.click();
      await page.waitForTimeout(20000);
    }

    await page.goto(APP, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(6000);
    const after = await page.evaluate((tag) => ({
      hasTag: document.body.innerText.includes(tag),
      slice: document.body.innerText.replace(/\s+/g, " ").slice(0, 1800),
      pods: [...document.querySelectorAll("tr")]
        .map((r) => r.innerText.replace(/\s+/g, " ").trim())
        .filter((t) => /maahed-ganjeh|RUNNING|Pending|NOT READY/i.test(t)),
    }), TAG);

    console.log(JSON.stringify({ ok: after.hasTag || set, set, tag: TAG, after }, null, 2));
  } catch (e) {
    console.log(JSON.stringify({ ok: false, detail: String(e) }));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
