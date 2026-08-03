/**
 * Open Darkube general page, capture image editor DOM, set tag to SHA, keep uvicorn.
 */
const { chromium } = require("playwright");

const APP =
  "https://console.hamravesh.com/@maahedir/darkube/app/faf37c36-82fb-4989-872e-932c7b934ae7/general";
const EMAIL = process.env.HAMRAVESH_EMAIL || "";
const PASS = process.env.HAMRAVESH_PASSWORD || "";
const TAG = process.env.IMAGE_TAG || "68b1078c673bcae817215e181455244a99e53870";
const IMAGE = process.env.IMAGE_REPO || "registry.hamdocker.ir/maahedir/maahed-ganjeh-tehran";

(async () => {
  const browser = await chromium.launch({
    channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
    headless: true,
  });
  const page = await browser.newPage();
  const log = { tag: TAG, image: IMAGE };
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

    // Keep uvicorn safe
    await page.locator("#args").waitFor({ state: "visible", timeout: 15000 });
    const args = await page.inputValue("#args");
    if (/urllib|githubusercontent/.test(args)) {
      await page.fill("#command", "/bin/sh -c");
      await page.fill("#args", "uvicorn app.main:app --host 0.0.0.0 --port 8000");
    }

    // Click the blue image repo link / latest link
    const imgLink = page.locator(`a,button,span`).filter({ hasText: IMAGE.split("/").slice(-1)[0] }).first();
    const latestLink = page.getByText("latest", { exact: true }).first();

    // Prefer clicking exact image path text
    const repoText = page.getByText(IMAGE, { exact: false }).first();
    if (await repoText.isVisible().catch(() => false)) {
      await repoText.click({ force: true });
      log.clickedRepo = true;
      await page.waitForTimeout(2000);
    }
    if (await latestLink.isVisible().catch(() => false)) {
      await latestLink.click({ force: true });
      log.clickedLatest = true;
      await page.waitForTimeout(2000);
    }

    // Dump modal/drawer content
    log.modal = await page.evaluate(() => {
      const roots = [
        ...document.querySelectorAll(".ant-modal, .ant-drawer, .ant-popover, [role='dialog']"),
      ];
      return roots.map((r) => ({
        cls: r.className?.toString?.().slice(0, 80),
        text: (r.innerText || "").replace(/\s+/g, " ").slice(0, 500),
        inputs: [...r.querySelectorAll("input,textarea")].map((i) => ({
          id: i.id,
          value: i.value,
          ph: i.placeholder,
        })),
      }));
    });

    // Fill any visible inputs that look like image/tag
    const filled = await page.evaluate(
      ({ image, tag }) => {
        const out = [];
        const inputs = [...document.querySelectorAll("input,textarea")].filter((el) => el.offsetParent !== null);
        for (const el of inputs) {
          const meta = `${el.id} ${el.name} ${el.placeholder} ${el.value}`;
          const near = (el.closest(".ant-form-item,div")?.innerText || "").slice(0, 80);
          const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
          const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
          const set = (v) => {
            const last = el.value;
            setter.call(el, v);
            if (el._valueTracker) el._valueTracker.setValue(last);
            el.dispatchEvent(new Event("input", { bubbles: true }));
            el.dispatchEvent(new Event("change", { bubbles: true }));
          };
          if (/tag|تگ/i.test(meta + near) || el.value === "latest") {
            set(tag);
            out.push({ kind: "tag", id: el.id, near });
          } else if (/image|ایمیج|repo|registry/i.test(meta + near) || /hamdocker|maahed-ganjeh/.test(el.value)) {
            // if field expects full image:repo:tag
            if (/:/.test(el.value) || /hamdocker/.test(el.value)) {
              set(`${image}:${tag}`);
              out.push({ kind: "image:tag", id: el.id, near });
            } else {
              set(image);
              out.push({ kind: "image", id: el.id, near });
            }
          }
        }
        return out;
      },
      { image: IMAGE, tag: TAG }
    );
    log.filled = filled;

    // Confirm in modal
    for (const name of [/^اعمال$/, /^تأیید$/, /^تایید$/, /^OK$/, /^ذخیره$/]) {
      const b = page.getByRole("button", { name }).first();
      if (await b.isVisible().catch(() => false)) {
        await b.click();
        log.modalBtn = String(name);
        await page.waitForTimeout(1500);
      }
    }

    const save = page.getByRole("button", { name: /^ذخیره تغییرات$/ });
    if (!(await save.isDisabled().catch(() => true))) {
      await save.click();
      log.saved = true;
      await page.waitForTimeout(55000);
    } else {
      log.saved = false;
      log.saveDisabled = true;
    }

    await page.goto(APP, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(8000);
    log.after = await page.evaluate((tag) => ({
      hasTag: document.body.innerText.includes(tag),
      imageSlice: (document.body.innerText.match(/ایمیج داکر[\s\S]{0,220}/) || [""])[0].replace(/\s+/g, " "),
      args: document.querySelector("#args")?.value,
      pods: [...document.querySelectorAll("tr")]
        .map((r) => r.innerText.replace(/\s+/g, " ").trim())
        .filter((t) => /maahed-ganjeh-tehran-|RUNNING|ERROR|NOT READY/i.test(t)),
      badge: (document.body.innerText.match(/\bhealthy\b|not ready/i) || [""])[0],
    }), TAG);

    await page.screenshot({ path: "tmp_image_editor.png", fullPage: true }).catch(() => null);
    console.log(JSON.stringify({ ok: Boolean(log.after?.hasTag), ...log }, null, 2));
  } catch (e) {
    console.log(JSON.stringify({ ok: false, detail: String(e), log }, null, 2));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
