import { expect, test } from '@playwright/test';

const workspaceId = '11111111-1111-4111-8111-111111111111';
const repository = { id: 'repo-1', owner: 'surya', name: 'forge', status: 'READY', default_branch: 'main', indexing_status: 'COMPLETED' };
const plan = { id: 'plan-1', repository_id: 'repo-1', intent: 'Add regression tests for OAuth session expiry', status: 'APPROVED', created_at: '2026-10-29T10:00:00Z', nodes: [{ id: 'node-1', action_type: 'edit_file', target: 'tests/security/test_sessions.py', parameters: { changes: 'Add expiry coverage' } }] };

async function mockAPI(page: import('@playwright/test').Page, options: { populated?: boolean; staleApproval?: boolean; githubStatus?: number; executionLookupStatus?: number; executionStatusCode?: number; sessionStatus?: number; verificationStatus?: string; publishStatus?: string } = {}) {
  await page.addInitScript((id) => localStorage.setItem('forge_org_id', id), workspaceId);
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/auth/me' && options.sessionStatus) return route.fulfill({ status: options.sessionStatus, body: '{}' });
    if (path === '/api/v1/repositories/github-repos' && options.githubStatus) return route.fulfill({ status: options.githubStatus, body: '{}' });
    if (path === '/api/v1/executions/plans/plan-1/latest' && options.executionLookupStatus) return route.fulfill({ status: options.executionLookupStatus, body: '{}' });
    if (path === '/api/v1/executions/job-1' && options.executionStatusCode) return route.fulfill({ status: options.executionStatusCode, body: '{}' });
    if (path === '/api/v1/patches/patch-1/accept' && route.request().method() === 'POST') {
      expect(JSON.parse(route.request().postData() || '{}').review_digest).toBe('digest-1');
      return route.fulfill({ status: options.staleApproval ? 409 : 200, contentType: 'application/json', body: JSON.stringify({ id: 'patch-1', status: 'ACCEPTED', publish_status: 'NOT_REQUESTED' }) });
    }
    if (path === '/api/v1/auth/workspaces/current/provider/test') {
      return route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ detail: 'OpenAI rejected the provider key' }) });
    }
    const data: Record<string, unknown> = {
      '/api/v1/auth/me': { id: 'user-1', name: 'Developer', email: 'developer@example.test' },
      '/api/v1/auth/workspaces': { workspaces: [{ id: workspaceId, name: 'Engineering', role: 'OWNER' }] },
      '/api/v1/auth/workspaces/current/provider': { config: options.populated ? { provider: 'openai', api_key: 'sk-...1234', model: 'gpt-4o' } : {} },
      '/api/v1/repositories/github-repos': { repositories: [] },
      '/api/v1/repositories/imported': { repositories: options.populated ? [repository] : [] },
      '/api/v1/plans': { plans: options.populated ? [plan] : [] },
      '/api/v1/plans/plan-1': plan,
      '/api/v1/executions/plans/plan-1/latest': { id: 'job-1', status: 'COMPLETED' },
      '/api/v1/executions/job-1': { id: 'job-1', status: 'COMPLETED' },
      '/api/v1/executions/job-1/logs': [],
      '/api/v1/executions/job-1/mutations': { mutations: [] },
      '/api/v1/verifications/executions/job-1/latest': { id: 'verify-1', status: options.verificationStatus || 'PASSED', results: [{ verifier: 'pytest', status: options.verificationStatus || 'PASSED', exit_code: options.verificationStatus === 'FAILED' ? 1 : 0, duration_ms: 800, attempt: 1, diagnostics: [] }] },
      '/api/v1/verifications/verify-1/repair': { id: 'repair-1', status: 'ELIGIBLE', attempt_number: 1, repair_plan_id: null, error_message: null, feedback: 'Tests failed' },
      '/api/v1/patches/executions/job-1': { id: 'patch-1', status: options.publishStatus ? 'ACCEPTED' : 'GENERATED', publish_status: options.publishStatus || 'NOT_REQUESTED', publish_error: options.publishStatus === 'FAILED' ? 'GITHUB_ACCESS_DENIED' : null, pull_request_url: null, files_changed: 2, total_additions: 4, total_deletions: 1 },
      '/api/v1/patches/patch-1/review': { review_digest: 'digest-1', base_commit_sha: 'abc123', changes: [{ path: 'tests/security/test_sessions.py', diff: '@@ -1 +1 @@\n-old\n+new' }, { path: 'services/auth/api.py', diff: '@@ -2 +2 @@\n-before\n+after' }] },
    };
    return route.fulfill({ status: path in data ? 200 : 404, contentType: 'application/json', body: JSON.stringify(data[path] || {}) });
  });
}

test('first-run dashboard points to a real next step', async ({ page }) => {
  await mockAPI(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Import a repository' })).toBeVisible();
  await expect(page.getByText('No task currently needs your decision.')).toBeVisible();
  await expect(page.getByText('No repository has been imported into this workspace.')).toBeVisible();
});

test('populated dashboard shows persisted review work', async ({ page }) => {
  await mockAPI(page, { populated: true });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Needs a decision' })).toBeVisible();
  await expect(page.getByText(/Review changes/).first()).toBeVisible();
  await expect(page.getByText('surya/forge')).toBeVisible();
});

test('GitHub discovery failure keeps imported repositories accessible', async ({ page }) => {
  await mockAPI(page, { populated: true, githubStatus: 503 });
  await page.goto('/repositories');
  await expect(page.locator('.product-alert')).toContainText('GitHub repositories could not be loaded');
  await expect(page.getByRole('link', { name: /Open/ }).last()).toHaveAttribute('href', '/repositories/repo-1');
});

test('execution lookup failure blocks a second start', async ({ page }) => {
  await mockAPI(page, { populated: true, executionLookupStatus: 503 });
  await page.goto('/tasks/plan-1');
  await expect(page.getByText('Execution status is unavailable. Refresh before starting work.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start execution' })).toHaveCount(0);
});

test('execution polling reports backend downtime', async ({ page }) => {
  await mockAPI(page, { populated: true, executionStatusCode: 503 });
  await page.goto('/tasks/plan-1');
  await expect(page.getByText('Execution status is temporarily unavailable. Forge will keep trying.')).toBeVisible();
});

test('expired session redirects to login', async ({ page }) => {
  await mockAPI(page, { sessionStatus: 401 });
  await page.goto('/');
  await expect(page).toHaveURL(/\/login$/);
});

test('backend session check outage offers retry without signing out', async ({ page }) => {
  await mockAPI(page, { sessionStatus: 503 });
  await page.goto('/');
  await expect(page.locator('.app-auth-error')).toContainText('could not check your session');
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
});

test('failed verification remains visible as failed evidence', async ({ page }) => {
  await mockAPI(page, { populated: true, verificationStatus: 'FAILED' });
  await page.goto('/tasks/plan-1');
  await page.getByRole('button', { name: 'Change review' }).click();
  await expect(page.getByText(/pytest: FAILED/)).toBeVisible();
  await expect(page.getByText('Tests failed')).toBeVisible();
});

test('failed publication shows a failure without a pull request link', async ({ page }) => {
  await mockAPI(page, { populated: true, publishStatus: 'FAILED' });
  await page.goto('/tasks/plan-1');
  await page.getByRole('button', { name: 'Change review' }).click();
  await expect(page.getByText(/Publication failed \(GITHUB_ACCESS_DENIED\)/)).toBeVisible();
  await expect(page.getByRole('link', { name: /pull request/i })).toHaveCount(0);
});

test('change review navigates files and binds approval to the reviewed digest', async ({ page }) => {
  await mockAPI(page, { populated: true, staleApproval: true });
  await page.goto('/tasks/plan-1');
  await page.getByRole('button', { name: 'Change review' }).click();
  await page.getByRole('button', { name: 'Load reviewed diff' }).click();
  await expect(page.getByLabel('Unified diff')).toContainText('+new');
  await page.getByRole('button', { name: 'services/auth/api.py' }).click();
  await expect(page.getByLabel('Unified diff')).toContainText('+after');
  await page.getByRole('button', { name: 'Approve this exact diff' }).click();
  await expect(page.getByText('Approval was rejected. Refresh the patch review.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Load reviewed diff' })).toBeVisible();
});

test('provider test reports a real API rejection', async ({ page }) => {
  await mockAPI(page);
  await page.goto('/settings/provider');
  await page.getByLabel('API key').fill('test-key');
  await page.getByRole('button', { name: 'Test connection' }).click();
  await expect(page.getByText('OpenAI rejected the provider key')).toBeVisible();
});

test('task review remains within a mobile viewport with reduced motion', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockAPI(page, { populated: true });
  await page.goto('/tasks/plan-1');
  await page.getByRole('button', { name: 'Change review' }).click();
  await page.getByRole('button', { name: 'Load reviewed diff' }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect(page.getByRole('button', { name: 'Approve this exact diff' })).toBeVisible();
});
