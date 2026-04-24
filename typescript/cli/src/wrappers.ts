// Wrapper-detection: is a given file the aspergillus wrapper form, or
// something else? Used by init (to decide back-up vs skip) and check
// (to detect drift).

const ESLINT_IMPORT_RE =
  /from\s+['"][^'"]*aspergillus\/typescript\/configs\/eslint\.config\.js['"]/;
const PRETTIER_REQUIRE_RE =
  /require\(\s*['"][^'"]*aspergillus\/typescript\/configs\/prettier\.config\.cjs['"]\s*\)/;
const TSCONFIG_EXTENDS_SUFFIX = 'aspergillus/typescript/configs/tsconfig.base.json';

export function isEslintWrapper(src: string): boolean {
  return ESLINT_IMPORT_RE.test(src);
}

export function isPrettierWrapper(src: string): boolean {
  return PRETTIER_REQUIRE_RE.test(src);
}

export function isTsconfigWrapper(src: string): boolean {
  try {
    const parsed = JSON.parse(src) as { extends?: unknown };
    return (
      typeof parsed.extends === 'string' &&
      parsed.extends.endsWith(TSCONFIG_EXTENDS_SUFFIX)
    );
  } catch {
    return false;
  }
}

// All known filenames that compete with each wrapper. When `init` runs,
// any of these at the consumer root gets renamed to <name>.local.bak
// (unless it IS the aspergillus wrapper, in which case we leave it).
export const CONFLICTS = {
  eslint: [
    'eslint.config.js',
    'eslint.config.mjs',
    'eslint.config.cjs',
    'eslint.config.ts',
    '.eslintrc',
    '.eslintrc.js',
    '.eslintrc.cjs',
    '.eslintrc.json',
    '.eslintrc.yaml',
    '.eslintrc.yml',
  ],
  prettier: [
    'prettier.config.js',
    'prettier.config.cjs',
    'prettier.config.mjs',
    '.prettierrc',
    '.prettierrc.json',
    '.prettierrc.yaml',
    '.prettierrc.yml',
    '.prettierrc.js',
    '.prettierrc.cjs',
    '.prettierrc.mjs',
    '.prettierrc.toml',
  ],
  tsconfig: ['tsconfig.json'],
  preCommit: ['.pre-commit-config.yaml', '.pre-commit-config.yml'],
} as const;

// Keys inside `package.json` that hold inline config aspergillus can't
// auto-migrate; we only warn.
export const INLINE_KEYS = {
  prettier: 'prettier',
  eslint: 'eslintConfig',
} as const;
