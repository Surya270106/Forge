import { expect, test } from '@playwright/test';

test('signed-in task reload shows persisted run evidence from the local API', async ({ page, request }) => {
  test.setTimeout(90000);
  const session = process.env.FORGE_LOCAL_SESSION;
  const organization = process.env.FORGE_LOCAL_ORGANIZATION;
  const plan = process.env.FORGE_LOCAL_PLAN;
  test.skip(!session || !organization || !plan || !process.env.FORGE_PREVIEW_URL, 'Requires an isolated local session and worker execution');

  await request.get('/api/v1/auth/me');
  await page.context().addCookies([{ name: 'forge_session', value: session!, url: process.env.FORGE_PREVIEW_URL!, httpOnly: true, sameSite: 'Lax' }]);
  await page.addInitScript(id => localStorage.setItem('forge_org_id', id), organization!);
  await page.goto(`/tasks/${plan}`);
  await expect(page.getByRole('navigation', { name: 'Plan views' })).toBeVisible({ timeout: 30000 });
  await page.getByRole('button', { name: 'Context Lens' }).click();
  await expect(page.getByRole('region', { name: 'Run Capsules' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Identity and integrity' })).toBeVisible();

  await page.reload();
  await page.getByRole('button', { name: 'Context Lens' }).click();
  await expect(page.getByRole('heading', { name: 'Identity and integrity' })).toBeVisible();
});
