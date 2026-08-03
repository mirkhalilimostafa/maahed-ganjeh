/**
 * Set Darkube image tag via #tag / ant-select near docker image, keep uvicorn args intact.
 * Env: HAMRAVESH_EMAIL, HAMRAVESH_PASSWORD, IMAGE_TAG
 */
const { chromium } = require("playwright");

const APP =
  "https://console.hamravesh.com/@maahedir/darkube/app/faf37c36-82fb-4989-872e-932c7b934ae7/general";
const EMAIL = process.env.HAMRAVESH_EMAIL || "";
const PASS = process.env.HAMRAVESH_PASSWORD || "";
const TAG = process.env.IMAGE_TAG || "68b1078c673bcae817215e181455244a99e53870";

async function setReactValue(page, selector, value) {
  await page.waitForSelector(selector, { state: "visible", timeout: 10000 });
  await page.evaluate(
    ({ selector, value }) => {
      const el = document.querySelector(selector);
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
      const last = el.value;
      setter.call(el, value);
      if (el._valueTracker) el._valueTracker.setValue(last);
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
  const log = { tag: TAG };
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
    await page.waitForTimeout(7000);

    // Ensure uvicorn stays safe
    const args = await page.locator("#args").inputValue().catch(() => "");
    log.argsBefore = args;
    if (!/uvicorn app\.main:app/.test(args) || /urllib|raw\.githubusercontent/.test(args)) {
      await setReactValue(page, "#command", "/bin/sh -c");
      await setReactValue(page, "#args", "uvicorn app.main:app --host 0.0.0.0 --port 8000");
      log.fixedArgs = true;
    }

    // Discover image tag control
    log.inputs = await page.evaluate(() =>
      [...document.querySelectorAll("input,textarea")]
        .filter((el) => el.offsetParent !== null)
        .map((el) => ({
          id: el.id,
          value: (el.value || "").slice(0, 80),
          ph: el.placeholder,
          near: (el.closest("div")?.innerText || "").replace(/\s+/g, " ").slice(0, 100),
        }))
    );

    // Click the "latest" text that sits next to image repo
    const latestChip = page.locator("span,div,button").filter({ hasText: /^latest$/ }).first();
    if (await latestChip.isVisible().catch(() => false)) {
      await latestChip.click({ force: true });
      await page.waitForTimeout(1000);
      log.clickedLatest = true;
    }

    // Type SHA into open select/input
    const openInput = page.locator(".ant-select-open input, input:focus").first();
    if (await openInput.isVisible().catch(() => false)) {
      await openInput.fill(TAG);
      await page.keyboard.press("Enter");
      log.typedTag = true;
      await page.waitForTimeout(1000);
    }

    // Direct #tag if exists
    if (await page.locator("#tag").isVisible().catch(() => false)) {
      await setReactValue(page, "#tag", TAG);
      log.setTagField = true;
    }

    const save = page.getByRole("button", { name: /^ذخیره تغییرات$/ });
    const disabled = await save.isDisabled().catch(() => true);
    log.saveDisabled = disabled;
    if (!disabled) {
      await save.click();
      log.saved = true;
      await page.waitForTimeout(50000);
    }

    await page.goto(APP, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(8000);
    log.after = await page.evaluate((tag) => ({
      hasTag: document.body.innerText.includes(tag),
      imageSlice: (document.body.innerText.match(/ایمیج داکر[\s\S]{0,180}/) || [""])[0].replace(/\s+/g, " "),
      args: document.querySelector("#args")?.value,
      pods: [...document.querySelectorAll("tr")]
        .map((r) => r.innerText.replace(/\s+/g, " ").trim())
        .filter((t) => /maahed-ganjeh-tehran-|RUNNING|ERROR|NOT READY/i.test(t)),
      badge: (document.body.innerText.match(/\bhealthy\b|not ready/i) || [""])[0],
    }), TAG);

    console.log(JSON.stringify({ ok: Boolean(log.after?.hasTag || log.saved), ...log }, null, 2));
  } catch (e) {
    console.log(JSON.stringify({ ok: false, detail: String(e), log }, null, 2));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
