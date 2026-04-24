import { existsSync, mkdirSync, copyFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// Reference configs live in ../../configs/ relative to the compiled CLI.
// Works at both bun-test time (src/) and post-build (dist/).
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

function relImport(from: string, to: string): string {
  const rel = relative(from, to).replace(/\\/g, '/');
  return rel.startsWith('.') ? rel : './' + rel;
}

function writeIfMissing(path: string, content: string, label: string): void {
  if (existsSync(path)) {
    process.stdout.write(`skip (exists): ${label}\n`);
    return;
  }
  writeFileSync(path, content);
  process.stdout.write(`wrote: ${label}\n`);
}

export async function init({ target }: InitOpts): Promise<number> {
  mkdirSync(target, { recursive: true });
  const rel = relImport(target, CONFIGS_DIR);

  const eslintWrapper = `// Aspergillus wrapper. Spreads the vendored reference config; add
// repo-specific overrides after the spread.
import base from '${rel}/eslint.config.js';

export default [...base];
`;

  const prettierWrapper = `// Aspergillus wrapper. Spreads the vendored reference; add overrides below.
module.exports = {
  ...require('${rel}/prettier.config.cjs'),
};
`;

  const tsconfigWrapper =
    JSON.stringify({ extends: `${rel}/tsconfig.base.json` }, null, 2) + '\n';

  writeIfMissing(join(target, 'eslint.config.js'), eslintWrapper, 'eslint.config.js');
  writeIfMissing(join(target, 'prettier.config.cjs'), prettierWrapper, 'prettier.config.cjs');
  writeIfMissing(join(target, 'tsconfig.json'), tsconfigWrapper, 'tsconfig.json');

  // Pre-commit has no native extends mechanism; copy the scaffold verbatim.
  const preCommitSrc = join(CONFIGS_DIR, 'pre-commit-config.yaml');
  const preCommitDest = join(target, '.pre-commit-config.yaml');
  if (existsSync(preCommitDest)) {
    process.stdout.write('skip (exists): .pre-commit-config.yaml\n');
  } else {
    copyFileSync(preCommitSrc, preCommitDest);
    process.stdout.write('wrote: .pre-commit-config.yaml\n');
  }

  process.stdout.write('\nNext: install devDependencies —\n');
  process.stdout.write(`  bun add -D ${DEV_DEPS.join(' ')}\n`);
  return 0;
}
