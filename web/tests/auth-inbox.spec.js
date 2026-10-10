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

test("categories can be created, listed, edited, and deleted", async ({ page }) => {
  const unique = Date.now();
  const registration = await page.request.post("/api/auth/register", {
    data: {
      display_name: "Category Test User",
      email: `categories-${unique}@example.com`,
      password: "password123",
    },
  });
  expect(registration.status()).toBe(201);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Inbox" })).toBeVisible();
  await page.getByText("Manage categories", { exact: true }).click();

  const categoryForm = page.locator("#category-form");
  const originalPath = `test-${unique}/notes`;
  const editedPath = `test-${unique}/guides`;
  await categoryForm.getByLabel("Name", { exact: true }).fill("Notes");
  await categoryForm.getByLabel("Path", { exact: true }).fill(originalPath);
  await categoryForm.getByRole("button", { name: "Create category" }).click();

  const originalRow = page.locator(".category-row").filter({ hasText: originalPath });
  await expect(originalRow).toBeVisible();

  await categoryForm.getByLabel("Name", { exact: true }).fill("Duplicate");
  await categoryForm.getByLabel("Path", { exact: true }).fill(originalPath);
  await categoryForm.getByRole("button", { name: "Create category" }).click();
  await expect(page.locator("#category-message")).toHaveText("Category path already exists");
  await expect(originalRow).toHaveCount(1);

  await originalRow.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(categoryForm.getByLabel("Name", { exact: true })).toHaveValue("Notes");
  await categoryForm.getByLabel("Name", { exact: true }).fill("Guides");
  await categoryForm.getByLabel("Path", { exact: true }).fill(editedPath);
  await categoryForm.getByRole("button", { name: "Save category" }).click();
  const editedRow = page.locator(".category-row").filter({ hasText: editedPath });
  await expect(editedRow).toBeVisible();
  await expect(originalRow).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("heading", { name: "Inbox" })).toBeVisible();
  await page.getByText("Manage categories", { exact: true }).click();
  await editedRow.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(categoryForm.getByLabel("Name", { exact: true })).toHaveValue("Guides");
  await expect(categoryForm.getByLabel("Path", { exact: true })).toHaveValue(editedPath);

  await editedRow.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.locator("#category-message")).toHaveText("Category deleted.");
  await expect(editedRow).toHaveCount(0);
});