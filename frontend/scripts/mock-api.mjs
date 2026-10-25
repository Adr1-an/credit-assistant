import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const rootContract = resolve('../openapi.yaml');
const snapshotContract = resolve('contract/openapi.yaml');
const contract = existsSync(rootContract) ? rootContract : snapshotContract;
if (!existsSync(contract)) {
  console.error('Не найден openapi.yaml — поместите его рядом с frontend/.');
  process.exit(1);
}
console.log(`Prism: контракт ${contract}`);
const prism = spawnSync('prism', ['mock', contract, '-h', '0.0.0.0', '-p', '4010'], {
  stdio: 'inherit',
  shell: process.platform === 'win32',
});
if (prism.error) {
  console.error('Не удалось запустить Prism:', prism.error.message);
  process.exit(1);
}
process.exit(prism.status ?? 1);
