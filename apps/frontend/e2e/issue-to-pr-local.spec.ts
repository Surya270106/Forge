import { expect, test } from '@playwright/test';

test('local issue workflow and confirmed mocked publication survive reload', async ({ page }) => {
  test.setTimeout(90000);
  const token = process.env.FORGE_LOCAL_SESSION;
  const org = process.env.FORGE_LOCAL_ORGANIZATION;
  const repo = process.env.FORGE_LOCAL_REPOSITORY;
  const plan = process.env.FORGE_LOCAL_PLAN;
  const issue = process.env.FORGE_LOCAL_ISSUE;
  test.skip(!token || !org || !repo || !plan || !issue || !process.env.FORGE_PREVIEW_URL,
    'Requires disposable local API, database, worker fixture, and browser session');

  await page.context().addCookies([{ name: 'forge_session', value: token!, url: process.env.FORGE_PREVIEW_URL!, httpOnly: true, sameSite: 'Lax' }]);
  await page.addInitScript(id => localStorage.setItem('forge_org_id', id), org!);
  await page.goto(`/repositories/${repo}`);
  await expect(page.getByRole('region', { name: 'GitHub issue to pull request' })).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole('button', { name: new RegExp(`#${issue}.*PUBLISHED`, 'i') })).toBeVisible();
  await page.getByRole('button', { name: new RegExp(`#${issue}.*PUBLISHED`, 'i') }).click();
  await expect(page.getByRole('link', { name: /Review plan and evidence/ })).toHaveAttribute('href', `/tasks/${plan}`);
  await page.getByRole('link', { name: /Review plan and evidence/ }).click();
  await expect(page.getByRole('region', { name: 'Source GitHub issue' })).toContainText(`#${issue}`);
  await expect(page.getByRole('region', { name: 'Source GitHub issue' })).toContainText('PUBLISHED');
  await page.reload();
  await expect(page.getByRole('region', { name: 'Source GitHub issue' })).toContainText(`#${issue}`);
  await page.getByRole('button', { name: /Change review/ }).click();
  await expect(page.getByText('GitHub publication: SUCCEEDED')).toBeVisible();
});
