const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./web/tests",
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:8080",
    trace: "on-first-retry",
  },
  reporter: "list",
});