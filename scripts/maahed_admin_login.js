/**
 * Login to maahed.ir admin-panel, OCR captcha, print JSON status to stdout.
 * Env: MAAHED_SITE_USERNAME, MAAHED_SITE_PASSWORD
 */
const { chromium } = require("playwright");
const Tesseract = require("tesseract.js");
const fs = require("fs");
const path = require("path");
const os = require("os");

async function ocr(file) {
  const { data } = await Tesseract.recognize(file, "eng", {
    tessedit_char_whitelist: "0123456789",
  });
  return String(data.text || "").replace(/\D/g, "");
}

async function main() {
  const username = process.env.MAAHED_SITE_USERNAME || "";
  const password = process.env.MAAHED_SITE_PASSWORD || "";
  if (!username || !password) {
    console.log(JSON.stringify({ ok: false, detail: "missing credentials" }));
    process.exit(0);
  }

  const browser = await chromium.launch({
    ...(process.env.PLAYWRIGHT_CHANNEL
      ? { channel: process.env.PLAYWRIGHT_CHANNEL }
      : {}),
    headless: true,
  });
  const context = await browser.newContext();
  const page = await context.newPage();
  let last = { ok: false, detail: "not attempted" };

  try {
    await page.goto("https://maahed.ir/admin-panel/login", { waitUntil: "networkidle" });
    await page.click("#loginform-username", { clickCount: 3 });
    await page.keyboard.type(username, { delay: 10 });
    await page.click("#loginform-password", { clickCount: 3 });
    await page.keyboard.type(password, { delay: 10 });

    for (let i = 0; i < 5; i++) {
      await page.evaluate(() => {
        if (typeof captcha === "function") captcha(1);
      });
      await page.waitForTimeout(1000);
      const shot = path.join(os.tmpdir(), `maahed-captcha-${Date.now()}.png`);
      await page.locator(".image-captcha").screenshot({ path: shot });
      let code = await ocr(shot);
      try {
        fs.unlinkSync(shot);
      } catch {}
      if (code.length < 3) {
        last = { ok: false, detail: `ocr weak: ${code}` };
        continue;
      }
      code = code.slice(0, 3);
      await page.fill("#loginform-captcha", code);
      await Promise.all([
        page.waitForNavigation({ waitUntil: "networkidle", timeout: 45000 }).catch(() => null),
        page.click('button[name="login-button"]'),
      ]);
      if (!page.url().includes("login")) {
        const order = await page.goto("https://maahed.ir/admin-panel/order/index", {
          waitUntil: "domcontentloaded",
          timeout: 45000,
        });
        const body = await page.locator("body").innerText();
        const pick = (label) => {
          const re = new RegExp(label + "\\s*\\n\\s*([0-9۰-۹,]+)");
          const m = body.match(re);
          return m ? m[1] : null;
        };
        const cookies = await context.cookies();
        last = {
          ok: true,
          detail: "admin login ok",
          url: page.url(),
          title: await page.title(),
          order_http: order ? order.status() : null,
          counts: {
            paid: pick("پرداخت شده"),
            pending: pick("درانتظار پرداخت") || pick("در انتظار پرداخت"),
            failed: pick("پرداخت ناموفق"),
            cancelled: pick("لغو شده"),
          },
          cookies: cookies.map((c) => ({
            name: c.name,
            value: c.value,
            domain: c.domain,
            path: c.path,
          })),
        };
        break;
      }
      last = { ok: false, detail: `still on login after captcha ${code}` };
    }
  } catch (e) {
    last = { ok: false, detail: String(e) };
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(last));
}

main();
