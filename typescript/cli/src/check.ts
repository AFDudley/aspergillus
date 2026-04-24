import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

type CheckOpts = { target: string };

// Wrapper-reference patterns. Each consumer config must contain the
// corresponding marker pointing at the aspergillus vendored reference.
// Consumers can freely add overrides; only the reference must remain.
const ESLINT_IMPORT_RE =
  /from\s+['"][^'"]*aspergillus\/typescript\/configs\/eslint\.config\.js['"]/;
const PRETTIER_REQUIRE_RE =
  /require\(\s*['"][^'"]*aspergillus\/typescript\/configs\/prettier\.config\.cjs['"]\s*\)/;
const TSCONFIG_EXTENDS_SUFFIX = 'aspergillus/typescript/configs/tsconfig.base.json';

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
  else if (!ESLINT_IMPORT_RE.test(eslintSrc))
    fail('drifted: eslint.config.js (no import of aspergillus eslint.config.js)');

  const prettierSrc = readOrNull(join(target, 'prettier.config.cjs'));
  if (prettierSrc === null) fail('missing: prettier.config.cjs');
  else if (!PRETTIER_REQUIRE_RE.test(prettierSrc))
    fail('drifted: prettier.config.cjs (no require of aspergillus prettier.config.cjs)');

  const tsconfigSrc = readOrNull(join(target, 'tsconfig.json'));
  if (tsconfigSrc === null) {
    fail('missing: tsconfig.json');
  } else {
    try {
      const parsed = JSON.parse(tsconfigSrc) as { extends?: unknown };
      const extendsVal = parsed.extends;
      if (typeof extendsVal !== 'string' || !extendsVal.endsWith(TSCONFIG_EXTENDS_SUFFIX)) {
        fail(
          'drifted: tsconfig.json (extends does not point at aspergillus tsconfig.base.json)',
        );
      }
    } catch {
      fail('drifted: tsconfig.json (invalid JSON)');
    }
  }

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
