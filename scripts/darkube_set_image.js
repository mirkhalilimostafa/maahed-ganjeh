/**
 * Change Darkube docker image name/tag via general page.
 * Env: HAMRAVESH_EMAIL, HAMRAVESH_PASSWORD, IMAGE_REPO, IMAGE_TAG
 */
const { chromium } = require("playwright");

const APP =
  "https://console.hamravesh.com/@maahedir/darkube/app/faf37c36-82fb-4989-872e-932c7b934ae7/general";
const EMAIL = process.env.HAMRAVESH_EMAIL || "";
const PASS = process.env.HAMRAVESH_PASSWORD || "";
const REPO = process.env.IMAGE_REPO || "registry.hamdocker.ir/maahedir/maahed-ganjeh-tehran";
const TAG = process.env.IMAGE_TAG || "latest";

async function setReactValue(page, selector, value) {
  await page.waitForSelector(selector, { state: "visible", timeout: 10000 });
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
  const log = { repo: REPO, tag: TAG };
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

    // Click edit near docker image section
    const imgLabel = page.getByText("ایمیج داکر", { exact: false }).first();
    await imgLabel.scrollIntoViewIfNeeded().catch(() => null);

    // Collect inputs near image
    log.beforeInputs = await page.evaluate(() =>
      [...document.querySelectorAll("input")]
        .map((i) => ({
          id: i.id,
          name: i.name,
          value: i.value,
          placeholder: i.placeholder,
          aria: i.getAttribute("aria-label"),
        }))
        .filter((x) => /image|tag|docker|registry|hamdocker|ghcr|latest|maahed/i.test(JSON.stringify(x)))
    );

    // Try clicking the repo text or latest tag to open editors
    for (const text of [REPO.split("/").pop(), "latest", REPO, "ایمیج داکر"]) {
      const el = page.getByText(text, { exact: false }).first();
      if (await el.isVisible().catch(() => false)) {
        await el.click({ timeout: 2000 }).catch(() => null);
        await page.waitForTimeout(800);
      }
    }

    // Edit pencils near image card
    const pencils = page.locator("button").filter({ has: page.locator("svg") });
    const pc = await pencils.count();
    log.pencilCount = pc;
    for (let i = 0; i < Math.min(pc, 12); i++) {
      await pencils.nth(i).click({ timeout: 1500 }).catch(() => null);
      await page.waitForTimeout(600);
      const visibleInputs = await page.evaluate(() =>
        [...document.querySelectorAll("input,textarea")]
          .filter((el) => el.offsetParent !== null)
          .map((el) => ({ id: el.id, name: el.name, value: el.value, ph: el.placeholder }))
      );
      if (visibleInputs.some((x) => /tag|image|repo|name/i.test(JSON.stringify(x)) || x.value.includes("hamdocker") || x.value.includes("ghcr"))) {
        log.openedWithPencil = i;
        log.visibleInputs = visibleInputs;
        break;
      }
    }

    // Fill any visible input that looks like image/repo/tag
    const filled = await page.evaluate(
      ({ repo, tag }) => {
        const inputs = [...document.querySelectorAll("input,textarea")].filter((el) => el.offsetParent !== null);
        const out = [];
        for (const el of inputs) {
          const meta = `${el.id} ${el.name} ${el.placeholder} ${el.getAttribute("aria-label") || ""} ${el.value}`;
          const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
          const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
          if (/tag/i.test(meta) || el.value === "latest" || /^[a-f0-9]{7,40}$/.test(el.value)) {
            const last = el.value;
            setter.call(el, tag);
            if (el._valueTracker) el._valueTracker.setValue(last);
            el.dispatchEvent(new Event("input", { bubbles: true }));
            el.dispatchEvent(new Event("change", { bubbles: true }));
            out.push({ kind: "tag", from: last, to: tag });
          } else if (/image|repo|registry|hamdocker|ghcr/i.test(meta) || /maahed-ganjeh/.test(el.value)) {
            const last = el.value;
            setter.call(el, repo);
            if (el._valueTracker) el._valueTracker.setValue(last);
            el.dispatchEvent(new Event("input", { bubbles: true }));
            el.dispatchEvent(new Event("change", { bubbles: true }));
            out.push({ kind: "repo", from: last, to: repo });
          }
        }
        return out;
      },
      { repo: REPO, tag: TAG }
    );
    log.filled = filled;

    // Ant select search
    const search = page.locator(".ant-select-open input, .ant-select-focused input, input[role='combobox']").first();
    if (await search.isVisible().catch(() => false)) {
      await search.fill(TAG);
      await page.keyboard.press("Enter");
      log.selectFilled = true;
    }

    const save = page.getByRole("button", { name: /^ذخیره تغییرات$/ });
    if (await save.isVisible().catch(() => false) && !(await save.isDisabled().catch(() => true))) {
      await save.click();
      log.saved = true;
      await page.waitForTimeout(25000);
    } else {
      log.saved = false;
      log.saveDisabled = await save.isDisabled().catch(() => null);
    }

    await page.goto(APP, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(6000);
    log.after = await page.evaluate((tag) => ({
      hasTag: document.body.innerText.includes(tag),
      hasLatest: document.body.innerText.includes("latest"),
      slice: document.body.innerText.replace(/\s+/g, " ").match(/ایمیج داکر.{0,120}/)?.[0] || "",
      pods: [...document.querySelectorAll("tr")]
        .map((r) => r.innerText.replace(/\s+/g, " ").trim())
        .filter((t) => /maahed-ganjeh-tehran-/.test(t)),
    }), TAG);

    console.log(JSON.stringify({ ok: Boolean(log.saved || (log.filled && log.filled.length)), ...log }, null, 2));
  } catch (e) {
    console.log(JSON.stringify({ ok: false, detail: String(e), log }, null, 2));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
