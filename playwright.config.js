const { defineConfig, devices } = require('@playwright/test');

const external = process.env.QA_BASE_URL;
module.exports = defineConfig({
  testDir: './tests/browser',
  outputDir: './output/browser-qa/results',
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: true,
  workers: 2,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['json', { outputFile: 'output/browser-qa/receipt.json' }], ['html', { outputFolder: 'output/browser-qa/report', open: 'never' }]],
  use: {
    baseURL: external || 'http://127.0.0.1:18766',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: external ? undefined : {
    command: 'python3 scripts/browser_qa_server.py',
    url: 'http://127.0.0.1:18766',
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: 'pipe',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 7'], browserName: 'chromium' } },
    { name: 'mobile-webkit', use: { ...devices['iPhone 14'], browserName: 'webkit' } },
  ],
});
