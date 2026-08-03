/**
 * Add 10Gi Darkube disk with partition data -> /data, then set UPLOAD_DIR=/data/uploads.
 * Env: HAMRAVESH_EMAIL, HAMRAVESH_PASSWORD
 */
const { chromium } = require("playwright");

const BASE =
  "https://console.hamravesh.com/@maahedir/darkube/app/faf37c36-82fb-4989-872e-932c7b934ae7";
const EMAIL = process.env.HAMRAVESH_EMAIL || "";
const PASS = process.env.HAMRAVESH_PASSWORD || "";

async function setReactValue(page, selector, value) {
  await page.waitForSelector(selector, { state: "visible", timeout: 15000 });
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

async function login(page) {
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
}

(async () => {
  const browser = await chromium.launch({
    channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
    headless: true,
  });
  const page = await browser.newPage();
  const log = {};
  try {
    await login(page);
    await page.goto(`${BASE}/resource_management`, {
      waitUntil: "domcontentloaded",
      timeout: 90000,
    });
    await page.waitForTimeout(7000);

    const hasDisk = await page.evaluate(() => {
      const t = document.body.innerText;
      return (/حجم دیسک|size_in_Gi|\/data/.test(t) && document.querySelector("#size_in_Gi")) ||
        (/پارتیشن|GiB/.test(t) && /data/.test(t) && !/افزودن دیسک/.test(t));
    });

    // If add button visible and no configured disk form, click add
    const addBtn = page.locator("button.ant-btn-primary").filter({ hasText: /افزودن دیسک/ }).first();
    if (await addBtn.isVisible().catch(() => false)) {
      // Check whether disk editor already open (#size_in_Gi)
      if (!(await page.locator("#size_in_Gi").isVisible().catch(() => false))) {
        await addBtn.click();
        await page.waitForTimeout(2500);
      }
    }

    await page.locator("#size_in_Gi").waitFor({ state: "visible", timeout: 20000 });
    await setReactValue(page, "#size_in_Gi", "10");
    await setReactValue(page, "#display_name", "data");
    await setReactValue(page, "#mount_path", "/data");
    log.diskFields = await page.evaluate(() => ({
      size: document.querySelector("#size_in_Gi")?.value,
      name: document.querySelector("#display_name")?.value,
      mount: document.querySelector("#mount_path")?.value,
    }));

    const saveAll = page.getByRole("button", { name: /^ذخیره تغییرات$/ });
    // nudge dirty
    if (await saveAll.isDisabled().catch(() => true)) {
      await setReactValue(page, "#mount_path", "/data ");
      await setReactValue(page, "#mount_path", "/data");
    }
    await saveAll.click();
    log.savedDisk = true;
    await page.waitForTimeout(70000);

    await page.goto(`${BASE}/resource_management`, {
      waitUntil: "domcontentloaded",
      timeout: 90000,
    });
    await page.waitForTimeout(6000);
    log.afterDisk = await page.evaluate(() => ({
      badge: (document.body.innerText.match(/\bhealthy\b|not ready/i) || [""])[0],
      hasData: document.body.innerText.includes("/data"),
      hasSize: /10|GiB|حجم/.test(document.body.innerText),
      diskSlice: (document.body.innerText.match(/مدیریت دیسک[\s\S]{0,600}/) || [""])[0].replace(/\s+/g, " "),
      costSlice: (document.body.innerText.match(/هزینه دیسک[\s\S]{0,80}/) || [""])[0],
    }));

    // Set UPLOAD_DIR=/data/uploads on envs page
    await page.goto(`${BASE}/envs`, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(6000);
    const hasUpload = await page.evaluate(() => document.body.innerText.includes("UPLOAD_DIR"));
    log.hasUploadEnv = hasUpload;

    if (!hasUpload) {
      await page.getByRole("button", { name: /افزودن متغیر محیطی/ }).click();
      await page.waitForTimeout(600);
      const items = page.locator(".ant-dropdown-menu-item, [role='menuitem']");
      const n = await items.count();
      let clicked = false;
      for (let i = 0; i < n; i++) {
        const t = ((await items.nth(i).innerText()) || "").trim();
        if (t && !/امن/.test(t)) {
          await items.nth(i).click();
          clicked = true;
          break;
        }
      }
      if (!clicked && n > 0) await items.first().click();
      await page.waitForTimeout(1000);
      await setReactValue(page, "#name", "UPLOAD_DIR");
      await setReactValue(page, "#value", "/data/uploads");
      await page
        .locator(".ant-drawer-open button, .ant-drawer button")
        .filter({ hasText: /^ذخیره$/ })
        .first()
        .click();
      await page.waitForTimeout(1500);
      log.addedUploadEnv = true;
    } else {
      // update existing row
      const row = page.locator("tr").filter({ hasText: "UPLOAD_DIR" }).first();
      if (await row.isVisible().catch(() => false)) {
        const buttons = row.locator("button");
        const c = await buttons.count();
        for (let i = 0; i < c; i++) {
          await buttons.nth(i).click();
          await page.waitForTimeout(700);
          if (await page.locator("#value").isVisible().catch(() => false)) break;
          await page.keyboard.press("Escape").catch(() => null);
        }
        if (await page.locator("#value").isVisible().catch(() => false)) {
          await setReactValue(page, "#value", "/data/uploads");
          await page
            .locator(".ant-drawer-open button, .ant-drawer button")
            .filter({ hasText: /^ذخیره$/ })
            .first()
            .click();
          await page.waitForTimeout(1000);
          log.updatedUploadEnv = true;
        }
      }
    }

    const saveEnv = page.getByRole("button", { name: /^ذخیره تغییرات$/ });
    if (!(await saveEnv.isDisabled().catch(() => true))) {
      await saveEnv.click();
      log.savedEnv = true;
      await page.waitForTimeout(45000);
    }

    // Verify mounts via terminal
    await page.goto(`${BASE}/terminal`, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(8000);
    const term = page.locator("textarea.xterm-helper-textarea").first();
    if (await term.isVisible().catch(() => false)) await term.click();
    else await page.mouse.click(500, 420);

    const cmds = [
      "df -h | head -20",
      "ls -la /data || echo NO_DATA",
      "mkdir -p /data/uploads && ls -la /data/uploads",
      "printenv UPLOAD_DIR DATABASE_URL | cat",
      "touch /data/uploads/_persist_check && ls -la /data/uploads/_persist_check",
    ];
    for (const c of cmds) {
      await page.keyboard.type(c, { delay: 2 });
      await page.keyboard.press("Enter");
      await page.waitForTimeout(2500);
    }
    log.term = await page.evaluate(() => document.body.innerText.slice(-3000));

    const ok =
      Boolean(log.afterDisk?.hasData || /\/data/.test(log.term || "")) &&
      /_persist_check|uploads/.test(log.term || "");
    console.log(JSON.stringify({ ok, ...log }, null, 2));
    if (!ok) process.exitCode = 2;
  } catch (e) {
    console.log(JSON.stringify({ ok: false, detail: String(e), log }, null, 2));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
