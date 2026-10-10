const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./web/tests",
  timeout: 30_000,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:8081",
    trace: "on-first-retry",
  },
  reporter: "list",
});