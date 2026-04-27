import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { isEslintWrapper, isPrettierWrapper, isTsconfigWrapper } from './wrappers.js';

type CheckOpts = { target: string };

function readOrNull(path: string): string | null {
  try {
    return readFileSync(path, 'utf8');
  } catch {
    return null;
  }
}

export async function check({ target }: CheckOpts): Promise<number> {
  let problems = 0;
  const fail = (msg: string) => {
    process.stdout.write(`${msg}\n`);
    problems++;
  };

  const eslintSrc = readOrNull(join(target, 'eslint.config.js'));
  if (eslintSrc === null) fail('missing: eslint.config.js');
  else if (!isEslintWrapper(eslintSrc))
    fail('drifted: eslint.config.js (no import of @afdudley/aspergillus/eslint-config)');

  const prettierSrc = readOrNull(join(target, 'prettier.config.cjs'));
  if (prettierSrc === null) fail('missing: prettier.config.cjs');
  else if (!isPrettierWrapper(prettierSrc))
    fail('drifted: prettier.config.cjs (no require of @afdudley/aspergillus/prettier-config)');

  const tsconfigSrc = readOrNull(join(target, 'tsconfig.json'));
  if (tsconfigSrc === null) fail('missing: tsconfig.json');
  else if (!isTsconfigWrapper(tsconfigSrc))
    fail('drifted: tsconfig.json (extends does not point at @afdudley/aspergillus/tsconfig)');

  // Scaffold-only; consumer owns the contents after init.
  if (!existsSync(join(target, '.pre-commit-config.yaml'))) {
    fail('missing: .pre-commit-config.yaml');
  }

  if (problems === 0) {
    process.stdout.write('ok: all consumer configs reference aspergillus\n');
    return 0;
  }
  process.stdout.write(`\n${problems} config(s) out of sync with reference\n`);
  return 1;
}
