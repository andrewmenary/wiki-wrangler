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

  await expect(page.getByRole("heading", { name: "Inbox", exact: true })).toBeVisible();
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

test("a capture can be reviewed with metadata and approved", async ({ page }) => {
  const unique = Date.now();
  const registration = await page.request.post("/api/auth/register", {
    data: {
      display_name: "Review Test User",
      email: `review-${unique}@example.com`,
      password: "password123",
    },
  });
  expect(registration.status()).toBe(201);

  const category = await page.request.post("/api/categories", {
    data: { name: "Runbooks", path: `test-${unique}/runbooks` },
  });
  expect(category.status()).toBe(201);
  const categoryBody = await category.json();

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Inbox" })).toBeVisible();
  await page.getByLabel("Capture title").fill("Service restart runbook");
  await page.getByLabel("Upload a Markdown or text file").setInputFiles({
    name: "runbook.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Restart the service after changing configuration."),
  });
  await page.getByRole("button", { name: "Upload and convert" }).click();
  await expect(page.locator("#capture-message")).toHaveText(
    "Uploaded and converted. Added to inbox.",
  );
  const item = page.locator(".item").filter({ hasText: "Service restart runbook" });
  await expect(item).toBeVisible();
  const itemId = await item.getByRole("button").getAttribute("data-item-id");
  await item.getByRole("button").click();

  await expect(page.locator("#review-title")).toHaveText("Service restart runbook");
  await page.getByLabel("Title", { exact: true }).fill("Service restart runbook v2");
  await page.getByLabel("Summary").fill("Steps for restarting the service.");
  await page.getByLabel("Tags").fill("operations, runbook, operations");
  await page.getByLabel("Category").selectOption(categoryBody.id);
  await page.getByLabel("Markdown draft").fill("# Restart the service\n\nFollow the maintenance window.");
  await page.getByRole("button", { name: "Save changes" }).click();

  await expect(page.locator("#review-message")).toHaveText("Changes saved.");
  await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.locator("#review-message")).toHaveText("Approved for publishing.");
  const renamedItem = page.locator(".item").filter({ hasText: "Service restart runbook v2" });
  await expect(renamedItem).toContainText("approved");

  const detail = await page.request.get(`/api/items/${itemId}`);
  expect(detail.status()).toBe(200);
  const detailBody = await detail.json();
  expect(detailBody.title).toBe("Service restart runbook v2");
  expect(detailBody.status).toBe("approved");
  expect(detailBody.summary).toBe("Steps for restarting the service.");
  expect(detailBody.tags).toEqual(["operations", "runbook"]);
  expect(detailBody.category_id).toBe(categoryBody.id);
  expect(detailBody.markdown_final).toBe("# Restart the service\n\nFollow the maintenance window.");
});

test("an Inbox capture can be discarded without deleting its history", async ({ page }) => {
  const unique = Date.now();
  const registration = await page.request.post("/api/auth/register", {
    data: {
      display_name: "Archive Test User",
      email: `archive-${unique}@example.com`,
      password: "password123",
    },
  });
  expect(registration.status()).toBe(201);

  const capture = await page.request.post("/api/items", {
    data: { title: "Discard from Inbox", source_type: "manual" },
  });
  expect(capture.status()).toBe(201);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Inbox", exact: true })).toBeVisible();
  const item = page.locator(".item").filter({ hasText: "Discard from Inbox" });
  await item.getByRole("button").click();
  await expect(page.getByRole("button", { name: "Archive" })).toBeVisible();
  await page.getByRole("button", { name: "Archive" }).click();
  await expect(page.locator("#review-message")).toHaveText(
    "Archived. The capture remains available in Inbox history.",
  );
  await expect(page.getByRole("button", { name: "Save changes" })).toBeHidden();
  await expect(item).toContainText("archived");
});