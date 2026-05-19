# Aspergillus multi-language restructure — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure aspergillus into `python/`, `typescript/`, `rust/` subtrees; scaffold reference ESLint/tsc/Prettier configs and a stub `aspergillus-ts` CLI; leave a Rust placeholder.

**Architecture:** Python code moves under `python/` with no functional change. TypeScript gets a `configs/` directory (reference `eslint.config.js`, `tsconfig.base.json`, `prettier.config.cjs`, `pre-commit-config.yaml`) and a stub `cli/` package exposing `aspergillus-ts init` (copies configs, prints devDeps) and `aspergillus-ts check` (drift diff vs reference). Rust gets `configs/clippy.toml` + `configs/cargo-lints.toml` + README only. Distribution model is git subtree; `docs/design.md` is rewritten to reflect the multi-language model and carry the canonical ASP↔tool rule-mapping table.

**Tech Stack:** Python 3.10+ / uv / Fixit / LibCST (existing). TypeScript / Bun / ESLint 9 flat config / Prettier 3 / typescript-eslint 8 (new). Rust clippy (reference configs only).

---

## File Structure

**Moved:**
- `src/aspergillus/` → `python/src/aspergillus/`
- `tests/` → `python/tests/`
- `pyproject.toml` → `python/pyproject.toml`
- `uv.lock` → `python/uv.lock`
- `.pre-commit-config.yaml` → `python/.pre-commit-config.yaml`

**New — TypeScript:**
- `typescript/configs/eslint.config.js` — reference flat config, Level 1 baseline
- `typescript/configs/tsconfig.base.json` — strict TS compiler baseline
- `typescript/configs/prettier.config.cjs` — Prettier 3 config
- `typescript/configs/pre-commit-config.yaml` — husky + lint-staged template
- `typescript/README.md` — adoption guide
- `typescript/cli/package.json` — `aspergillus-ts` CLI package manifest
- `typescript/cli/tsconfig.json` — CLI build config
- `typescript/cli/src/index.ts` — CLI entrypoint
- `typescript/cli/src/init.ts` — `init` command
- `typescript/cli/src/check.ts` — `check` command
- `typescript/cli/src/init.test.ts` — `init` tests
- `typescript/cli/src/check.test.ts` — `check` tests

**New — Rust:**
- `rust/configs/clippy.toml`
- `rust/configs/cargo-lints.toml`
- `rust/README.md`

**Modified:**
- `README.md` — add multi-language navigation
- `docs/design.md` — rewrite for multi-language; include rule-mapping table
- `docs/implementation-plan.md` — append note that this restructure supersedes old layout

**Removed:**
- Repo-root `pyproject.toml` (moves to `python/`)
- Repo-root `.pre-commit-config.yaml` (moves to `python/`)
- Repo-root `uv.lock` (moves to `python/`)

---

## Task 1: Move Python code under `python/`

**Files:**
- Move: `src/aspergillus/` → `python/src/aspergillus/`
- Move: `tests/` → `python/tests/`
- Move: `pyproject.toml` → `python/pyproject.toml`
- Move: `uv.lock` → `python/uv.lock`
- Move: `.pre-commit-config.yaml` → `python/.pre-commit-config.yaml`

- [ ] **Step 1: Create `python/` directory and move files**

Run:
```bash
cd /home/dev/git_puller/repos/aspergillus
mkdir -p python
git mv src python/src
git mv tests python/tests
git mv pyproject.toml python/pyproject.toml
git mv uv.lock python/uv.lock
git mv .pre-commit-config.yaml python/.pre-commit-config.yaml
```

- [ ] **Step 2: Verify tests still pass in the new location**

Run:
```bash
cd /home/dev/git_puller/repos/aspergillus/python
uv sync
uv run pytest
```

Expected: all existing tests pass (level2, level3, cli, orchestrator_integration). If any test hardcodes a path like `src/aspergillus/...`, fix that path. No behavior changes expected — the package imports itself as `aspergillus.*` which is unchanged.

- [ ] **Step 3: Verify fixit still works**

Run:
```bash
cd /home/dev/git_puller/repos/aspergillus/python
uv run fixit lint src/aspergillus/rules/level2.py
```

Expected: exits 0 (self-clean) or reports any pre-existing findings — either is fine, we're verifying the tool runs, not fixing new issues.

- [ ] **Step 4: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus
git add -A
git commit -m "restructure: move Python code under python/"
```

---

## Task 2: Scaffold `typescript/configs/tsconfig.base.json`

**Files:**
- Create: `typescript/configs/tsconfig.base.json`

- [ ] **Step 1: Create the directory and write the file**

```bash
mkdir -p /home/dev/git_puller/repos/aspergillus/typescript/configs
```

Write `typescript/configs/tsconfig.base.json`:

```json
{
  "$schema": "https://json.schemastore.org/tsconfig",
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noFallthroughCasesInSwitch": true,
    "noImplicitOverride": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "forceConsistentCasingInFileNames": true,
    "lib": ["ESNext", "DOM", "DOM.Iterable"]
  }
}
```

- [ ] **Step 2: Validate JSON**

Run:
```bash
cd /home/dev/git_puller/repos/aspergillus
node -e "JSON.parse(require('fs').readFileSync('typescript/configs/tsconfig.base.json','utf8'))"
```

Expected: no output (valid JSON).

- [ ] **Step 3: Commit**

```bash
git add typescript/configs/tsconfig.base.json
git commit -m "ts: add reference tsconfig.base.json"
```

---

## Task 3: Scaffold `typescript/configs/prettier.config.cjs`

**Files:**
- Create: `typescript/configs/prettier.config.cjs`

- [ ] **Step 1: Write the file**

Write `typescript/configs/prettier.config.cjs`:

```js
/** @type {import("prettier").Config} */
module.exports = {
  semi: true,
  singleQuote: true,
  trailingComma: 'all',
  printWidth: 100,
  tabWidth: 2,
  useTabs: false,
  arrowParens: 'always',
  endOfLine: 'lf',
};
```

- [ ] **Step 2: Validate syntax**

Run:
```bash
node -c /home/dev/git_puller/repos/aspergillus/typescript/configs/prettier.config.cjs
```

Expected: no output (valid JS).

- [ ] **Step 3: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus
git add typescript/configs/prettier.config.cjs
git commit -m "ts: add reference prettier config"
```

---

## Task 4: Scaffold `typescript/configs/eslint.config.js` (Level 1 baseline)

**Files:**
- Create: `typescript/configs/eslint.config.js`

- [ ] **Step 1: Write the file**

Write `typescript/configs/eslint.config.js`:

```js
// Aspergillus reference ESLint flat config — Level 1 baseline.
//
// Consumers import and spread this from their repo's eslint.config.js:
//
//   import base from '../vendor/aspergillus/typescript/configs/eslint.config.js';
//   export default [...base, /* repo-specific overrides */];
//
// Level 2 and Level 3 rules are appended by follow-up work; this file
// currently enforces only the Level 1 baseline (external-tool tier).
//
// Required peer devDependencies (install in the consumer repo):
//   @eslint/js typescript-eslint eslint-plugin-import
//   eslint-plugin-unused-imports eslint-config-prettier
//
// Adoption workflow: every new rule lands at "warn", flips to "error"
// in a dedicated PR once violations reach zero. See typescript/README.md.

import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import importPlugin from 'eslint-plugin-import';
import unusedImports from 'eslint-plugin-unused-imports';
import prettierConfig from 'eslint-config-prettier';

export default [
  {
    ignores: [
      'dist/**',
      'build/**',
      'node_modules/**',
      'coverage/**',
      '.next/**',
      '.expo/**',
    ],
  },

  js.configs.recommended,
  ...tseslint.configs.recommended,

  {
    files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    plugins: {
      import: importPlugin,
      'unused-imports': unusedImports,
    },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
    },
    rules: {
      // Level 1 baseline — lands at error.
      'no-var': 'error',
      'no-param-reassign': 'error',
      '@typescript-eslint/no-floating-promises': 'error',
      'unused-imports/no-unused-imports': 'error',
      'import/no-cycle': 'error',
      'import/order': [
        'error',
        {
          groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
          'newlines-between': 'always',
          alphabetize: { order: 'asc', caseInsensitive: true },
        },
      ],

      // Level 1 baseline — lands at warn (promotes at Level 2).
      '@typescript-eslint/no-explicit-any': 'warn',
      'no-console': ['warn', { allow: ['warn', 'error'] }],
    },
  },

  // Keep Prettier last so it disables conflicting formatting rules.
  prettierConfig,
];
```

- [ ] **Step 2: Syntax-check**

Run:
```bash
node --input-type=module -e "import('/home/dev/git_puller/repos/aspergillus/typescript/configs/eslint.config.js').then(() => console.log('ok')).catch(e => { console.error(e.message); process.exit(1); })"
```

Expected: prints `ok`. If you see `ERR_MODULE_NOT_FOUND` for ESLint plugin imports, that is OK — the file parses; only the imports fail because this directory has no `node_modules`. To confirm it's only missing modules (not a syntax error), re-run with:

```bash
node --check /home/dev/git_puller/repos/aspergillus/typescript/configs/eslint.config.js
```

Expected: no output (valid syntax).

- [ ] **Step 3: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus
git add typescript/configs/eslint.config.js
git commit -m "ts: add reference eslint.config.js (Level 1 baseline)"
```

---

## Task 5: Scaffold `typescript/configs/pre-commit-config.yaml`

**Files:**
- Create: `typescript/configs/pre-commit-config.yaml`

- [ ] **Step 1: Write the file**

Write `typescript/configs/pre-commit-config.yaml`:

```yaml
# Aspergillus reference pre-commit config for TypeScript consumers.
# Copied into consumer repos by `aspergillus-ts init`.
#
# Expects husky + lint-staged to be installed and wired in the consumer.
# The lint-staged config below drives ESLint and Prettier on staged files.

repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: local
    hooks:
      - id: eslint
        name: eslint (aspergillus reference config)
        entry: bunx eslint --max-warnings=0
        language: system
        files: \.(ts|tsx|js|jsx|mjs|cjs)$
        pass_filenames: true
        require_serial: false

      - id: prettier
        name: prettier (aspergillus reference config)
        entry: bunx prettier --check
        language: system
        files: \.(ts|tsx|js|jsx|mjs|cjs|json|md|ya?ml)$
        pass_filenames: true
```

- [ ] **Step 2: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus
git add typescript/configs/pre-commit-config.yaml
git commit -m "ts: add reference pre-commit-config.yaml"
```

---

## Task 6: Scaffold `typescript/cli/` package skeleton

**Files:**
- Create: `typescript/cli/package.json`
- Create: `typescript/cli/tsconfig.json`
- Create: `typescript/cli/.gitignore`

- [ ] **Step 1: Create the directory**

```bash
mkdir -p /home/dev/git_puller/repos/aspergillus/typescript/cli/src
```

- [ ] **Step 2: Write `typescript/cli/package.json`**

```json
{
  "name": "@afdudley/aspergillus-ts",
  "version": "0.1.0",
  "description": "Aspergillus TypeScript CLI — init and check commands",
  "type": "module",
  "bin": {
    "aspergillus-ts": "dist/index.js"
  },
  "files": ["dist"],
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "test": "bun test",
    "start": "bun run src/index.ts"
  },
  "engines": {
    "node": ">=18"
  },
  "devDependencies": {
    "@types/bun": "latest",
    "@types/node": ">=18",
    "typescript": ">=5.4"
  }
}
```

- [ ] **Step 3: Write `typescript/cli/tsconfig.json`**

```json
{
  "extends": "../configs/tsconfig.base.json",
  "compilerOptions": {
    "outDir": "dist",
    "rootDir": "src",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "declaration": false,
    "sourceMap": true,
    "lib": ["ESNext"]
  },
  "include": ["src/**/*"],
  "exclude": ["src/**/*.test.ts", "dist"]
}
```

- [ ] **Step 4: Write `typescript/cli/.gitignore`**

```
dist/
node_modules/
*.tsbuildinfo
```

- [ ] **Step 5: Install CLI deps and verify build toolchain works**

```bash
cd /home/dev/git_puller/repos/aspergillus/typescript/cli
bun install
```

Expected: installs `typescript`, `@types/bun`, `@types/node` into `node_modules/`.

- [ ] **Step 6: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus
git add typescript/cli/package.json typescript/cli/tsconfig.json typescript/cli/.gitignore typescript/cli/bun.lock 2>/dev/null || true
git add typescript/cli/package.json typescript/cli/tsconfig.json typescript/cli/.gitignore
git commit -m "ts-cli: scaffold package skeleton"
```

---

## Task 7: Implement CLI entrypoint (dispatch only, no commands yet)

**Files:**
- Create: `typescript/cli/src/index.ts`

- [ ] **Step 1: Write `typescript/cli/src/index.ts`**

```ts
#!/usr/bin/env node
// Aspergillus TypeScript CLI.
// Commands: init, check. See typescript/README.md for adoption workflow.

import { init } from './init.js';
import { check } from './check.js';

const USAGE = `aspergillus-ts <command>

Commands:
  init [--target <dir>]      Copy reference configs into target dir (default: cwd)
  check [--target <dir>]     Diff consumer config vs reference; exit 1 on drift

Flags:
  --target <dir>             Consumer repo root (default: cwd)
  -h, --help                 Show this message
`;

type Args = { command: string | undefined; target: string; help: boolean };

export function parseArgs(argv: readonly string[]): Args {
  const rest = argv.slice(2);
  let target = process.cwd();
  let help = false;
  let command: string | undefined;
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a === '-h' || a === '--help') help = true;
    else if (a === '--target') target = rest[++i] ?? target;
    else if (!command) command = a;
  }
  return { command, target, help };
}

export async function main(argv: readonly string[]): Promise<number> {
  const { command, target, help } = parseArgs(argv);
  if (help || !command) {
    process.stdout.write(USAGE);
    return help ? 0 : 1;
  }
  switch (command) {
    case 'init':
      return init({ target });
    case 'check':
      return check({ target });
    default:
      process.stderr.write(`unknown command: ${command}\n\n${USAGE}`);
      return 1;
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main(process.argv).then((code) => process.exit(code));
}
```

- [ ] **Step 2: Commit (compiles after init.ts/check.ts exist — next tasks)**

```bash
cd /home/dev/git_puller/repos/aspergillus
git add typescript/cli/src/index.ts
git commit -m "ts-cli: add entrypoint and arg parser"
```

Note: `tsc` will fail until Tasks 8–9 land (`./init.js` / `./check.js` not yet created). That is expected — the build verification step runs at end of Task 9.

---

## Task 8: Implement `init` command (TDD)

**Files:**
- Create: `typescript/cli/src/init.ts`
- Create: `typescript/cli/src/init.test.ts`

- [ ] **Step 1: Write the failing test `typescript/cli/src/init.test.ts`**

```ts
import { describe, test, expect, beforeEach, afterEach } from 'bun:test';
import { mkdtempSync, rmSync, existsSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { init } from './init.js';

describe('init', () => {
  let tmp: string;

  beforeEach(() => {
    tmp = mkdtempSync(join(tmpdir(), 'asp-init-'));
  });

  afterEach(() => {
    rmSync(tmp, { recursive: true, force: true });
  });

  test('copies all four reference configs into the target dir', async () => {
    const code = await init({ target: tmp });
    expect(code).toBe(0);
    expect(existsSync(join(tmp, 'eslint.config.js'))).toBe(true);
    expect(existsSync(join(tmp, 'tsconfig.base.json'))).toBe(true);
    expect(existsSync(join(tmp, 'prettier.config.cjs'))).toBe(true);
    expect(existsSync(join(tmp, '.pre-commit-config.yaml'))).toBe(true);
  });

  test('does not overwrite existing files', async () => {
    const path = join(tmp, 'eslint.config.js');
    writeFileSync(path, 'existing-content');
    const code = await init({ target: tmp });
    expect(code).toBe(0);
    expect(readFileSync(path, 'utf8')).toBe('existing-content');
  });

  test('creates the target dir if missing', async () => {
    const nested = join(tmp, 'nested', 'repo');
    const code = await init({ target: nested });
    expect(code).toBe(0);
    expect(existsSync(join(nested, 'eslint.config.js'))).toBe(true);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/dev/git_puller/repos/aspergillus/typescript/cli
bun test src/init.test.ts
```

Expected: FAIL with "Cannot find module './init.js'" or similar import error.

- [ ] **Step 3: Write `typescript/cli/src/init.ts`**

```ts
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /home/dev/git_puller/repos/aspergillus/typescript/cli
bun test src/init.test.ts
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus
git add typescript/cli/src/init.ts typescript/cli/src/init.test.ts
git commit -m "ts-cli: implement init command"
```

---

## Task 9: Implement `check` command (TDD)

**Files:**
- Create: `typescript/cli/src/check.ts`
- Create: `typescript/cli/src/check.test.ts`

The check command does a *content-hash* drift check in v0.1: it compares the consumer's file bytes against the reference file bytes. An ESLint-AST-aware diff is future work.

- [ ] **Step 1: Write the failing test `typescript/cli/src/check.test.ts`**

```ts
import { describe, test, expect, beforeEach, afterEach } from 'bun:test';
import { mkdtempSync, rmSync, writeFileSync, copyFileSync, mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { check } from './check.js';

const here = dirname(fileURLToPath(import.meta.url));
const CONFIGS_DIR = resolve(here, '..', '..', 'configs');

describe('check', () => {
  let tmp: string;

  beforeEach(() => {
    tmp = mkdtempSync(join(tmpdir(), 'asp-check-'));
  });

  afterEach(() => {
    rmSync(tmp, { recursive: true, force: true });
  });

  test('returns 0 when consumer matches reference byte-for-byte', async () => {
    mkdirSync(tmp, { recursive: true });
    copyFileSync(join(CONFIGS_DIR, 'eslint.config.js'), join(tmp, 'eslint.config.js'));
    copyFileSync(join(CONFIGS_DIR, 'tsconfig.base.json'), join(tmp, 'tsconfig.base.json'));
    copyFileSync(join(CONFIGS_DIR, 'prettier.config.cjs'), join(tmp, 'prettier.config.cjs'));
    copyFileSync(join(CONFIGS_DIR, 'pre-commit-config.yaml'), join(tmp, '.pre-commit-config.yaml'));
    const code = await check({ target: tmp });
    expect(code).toBe(0);
  });

  test('returns 1 when a file is missing', async () => {
    const code = await check({ target: tmp });
    expect(code).toBe(1);
  });

  test('returns 1 when a file has drifted', async () => {
    copyFileSync(join(CONFIGS_DIR, 'eslint.config.js'), join(tmp, 'eslint.config.js'));
    copyFileSync(join(CONFIGS_DIR, 'tsconfig.base.json'), join(tmp, 'tsconfig.base.json'));
    copyFileSync(join(CONFIGS_DIR, 'prettier.config.cjs'), join(tmp, 'prettier.config.cjs'));
    writeFileSync(join(tmp, '.pre-commit-config.yaml'), 'drifted content\n');
    const code = await check({ target: tmp });
    expect(code).toBe(1);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/dev/git_puller/repos/aspergillus/typescript/cli
bun test src/check.test.ts
```

Expected: FAIL — `./check.js` doesn't exist.

- [ ] **Step 3: Write `typescript/cli/src/check.ts`**

```ts
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/dev/git_puller/repos/aspergillus/typescript/cli
bun test src/check.test.ts
```

Expected: 3 tests pass.

- [ ] **Step 5: Build-check the whole CLI**

```bash
cd /home/dev/git_puller/repos/aspergillus/typescript/cli
bun run build
```

Expected: `dist/index.js`, `dist/init.js`, `dist/check.js` produced with no errors.

- [ ] **Step 6: Smoke-test the built binary**

```bash
cd /tmp
rm -rf asp-smoke && mkdir asp-smoke
node /home/dev/git_puller/repos/aspergillus/typescript/cli/dist/index.js init --target /tmp/asp-smoke
node /home/dev/git_puller/repos/aspergillus/typescript/cli/dist/index.js check --target /tmp/asp-smoke
```

Expected: `init` prints 4 `wrote:` lines and a `bun add -D` hint; `check` prints `ok: all reference configs match` and exits 0.

- [ ] **Step 7: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus
git add typescript/cli/src/check.ts typescript/cli/src/check.test.ts
git commit -m "ts-cli: implement check command"
```

---

## Task 10: Write `typescript/README.md`

**Files:**
- Create: `typescript/README.md`

- [ ] **Step 1: Write the file**

Write `typescript/README.md`:

```markdown
# Aspergillus — TypeScript

Reference ESLint, tsconfig, Prettier, and pre-commit configs for applying
the aspergillus rule set to TypeScript projects (Node services, React/Vite
apps, shared libraries).

## What's here

- `configs/eslint.config.js` — reference flat config, Level 1 baseline
- `configs/tsconfig.base.json` — strict TypeScript compiler baseline
- `configs/prettier.config.cjs` — Prettier 3 config
- `configs/pre-commit-config.yaml` — pre-commit hooks (ESLint + Prettier)
- `cli/` — `aspergillus-ts` stub CLI (`init`, `check`)

## Adoption (subtree era)

1. **Add aspergillus as a subtree** in your repo:

   ```bash
   git subtree add --prefix vendor/aspergillus <repo-url> main --squash
   ```

2. **Build the CLI once:**

   ```bash
   cd vendor/aspergillus/typescript/cli && bun install && bun run build && cd -
   ```

3. **Run `init` to copy reference configs into the repo root:**

   ```bash
   node vendor/aspergillus/typescript/cli/dist/index.js init
   ```

   `init` writes (but never overwrites) `eslint.config.js`,
   `tsconfig.base.json`, `prettier.config.cjs`, and `.pre-commit-config.yaml`,
   then prints the `bun add -D …` command for peer devDependencies.

4. **Install the printed devDependencies, then run the linter once with
   auto-fix:**

   ```bash
   bun run eslint . --fix
   ```

5. **Pull updates** by re-running the subtree pull and then `check`:

   ```bash
   git subtree pull --prefix vendor/aspergillus <repo-url> main --squash
   node vendor/aspergillus/typescript/cli/dist/index.js check
   ```

   `check` exits non-zero on any drift from the reference. Wire it into CI
   if you want drift enforcement.

## Severity-flip workflow

Every new rule lands at `warn`. It stays at `warn` until the tree has zero
violations for that rule; then a dedicated PR flips it to `error`. Rationale:
separates the "adopt the rule" change (reviewable mechanics) from the
"fix every existing violation" change (reviewable scope).

This is the main incremental axis — not level-preset switching. Level 2
and Level 3 rules are appended to the same `eslint.config.js` over time;
each new rule is subject to the warn→error flip.

## Rule mapping (summary)

See `../docs/design.md` for the authoritative ASP ID ↔ per-language tool
mapping. For TypeScript the short form is:

| ASP | Tooling |
|-----|---------|
| 201 | `max-lines-per-function` |
| 202 | Manual (assertion density — code review) |
| 203 | `functional/no-let`, `functional/immutable-data` |
| 204 | `functional/no-loop-statements` |
| 205 | `eslint-plugin-boundaries` (architecture enforcement) |
| 206 | `eslint-plugin-boundaries` + project layering |
| 301 | `functional/no-throw-statements`, `@okee-tech/neverthrow/must-consume-result` |
| 302 | `strictNullChecks` in tsconfig + neverthrow-typed returns |

## Future: published packages

Once the reference configs stabilize across 3+ consumer repos, these will
be published to GitHub Packages as `@afdudley/eslint-config`,
`@afdudley/tsconfig`, `@afdudley/prettier-config`, and
`@afdudley/aspergillus-ts`. Consumer config collapses to:

```js
// eslint.config.js
import base from '@afdudley/eslint-config';
export default [...base, /* repo overrides */];
```

```json
// tsconfig.json
{ "extends": "@afdudley/tsconfig" }
```

Trigger: N=3 TS consumers, or the first breaking change that needs
coordinated updates across consumers.
```

- [ ] **Step 2: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus
git add typescript/README.md
git commit -m "ts: add adoption README"
```

---

## Task 11: Scaffold Rust placeholder

**Files:**
- Create: `rust/configs/clippy.toml`
- Create: `rust/configs/cargo-lints.toml`
- Create: `rust/README.md`

- [ ] **Step 1: Create the directory and write `rust/configs/clippy.toml`**

```bash
mkdir -p /home/dev/git_puller/repos/aspergillus/rust/configs
```

Write `rust/configs/clippy.toml`:

```toml
# Aspergillus reference clippy config.
# Copy into consumer repo root as `clippy.toml`.

too-many-lines-threshold = 60        # ASP201
cognitive-complexity-threshold = 15
allow-unwrap-in-tests = true
```

- [ ] **Step 2: Write `rust/configs/cargo-lints.toml`**

```toml
# Aspergillus reference lints.
# Paste into consumer `Cargo.toml`.

[lints.clippy]
too_many_lines = "warn"       # ASP201 — flip to "deny" when zero violations
unwrap_used = "deny"          # ASP301 — prefer Result<T, E>
expect_used = "deny"          # ASP301
panic = "deny"                # ASP301
todo = "deny"
# ASP203 (no global mutable state) — language enforces; no safe `static mut`
# ASP204 (no unbounded loops) — manual; prefer iterators
# ASP202 (assertion density) — manual; future dylint rule planned
```

- [ ] **Step 3: Write `rust/README.md`**

```markdown
# Aspergillus — Rust

Reference clippy and Cargo lint configs. No custom dylint rules yet;
Rust support is placeholder-tier.

## What's here

- `configs/clippy.toml` — clippy thresholds (line count, complexity)
- `configs/cargo-lints.toml` — snippet to paste into consumer `Cargo.toml`

## Adoption

1. Copy `configs/clippy.toml` to the consumer repo root.
2. Paste `configs/cargo-lints.toml` contents into the consumer's
   `Cargo.toml` under `[lints.clippy]`.
3. Run `cargo clippy --all-targets --all-features -- -D warnings`.
4. For each clippy rule at `warn`, fix violations and flip to `deny` in a
   dedicated PR. Matches the TypeScript severity-flip workflow.

## Mapping

See `../docs/design.md` for the authoritative ASP ID ↔ per-language tool
mapping. Rust summary:

| ASP | Tooling |
|-----|---------|
| 201 | `clippy::too_many_lines` (threshold 60) |
| 202 | Manual (future: custom dylint rule) |
| 203 | Language (no safe `static mut`) |
| 204 | Manual (prefer iterators) |
| 205 | Module structure (pure `core.rs`, I/O modules separate) |
| 206 | Module structure |
| 301 | `clippy::unwrap_used`, `expect_used`, `panic`; `Result<T, E>` |
| 302 | No null in the language; `Option` used sparingly |

## Future

A custom dylint rule for ASP202 (assertion density) is planned. Not started.
```

- [ ] **Step 4: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus
git add rust/
git commit -m "rust: add reference clippy/cargo configs (placeholder)"
```

---

## Task 12: Rewrite `docs/design.md` for the multi-language model

**Files:**
- Modify: `docs/design.md` (full rewrite)

- [ ] **Step 1: Replace the entire contents of `docs/design.md`**

The current design.md is Python-only. Replace it with a multi-language
description that carries the canonical rule-mapping table.

Write `docs/design.md`:

```markdown
# aspergillus — NASA-grade multi-language linter

A rule set inspired by NASA's Power of 10, implemented as a Fixit/LibCST
rule-pack for Python and as reference configs composing stock linters for
TypeScript and Rust. Named after *Aspergillus nidulans*, the first fungus
NASA intentionally grew on the International Space Station.

## Repository layout

```
aspergillus/
├── docs/                       # design, this file, implementation notes
├── python/                     # Python: actual code (Fixit rules)
├── typescript/                 # TS: reference configs + stub CLI
└── rust/                       # Rust: reference configs (placeholder)
```

Each language subtree stands alone. Consumers pull aspergillus as a git
subtree and use only the language subtree(s) they need.

## Rule set

### Level 1 — External tooling baseline (not aspergillus code)

Handled by existing tools, configured via aspergillus's reference configs:

| Language   | Tools |
|------------|-------|
| Python     | ruff, ruff-format, mypy, bandit, pre-commit |
| TypeScript | ESLint, typescript-eslint, Prettier, tsc strict, pre-commit |
| Rust       | clippy, rustfmt |

Reference configs live in `python/src/aspergillus/configs/`,
`typescript/configs/`, and `rust/configs/` respectively.

### Level 2 — Blocking

| Rule   | Description                              | Python (Fixit)                   | TypeScript                              | Rust |
|--------|------------------------------------------|----------------------------------|-----------------------------------------|------|
| ASP201 | Function ≤ 60 lines                      | `FunctionTooLong`                | `max-lines-per-function`                | `clippy::too_many_lines` |
| ASP202 | Assertion density ≥ 2 per function       | `LowAssertionDensity`            | Manual (code review)                    | Manual (planned dylint rule) |
| ASP203 | No global mutable state                  | `GlobalMutableState`             | `functional/no-let`, `immutable-data`   | Language (no safe `static mut`) |
| ASP204 | No unbounded loops                       | `UnboundedLoop`                  | `functional/no-loop-statements`         | Manual (prefer iterators) |
| ASP205 | No impure functions outside I/O boundary | `ImpureFunction`                 | `eslint-plugin-boundaries`              | Module structure (pure core) |
| ASP206 | Functional core / imperative shell       | `MixedIOAndLogic`                | `eslint-plugin-boundaries`              | Module structure |

### Level 3 — Warning

| Rule   | Description                        | Python (Fixit)            | TypeScript                                       | Rust |
|--------|------------------------------------|---------------------------|--------------------------------------------------|------|
| ASP301 | Result types, no exceptions        | `RaiseInsteadOfResult`    | `functional/no-throw-statements`, neverthrow     | `Result<T, E>`; `clippy::unwrap_used`/`expect_used`/`panic` |
| ASP302 | No Optional/None returns           | `OptionalReturnType`      | `strictNullChecks` + neverthrow                  | No null in language |

### Levels 4–5 — Planned, not implemented

Contracts, property-based tests (L4), and formal verification (L5). See
`python/src/aspergillus/` for the fullest current implementation, and
this document's history for research pointers.

## I/O blocklist (ASP205/206)

Python's purity and FC/IS rules rely on a curated I/O blocklist (see
`python/src/aspergillus/io_blocklist.py`). Consumers extend it per-project
via `[tool.aspergillus] extra_io_functions`. TypeScript's equivalent is
encoded as architectural boundaries (`eslint-plugin-boundaries`) rather
than a name blocklist — `core/` is forbidden from importing I/O modules,
which is more precise than pattern-matching call sites.

## Distribution

### Phase 1 — Subtree (current)

Consumers pull aspergillus as a git subtree at `vendor/aspergillus/`:

```bash
git subtree add --prefix vendor/aspergillus <repo-url> main --squash
```

- **Python consumer:** `uv tool install ./vendor/aspergillus/python`; set
  `[tool.fixit] enable = ["aspergillus.rules"]` in `pyproject.toml`.
- **TypeScript consumer:** build the CLI (`cd vendor/aspergillus/typescript/cli && bun install && bun run build`),
  run `node vendor/aspergillus/typescript/cli/dist/index.js init`,
  install printed devDependencies.
- **Rust consumer:** copy `vendor/aspergillus/rust/configs/clippy.toml` to
  repo root; paste `cargo-lints.toml` into `Cargo.toml`.

Updates: `git subtree pull --prefix vendor/aspergillus <repo-url> main --squash`.

### Phase 2 — Published packages (planned)

Once the reference configs stabilize across 3+ consumer repos:

- Python: already publishable from `python/` (uv, PyPI or private index).
- TypeScript: publish `@afdudley/eslint-config`, `@afdudley/tsconfig`,
  `@afdudley/prettier-config`, `@afdudley/aspergillus-ts` to
  GitHub Packages. Consumer config collapses to one-line `extends:`.
- Rust: publish a proc-macro crate or cargo-template (TBD) for cargo-lints
  injection.

## Enforcement model

- **Level 2 blocks** — pre-commit fails on any violation.
- **Level 3 also blocks** in strict adopters (recommended); warn elsewhere.
- **Severity-flip workflow**: every new rule lands at `warn`, stays there
  until violations reach 0, then flips to `error` in a dedicated PR.
- **Per-rule suppression**: `# noqa: ASP2XX` (Python), ESLint disable comments
  (TS), `#[allow(clippy::…)]` (Rust).

## What this is NOT

- Not a type checker (mypy/tsc/rustc handle that).
- Not a formatter (ruff-format/Prettier/rustfmt handle that).
- Not a general-purpose linter (ruff/ESLint recommended/clippy defaults).
- Not auto-fix (report-only in v0.1 for all three languages).
```

- [ ] **Step 2: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus
git add docs/design.md
git commit -m "docs: rewrite design.md for multi-language model"
```

---

## Task 13: Update root `README.md`

**Files:**
- Modify: `README.md` (replace contents)

- [ ] **Step 1: Read the current README**

```bash
cat /home/dev/git_puller/repos/aspergillus/README.md
```

Note the existing content so the rewrite preserves the NASA framing.

- [ ] **Step 2: Replace with multi-language README**

Write `README.md`:

```markdown
# aspergillus

NASA-grade code quality rules, applied across multiple languages.

Named after *Aspergillus nidulans*, the first fungus NASA intentionally
grew on the International Space Station.

## What it is

A rule set derived from NASA's Power of 10, ported to:

- **Python** — Fixit/LibCST rule-pack. Implements ASP201–206 (Level 2)
  and ASP301–302 (Level 3) as custom lint rules.
- **TypeScript** — reference ESLint/tsconfig/Prettier configs plus a
  stub `aspergillus-ts` CLI. Composes stock plugins; no custom rules.
- **Rust** — reference clippy/Cargo-lints configs. Placeholder tier.

See [`docs/design.md`](docs/design.md) for the full rule table and
per-language mappings.

## Repository layout

| Path | Contents |
|------|----------|
| `docs/` | Design, implementation notes, this repo's spec/plan history |
| `python/` | Python package, tests, pre-commit config |
| `typescript/` | Reference configs + stub CLI |
| `rust/` | Reference clippy/Cargo lint configs (placeholder) |

## Adoption

Consumers pull aspergillus as a git subtree and use the language
subtree(s) they need:

- Python — see `python/` (install via `uv tool install ./python`).
- TypeScript — see `typescript/README.md`.
- Rust — see `rust/README.md`.

## Levels

- **Level 1** — external tooling baseline (ruff, ESLint, clippy, …).
  Not aspergillus code; aspergillus ships reference configs only.
- **Level 2** — structural rules (ASP201–206). Blocking.
- **Level 3** — error-handling rules (ASP301–302). Blocking in strict
  adopters.
- **Level 4/5** — planned (contracts; formal verification). Not implemented.

See [`docs/design.md`](docs/design.md) for the authoritative rule table.
```

- [ ] **Step 3: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus
git add README.md
git commit -m "docs: update README for multi-language layout"
```

---

## Task 14: Update `docs/implementation-plan.md` (supersede note)

**Files:**
- Modify: `docs/implementation-plan.md`

- [ ] **Step 1: Prepend a supersede note**

Read the file first to see what's there:

```bash
head -5 /home/dev/git_puller/repos/aspergillus/docs/implementation-plan.md
```

Then prepend this block at the top of the file (do not delete existing content):

```markdown
> **Superseded by the multi-language restructure.** This document describes
> the original single-language Python implementation plan. The authoritative
> layout and per-language plan now live in
> `docs/superpowers/plans/2026-04-24-aspergillus-multilang-restructure.md`
> and the updated design in `docs/design.md`. Kept for history.

---

```

- [ ] **Step 2: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus
git add docs/implementation-plan.md
git commit -m "docs: note implementation-plan.md is superseded"
```

---

## Task 15: End-to-end dogfood — apply to a scratch target

**Files:** (verification only — no files modified in this repo)

- [ ] **Step 1: Run `init` into a temp directory**

```bash
rm -rf /tmp/asp-dogfood && mkdir /tmp/asp-dogfood
cd /home/dev/git_puller/repos/aspergillus/typescript/cli
node dist/index.js init --target /tmp/asp-dogfood
ls /tmp/asp-dogfood
```

Expected output from `init`: 4 `wrote:` lines listing `eslint.config.js`,
`tsconfig.base.json`, `prettier.config.cjs`, `.pre-commit-config.yaml`,
followed by a `bun add -D …` hint.
Expected `ls`: 4 files visible (note `.pre-commit-config.yaml` is dotfiled,
may need `ls -a`).

- [ ] **Step 2: Run `check` to confirm zero drift**

```bash
node /home/dev/git_puller/repos/aspergillus/typescript/cli/dist/index.js check --target /tmp/asp-dogfood
echo "exit=$?"
```

Expected: `ok: all reference configs match` and `exit=0`.

- [ ] **Step 3: Introduce drift and confirm `check` catches it**

```bash
echo "drifted" >> /tmp/asp-dogfood/.pre-commit-config.yaml
node /home/dev/git_puller/repos/aspergillus/typescript/cli/dist/index.js check --target /tmp/asp-dogfood
echo "exit=$?"
```

Expected: `drifted: .pre-commit-config.yaml`, summary line, `exit=1`.

- [ ] **Step 4: Clean up**

```bash
rm -rf /tmp/asp-dogfood
```

No commit for this task — verification only.

---

## Task 16: Final self-lint on Python side after restructure

**Files:** (verification only)

- [ ] **Step 1: Run pre-commit against the moved Python code**

```bash
cd /home/dev/git_puller/repos/aspergillus/python
uv run pre-commit run --all-files
```

Expected: all hooks pass (ruff, ruff-format, mypy, fixit/aspergillus). If
pre-commit fails because `.pre-commit-config.yaml` references paths that no
longer exist (e.g. `src/`), edit the file to reference `src/` relative to
the `python/` dir — it already should, since we did a whole-tree move.

- [ ] **Step 2: If any config was updated, commit**

```bash
cd /home/dev/git_puller/repos/aspergillus
git status --short
# If python/.pre-commit-config.yaml was edited:
git add python/.pre-commit-config.yaml
git commit -m "python: fix pre-commit paths after restructure"
```

Otherwise nothing to commit.

---

## Out of scope (follow-up work)

- Dogfooding into TrashScan-Explorer (separate plan — requires coordinating
  with an actual consumer repo's existing ESLint config).
- Appending Level 2 mapped rules to `typescript/configs/eslint.config.js`
  (separate plan — requires deciding the `boundaries/elements` layout per
  consumer archetype: Node service, React/Vite SPA, shared lib).
- Appending Level 3 mapped rules + `neverthrow` integration.
- Publishing packages to GitHub Packages (Phase 2 milestone).
- Custom dylint rule for Rust ASP202.

---

## Verification summary

After all tasks:

- `cd python && uv run pytest && uv run pre-commit run --all-files` — green.
- `cd typescript/cli && bun test && bun run build` — green.
- `node typescript/cli/dist/index.js init --target /tmp/x` into an empty dir
  writes 4 files and prints the dev-deps hint.
- `node typescript/cli/dist/index.js check --target /tmp/x` exits 0 on a
  fresh init and exits 1 after tampering.
- `docs/design.md` contains the multi-language rule-mapping table.
- `rust/README.md`, `typescript/README.md`, and root `README.md` all exist
  and link to `docs/design.md`.
