import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

// В составе полного репозитория источник истины — contract/openapi.yaml.
// Для скачанного отдельно frontend/ доступна сохранённая копия того же файла.
const rootContract = resolve('../contract/openapi.yaml');
const snapshotContract = resolve('contract/openapi.yaml');
const contract = existsSync(rootContract) ? rootContract : snapshotContract;

if (!existsSync(contract)) {
  console.error('Не найден openapi.yaml. Положите его рядом с frontend/ (в корень проекта).');
  process.exit(1);
}

if (contract === snapshotContract) {
  console.log('Используется копия OpenAPI из frontend/contract/. При обновлении контракта команды положите openapi.yaml рядом с frontend/.');
}

const generator = spawnSync('openapi-typescript', [contract, '-o', 'src/api/schema.d.ts'], {
  stdio: 'inherit',
  shell: process.platform === 'win32',
});
if (generator.error) {
  console.error('Не удалось запустить openapi-typescript:', generator.error.message);
  process.exit(1);
}
process.exit(generator.status ?? 1);
