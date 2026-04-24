import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const here = dirname(fileURLToPath(import.meta.url));
const CONFIGS_DIR = resolve(here, '..', '..', 'configs');

// Same source→dest mapping as init. Must stay in sync.
const FILES: ReadonlyArray<readonly [sourceName: string, destName: string]> = [
  ['eslint.config.js', 'eslint.config.js'],
  ['tsconfig.base.json', 'tsconfig.base.json'],
  ['prettier.config.cjs', 'prettier.config.cjs'],
  ['pre-commit-config.yaml', '.pre-commit-config.yaml'],
];

type CheckOpts = { target: string };

function sha256(path: string): string {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

export async function check({ target }: CheckOpts): Promise<number> {
  let drifted = 0;
  for (const [src, dest] of FILES) {
    const consumerPath = join(target, dest);
    if (!existsSync(consumerPath)) {
      process.stdout.write(`missing: ${dest}\n`);
      drifted++;
      continue;
    }
    const refHash = sha256(join(CONFIGS_DIR, src));
    const consumerHash = sha256(consumerPath);
    if (refHash !== consumerHash) {
      process.stdout.write(`drifted: ${dest}\n`);
      drifted++;
    }
  }
  if (drifted === 0) {
    process.stdout.write('ok: all reference configs match\n');
    return 0;
  }
  process.stdout.write(`\n${drifted} config(s) out of sync with reference\n`);
  return 1;
}
