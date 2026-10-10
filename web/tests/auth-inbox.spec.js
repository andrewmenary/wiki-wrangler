const { test, expect } = require("@playwright/test");

test("a new user can register and reach the Inbox", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByLabel("Display name")).toBeHidden();
  await page.getByRole("button", { name: "Create an account" }).click();
  await expect(page.getByLabel("Display name")).toBeVisible();

  const email = `playwright-${Date.now()}@example.com`;
  await page.getByLabel("Display name").fill("Browser Test User");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page.getByRole("heading", { name: "Inbox" })).toBeVisible();
  await expect(page.getByText("Signed in as Browser Test User.", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Display name")).toBeHidden();
});