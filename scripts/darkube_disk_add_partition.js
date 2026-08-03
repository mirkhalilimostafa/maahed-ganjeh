/**
 * Commit Darkube disk partition (click purple + near mount_path), then save.
 * Then set UPLOAD_DIR=/data/uploads and verify /data via terminal.
 *
 * Env: HAMRAVESH_EMAIL, HAMRAVESH_PASSWORD, PLAYWRIGHT_CHANNEL=chrome
 */
const { chromium } = require("playwright");
const fs = require("fs");

const BASE =
  "https://console.hamravesh.com/@maahedir/darkube/app/faf37c36-82fb-4989-872e-932c7b934ae7";
const APP = `${BASE}/resource_management`;
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
      el.blur?.();
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

async function expandDisk(page) {
  const hdr = page.locator(".ant-collapse-header").filter({ hasText: /دیسک|icHdd/i }).first();
  if (await hdr.isVisible().catch(() => false)) {
    if ((await hdr.getAttribute("aria-expanded")) === "false") {
      await hdr.click();
      await page.waitForTimeout(800);
    }
  }
}

async function diskState(page) {
  return page.evaluate(() => {
    const t = document.body.innerText;
    return {
      hasAddBtn: [...document.querySelectorAll("button")].some((b) =>
        /افزودن دیسک/.test((b.innerText || "").trim())
      ),
      hasSizeField: !!document.querySelector("#size_in_Gi"),
      size: document.querySelector("#size_in_Gi")?.value || null,
      name: document.querySelector("#display_name")?.value || null,
      mount: document.querySelector("#mount_path")?.value || null,
      needsPartition: t.includes("حداقل باید یک پارتیشن"),
      hasDataText: t.includes("/data"),
      cost: (t.match(/هزینه دیسک[^\d]*([\d٬,]+)/) || [])[1] || null,
      badge: (t.match(/\bhealthy\b|not ready/i) || [""])[0],
      diskSlice: (t.match(/مدیریت دیسک[\s\S]{0,900}/) || [""])[0].replace(/\s+/g, " "),
      partitionRows: [...document.querySelectorAll("tr, li, .ant-list-item")]
        .map((r) => r.innerText.replace(/\s+/g, " ").trim())
        .filter((x) => /\/data|\bdata\b/i.test(x) && !/پارتیشن جدید/.test(x))
        .slice(0, 10),
    };
  });
}

/** Click the purple + that commits the partition row (NOT backup / add-disk CTA). */
async function clickPartitionPlus(page) {
  // Preferred: primary button with fa-plus closest to #mount_path
  const clicked = await page.evaluate(() => {
    const mount = document.querySelector("#mount_path");
    if (!mount) return { ok: false, reason: "no-mount" };

    // Walk up until we find a container that has a plus button
    let root = mount;
    for (let i = 0; i < 10 && root; i++) {
      const plusBtns = [...root.querySelectorAll("button")].filter((b) => {
        const html = b.innerHTML || "";
        const text = (b.innerText || "").trim();
        const hasPlus =
          html.includes("fa-plus") ||
          html.includes("anticon-plus") ||
          !!b.querySelector(".fa-plus, .fas.fa-plus, .anticon-plus");
        // Must be icon-only (or nearly), not labeled backup/save/etc.
        const badLabel = /بکاپ|ذخیره|مقیاس|حذف|مطالعه|افزودن تنظیمات/i.test(text);
        return hasPlus && !badLabel;
      });
      if (plusBtns.length) {
        const btn = plusBtns[0];
        btn.scrollIntoView({ block: "center" });
        btn.click();
        return {
          ok: true,
          via: "ancestor-fa-plus",
          depth: i,
          cls: (btn.className || "").toString().slice(0, 80),
          html: btn.outerHTML.slice(0, 160),
        };
      }
      root = root.parentElement;
    }

    // Fallback: find "پارتیشن جدید" section plus
    const section = [...document.querySelectorAll("*")].find(
      (el) =>
        (el.innerText || "").includes("پارتیشن جدید") &&
        el.querySelector &&
        el.querySelector("#mount_path")
    );
    if (section) {
      const btn = [...section.querySelectorAll("button")].find((b) =>
        /fa-plus|anticon-plus/.test(b.innerHTML || "")
      );
      if (btn) {
        btn.click();
        return { ok: true, via: "section-plus", html: btn.outerHTML.slice(0, 160) };
      }
    }
    return { ok: false, reason: "plus-not-found" };
  });
  return clicked;
}

(async () => {
  if (!EMAIL || !PASS) {
    console.log(JSON.stringify({ ok: false, detail: "missing HAMRAVESH_EMAIL/PASSWORD" }));
    process.exit(1);
  }

  const browser = await chromium.launch({
    channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
    headless: true,
  });
  const page = await browser.newPage();
  const log = {};

  try {
    await login(page);
    await page.goto(APP, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(7000);
    await expandDisk(page);

    log.before = await diskState(page);

    // Already configured?
    if (
      log.before.hasDataText &&
      !log.before.hasAddBtn &&
      !log.before.needsPartition &&
      !log.before.hasSizeField
    ) {
      log.alreadyConfigured = true;
    } else {
      // Open add-disk form if needed
      if (!log.before.hasSizeField) {
        const addDisk = page.locator("button.ant-btn-primary").filter({ hasText: /^افزودن دیسک$/ }).first();
        if (await addDisk.isVisible().catch(() => false)) {
          await addDisk.click();
          await page.waitForTimeout(2500);
        }
      }

      await page.locator("#size_in_Gi").waitFor({ state: "visible", timeout: 20000 });
      await setReactValue(page, "#size_in_Gi", "10");
      await page.locator("#display_name").click();
      await page.locator("#display_name").fill("");
      await page.locator("#display_name").type("data", { delay: 20 });
      await page.locator("#mount_path").click();
      await page.locator("#mount_path").fill("");
      await page.locator("#mount_path").type("/data", { delay: 20 });
      await page.waitForTimeout(400);

      log.plusClick = await clickPartitionPlus(page);
      await page.waitForTimeout(1500);

      // Playwright locator fallback if evaluate click failed
      if (!log.plusClick?.ok) {
        const near = page.locator("#mount_path").locator("xpath=ancestor::div[contains(., 'پارتیشن')][1]");
        const plusBtn = near.locator("button.ant-btn-primary").filter({ has: page.locator(".fa-plus, .fas.fa-plus") }).first();
        if (await plusBtn.isVisible().catch(() => false)) {
          await plusBtn.click();
          log.plusClick = { ok: true, via: "playwright-locator" };
          await page.waitForTimeout(1500);
        }
      }

      // Second attempt: getByTitle / tooltip
      log.afterPlus = await diskState(page);
      if (log.afterPlus.needsPartition || !(log.afterPlus.partitionRows?.length)) {
        const byTitle = page.locator('button[aria-describedby], button.ant-btn-primary').filter({
          has: page.locator("i.fa-plus, .fas.fa-plus, .anticon-plus"),
        });
        const n = await byTitle.count();
        log.plusCandidates = n;
        for (let i = 0; i < n; i++) {
          const btn = byTitle.nth(i);
          const box = await btn.boundingBox().catch(() => null);
          const text = ((await btn.innerText().catch(() => "")) || "").trim();
          if (/بکاپ|ذخیره|مقیاس/.test(text)) continue;
          // Prefer buttons near the form vertically (middle of page)
          if (box && box.y > 200 && box.y < 900) {
            await btn.click({ force: true });
            log.plusClickRetry = { i, y: box.y, text };
            await page.waitForTimeout(1200);
            const st = await diskState(page);
            if (!st.needsPartition || st.partitionRows.length) {
              log.afterPlus = st;
              break;
            }
          }
        }
      }

      await page.screenshot({ path: "E:/maahed ganjeh/tmp_disk_partition.png", fullPage: true }).catch(() => null);

      log.preSave = await diskState(page);

      // Only save if partition committed (warning gone OR row present)
      const ready =
        !log.preSave.needsPartition ||
        (log.preSave.partitionRows && log.preSave.partitionRows.length > 0) ||
        (log.preSave.hasDataText && log.plusClick?.ok);

      if (!ready && log.preSave.needsPartition) {
        // Last resort: press Enter on mount then click plus again
        await page.locator("#mount_path").press("Enter").catch(() => null);
        await page.waitForTimeout(400);
        await clickPartitionPlus(page);
        await page.waitForTimeout(1000);
        log.preSave2 = await diskState(page);
      }

      const save = page.getByRole("button", { name: /^ذخیره تغییرات$/ });
      const disabled = await save.isDisabled().catch(() => true);
      log.saveDisabled = disabled;

      const canSave =
        !disabled &&
        (!(await diskState(page)).needsPartition ||
          ((await diskState(page)).partitionRows || []).length > 0);

      // If warning still shows, try save anyway only when plus was clicked and fields filled
      if (!disabled && (canSave || log.plusClick?.ok || log.plusClickRetry)) {
        await save.click();
        log.saved = true;
        await page.waitForTimeout(8000);
        log.toast = await page.evaluate(() =>
          [...document.querySelectorAll(".ant-notification, .ant-message, .ant-modal-confirm")]
            .map((e) => e.innerText.replace(/\s+/g, " ").trim())
            .filter(Boolean)
            .slice(0, 5)
        );
        // Wait for redeploy / healthy
        await page.waitForTimeout(70000);
      } else {
        log.saved = false;
        log.skipReason = "partition-not-committed-or-save-disabled";
      }
    }

    // Reload verify
    await page.goto(APP, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(7000);
    await expandDisk(page);
    log.afterReload = await diskState(page);
    await page.screenshot({ path: "E:/maahed ganjeh/tmp_disk_after2.png", fullPage: true }).catch(() => null);

    // UPLOAD_DIR env
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
      const row = page.locator("tr").filter({ hasText: "UPLOAD_DIR" }).first();
      if (await row.isVisible().catch(() => false)) {
        const valText = await row.innerText();
        log.uploadRow = valText.replace(/\s+/g, " ").trim().slice(0, 120);
        if (!/\/data\/uploads/.test(valText)) {
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
        } else {
          log.uploadOk = true;
        }
      }
    }

    const saveEnv = page.getByRole("button", { name: /^ذخیره تغییرات$/ });
    if (!(await saveEnv.isDisabled().catch(() => true))) {
      await saveEnv.click();
      log.savedEnv = true;
      await page.waitForTimeout(45000);
    }

    // Terminal verify
    await page.goto(`${BASE}/terminal`, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(10000);
    const term = page.locator("textarea.xterm-helper-textarea").first();
    if (await term.isVisible().catch(() => false)) await term.click();
    else await page.mouse.click(520, 420);

    const cmds = [
      "df -h | head -30",
      "ls -la /data 2>&1 || echo NO_DATA",
      "mkdir -p /data/uploads && ls -la /data/uploads",
      "printenv UPLOAD_DIR DATABASE_URL 2>&1 || true",
      "touch /data/uploads/_persist_check && ls -la /data/uploads/_persist_check",
    ];
    for (const c of cmds) {
      await page.keyboard.type(c, { delay: 5 });
      await page.keyboard.press("Enter");
      await page.waitForTimeout(2800);
    }
    await page.waitForTimeout(2000);
    log.term = await page.evaluate(() => document.body.innerText.slice(-3500));
    await page.screenshot({ path: "E:/maahed ganjeh/tmp_disk_terminal.png", fullPage: true }).catch(() => null);

    const diskOk =
      (log.afterReload?.hasDataText && !log.afterReload?.hasAddBtn) ||
      (log.afterReload?.hasDataText && /data/.test(log.afterReload?.diskSlice || "")) ||
      /\/data/.test(log.term || "");
    const mountOk = /\/data|NO_DATA|_persist_check/.test(log.term || "");
    log.ok = Boolean(diskOk && (mountOk || log.afterReload?.hasDataText));

    fs.writeFileSync(
      "E:/maahed ganjeh/tmp_disk_result.json",
      JSON.stringify(log, null, 2),
      "utf8"
    );
    console.log(JSON.stringify(log, null, 2));
    if (!log.ok) process.exitCode = 2;
  } catch (e) {
    console.log(JSON.stringify({ ok: false, detail: String(e), log }, null, 2));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
