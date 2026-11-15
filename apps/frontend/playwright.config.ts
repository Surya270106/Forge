import { defineConfig, devices } from '@playwright/test';
import path from 'path';

const previewURL = process.env.FORGE_PREVIEW_URL || 'http://localhost:3000';

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  expect: {
    timeout: 5000
  },
  fullyParallel: false, // Run tests sequentially to avoid DB lock issues during E2E
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Single worker for predictable execution
  reporter: 'html',
  use: {
    actionTimeout: 0,
    baseURL: previewURL,
    trace: 'on-first-retry',
    video: process.env.FORGE_PREVIEW_URL ? 'off' : 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], launchOptions: process.env.FORGE_CHROMIUM_PATH ? { executablePath: process.env.FORGE_CHROMIUM_PATH } : undefined },
    }
  ],
  webServer: process.env.FORGE_PREVIEW_URL ? [] : [
    {
      command: 'npm run dev',
      port: 3000,
      timeout: 120 * 1000,
      reuseExistingServer: true,
    },
    // We assume backend is started separately via run_integration.py or similar
  ],
});
