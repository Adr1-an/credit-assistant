import test from 'node:test';
import assert from 'node:assert/strict';
import { parseArgs, runSmoke } from '../scripts/api-smoke.mjs';

const url = 'http://localhost:3000/api';
test('CLI accepts only documented flags and UUID', () => {
  assert.deepEqual(parseArgs([]), { base: process.env.API_SMOKE_BASE?.replace(/\/+$/, '') || url, applicationId: undefined });
  assert.throws(() => parseArgs(['--application-id', 'wrong']), /UUID/);
  assert.throws(() => parseArgs(['--bogus']), /Неизвестный/);
});

test('read-only smoke test accepts OpenAPI-shaped responses', async () => {
  const fetchImpl = async (route) => {
    const path = new URL(route).pathname;
    const data = path.endsWith('/health') ? { status: 'ok', aiAvailable: false }
      : path.endsWith('/question-sets') ? { common: {}, goals: [] }
      : [];
    return { ok: true, status: 200, json: async () => data };
  };
  const result = await runSmoke({ base: url }, fetchImpl);
  assert.equal(result.length, 4);
  assert.ok(result.every((entry) => entry.ok));
});

test('error response message is surfaced without treating it as success', async () => {
  const result = await runSmoke({ base: url }, async () => ({ ok: false, status: 503, json: async () => ({ code: 'SERVICE_UNAVAILABLE', message: 'Сервис временно недоступен' }) }));
  assert.equal(result.length, 4);
  assert.ok(result.every((entry) => !entry.ok && entry.detail.includes('Сервис временно недоступен')));
});
