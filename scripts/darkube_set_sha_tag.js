/**
 * Set Darkube image tag to immutable SHA (forces pull of bot-enabled image).
 * Env: HAMRAVESH_EMAIL, HAMRAVESH_PASSWORD, IMAGE_TAG
 */
const { chromium } = require("playwright");
const fs = require("fs");

const APP =
  "https://console.hamravesh.com/@maahedir/darkube/app/faf37c36-82fb-4989-872e-932c7b934ae7/general";
const EMAIL = process.env.HAMRAVESH_EMAIL || "";
const PASS = process.env.HAMRAVESH_PASSWORD || "";
const TAG = process.env.IMAGE_TAG || "68b1078c673bcae817215e181455244a99e53870";

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
    await page.goto(APP, { waitUntil: "networkidle", timeout: 90000 }).catch(() => null);
    await page.waitForTimeout(7000);

    // Dump nearby structure for image section
    log.domHint = await page.evaluate(() => {
      const nodes = [...document.querySelectorAll("*")].filter((el) =>
        /ایمیج داکر|hamdocker|maahed-ganjeh-tehran|latest/.test(el.innerText || "")
      );
      return nodes.slice(0, 15).map((el) => ({
        tag: el.tagName,
        cls: el.className?.toString?.().slice(0, 80),
        text: (el.innerText || "").replace(/\s+/g, " ").slice(0, 120),
      }));
    });

    // Click the visible "latest" chip/button under docker image
    const latest = page.locator("text=latest").first();
    await latest.click({ force: true });
    await page.waitForTimeout(1500);

    // Type into whatever focused/open select
    const active = page.locator("input:focus, .ant-select-open input, .ant-modal input, .ant-drawer input").first();
    if (await active.isVisible().catch(() => false)) {
      await active.fill("");
      await active.type(TAG, { delay: 10 });
      await page.keyboard.press("Enter");
      log.typedInto = "focused-input";
      await page.waitForTimeout(1000);
    } else {
      // Click ant-select near latest
      const selects = page.locator(".ant-select");
      const n = await selects.count();
      log.selectCount = n;
      for (let i = 0; i < n; i++) {
        const t = await selects.nth(i).innerText().catch(() => "");
        if (/latest|tag|تگ/i.test(t) || t.trim() === "latest") {
          await selects.nth(i).click();
          await page.waitForTimeout(500);
          const inp = page.locator(".ant-select-open input").first();
          if (await inp.isVisible().catch(() => false)) {
            await inp.fill(TAG);
            await page.keyboard.press("Enter");
            log.typedInto = `select-${i}`;
            break;
          }
        }
      }
    }

    // If a modal with confirm
    const ok = page.getByRole("button", { name: /تأیید|تایید|OK|اعمال|ذخیره/i }).first();
    if (await ok.isVisible().catch(() => false)) {
      await ok.click();
      log.modalOk = true;
    }

    const save = page.getByRole("button", { name: /^ذخیره تغییرات$/ });
    const canSave = await save.isVisible().catch(() => false);
    const disabled = canSave ? await save.isDisabled().catch(() => true) : true;
    log.canSave = canSave;
    log.saveDisabled = disabled;
    if (canSave && !disabled) {
      await save.click();
      log.saved = true;
      await page.waitForTimeout(30000);
    }

    await page.goto(APP, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(8000);
    log.after = await page.evaluate((tag) => ({
      hasTag: document.body.innerText.includes(tag),
      imageSlice: (document.body.innerText.match(/ایمیج داکر[\s\S]{0,200}/) || [""])[0].replace(/\s+/g, " "),
      pods: [...document.querySelectorAll("tr")]
        .map((r) => r.innerText.replace(/\s+/g, " ").trim())
        .filter((t) => /maahed-ganjeh-tehran-/.test(t)),
    }), TAG);

    await page.screenshot({ path: "tmp_darkube_image_tag.png", fullPage: true }).catch(() => null);
    console.log(JSON.stringify({ ok: Boolean(log.saved || log.after?.hasTag), ...log }, null, 2));
  } catch (e) {
    console.log(JSON.stringify({ ok: false, detail: String(e), log }, null, 2));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
