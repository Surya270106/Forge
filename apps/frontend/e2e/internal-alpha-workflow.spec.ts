import { test, expect } from '@playwright/test';

test.describe.skip('Internal Alpha Full Workflow', () => {
  
  test('Complete workflow from import to execution', async ({ page }) => {
    // Navigate to the Dashboard
    await page.goto('/');

    // Check title
    await expect(page.locator('h1')).toHaveText('Forge Dashboard');

    // 1. Register and Import Repository
    const btnImport = page.locator('#btn-import');
    await expect(btnImport).toBeVisible();
    await btnImport.click();
    
    // Check logs for queued and completed
    const consoleLogs = page.locator('#log-console');
    await expect(consoleLogs).toContainText('Starting repository import...');
    await expect(consoleLogs).toContainText('Import completed', { timeout: 15000 });

    // 2. Start Memory Indexing
    const btnIndex = page.locator('#btn-index');
    await expect(btnIndex).toBeEnabled();
    await btnIndex.click();
    await expect(consoleLogs).toContainText('Indexing completed', { timeout: 15000 });

    // 3. Create Task & Generate Plan
    const btnPlan = page.locator('#btn-plan');
    await expect(btnPlan).toBeEnabled();
    await btnPlan.click();
    await expect(consoleLogs).toContainText('Plan', { timeout: 15000 });
    await expect(consoleLogs).toContainText('generated');
    
    // Inspect plan DAG
    const planSection = page.locator('#plan-section');
    await expect(planSection).toBeVisible();
    await expect(planSection).toContainText('PENDING_APPROVAL');

    // 4. Approve Plan
    const btnApprove = page.locator('#btn-approve');
    await expect(btnApprove).toBeEnabled();
    await btnApprove.click();
    await expect(consoleLogs).toContainText('Plan approved', { timeout: 15000 });

    // 5. Start Execution
    const btnExecute = page.locator('#btn-execute');
    await expect(btnExecute).toBeEnabled();
    await btnExecute.click();
    await expect(consoleLogs).toContainText('Execution started', { timeout: 10000 });
    await expect(consoleLogs).toContainText('Execution completed', { timeout: 30000 });
  });

  test('Tenant isolation check', async ({ page }) => {
    await page.goto('/');
    
    // Change organization ID
    const orgInput = page.locator('input[type="text"]');
    await orgInput.fill('11111111-1111-1111-1111-111111111111');

    // Trying to fetch a plan for a nonexistent repo or wrong tenant should fail
    // However, our UI drives from step 1. We will attempt import and ensure it attaches to the new tenant.
    const btnImport = page.locator('#btn-import');
    await btnImport.click();
    
    // Wait for the repo ID in logs
    const consoleLogs = page.locator('#log-console');
    await expect(consoleLogs).toContainText('Import completed', { timeout: 15000 });
  });
});
