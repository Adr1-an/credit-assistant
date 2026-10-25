import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const source = (relative) => readFileSync(resolve(relative), 'utf8');
const yaml = source('contract/openapi.yaml');
const questions = JSON.parse(source('contract/question-sets.json'));
const client = source('src/api/client.ts');

test('копия утверждённого OpenAPI содержит ключевые операции', () => {
  for (const path of ['/question-sets', '/applications/{id}/dialog', '/applications/{id}/handoff',
    '/applications/{id}/goals', '/staff/applications', '/demo/statements/{inn}']) {
    assert.ok(yaml.includes(`  ${path}:`), `Отсутствует ${path}`);
  }
  assert.match(yaml, /#\/components\/schemas\/QuestionSets/);
  assert.match(yaml, /Новая заявка не создана/);
});

test('раздельные вопросы по закупке из актуального справочника', () => {
  const inventory = questions.goals.find((g) => g.goalType === 'INVENTORY');
  const items = inventory?.questions.find((q) => q.id === 'inventory.items');
  const amount = inventory?.questions.find((q) => q.id === 'inventory.amount');
  assert.equal(items?.type, 'text');
  assert.equal(amount?.type, 'money');
  assert.equal(items?.required, true);
  assert.equal(amount?.required, true);
});

test('рабочий API пользуется только относительными /api/ и новыми операциями', () => {
  assert.match(client, /fetch\(`\/api\$\{path\}`/);
  assert.match(client, /getDialog:/);
  assert.match(client, /sendDialogMessage:/);
  assert.match(client, /handoffToStaff:/);
  assert.match(client, /suggestOkved:/);
  assert.match(client, /existing: response\.status === 200/);
  assert.doesNotMatch(client, /fetch\(['"]http:\/\//);
});

test('Vite и nginx слушают порт 3000, backend доступен через /api', () => {
  assert.match(source('vite.config.ts'), /port: 3000/);
  assert.match(source('vite.config.ts'), /localhost:8000/);
  assert.match(source('nginx/default.conf.template'), /listen 3000;/);
  assert.match(source('nginx/default.conf.template'), /proxy_pass http:\/\/backend:8000;/);
});
