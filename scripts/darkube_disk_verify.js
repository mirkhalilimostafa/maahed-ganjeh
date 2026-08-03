/**
 * Verify Darkube disk after attach: UI shows /data, healthy, replicas=1,
 * terminal can ls /data, UPLOAD_DIR present.
 */
const { chromium } = require("playwright");

const BASE =
  "https://console.hamravesh.com/@maahedir/darkube/app/faf37c36-82fb-4989-872e-932c7b934ae7";
const EMAIL = process.env.HAMRAVESH_EMAIL || "";
const PASS = process.env.HAMRAVESH_PASSWORD || "";

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

    // Wait until healthy (disk attach can take a while)
    for (let i = 0; i < 24; i++) {
      await page.goto(`${BASE}/resource_management`, {
        waitUntil: "domcontentloaded",
        timeout: 90000,
      });
      await page.waitForTimeout(5000);
      const hdr = page.locator(".ant-collapse-header").filter({ hasText: /دیسک|icHdd/i }).first();
      if (await hdr.isVisible().catch(() => false)) {
        if ((await hdr.getAttribute("aria-expanded")) === "false") await hdr.click();
        await page.waitForTimeout(600);
      }
      const st = await page.evaluate(() => {
        const t = document.body.innerText;
        return {
          badge: (t.match(/\bhealthy\b|not ready/i) || [""])[0],
          hasData: /پارتیشن‌های دیسک[\s\S]{0,80}\/data|data\s*\/data/.test(t) || t.includes("/data"),
          hasAddOnly: /افزودن دیسک/.test(t) && !/پارتیشن‌های دیسک/.test(t),
          size: document.querySelector("#size_in_Gi")?.value || null,
          replica: (t.match(/تعداد Replica[^\d]*(\d+)/) || t.match(/Replica[^\d]*(\d+)/) || [])[1] || null,
          diskSlice: (t.match(/مدیریت دیسک[\s\S]{0,700}/) || [""])[0].replace(/\s+/g, " "),
          cost: (t.match(/هزینه دیسک[^\n\d]*([\d٬,]+)/) || [])[1] || null,
        };
      });
      log.ui = st;
      log.waitIter = i;
      if (/healthy/i.test(st.badge) && st.hasData && !st.hasAddOnly) break;
      await page.waitForTimeout(10000);
    }

    await page.screenshot({ path: "E:/maahed ganjeh/tmp_disk_verify_ui.png", fullPage: true }).catch(() => null);

    // Envs check
    await page.goto(`${BASE}/envs`, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(5000);
    log.envs = await page.evaluate(() => {
      const t = document.body.innerText;
      return {
        upload: (t.match(/UPLOAD_DIR[^\n]{0,80}/) || [""])[0].replace(/\s+/g, " "),
        db: (t.match(/DATABASE_URL[^\n]{0,120}/) || [""])[0].replace(/\s+/g, " "),
      };
    });

    // Terminal
    await page.goto(`${BASE}/terminal`, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(12000);
    log.termConnect = await page.evaluate(() => ({
      err: document.body.innerText.includes("خطا در اتصال"),
      notReady: /not ready/i.test(document.body.innerText),
      healthy: /healthy/i.test(document.body.innerText),
    }));

    if (!log.termConnect.err) {
      const term = page.locator("textarea.xterm-helper-textarea").first();
      if (await term.isVisible().catch(() => false)) await term.click();
      else await page.mouse.click(520, 420);
      for (const c of [
        "df -h",
        "ls -la /data",
        "mkdir -p /data/uploads && touch /data/uploads/_persist_check && ls -la /data/uploads",
        "printenv UPLOAD_DIR DATABASE_URL",
      ]) {
        await page.keyboard.type(c, { delay: 4 });
        await page.keyboard.press("Enter");
        await page.waitForTimeout(2500);
      }
      await page.waitForTimeout(1500);
      log.term = await page.evaluate(() => document.body.innerText.slice(-2500));
    } else {
      // retry once
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForTimeout(15000);
      log.termConnect2 = await page.evaluate(() => ({
        err: document.body.innerText.includes("خطا در اتصال"),
        badge: (document.body.innerText.match(/\bhealthy\b|not ready/i) || [""])[0],
      }));
      if (!log.termConnect2.err) {
        const term = page.locator("textarea.xterm-helper-textarea").first();
        if (await term.isVisible().catch(() => false)) await term.click();
        else await page.mouse.click(520, 420);
        for (const c of ["df -h | grep -E 'data|Filesystem'", "ls -la /data", "printenv UPLOAD_DIR"]) {
          await page.keyboard.type(c, { delay: 4 });
          await page.keyboard.press("Enter");
          await page.waitForTimeout(2500);
        }
        log.term = await page.evaluate(() => document.body.innerText.slice(-2000));
      }
    }

    await page.screenshot({ path: "E:/maahed ganjeh/tmp_disk_verify_term.png", fullPage: true }).catch(() => null);

    // External health
    try {
      const r = await fetch("https://maahed-ganjeh-tehran.darkube.app/health").catch(() => null);
      log.healthHttp = r ? { status: r.status, body: (await r.text()).slice(0, 200) } : null;
    } catch (e) {
      log.healthHttp = { err: String(e) };
    }

    log.ok =
      Boolean(log.ui?.hasData) &&
      !log.ui?.hasAddOnly &&
      /UPLOAD_DIR\s*\/data\/uploads/.test(log.envs?.upload || "") &&
      (/healthy/i.test(log.ui?.badge || "") || log.healthHttp?.status === 200);

    console.log(JSON.stringify(log, null, 2));
    if (!log.ok) process.exitCode = 2;
  } catch (e) {
    console.log(JSON.stringify({ ok: false, detail: String(e), log }, null, 2));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
