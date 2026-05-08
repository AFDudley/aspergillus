# L3 Error Handling Implementation Plan (TypeScript)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement aspergillus Level 3 in TypeScript per `docs/design-decisions/2026-05-08-l3-error-handling-mechanism.md`: refactor layouts to support per-element severity stratification, wire L3 rules at `warn`, and ship a reference discriminated-union error module.

**Architecture:** Five existing layout files shift from a single config block to an array of blocks. Three blocks per layout: boundaries enforcement (existing), L3 functional-core block (rules at `warn`), L3 imperative-shell block (`functional/no-throw-statements` set to `off`; `must-consume-result` and `strict-boolean-expressions` stay `warn`). Base eslint config (`typescript/configs/eslint.config.js`) gets the same three L3 rules wired at `warn` so consumers without a layout still get the universal-applicability rules. New `@afdudley/aspergillus/errors` exports a tiny `AspError<TTag, TData>` discriminated-union helper; aspergillus rules enforce shape, not import.

**Tech Stack:** Node ≥18, ESLint v9 flat config, `eslint-plugin-functional`, `@okee-tech/eslint-plugin-neverthrow`, `@typescript-eslint/strict-boolean-expressions` (in `typescript-eslint`), `bun:test` for unit tests.

---

## File structure

**Create:**

| File | Responsibility |
|---|---|
| `typescript/errors/index.js` | `AspError<TTag, TData>` JSDoc type + `aspError(tag, message, data?, cause?)` constructor |
| `typescript/errors/index.test.js` | bun:test unit tests for the constructor |
| `typescript/layouts/layouts.test.js` | bun:test shape assertions for all 5 layouts (array shape, expected severity per element type) |

**Modify:**

| File | Change |
|---|---|
| `typescript/layouts/node-service.js` | Convert single-block export to array; add L3 stratification blocks |
| `typescript/layouts/react-spa.js` | Same |
| `typescript/layouts/rn-app.js` | Same |
| `typescript/layouts/generic-3-layer.js` | Same |
| `typescript/layouts/fullstack-monorepo.js` | Same |
| `typescript/configs/eslint.config.js` | Add L3 rule block (universal rules at `warn`); add `@okee-tech/neverthrow` plugin import |
| `package.json` | Add `./errors` export; add new peer-deps comment in eslint.config (no actual deps change since plugins are peerDeps already documented in the file's banner) |
| `docs/design.md` | Rewrite L3 row of rule table + L3 prose; cross-link the design-decisions doc |

**Stratification rule** (applied across all layouts):

- `must-consume-result` and `strict-boolean-expressions`: `warn` everywhere (these are universally good — a Result that's ignored is a bug regardless of layer; `if (x)` ambiguity is a type-soundness problem regardless of layer).
- `functional/no-throw-statements`: `warn` in functional-core element types, `off` in imperative-shell element types.

Per-layout element classification:

| Layout | FC (warn no-throw) | Shell (off no-throw) |
|---|---|---|
| `generic-3-layer` | `core`, `infra` | `app` |
| `node-service` | `core`, `db`, `services` | `routes` |
| `rn-app` | `core`, `services` | `hooks`, `components`, `screens` |
| `react-spa` | `shared`, `services` | `hooks`, `components`, `pages` |
| `fullstack-monorepo` | `server-core`, `server-db`, `server-services`, `client-shared`, `client-services`, `shared` | `server-routes`, `client-hooks`, `client-components`, `client-pages` |

Severity-flip workflow: rules land at `warn`. Consumers flip the FC `no-throw-statements` to `error` (and the universal `must-consume-result` and `strict-boolean-expressions`) in the PR that achieves zero violations on their codebase. The shell `off` is permanent — that layer is allowed to throw at framework boundaries and catch from third-party libraries.

---

## Task 1: Reference error module

**Files:**
- Create: `typescript/errors/index.js`
- Create: `typescript/errors/index.test.js`
- Modify: `package.json` (add `./errors` to `exports` + add `typescript/errors/**` to `files`)

- [ ] **Step 1: Write the failing test**

Create `typescript/errors/index.test.js`:

```js
// Tests for the @afdudley/aspergillus/errors reference helper.

import { describe, it, expect } from 'bun:test';

import { aspError } from './index.js';

describe('aspError', () => {
  it('creates an object with _tag and message', () => {
    const e = aspError('NotFound', 'user 42 missing');
    expect(e._tag).toBe('NotFound');
    expect(e.message).toBe('user 42 missing');
    expect(e.data).toBeUndefined();
    expect(e.cause).toBeUndefined();
  });

  it('attaches optional data', () => {
    const e = aspError('Validation', 'bad email', { field: 'email' });
    expect(e.data).toEqual({ field: 'email' });
  });

  it('attaches optional cause', () => {
    const inner = new Error('connection refused');
    const e = aspError('Db', 'database error', undefined, inner);
    expect(e.cause).toBe(inner);
  });

  it('preserves discriminated _tag literal', () => {
    const e1 = aspError('A', 'a');
    const e2 = aspError('B', 'b');
    expect(e1._tag).toBe('A');
    expect(e2._tag).toBe('B');
  });

  it('returns a frozen-shaped plain object (no prototype chain)', () => {
    const e = aspError('Plain', 'msg');
    expect(Object.getPrototypeOf(e)).toBe(Object.prototype);
    expect(e instanceof Error).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/dev/git_puller/repos/aspergillus && bun test typescript/errors
```

Expected: FAIL with module-not-found error on `./index.js`.

- [ ] **Step 3: Implement the helper**

Create `typescript/errors/index.js`:

```js
// Reference discriminated-union error helper for aspergillus consumers.
//
// Aspergillus L3 rules enforce SHAPE, not import. Consumers may use
// this helper, build their own `AspError`-shaped union, or bring an
// existing convention. The fields below are the minimum the rules
// recognize.
//
// Usage:
//   import { aspError } from '@afdudley/aspergillus/errors';
//
//   /** @typedef {import('@afdudley/aspergillus/errors').AspError<'NotFound', { id: string }>} NotFoundError */
//
//   export const notFound = (id) =>
//     aspError('NotFound', `user ${id} not found`, { id });

/**
 * @template {string} TTag
 * @template TData
 * @typedef {{
 *   readonly _tag: TTag,
 *   readonly message: string,
 *   readonly data?: TData,
 *   readonly cause?: unknown,
 * }} AspError
 */

/**
 * Construct an AspError. Plain object; no prototype chain, no
 * `instanceof` semantics. `_tag` is a literal type that drives
 * exhaustive switch checking on the consumer side.
 *
 * @template {string} TTag
 * @template TData
 * @param {TTag} tag
 * @param {string} message
 * @param {TData} [data]
 * @param {unknown} [cause]
 * @returns {AspError<TTag, TData>}
 */
export const aspError = (tag, message, data, cause) => ({
  _tag: tag,
  message,
  data,
  cause,
});
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/dev/git_puller/repos/aspergillus && bun test typescript/errors
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Update package.json exports + files**

Modify `package.json`. The current `exports` block looks like:

```json
  "exports": {
    "./eslint-config": "./typescript/configs/eslint.config.js",
    "./eslint-rules": "./typescript/rules/index.js",
    "./layouts/*": "./typescript/layouts/*.js",
    "./tsconfig": "./typescript/configs/tsconfig.base.json",
    "./prettier-config": "./typescript/configs/prettier.config.cjs",
    "./pre-commit": "./typescript/configs/pre-commit-config.yaml"
  },
```

Add a new line `"./errors": "./typescript/errors/index.js",` between `./eslint-rules` and `./layouts/*` (mind the trailing comma).

The current `files` array contains:

```json
  "files": [
    "typescript/configs/**",
    "typescript/cli/lib/**",
    "typescript/cli/package.json",
    "typescript/rules/**",
    "!typescript/rules/**/*.test.js",
    "!typescript/rules/package.json",
    "typescript/layouts/**",
    "!typescript/layouts/index.js",
    "README.md",
    "LICENSE"
  ],
```

Add two new lines after `"!typescript/rules/package.json",` (before `typescript/layouts/**`):

```json
    "typescript/errors/**",
    "!typescript/errors/**/*.test.js",
```

- [ ] **Step 6: Verify package shape**

```bash
cd /home/dev/git_puller/repos/aspergillus && node --input-type=module -e "import('./typescript/errors/index.js').then(m => console.log(typeof m.aspError))"
```

Expected output: `function`

- [ ] **Step 7: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus && git add typescript/errors/ package.json && git commit -m "$(cat <<'EOF'
Add reference AspError discriminated-union helper

L3 rules enforce shape, not import. Consumers may use this helper,
build their own AspError-shaped union, or bring an existing convention.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Layout shape test scaffold

**Files:**
- Create: `typescript/layouts/layouts.test.js`

This task writes the failing test that drives the layout refactors in Tasks 3–7. Tests will fail until each layout is converted; that's the TDD signal.

- [ ] **Step 1: Write the failing tests**

Create `typescript/layouts/layouts.test.js`:

```js
// Shape tests for aspergillus layouts. Each layout exports an array of
// flat-config blocks: a boundaries block plus L3 stratification blocks.

import { describe, it, expect } from 'bun:test';

import genericThreeLayer from './generic-3-layer.js';
import nodeService from './node-service.js';
import reactSpa from './react-spa.js';
import rnApp from './rn-app.js';
import fullstackMonorepo from './fullstack-monorepo.js';

const ALL = {
  'generic-3-layer': genericThreeLayer,
  'node-service': nodeService,
  'react-spa': reactSpa,
  'rn-app': rnApp,
  'fullstack-monorepo': fullstackMonorepo,
};

const findBlock = (layout, predicate) => layout.find(predicate);
const hasFilesGlob = (block, substring) =>
  Array.isArray(block.files) && block.files.some((f) => f.includes(substring));

describe.each(Object.entries(ALL))('layout %s', (name, layout) => {
  it('exports an array of config blocks', () => {
    expect(Array.isArray(layout)).toBe(true);
    expect(layout.length).toBeGreaterThanOrEqual(3);
  });

  it('first block defines boundaries plugin and elements', () => {
    const first = layout[0];
    expect(first.plugins?.boundaries).toBeDefined();
    expect(first.settings?.['boundaries/elements']).toBeDefined();
  });

  it('has an FC block that warns no-throw-statements', () => {
    const fc = findBlock(
      layout,
      (b) => b.rules?.['functional/no-throw-statements'] === 'warn',
    );
    expect(fc).toBeDefined();
  });

  it('has a shell block that disables no-throw-statements', () => {
    const shell = findBlock(
      layout,
      (b) => b.rules?.['functional/no-throw-statements'] === 'off',
    );
    expect(shell).toBeDefined();
  });
});

describe('node-service stratification', () => {
  it('FC block targets core, db, services', () => {
    const fc = findBlock(
      nodeService,
      (b) => b.rules?.['functional/no-throw-statements'] === 'warn',
    );
    expect(hasFilesGlob(fc, '/core/')).toBe(true);
    expect(hasFilesGlob(fc, '/db/')).toBe(true);
    expect(hasFilesGlob(fc, '/services/')).toBe(true);
  });

  it('shell block targets routes', () => {
    const shell = findBlock(
      nodeService,
      (b) => b.rules?.['functional/no-throw-statements'] === 'off',
    );
    expect(hasFilesGlob(shell, '/routes/')).toBe(true);
  });
});

describe('fullstack-monorepo stratification', () => {
  it('FC block covers server- and client- FC element globs', () => {
    const fc = findBlock(
      fullstackMonorepo,
      (b) => b.rules?.['functional/no-throw-statements'] === 'warn',
    );
    expect(hasFilesGlob(fc, '/server/')).toBe(true);
    expect(hasFilesGlob(fc, '/client/')).toBe(true);
  });

  it('shell block covers server-routes and client-pages globs', () => {
    const shell = findBlock(
      fullstackMonorepo,
      (b) => b.rules?.['functional/no-throw-statements'] === 'off',
    );
    expect(hasFilesGlob(shell, '/routes/')).toBe(true);
    expect(hasFilesGlob(shell, '/pages/')).toBe(true);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/dev/git_puller/repos/aspergillus && bun test typescript/layouts
```

Expected: FAIL — every layout currently exports a single object, not an array. The first assertion (`Array.isArray`) fails for all 5.

- [ ] **Step 3: Commit the failing tests**

```bash
cd /home/dev/git_puller/repos/aspergillus && git add typescript/layouts/layouts.test.js && git commit -m "$(cat <<'EOF'
Add layout shape tests (failing) for L3 refactor

Asserts each layout exports an array of flat-config blocks with FC and
shell L3 stratification. Tasks 3-7 convert each layout in turn.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Refactor `generic-3-layer` layout

**Files:**
- Modify: `typescript/layouts/generic-3-layer.js`

- [ ] **Step 1: Verify current shape**

```bash
cd /home/dev/git_puller/repos/aspergillus && node --input-type=module -e "import('./typescript/layouts/generic-3-layer.js').then(m => console.log(Array.isArray(m.default)))"
```

Expected: `false` (single object, not array)

- [ ] **Step 2: Convert to array of blocks with L3 stratification**

Replace the `export default { ... };` block in `typescript/layouts/generic-3-layer.js` with:

```js
const elements = [
  { type: 'core', pattern: ['**/core/**', '**/lib/**'] },
  { type: 'infra', pattern: ['**/infra/**', '**/services/**'] },
  { type: 'app', pattern: '**/app/**' },
];

export default [
  // Block 1: boundaries enforcement (ASP205/206) — applies to all files.
  {
    files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    plugins: { boundaries },
    settings: {
      'boundaries/elements': elements,
      'boundaries/include': ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
      'boundaries/ignore': ['**/*.test.*', '**/*.spec.*', '**/__tests__/**'],
      'import/resolver': {
        typescript: { alwaysTryTypes: true },
      },
    },
    rules: {
      'boundaries/dependencies': [
        'warn',
        {
          default: 'disallow',
          rules: [
            // Type-only imports are allowed everywhere.
            {
              from: { type: '*' },
              allow: { to: { type: '*' }, dependency: { kind: 'type' } },
            },
            { from: { type: 'core' }, allow: { to: { type: 'core' } } },
            { from: { type: 'infra' }, allow: { to: { type: ['infra', 'core'] } } },
            { from: { type: 'app' }, allow: { to: { type: ['app', 'infra', 'core'] } } },
          ],
        },
      ],
    },
  },

  // Block 2: L3 functional-core — no-throw lands at warn (severity-flip
  // workflow). Universal L3 rules also live here so they're scoped to
  // the same files: globs.
  {
    files: ['**/core/**/*.{ts,tsx,js,jsx,mjs,cjs}', '**/lib/**/*.{ts,tsx,js,jsx,mjs,cjs}', '**/infra/**/*.{ts,tsx,js,jsx,mjs,cjs}', '**/services/**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    rules: {
      'functional/no-throw-statements': 'warn',
    },
  },

  // Block 3: L3 imperative-shell — no-throw is off. Shell may throw at
  // framework boundaries (HTTP, IPC) and catch from third-party libs.
  {
    files: ['**/app/**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    rules: {
      'functional/no-throw-statements': 'off',
    },
  },
];
```

- [ ] **Step 3: Run shape tests**

```bash
cd /home/dev/git_puller/repos/aspergillus && bun test typescript/layouts/layouts.test.js
```

Expected: tests for `generic-3-layer` PASS; other layouts still FAIL.

- [ ] **Step 4: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus && git add typescript/layouts/generic-3-layer.js && git commit -m "$(cat <<'EOF'
Refactor generic-3-layer layout to array shape with L3 stratification

Single config block becomes three: boundaries, L3 functional-core
(no-throw warn), L3 imperative-shell (no-throw off).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Refactor `node-service` layout

**Files:**
- Modify: `typescript/layouts/node-service.js`

- [ ] **Step 1: Convert to array of blocks with L3 stratification**

Replace the `export default { ... };` block in `typescript/layouts/node-service.js` with:

```js
const elements = [
  { type: 'core', pattern: ['**/core/**', '**/lib/**'] },
  { type: 'db', pattern: ['**/db/**', '**/repositories/**'] },
  { type: 'services', pattern: '**/services/**' },
  { type: 'routes', pattern: ['**/routes/**', '**/controllers/**', '**/handlers/**'] },
];

export default [
  {
    files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    plugins: { boundaries },
    settings: {
      'boundaries/elements': elements,
      'boundaries/include': ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
      'boundaries/ignore': ['**/*.test.*', '**/*.spec.*', '**/__tests__/**'],
      'import/resolver': {
        typescript: { alwaysTryTypes: true },
      },
    },
    rules: {
      'boundaries/dependencies': [
        'warn',
        {
          default: 'disallow',
          rules: [
            {
              from: { type: '*' },
              allow: { to: { type: '*' }, dependency: { kind: 'type' } },
            },
            { from: { type: 'core' }, allow: { to: { type: 'core' } } },
            { from: { type: 'db' }, allow: { to: { type: ['db', 'core'] } } },
            { from: { type: 'services' }, allow: { to: { type: ['services', 'db', 'core'] } } },
            { from: { type: 'routes' }, allow: { to: { type: ['routes', 'services', 'core'] } } },
          ],
        },
      ],
    },
  },

  // L3 functional-core: core, db, services.
  {
    files: [
      '**/core/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/lib/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/db/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/repositories/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/services/**/*.{ts,tsx,js,jsx,mjs,cjs}',
    ],
    rules: {
      'functional/no-throw-statements': 'warn',
    },
  },

  // L3 imperative-shell: routes/controllers/handlers throw HTTP errors
  // and catch from third-party libs. Layer-correct.
  {
    files: [
      '**/routes/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/controllers/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/handlers/**/*.{ts,tsx,js,jsx,mjs,cjs}',
    ],
    rules: {
      'functional/no-throw-statements': 'off',
    },
  },
];
```

- [ ] **Step 2: Run shape tests**

```bash
cd /home/dev/git_puller/repos/aspergillus && bun test typescript/layouts/layouts.test.js
```

Expected: `node-service` tests PASS, including the targeted stratification tests.

- [ ] **Step 3: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus && git add typescript/layouts/node-service.js && git commit -m "$(cat <<'EOF'
Refactor node-service layout to array shape with L3 stratification

L3 FC: core, lib, db, repositories, services. L3 shell: routes,
controllers, handlers (allowed to throw at HTTP boundary and catch
from third-party libs).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Refactor `react-spa` layout

**Files:**
- Modify: `typescript/layouts/react-spa.js`

- [ ] **Step 1: Convert to array of blocks with L3 stratification**

Replace the `export default { ... };` block in `typescript/layouts/react-spa.js` with:

```js
const elements = [
  { type: 'services', pattern: ['**/services/**', '**/api/**'] },
  { type: 'hooks', pattern: '**/hooks/**' },
  { type: 'components', pattern: '**/components/**' },
  { type: 'pages', pattern: ['**/pages/**', '**/app/**'] },
  { type: 'shared', pattern: ['**/lib/**', '**/shared/**'] },
];

export default [
  {
    files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    plugins: { boundaries },
    settings: {
      'boundaries/elements': elements,
      'boundaries/include': ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
      'boundaries/ignore': ['**/*.test.*', '**/*.spec.*', '**/__tests__/**'],
      'import/resolver': {
        typescript: { alwaysTryTypes: true },
      },
    },
    rules: {
      'boundaries/dependencies': [
        'warn',
        {
          default: 'disallow',
          rules: [
            {
              from: { type: '*' },
              allow: { to: { type: '*' }, dependency: { kind: 'type' } },
            },
            { from: { type: 'shared' }, allow: { to: { type: 'shared' } } },
            { from: { type: 'services' }, allow: { to: { type: ['services', 'shared'] } } },
            { from: { type: 'hooks' }, allow: { to: { type: ['hooks', 'services', 'shared'] } } },
            { from: { type: 'components' }, allow: { to: { type: ['components', 'hooks', 'shared'] } } },
            { from: { type: 'pages' }, allow: { to: { type: ['pages', 'components', 'hooks', 'services', 'shared'] } } },
          ],
        },
      ],
    },
  },

  // L3 functional-core: shared, services.
  {
    files: [
      '**/shared/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/lib/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/services/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/api/**/*.{ts,tsx,js,jsx,mjs,cjs}',
    ],
    rules: {
      'functional/no-throw-statements': 'warn',
    },
  },

  // L3 imperative-shell: hooks/components/pages may handle UI events
  // that catch from third-party libraries.
  {
    files: [
      '**/hooks/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/components/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/pages/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/app/**/*.{ts,tsx,js,jsx,mjs,cjs}',
    ],
    rules: {
      'functional/no-throw-statements': 'off',
    },
  },
];
```

- [ ] **Step 2: Run shape tests**

```bash
cd /home/dev/git_puller/repos/aspergillus && bun test typescript/layouts/layouts.test.js
```

Expected: `react-spa` tests PASS.

- [ ] **Step 3: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus && git add typescript/layouts/react-spa.js && git commit -m "$(cat <<'EOF'
Refactor react-spa layout to array shape with L3 stratification

L3 FC: shared, lib, services, api. L3 shell: hooks, components,
pages, app (handle UI events that may catch from third-party libs).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Refactor `rn-app` layout

**Files:**
- Modify: `typescript/layouts/rn-app.js`

- [ ] **Step 1: Convert to array of blocks with L3 stratification**

Replace the `export default { ... };` block in `typescript/layouts/rn-app.js` with:

```js
const elements = [
  { type: 'core', pattern: ['**/core/**', '**/lib/**'] },
  { type: 'services', pattern: ['**/services/**', '**/api/**'] },
  { type: 'hooks', pattern: '**/hooks/**' },
  { type: 'components', pattern: '**/components/**' },
  { type: 'screens', pattern: '**/screens/**' },
];

export default [
  {
    files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    plugins: { boundaries },
    settings: {
      'boundaries/elements': elements,
      'boundaries/include': ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
      'boundaries/ignore': ['**/*.test.*', '**/*.spec.*', '**/__tests__/**'],
      'import/resolver': {
        typescript: { alwaysTryTypes: true },
      },
    },
    rules: {
      'boundaries/dependencies': [
        'warn',
        {
          default: 'disallow',
          rules: [
            {
              from: { type: '*' },
              allow: { to: { type: '*' }, dependency: { kind: 'type' } },
            },
            { from: { type: 'core' }, allow: { to: { type: 'core' } } },
            { from: { type: 'services' }, allow: { to: { type: ['services', 'core'] } } },
            { from: { type: 'hooks' }, allow: { to: { type: ['hooks', 'services', 'core'] } } },
            { from: { type: 'components' }, allow: { to: { type: ['components', 'hooks', 'core'] } } },
            { from: { type: 'screens' }, allow: { to: { type: ['screens', 'hooks', 'components', 'core'] } } },
          ],
        },
      ],
    },
  },

  // L3 functional-core: core, lib, services.
  {
    files: [
      '**/core/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/lib/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/services/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/api/**/*.{ts,tsx,js,jsx,mjs,cjs}',
    ],
    rules: {
      'functional/no-throw-statements': 'warn',
    },
  },

  // L3 imperative-shell: hooks/components/screens.
  {
    files: [
      '**/hooks/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/components/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/screens/**/*.{ts,tsx,js,jsx,mjs,cjs}',
    ],
    rules: {
      'functional/no-throw-statements': 'off',
    },
  },
];
```

- [ ] **Step 2: Run shape tests**

```bash
cd /home/dev/git_puller/repos/aspergillus && bun test typescript/layouts/layouts.test.js
```

Expected: `rn-app` tests PASS.

- [ ] **Step 3: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus && git add typescript/layouts/rn-app.js && git commit -m "$(cat <<'EOF'
Refactor rn-app layout to array shape with L3 stratification

L3 FC: core, lib, services, api. L3 shell: hooks, components, screens.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Refactor `fullstack-monorepo` layout

**Files:**
- Modify: `typescript/layouts/fullstack-monorepo.js`

- [ ] **Step 1: Convert to array of blocks with L3 stratification**

Replace the `export default { ... };` block in `typescript/layouts/fullstack-monorepo.js` with:

```js
const elements = [
  { type: 'server-core', pattern: ['**/server/**/core/**', '**/server/**/lib/**'] },
  { type: 'server-db', pattern: ['**/server/**/db/**', '**/server/**/repositories/**'] },
  { type: 'server-services', pattern: '**/server/**/services/**' },
  { type: 'server-routes', pattern: ['**/server/**/routes/**', '**/server/**/controllers/**', '**/server/**/handlers/**'] },
  { type: 'client-shared', pattern: ['**/client/**/lib/**', '**/client/**/shared/**'] },
  { type: 'client-services', pattern: ['**/client/**/services/**', '**/client/**/api/**'] },
  { type: 'client-hooks', pattern: '**/client/**/hooks/**' },
  { type: 'client-components', pattern: '**/client/**/components/**' },
  { type: 'client-pages', pattern: ['**/client/**/pages/**', '**/client/**/app/**'] },
  { type: 'shared', pattern: 'shared/**', mode: 'full' },
];

export default [
  {
    files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    plugins: { boundaries },
    settings: {
      'boundaries/elements': elements,
      'boundaries/include': ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
      'boundaries/ignore': ['**/*.test.*', '**/*.spec.*', '**/__tests__/**'],
      'import/resolver': {
        typescript: { alwaysTryTypes: true },
      },
    },
    rules: {
      'boundaries/dependencies': [
        'warn',
        {
          default: 'disallow',
          rules: [
            {
              from: { type: '*' },
              allow: { to: { type: '*' }, dependency: { kind: 'type' } },
            },
            { from: { type: 'shared' }, allow: { to: { type: 'shared' } } },
            { from: { type: 'server-core' }, allow: { to: { type: ['server-core', 'shared'] } } },
            { from: { type: 'server-db' }, allow: { to: { type: ['server-db', 'server-core', 'shared'] } } },
            { from: { type: 'server-services' }, allow: { to: { type: ['server-services', 'server-db', 'server-core', 'shared'] } } },
            { from: { type: 'server-routes' }, allow: { to: { type: ['server-routes', 'server-services', 'server-core', 'shared'] } } },
            { from: { type: 'client-shared' }, allow: { to: { type: ['client-shared', 'shared'] } } },
            { from: { type: 'client-services' }, allow: { to: { type: ['client-services', 'client-shared', 'shared'] } } },
            { from: { type: 'client-hooks' }, allow: { to: { type: ['client-hooks', 'client-services', 'client-shared', 'shared'] } } },
            { from: { type: 'client-components' }, allow: { to: { type: ['client-components', 'client-hooks', 'client-shared', 'shared'] } } },
            { from: { type: 'client-pages' }, allow: { to: { type: ['client-pages', 'client-components', 'client-hooks', 'client-services', 'client-shared', 'shared'] } } },
          ],
        },
      ],
    },
  },

  // L3 functional-core: server core/db/services + client shared/services
  // + top-level shared.
  {
    files: [
      '**/server/**/core/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/server/**/lib/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/server/**/db/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/server/**/repositories/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/server/**/services/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/client/**/lib/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/client/**/shared/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/client/**/services/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/client/**/api/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      'shared/**/*.{ts,tsx,js,jsx,mjs,cjs}',
    ],
    rules: {
      'functional/no-throw-statements': 'warn',
    },
  },

  // L3 imperative-shell: server routes + client UI layers.
  {
    files: [
      '**/server/**/routes/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/server/**/controllers/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/server/**/handlers/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/client/**/hooks/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/client/**/components/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/client/**/pages/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/client/**/app/**/*.{ts,tsx,js,jsx,mjs,cjs}',
    ],
    rules: {
      'functional/no-throw-statements': 'off',
    },
  },
];
```

- [ ] **Step 2: Run shape tests**

```bash
cd /home/dev/git_puller/repos/aspergillus && bun test typescript/layouts/layouts.test.js
```

Expected: ALL layout tests PASS, including `fullstack-monorepo` stratification.

- [ ] **Step 3: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus && git add typescript/layouts/fullstack-monorepo.js && git commit -m "$(cat <<'EOF'
Refactor fullstack-monorepo layout to array shape with L3 stratification

L3 FC: server core/db/services, client shared/services, top-level
shared. L3 shell: server routes/controllers/handlers, client hooks/
components/pages.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Wire L3 rules in base eslint config

**Files:**
- Modify: `typescript/configs/eslint.config.js`

The base config gets the universally-applicable L3 rules (`must-consume-result`, `strict-boolean-expressions`) at `warn` so consumers without a layout still get them. `no-throw-statements` stays out of the base — its severity is layer-dependent and lives in layouts.

- [ ] **Step 1: Add neverthrow plugin import**

In `typescript/configs/eslint.config.js`, after the existing `import functional from 'eslint-plugin-functional';` line, add:

```js
import neverthrow from '@okee-tech/eslint-plugin-neverthrow';
```

- [ ] **Step 2: Add L3 rule block**

In `typescript/configs/eslint.config.js`, after the existing Level 2 block (the one with `aspergillus`/`functional` plugins) and before the trailing `prettierConfig`, insert a new block:

```js
  // Level 3 — universal rules. Lands at warn pending severity-flip.
  // The layer-stratified rule (`functional/no-throw-statements`) lives
  // in the layout files so that imperative-shell layers can switch it
  // off. See docs/design-decisions/2026-05-08-l3-error-handling-mechanism.md.
  {
    files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    plugins: {
      '@okee-tech/neverthrow': neverthrow,
    },
    rules: {
      // ASP301 — must consume Result. Type-aware; checks the resolved
      // type, not the import path. A Result that's created and
      // discarded is a silently-dropped error. Universal — applies in
      // shell as well as core, since "we have a Result, do something
      // with it" is a layer-agnostic principle.
      '@okee-tech/neverthrow/must-consume-result': 'warn',

      // ASP302 — type-soundness for boolean expressions. Catches
      // `if (result)` ambiguity (truthy on a `Result` object always,
      // since neverthrow's Result is a non-empty object). Forces
      // explicit `result.isOk()` etc.
      '@typescript-eslint/strict-boolean-expressions': 'warn',
    },
  },
```

- [ ] **Step 3: Update the file's banner comment**

In the same file, update the comment that says `Level 2 rules (ASP201–204) land at warn per the severity-flip workflow; Level 3 rules are still pending.` Replace it with:

```
// Level 2 rules (ASP201–204) and Level 3 rules (ASP301–302) land at
// warn per the severity-flip workflow. The layer-stratified L3 rule
// (`functional/no-throw-statements`) is shipped via the layouts in
// `typescript/layouts/` — see docs/design-decisions/2026-05-08-l3-
// error-handling-mechanism.md.
```

And update the peer-deps comment block to add `@okee-tech/eslint-plugin-neverthrow` to the list:

```
//   eslint prettier typescript
//   @eslint/js typescript-eslint eslint-plugin-import
//   eslint-plugin-unused-imports eslint-plugin-functional
//   @okee-tech/eslint-plugin-neverthrow
//   eslint-config-prettier
```

- [ ] **Step 4: Smoke-test imports resolve**

```bash
cd /home/dev/git_puller/repos/aspergillus && node --input-type=module -e "import('./typescript/configs/eslint.config.js').then(c => console.log('blocks=' + c.default.length))"
```

Expected: prints `blocks=N` where `N` is one greater than before the change. If it errors with module not found on `@okee-tech/eslint-plugin-neverthrow`, that's expected — the plugin is a peer dep, not installed in aspergillus itself. The verification only confirms the JS file parses.

If the import error is a problem for the test command above, run instead:

```bash
cd /home/dev/git_puller/repos/aspergillus && node --check typescript/configs/eslint.config.js
```

Expected: no output (parse OK).

- [ ] **Step 5: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus && git add typescript/configs/eslint.config.js && git commit -m "$(cat <<'EOF'
Wire L3 universal rules into base eslint config

Adds @okee-tech/neverthrow/must-consume-result and
@typescript-eslint/strict-boolean-expressions at warn. The
layer-stratified L3 rule (functional/no-throw-statements) ships via
layouts so imperative-shell layers can switch it off.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Update `docs/design.md`

**Files:**
- Modify: `docs/design.md`

- [ ] **Step 1: Read the current L3 section**

```bash
cd /home/dev/git_puller/repos/aspergillus && sed -n '57,68p' docs/design.md
```

This shows the existing L3 row of the rule table.

- [ ] **Step 2: Update the L3 row in the rule table**

Find the line in `docs/design.md` that begins with `| ASP301 | Result types, no exceptions` and replace the L3 rows (ASP301 and ASP302) with:

```
| ASP301 | Result types, no exceptions        | `RaiseInsteadOfResult`    | `functional/no-throw-statements` (FC layers only) + `@okee-tech/neverthrow/must-consume-result` (universal) | `Result<T, E>`; `clippy::unwrap_used`/`expect_used`/`panic` |
| ASP302 | No Optional/None returns           | `OptionalReturnType`      | `tsconfig.strictNullChecks` + `@typescript-eslint/strict-boolean-expressions` | No null in language |
```

- [ ] **Step 3: Update the "Level 3 — Warning" section heading and prose**

After the rule table, update the `### Level 3 — Warning` section to describe the implementation. Find the existing prose under that heading and replace it with:

```
### Level 3 — Warning

Level 3 enforces NASA Power of 10 Rule 7: errors must be visible in
types and impossible to silently drop. In TypeScript this is
implemented via three rules:

- `functional/no-throw-statements` — bans `throw` in functional-core
  layers (`core`, `services`, etc., per the layout). Imperative-shell
  layers (`routes`, `hooks`, etc.) keep `throw` available — they are
  allowed to throw at framework boundaries and catch from third-party
  libs that throw. Layer-stratification ships in the layouts.
- `@okee-tech/neverthrow/must-consume-result` — type-aware; flags any
  `Result<T, E>` that's created and discarded. Universal (FC and
  shell). Locks `neverthrow` as load-bearing rather than optional.
- `@typescript-eslint/strict-boolean-expressions` — catches
  `if (result)` ambiguity and similar truthy-on-objects patterns.
  Universal.

Plus `tsconfig.strictNullChecks: true` (covers ASP302 — no
`null`/`undefined` as error signal).

Result types come from the `neverthrow` library (`Result<T, E>` and
`ResultAsync<T, E>`). A reference discriminated-union error helper
ships at `@afdudley/aspergillus/errors` (`AspError<TTag, TData>` +
`aspError(tag, message, data?, cause?)`); consumers may use it, build
their own `AspError`-shaped union, or bring an existing convention.
Aspergillus rules enforce shape, not import.

Severity-flip workflow applies: rules land at `warn` and flip to
`error` once consumers reach zero violations on the relevant layer.
The shell `off` for `no-throw-statements` is permanent.

See `docs/design-decisions/2026-05-08-l3-error-handling-mechanism.md`
for the full rationale, options considered, and risks accepted.
```

- [ ] **Step 4: Update the "Level 3 also blocks" line in the enforcement-model section**

Find the line in `docs/design.md` that reads `- **Level 3 also blocks** in strict adopters (recommended); warn elsewhere.` and leave it as-is — the severity-flip workflow already matches this description.

- [ ] **Step 5: Commit**

```bash
cd /home/dev/git_puller/repos/aspergillus && git add docs/design.md && git commit -m "$(cat <<'EOF'
Update design.md L3 section to match implementation

Rewrite the L3 row of the rule table and the prose under "Level 3 —
Warning" to reflect the chosen mechanism (neverthrow + layer-stratified
no-throw + universal must-consume-result + strict-boolean-expressions)
and cross-link the design-decisions doc.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Verification (after all tasks complete)

- [ ] **Run all tests**

```bash
cd /home/dev/git_puller/repos/aspergillus && bun test
```

Expected: all tests pass — asp202 (pre-existing) + errors module + layout shape tests.

- [ ] **Verify package exports**

```bash
cd /home/dev/git_puller/repos/aspergillus && node --input-type=module -e "
const errors = await import('./typescript/errors/index.js');
console.log('aspError:', typeof errors.aspError);
const layouts = ['generic-3-layer', 'node-service', 'react-spa', 'rn-app', 'fullstack-monorepo'];
for (const name of layouts) {
  const m = await import('./typescript/layouts/' + name + '.js');
  console.log(name + ':', Array.isArray(m.default) ? 'array(' + m.default.length + ')' : 'NOT ARRAY');
}
"
```

Expected:

```
aspError: function
generic-3-layer: array(3)
node-service: array(3)
react-spa: array(3)
rn-app: array(3)
fullstack-monorepo: array(3)
```

- [ ] **Verify tsconfig already covers ASP302**

```bash
cd /home/dev/git_puller/repos/aspergillus && grep -E '"strict"|"strictNullChecks"' typescript/configs/tsconfig.base.json
```

Expected: `"strict": true,` (which implies `strictNullChecks: true`). No tsconfig change is required — ASP302's tsconfig requirement is already satisfied by the existing `strict: true`.

- [ ] **Branch summary**

```bash
cd /home/dev/git_puller/repos/aspergillus && git log multilang-support..HEAD --oneline
```

Expected output: ~10 commits — one design-decisions doc (already on branch), one error module, one shape-test scaffold, five layout refactors, one base config wiring, one design.md update.

---

## Notes for the implementer

- **Severity-flip discipline.** All L3 rules land at `warn`. Do not flip to `error` in this branch — that happens per-consumer when each codebase reaches zero violations.
- **Element-type matching.** The layouts use first-match-wins ordering for boundaries. Don't reorder elements within a layout's `boundaries/elements` array unless the existing comments say it's safe.
- **No L3 in `layouts/index.js`.** That file just lists layout names for the CLI's `--layout` flag validation.
- **Reference error module is JS, not TS.** Aspergillus ships JS with JSDoc types so consumers don't need a TS build step to use it. Keep the JSDoc `@template` annotations — they're how TS infers the types when consumers import.
