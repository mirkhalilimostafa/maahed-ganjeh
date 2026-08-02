const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

test.describe("functional — auth & navigation", () => {
  test("login success lands on sources status", async ({ page }) => {
    await login(page);
    await expect(page.getByText("وضعیت اتصالات")).toBeVisible();
    await expect(page.getByRole("heading", { name: "سپیدار", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "سایت maahed.ir", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "بات", exact: true })).toBeVisible();
  });

  test("bad password stays on login with error", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("نام کاربری").fill("admin");
    await page.getByLabel("رمز عبور").fill("wrong-password-xyz");
    await page.getByRole("button", { name: "ورود" }).click();
    await expect(page).toHaveURL(/login/);
    await expect(page.locator(".error")).toBeVisible({ timeout: 10000 });
  });
});

test.describe("functional — dashboard request flow", () => {
  test("create investor dashboard shows widgets + freshness + bot stub notify", async ({ page }) => {
    test.setTimeout(180_000);
    await login(page);
    await page.getByRole("link", { name: "ساخت داشبورد" }).click();
    await page.getByRole("button", { name: "ساخت پیشنهاد داشبورد" }).click();
    await page.waitForURL(/\/dashboards\/[0-9a-f-]+/, { timeout: 120000 });

    const widgets = page.locator(".widget");
    await expect(widgets.filter({ hasText: "عملکرد و رشد فروش" }).first()).toBeVisible();
    await expect(widgets.filter({ hasText: "داده مالی پایه" }).first()).toBeVisible();
    const freshness = page.locator(".widget .freshness");
    await expect(freshness.first()).toBeVisible();
    expect(await freshness.count()).toBeGreaterThanOrEqual(2);

    await expect(page.locator(".panel .meta").filter({ hasText: "لینک:" }).first()).toBeVisible();
  });

  test("incomplete short request is rejected or handled without crash", async ({ page }) => {
    await login(page);
    await page.getByRole("link", { name: "ساخت داشبورد" }).click();
    await page.locator("input").first().fill("ت");
    await page.locator("textarea").fill("اب");
    await page.getByRole("button", { name: "ساخت پیشنهاد داشبورد" }).click();
    await page.waitForTimeout(2000);
    await expect(page.locator("body")).not.toHaveText(/Cannot GET|Internal Server Error|Traceback/i);
  });

  test("revise after view updates dashboard", async ({ page }) => {
    test.setTimeout(240_000);
    await login(page);
    await page.getByRole("link", { name: "ساخت داشبورد" }).click();
    await page.getByRole("button", { name: "ساخت پیشنهاد داشبورد" }).click();
    await page.waitForURL(/\/dashboards\/[0-9a-f-]+/, { timeout: 120000 });

    await page.locator("textarea").fill("فروش سایت را جدا نگه دار و تازگی را حفظ کن");
    await page.getByRole("button", { name: "اعمال اصلاح" }).click();
    await expect(page.locator(".panel .meta").filter({ hasText: "وضعیت: revised" })).toBeVisible({
      timeout: 120000,
    });
    await expect(page.getByText("[اصلاح کاربر]: فروش سایت را جدا نگه دار")).toBeVisible();
  });
});

test.describe("functional — MVP checklist page", () => {
  test("MVP auto scenario completes checks", async ({ page }) => {
    test.setTimeout(300_000);
    await login(page);
    await page.getByRole("link", { name: "تست MVP" }).click();
    await page.getByRole("button", { name: /اجرای خودکار سناریوی MVP/ }).click();
    await expect(page.getByText("نتیجه اجرا")).toBeVisible({ timeout: 240000 });
    await expect(page.locator("pre")).toContainText('"dashboard_created": true');
    await expect(page.locator("pre")).toContainText('"freshness_on_each_widget": true');
  });
});

test.describe("functional — public dashboard link", () => {
  test("public /d/:id opens without auth", async ({ page, request }) => {
    const loginRes = await request.post("/api/auth/login", {
      form: {
        username: process.env.GANJEH_ADMIN_USER || "admin",
        password: process.env.GANJEH_ADMIN_PASS || "0Rshj3BPXgEuwdDL",
      },
    });
    expect(loginRes.ok()).toBeTruthy();
    const { access_token } = await loginRes.json();
    const createRes = await request.post("/api/dashboards", {
      headers: { Authorization: `Bearer ${access_token}` },
      data: {
        title: "E2E public",
        request_text: "داشبورد جلسه سرمایه‌گذار برای تست لینک عمومی",
      },
    });
    expect(createRes.ok()).toBeTruthy();
    const dash = await createRes.json();
    expect(dash.url).toMatch(/^https?:\/\//);
    await page.goto(`/d/${dash.public_id}`);
    await expect(page.getByRole("heading", { name: "E2E public", exact: true })).toBeVisible();
    await expect(page.locator(".widget .freshness").first()).toBeVisible();
  });
});

test.describe("functional — bot notify", () => {
  test("creating dashboard handles bot notify without crashing", async ({ request }) => {
    const loginRes = await request.post("/api/auth/login", {
      form: {
        username: process.env.GANJEH_ADMIN_USER || "admin",
        password: process.env.GANJEH_ADMIN_PASS || "0Rshj3BPXgEuwdDL",
      },
    });
    const { access_token } = await loginRes.json();
    const headers = { Authorization: `Bearer ${access_token}` };
    const createPayload = {
      title: "bot notify check",
      request_text: "جلسه سرمایه‌گذار — تست ارسال لینک به بات",
    };
    if (process.env.BOT_NOTIFY_RECIPIENT) {
      createPayload.notify_recipient = process.env.BOT_NOTIFY_RECIPIENT;
    }
    const createRes = await request.post("/api/dashboards", {
      headers,
      data: createPayload,
    });
    expect(createRes.ok()).toBeTruthy();
    const dash = await createRes.json();
    expect(["stub", "bale", "telegram", "multi"]).toContain(dash.bot_notify?.channel);
    if (dash.bot_notify?.ok && dash.bot_notify.channel === "stub") {
      const recent = await request.get("/api/bots/stub/recent", { headers });
      expect(recent.ok()).toBeTruthy();
      const body = await recent.json();
      expect(
        body.items.some(
          (i) =>
            (i.message || "").includes(dash.public_id) ||
            (i.payload?.dashboard_url || "").includes(dash.public_id),
        ),
      ).toBeTruthy();
    } else if (!dash.bot_notify?.ok) {
      // Without a numeric chat_id, Bale must not pretend username=admin is a recipient.
      expect(String(dash.bot_notify?.detail || "")).toMatch(/گیرنده|chat_id|BOT_NOTIFY|no such/i);
    }
  });
});
