import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

const fixturePath = process.env.FORGE_CANCEL_FIXTURE_FILE;

test('owner cancels a real Docker execution through the task workspace', async ({ page, context }) => {
  test.skip(!fixturePath, 'Requires the disposable local cancellation stack and fixture');
  test.setTimeout(120_000);
  const fixture = JSON.parse(readFileSync(fixturePath!, 'utf8')) as {
    organization_id: string; user_id: string; plan_id: string; token: string;
  };
  const base = process.env.FORGE_PREVIEW_URL || 'http://localhost:13000';
  const headers = { 'X-Organization-Id': fixture.organization_id };
  await context.addCookies([{ name: 'forge_session', value: fixture.token, url: base }]);
  await page.addInitScript((id) => localStorage.setItem('forge_org_id', id), fixture.organization_id);
  await page.goto(`/tasks/${fixture.plan_id}`);
  await expect(page.getByRole('button', { name: 'Start execution' }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Start execution' }).first().click();

  let executionId = '';
  await expect.poll(async () => {
    const response = await page.request.get(`${base}/api/v1/executions/plans/${fixture.plan_id}/latest`, { headers });
    if (!response.ok()) return false;
    const job = await response.json();
    executionId = job.id;
    return job.status === 'RUNNING';
  }, { timeout: 30_000 }).toBe(true);

  let sandboxId = '';
  await expect.poll(async () => {
    const response = await page.request.get(`${base}/api/v1/executions/${executionId}/timeline?cursor=0&limit=50`, { headers });
    if (!response.ok()) return false;
    const timeline = await response.json();
    const created = timeline.events.find((event: { event_type: string }) => event.event_type === 'sandbox.created');
    sandboxId = created?.data?.sandbox_id || '';
    return Boolean(sandboxId);
  }, { timeout: 30_000 }).toBe(true);

  page.once('dialog', (dialog) => dialog.accept());
  const accepted = page.waitForResponse((response) => response.url().endsWith(`/${executionId}/cancel`));
  await page.getByRole('button', { name: 'Cancel execution' }).click();
  expect((await accepted).status()).toBe(202);
  await expect(page.locator('.console-actions strong')).toHaveText('Cancellation requested');
  await expect(page.locator('.console-actions strong')).toHaveText('CANCELLED', { timeout: 30_000 });

  const jobResponse = await page.request.get(`${base}/api/v1/executions/${executionId}`, { headers });
  expect(jobResponse.ok()).toBe(true);
  const job = await jobResponse.json();
  expect(job.status).toBe('CANCELLED');
  expect(job.cancellation_requested_at).toBeTruthy();
  const timelineResponse = await page.request.get(`${base}/api/v1/executions/${executionId}/timeline?cursor=0&limit=100`, { headers });
  const timeline = (await timelineResponse.json()).events as { event_type: string; actor_id: string | null }[];
  const events = timeline.map((event) => event.event_type);
  expect(events).toContain('execution.cancel_requested');
  expect(events).toContain('execution.cancellation_started');
  expect(events).toContain('execution.cancelled');
  expect(events).not.toContain('execution.completed');
  expect(timeline.find((event) => event.event_type === 'execution.cancel_requested')?.actor_id).toBe(fixture.user_id);
  expect(() => execFileSync('docker', ['inspect', `forge-sandbox-${sandboxId}`], { stdio: 'ignore' })).toThrow();
  const persisted = execFileSync('docker', ['exec', 'forge-cancel-pg', 'psql', '-U', 'postgres',
    '-d', 'forge_e2e_cancel_browser', '-At', '-c',
    `SELECT status::text, cancellation_requested_at IS NOT NULL FROM execution_jobs WHERE id = '${executionId}'`],
  { encoding: 'utf8' }).trim();
  expect(persisted).toBe('CANCELLED|t');

  const repeated = await page.request.post(`${base}/api/v1/executions/${executionId}/cancel`, {
    headers: { ...headers, Origin: base },
  });
  expect(repeated.status()).toBe(200);
  expect((await repeated.json()).status).toBe('CANCELLED');
  const afterRepeat = await page.request.get(`${base}/api/v1/executions/${executionId}/timeline?cursor=0&limit=100`, { headers });
  expect((await afterRepeat.json()).events.length).toBe(timeline.length);

  await page.reload();
  await page.getByRole('navigation', { name: 'Plan views' }).getByRole('button', { name: 'Execution' }).click();
  await expect(page.locator('.console-actions strong')).toHaveText('CANCELLED');
  await expect(page.getByText('Execution cancelled').first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cancel execution' })).toHaveCount(0);
});
