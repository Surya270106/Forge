import { expect, test } from '@playwright/test';

test('login exchange requires the initiating browser state', async ({ request, baseURL }) => {
  const origin = process.env.FORGE_REQUEST_ORIGIN || baseURL!;
  const response = await request.post('/api/auth/exchange', {
    headers: { Origin: origin },
    data: { code: 'a'.repeat(32), state: 'forged-state' },
  });
  expect(response.status()).toBe(403);

  const mismatch = await request.post('/api/auth/exchange', {
    headers: { Origin: origin, Cookie: 'forge_oauth_state=initiated-state' },
    data: { code: 'a'.repeat(32), state: 'forged-state' },
  });
  expect(mismatch.status()).toBe(403);

  if (process.env.FORGE_LOCAL_API_E2E === '1') {
    const matching = await request.post('/api/auth/exchange', {
      headers: { Origin: origin, Cookie: 'forge_oauth_state=initiated-state' },
      data: { code: 'a'.repeat(32), state: 'initiated-state' },
    });
    expect(matching.status()).toBe(400);
  }
});

test('local API login start returns a browser-bound state cookie', async ({ request }) => {
  test.skip(process.env.FORGE_LOCAL_API_E2E !== '1', 'Requires the isolated local API and Redis');
  const response = await request.get('/api/v1/auth/github/login');
  expect(response.status()).toBe(200);
  const data = await response.json();
  const state = new URL(data.url).searchParams.get('state');
  expect(state).toMatch(/^[0-9a-f-]{36}$/);
  expect(response.headers()['set-cookie']).toContain(`forge_oauth_state=${state}`);
  expect(response.headers()['set-cookie']).toMatch(/;\s*HttpOnly/i);
  expect(response.headers()['set-cookie']).toMatch(/;\s*SameSite=lax/i);
  expect(response.headers()['set-cookie']).toMatch(/;\s*Max-Age=600/i);
});
