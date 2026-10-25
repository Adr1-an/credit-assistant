#!/usr/bin/env node
/** Checks whether frontend uses the current team contract; never edits schemas or fields. */
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
const root = resolve('../contract/openapi.yaml');
const snapshot = resolve('contract/openapi.yaml');
const rootQuestions = resolve('../contract/question-sets.json');
const snapshotQuestions = resolve('contract/question-sets.json');
const hash = (path) => createHash('sha256').update(readFileSync(path)).digest('hex');

console.log('Сверка контракта без изменения файлов:');
if (existsSync(root)) {
  const match = hash(root) === hash(snapshot);
  console.log(`${match ? '✓' : '!'} openapi.yaml в корне ${match ? 'совпадает' : 'ОТЛИЧАЕТСЯ'} от frontend/contract/openapi.yaml`);
  console.log('Генератор типов читает основной файл ../contract/openapi.yaml.');
  if (!match) console.log('После согласования обновите копию frontend/contract/openapi.yaml, чтобы standalone ZIP не содержал старую версию.');
} else console.log('! Основной ../contract/openapi.yaml не найден — типы будут генерироваться из локальной копии. Проверьте актуальность.');
if (existsSync(rootQuestions)) {
  const match = hash(rootQuestions) === hash(snapshotQuestions);
  console.log(`${match ? '✓' : '!'} question-sets.json ${match ? 'совпадает' : 'ОТЛИЧАЕТСЯ'} от локальной копии.`);
}
const yaml = readFileSync(existsSync(root) ? root : snapshot, 'utf8');
const questions = JSON.parse(readFileSync(existsSync(rootQuestions) ? rootQuestions : snapshotQuestions, 'utf8'));
const part = yaml.split('  /question-sets:')[1]?.split('  /applications/{id}/dialog:')[0] ?? '';
console.log('\nПроверка ключевых согласованных операций:');
const required = [
  '/applications/{id}/handoff', '/applications/{id}/dialog', '/question-sets',
  '/demo/statements/{inn}', '/demo/applications/{id}/advance-month',
  '/staff/applications/{id}/decision',
];
let missing = 0;
for (const operation of required) {
  const found = yaml.includes(`  ${operation}:`);
  console.log(`${found ? '✓' : '!'} ${operation}`);
  if (!found) missing++;
}
if (!yaml.includes("schema: { $ref: '#/components/schemas/QuestionSets' }")) {
  console.error('! /question-sets должен иметь явную схему QuestionSets.'); missing++;
}
if (!questions.goals?.some((g) => g.goalType === 'INVENTORY' && g.questions?.some((q) => q.id === 'inventory.items'))) {
  console.error('! В INVENTORY не найден утверждённый текстовый вопрос inventory.items.'); missing++;
}
if (missing) process.exitCode = 1;
