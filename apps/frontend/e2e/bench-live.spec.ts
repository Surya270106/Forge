import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

const fixturePath = process.env.FORGE_BENCH_FIXTURE_FILE;

test('owner runs a benchmark through the real local API and Docker worker', async ({ page, context }) => {
  test.skip(!fixturePath, 'Requires a disposable local API, worker, and signed-in fixture');
  test.setTimeout(120_000);
  const fixture = JSON.parse(readFileSync(fixturePath!, 'utf8')) as { organization_id: string; token: string };
  const base = process.env.FORGE_PREVIEW_URL || 'http://localhost:13000';
  await context.addCookies([{ name: 'forge_session', value: fixture.token, url: base }]);
  await page.addInitScript((id) => localStorage.setItem('forge_org_id', id), fixture.organization_id);

  await page.goto('/bench');
  await expect(page.getByRole('heading', { name: 'New evaluation' })).toBeVisible();
  const tasks = page.locator('.bench-task-list input[type="checkbox"]');
  await expect(tasks).toHaveCount(12);
  for (let index = 1; index < 12; index += 1) await tasks.nth(index).uncheck();
  await page.getByRole('button', { name: 'Start local evaluation' }).click();
  await expect(page).toHaveURL(/\/bench\/[0-9a-f-]{36}$/);
  await expect(page.getByRole('heading', { name: 'Recorded outcomes' })).toBeVisible();
  await expect.poll(async () => (await page.locator('.bench-summary strong').first().textContent())?.trim(),
    { timeout: 90_000 }).toBe('COMPLETED');
  await expect(page.locator('.bench-trial')).toHaveCount(1);
  await expect(page.locator('.bench-trial')).toContainText('PASSED');
  await expect(page.locator('.bench-trial')).toContainText('protected-files');
  await expect(page.getByRole('link', { name: 'Open execution and Flight Recorder' })).toBeVisible();
  await page.reload();
  await expect(page.locator('.bench-trial')).toContainText('PASSED');
});
