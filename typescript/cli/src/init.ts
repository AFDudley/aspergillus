import { existsSync, mkdirSync, copyFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// Reference configs live in ../../configs/ relative to the compiled CLI
// (dist/init.js → ../../configs/). During `bun test`, __filename points
// into src/, so ../../configs/ resolves to typescript/configs/ either way.
const here = dirname(fileURLToPath(import.meta.url));
const CONFIGS_DIR = resolve(here, '..', '..', 'configs');

const DEV_DEPS = [
  '@eslint/js',
  'typescript-eslint',
  'eslint-plugin-import',
  'eslint-plugin-unused-imports',
  'eslint-config-prettier',
  'eslint',
  'prettier',
  'typescript',
] as const;

type InitOpts = { target: string };

// `.pre-commit-config.yaml` in the consumer is conventionally dotfiled;
// the reference ships it as `pre-commit-config.yaml` to keep the configs
// directory visible, and we add the dot on copy.
const FILES: ReadonlyArray<readonly [sourceName: string, destName: string]> = [
  ['eslint.config.js', 'eslint.config.js'],
  ['tsconfig.base.json', 'tsconfig.base.json'],
  ['prettier.config.cjs', 'prettier.config.cjs'],
  ['pre-commit-config.yaml', '.pre-commit-config.yaml'],
];

export async function init({ target }: InitOpts): Promise<number> {
  mkdirSync(target, { recursive: true });
  const availableSources = new Set(readdirSync(CONFIGS_DIR));
  for (const [src, dest] of FILES) {
    if (!availableSources.has(src)) {
      process.stderr.write(`missing reference config: ${src}\n`);
      return 1;
    }
    const destPath = join(target, dest);
    if (existsSync(destPath)) {
      process.stdout.write(`skip (exists): ${dest}\n`);
      continue;
    }
    copyFileSync(join(CONFIGS_DIR, src), destPath);
    process.stdout.write(`wrote: ${dest}\n`);
  }
  process.stdout.write('\nNext: install devDependencies —\n');
  process.stdout.write(`  bun add -D ${DEV_DEPS.join(' ')}\n`);
  return 0;
}
