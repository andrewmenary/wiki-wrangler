const { test, expect } = require("@playwright/test");

test("a user can register, restore a session, sign out, and sign back in", async ({ page }) => {
  const greeting = page.locator("#app-view").getByText("Signed in as Browser Test User.", { exact: true });
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
  await expect(greeting).toBeVisible();
  await expect(page.getByLabel("Display name")).toBeHidden();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Inbox" })).toBeVisible();
  await expect(greeting).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await expect(page.getByLabel("Display name")).toBeHidden();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText("Invalid email or password", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Inbox" })).toBeHidden();

  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Inbox" })).toBeVisible();
  await expect(greeting).toBeVisible();
});