import { expect, test } from '@playwright/test';

test('session check timeout offers a retry instead of an endless loading state', async ({ page }) => {
  test.setTimeout(30000);
  await page.route('**/api/v1/auth/me', async route => {
    await new Promise(resolve => setTimeout(resolve, 7000));
    await route.fulfill({ status: 200, body: '{}' }).catch(() => {});
  });
  await page.goto('/tasks');
  await expect(page.getByText('Workspace sign-in timed out.')).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
});
