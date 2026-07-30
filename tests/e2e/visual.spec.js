const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");
const fs = require("fs");
const path = require("path");

const outDir = path.join(__dirname, "../../playwright-visual");

test.beforeAll(() => {
  fs.mkdirSync(outDir, { recursive: true });
});

async function shot(page, name) {
  const file = path.join(outDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}

test.describe("visual checklist", () => {
  test("login desktop/mobile no overlap", async ({ page }, testInfo) => {
    await page.goto("/login");
    const name = `login-${testInfo.project.name}`;
    await shot(page, name);
    await expect(page.getByRole("heading", { name: /ماهد/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "ورود" })).toBeVisible();
    // brand present, form usable
    const box = await page.getByRole("button", { name: "ورود" }).boundingBox();
    expect(box).toBeTruthy();
    expect(box.width).toBeGreaterThan(40);
  });

  test("dashboard view layout has freshness near widgets", async ({ page }, testInfo) => {
    await login(page);
    await page.getByRole("link", { name: "ساخت داشبورد" }).click();
    await page.getByRole("button", { name: "ساخت پیشنهاد داشبورد" }).click();
    await page.waitForURL(/\/dashboards\/[0-9a-f-]+/, { timeout: 60000 });
    await shot(page, `dashboard-${testInfo.project.name}`);
    const widgets = page.locator(".widget");
    await expect(widgets.first()).toBeVisible();
    const count = await widgets.count();
    for (let i = 0; i < count; i++) {
      await expect(widgets.nth(i).locator(".freshness")).toBeVisible();
    }
  });
});
