#!/usr/bin/env node
/** Read-only API check. All requested paths are from openapi.yaml (servers.url=/api). */
import { pathToFileURL } from 'node:url';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);

export function parseArgs(argv) {
  let base = process.env.API_SMOKE_BASE || 'http://localhost:3000/api';
  let applicationId = undefined;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--base' && argv[i + 1]) { base = argv[++i]; continue; }
    if (argv[i] === '--application-id' && argv[i + 1]) { applicationId = argv[++i]; continue; }
    throw new Error(`Неизвестный аргумент: ${argv[i]}. Допустимы --base URL и --application-id UUID.`);
  }
  if (!/^https?:\/\//.test(base)) throw new Error('Для --base нужен адрес вида http://localhost:5173/api');
  if (applicationId && !uuid.test(applicationId)) throw new Error('ID заявки должен быть UUID из адреса /applications/:id.');
  return { base: base.replace(/\/+$/, ''), applicationId };
}

/** Tiny shape checks, not handwritten API types; TypeScript API types come only from OpenAPI. */
export const checks = [
  { path: '/health', label: 'Сервер /health', accepts: (x) => isObject(x) && x.status === 'ok' && typeof x.aiAvailable === 'boolean' },
  { path: '/question-sets', label: 'Вопросы /question-sets', accepts: (x) => isObject(x) },
  { path: '/demo/clients', label: 'Тестовые клиенты /demo/clients', accepts: Array.isArray },
  { path: '/staff/applications', label: 'Кабинет /staff/applications', accepts: Array.isArray },
];

export async function runSmoke({ base, applicationId }, fetchImpl = fetch) {
  const work = [...checks];
  if (applicationId) {
    work.push({
      path: `/applications/${encodeURIComponent(applicationId)}`,
      label: 'Восстановление заявки по ID',
      accepts: (x) => isObject(x) && x.id === applicationId && typeof x.nextAction === 'string' && typeof x.status === 'string',
    });
  }
  const results = [];
  for (const check of work) {
    const url = `${base}${check.path}`;
    try {
      const response = await fetchImpl(url, { method: 'GET', headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(8000) });
      let body;
      try { body = await response.json(); }
      catch { results.push({ ...check, ok: false, detail: `HTTP ${response.status}: ответ не JSON` }); continue; }
      if (!response.ok) {
        const detail = isObject(body) && typeof body.message === 'string' ? body.message : `HTTP ${response.status}`;
        results.push({ ...check, ok: false, detail: `HTTP ${response.status}: ${detail}` });
        continue;
      }
      const ok = check.accepts(body);
      results.push({ ...check, ok, detail: ok ? `HTTP ${response.status}, формат ожидаемый` : 'Получен JSON, но обязательные поля/тип не совпадают с контрактом' });
    } catch (err) {
      results.push({ ...check, ok: false, detail: err instanceof Error ? err.message : 'Ошибка сети' });
    }
  }
  return results;
}

async function main() {
  try {
    const args = parseArgs(process.argv.slice(2));
    console.log(`Проверка API (только чтение): ${args.base}`);
    const results = await runSmoke(args);
    for (const result of results) console.log(`${result.ok ? '✓' : '✗'} ${result.label} — ${result.detail}`);
    if (!args.applicationId) console.log('Проверка продолжения заявки пропущена: при необходимости передайте --application-id <UUID>.');
    console.log('ВНИМАНИЕ: успешная проверка Prism не означает, что FastAPI сохраняет заявки.');
    if (results.some((x) => !x.ok)) process.exitCode = 1;
  } catch (e) {
    console.error(e instanceof Error ? e.message : String(e));
    process.exitCode = 2;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
