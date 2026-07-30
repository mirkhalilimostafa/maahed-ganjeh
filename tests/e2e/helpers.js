const ADMIN_USER = process.env.GANJEH_ADMIN_USER || "admin";
const ADMIN_PASS = process.env.GANJEH_ADMIN_PASS || "0Rshj3BPXgEuwdDL";

async function login(page) {
  await page.goto("/login");
  await page.getByLabel("نام کاربری").fill(ADMIN_USER);
  await page.getByLabel("رمز عبور").fill(ADMIN_PASS);
  await page.getByRole("button", { name: "ورود" }).click();
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 20000 });
}

module.exports = { login, ADMIN_USER, ADMIN_PASS };
