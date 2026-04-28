# TypeScript ASP205/206 + boundary layouts implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement ASP205 (no impure functions outside I/O boundary) and ASP206 (functional core / imperative shell) for TypeScript by shipping `eslint-plugin-boundaries` integration with five preset layouts (`node-service`, `rn-app`, `react-spa`, `fullstack-monorepo`, `generic-3-layer`) consumers select via `aspergillus-ts init --layout=<name>` (with interactive prompt fallback). Land at `0.1.0-rc.3`.

**Architecture:** Each preset layout is an ESLint flat-config block that registers the `eslint-plugin-boundaries` plugin, declares `boundaries/elements` (directory → element-type mapping), and configures `boundaries/element-types` (which element-types may import which) at `warn` severity. Layouts ship as importable `./layouts/<name>` package exports — `aspergillus-ts init` writes a thin `import layout from '@afdudley/aspergillus/layouts/<name>'` line into the consumer's `eslint.config.js` plus comments explaining how to switch layouts and how to override the imported settings. `--layout=none` (today's behavior) writes no layout import — the consumer declares elements themselves. `eslint-plugin-boundaries` is a peer dep installed only when a layout is chosen; `init`'s printed install command filters it for `--layout=none`.

**Tech Stack:** ESLint 9 flat config; `eslint-plugin-boundaries` (new peer dep, installed conditionally); `node:readline` for interactive prompt (no new runtime dep); bun:test for CLI tests.

---

## Why layouts are imports, not static blocks

The earlier draft of this plan had `init` write a static layout block into the consumer's `eslint.config.js`. We changed to imported exports because:

- Aspergillus refines the layout definitions over time. Updates ship to consumers via `npm update @afdudley/aspergillus`.
- The consumer's wrapper stays small — one import line instead of 20+ lines of element/rule definitions.
- Consumers can still override anything: ESLint flat config is "later block wins" for rules and "later wins" for `settings` array values, so an override block appended after the layout import takes precedence.

The trade-off is that layouts evolve under consumers' feet on aspergillus update. Mitigation: layouts land at `warn`, and any layout change should be a deliberate version bump in aspergillus with a CHANGELOG entry.

---

## File Structure

**New files:**
- `typescript/layouts/node-service.js`
- `typescript/layouts/rn-app.js`
- `typescript/layouts/react-spa.js`
- `typescript/layouts/fullstack-monorepo.js`
- `typescript/layouts/generic-3-layer.js`
- `typescript/layouts/index.js` — barrel that re-exports `LAYOUT_NAMES` constant for the CLI to use as a single source of truth
- `typescript/cli/src/layouts.ts` — CLI-side layout name list (mirror of `LAYOUT_NAMES`) plus prompt logic; kept TS-side because the CLI is TS

**Modified files:**
- `package.json` — bump version to `0.1.0-rc.3`; add `./layouts/*` subpath export; add `typescript/layouts/**` to `files`; declare `eslint-plugin-boundaries` as `peerDependenciesMeta` *optional* (since it's only required when a layout is chosen)
- `typescript/cli/src/index.ts` — parse `--layout=<name>` flag; pass through to `init`
- `typescript/cli/src/init.ts` — accept `layout` option; interactive prompt when TTY and flag absent; extend `eslintWrapper` template with optional layout import + override comments; filter `eslint-plugin-boundaries` from `DEV_DEPS` when `layout === 'none'`
- `typescript/cli/src/wrappers.ts` — `isEslintWrapper` already detects the aspergillus signature; verify it still matches new layout-included wrappers (likely no change needed if signature is the `import base from '@afdudley/aspergillus/eslint-config'` line)
- `typescript/cli/src/init.test.ts` — cover `--layout=<name>` for each name; cover `--layout=none` (no layout import in output); cover prompt flow with mocked stdin
- `typescript/configs/eslint.config.js` — append a Level 2 rule note for ASP205/206 referencing the layouts (no plugin registration here; layouts handle their own)
- `typescript/README.md` — new "Layouts (ASP205/206)" section; table of layouts; example override block
- `docs/design.md` — already updated in prior commit; verify the `0.1.0-rc.3` reference matches once published

**Out of scope:**
- Custom `aspergillus/asp205-purity-boundary` rule (Python-blocklist-style) — explicitly rejected; architectural boundaries are the right TS approach
- Auto-detection of consumer's project shape (e.g., reading `package.json` for `react-native` to suggest `rn-app`) — nice-to-have, not in scope for first cut
- A new `aspergillus-ts add-layout` subcommand — re-running `init --layout=<name>` already overwrites with `.local.bak` backup; no separate command needed

---

## Layout reference

Authoritative source for each layout's element types and import rules. Tasks 2–6 implement these one per task. Patterns use `**/<dir>/**` so they match files under any project root (works for both flat and monorepo layouts).

### `node-service` — Express/Fastify backend with DB

| Element | Pattern | Allowed imports |
|---|---|---|
| `core` | `**/core/**` | `core` |
| `db` | `**/db/**` | `db`, `core` |
| `services` | `**/services/**` | `services`, `db`, `core` |
| `routes` | `**/routes/**` | `routes`, `services`, `core` |

Rationale: routes can't bypass services to hit `db` directly (FC/IS); services wrap I/O over a pure core; core has no dependencies.

### `rn-app` — React Native (modeled on mtm)

| Element | Pattern | Allowed imports |
|---|---|---|
| `core` | `**/core/**` | `core` |
| `services` | `**/services/**` | `services`, `core` |
| `hooks` | `**/hooks/**` | `hooks`, `services`, `core` |
| `components` | `**/components/**` | `components`, `core` |
| `screens` | `**/screens/**` | `screens`, `hooks`, `components`, `core` |

Rationale: components are pure render functions of props (no `services` access); hooks are the imperative shell; screens compose hooks + components.

### `react-spa` — React/Vite SPA

| Element | Pattern | Allowed imports |
|---|---|---|
| `shared` | `**/shared/**` | `shared` |
| `services` | `**/services/**` | `services`, `shared` |
| `components` | `**/components/**` | `components`, `shared` |
| `pages` | `**/pages/**` | `pages`, `components`, `services`, `shared` |

Rationale: `shared` plays the `core` role per React-ecosystem convention; pages are the imperative shell.

### `fullstack-monorepo` — server + client + shared

| Element | Pattern | Allowed imports |
|---|---|---|
| `shared` | `**/shared/**` | `shared` |
| `server-core` | `**/server/core/**` | `server-core`, `shared` |
| `server-db` | `**/server/db/**` | `server-db`, `shared` |
| `server-services` | `**/server/services/**` | `server-services`, `server-db`, `server-core`, `shared` |
| `server-routes` | `**/server/routes/**` | `server-routes`, `server-services`, `server-core`, `shared` |
| `client-shared` | `**/client/shared/**` | `client-shared`, `shared` |
| `client-services` | `**/client/services/**` | `client-services`, `client-shared`, `shared` |
| `client-components` | `**/client/components/**` | `client-components`, `client-shared`, `shared` |
| `client-pages` | `**/client/pages/**` | `client-pages`, `client-components`, `client-services`, `client-shared`, `shared` |

Rationale: enforces the server/client split (no client → server imports outside `shared`); within each side, the FC/IS pattern. Matches TrashScan-Explorer's natural shape.

### `generic-3-layer` — fallback when nothing else fits

| Element | Pattern | Allowed imports |
|---|---|---|
| `core` | `**/core/**` | `core` |
| `infra` | `**/infra/**` | `infra`, `core` |
| `app` | `**/app/**` | `app`, `infra`, `core` |

Rationale: minimal viable FC/IS; consumers can refine later by switching to a more specific layout or overriding.

### `none` — escape hatch

`init --layout=none` writes the existing wrapper (no layout import). Consumer declares `settings.boundaries/elements` themselves if they want ASP205/206 enforcement.

---

## Task 1: Scaffold the layouts directory

**Files:**
- Create: `typescript/layouts/index.js`

`index.js` is a barrel exporting `LAYOUT_NAMES` for use by aspergillus's own tests and tools. Each layout file is imported separately via the `./layouts/<name>` subpath export — this barrel is internal-only (excluded from the `files` glob; not in the publish manifest).

- [ ] **Step 1: Create `typescript/layouts/index.js`**

```javascript
// Internal barrel — lists the layout names aspergillus ships. The CLI's
// `aspergillus-ts init --layout=<name>` flag validates against this list.
// Consumers import individual layouts via `@afdudley/aspergillus/layouts/<name>`,
// not this file (which is excluded from the publish manifest).

export const LAYOUT_NAMES = [
  'node-service',
  'rn-app',
  'react-spa',
  'fullstack-monorepo',
  'generic-3-layer',
];
```

- [ ] **Step 2: Commit**

```bash
git add typescript/layouts/index.js
git commit -m "layouts: scaffold layouts dir (internal barrel)"
```

---

## Task 2: Implement `node-service` layout

**Files:**
- Create: `typescript/layouts/node-service.js`

- [ ] **Step 1: Write `typescript/layouts/node-service.js`**

```javascript
// ASP205/206 boundary layout for Node.js services (Express/Fastify + DB).
//
// Elements (matched via path pattern):
//   core/     — pure logic. No I/O imports.
//   db/       — data access. Imports core.
//   services/ — I/O wrappers. Imports db + core.
//   routes/   — HTTP shell. Imports services + core (NOT db directly).
//
// Lands the boundaries/element-types rule at `warn`. Override or extend
// by appending a later flat-config block in your eslint.config.js.

import boundaries from 'eslint-plugin-boundaries';

export default {
  files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
  plugins: { boundaries },
  settings: {
    'boundaries/elements': [
      { type: 'core', pattern: '**/core/**' },
      { type: 'db', pattern: '**/db/**' },
      { type: 'services', pattern: '**/services/**' },
      { type: 'routes', pattern: '**/routes/**' },
    ],
    'boundaries/include': ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    'boundaries/ignore': ['**/*.test.*', '**/*.spec.*', '**/__tests__/**'],
  },
  rules: {
    'boundaries/element-types': [
      'warn',
      {
        default: 'disallow',
        rules: [
          { from: ['core'], allow: ['core'] },
          { from: ['db'], allow: ['db', 'core'] },
          { from: ['services'], allow: ['services', 'db', 'core'] },
          { from: ['routes'], allow: ['routes', 'services', 'core'] },
        ],
      },
    ],
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add typescript/layouts/node-service.js
git commit -m "layouts: add node-service (Express/Fastify + DB)"
```

---

## Task 3: Implement `rn-app` layout

**Files:**
- Create: `typescript/layouts/rn-app.js`

- [ ] **Step 1: Write the file**

```javascript
// ASP205/206 boundary layout for React Native apps. Modeled on the
// mtm code-quality.md pattern.
//
// Elements:
//   core/       — pure functions. No imports from native modules / API.
//   services/   — I/O boundary. API calls, native module wrappers.
//   hooks/      — imperative shell. Calls services, manages React state.
//   components/ — pure render of props. No useEffect, no I/O.
//   screens/    — compose hooks + components. Thin wiring.

import boundaries from 'eslint-plugin-boundaries';

export default {
  files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
  plugins: { boundaries },
  settings: {
    'boundaries/elements': [
      { type: 'core', pattern: '**/core/**' },
      { type: 'services', pattern: '**/services/**' },
      { type: 'hooks', pattern: '**/hooks/**' },
      { type: 'components', pattern: '**/components/**' },
      { type: 'screens', pattern: '**/screens/**' },
    ],
    'boundaries/include': ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    'boundaries/ignore': ['**/*.test.*', '**/*.spec.*', '**/__tests__/**'],
  },
  rules: {
    'boundaries/element-types': [
      'warn',
      {
        default: 'disallow',
        rules: [
          { from: ['core'], allow: ['core'] },
          { from: ['services'], allow: ['services', 'core'] },
          { from: ['hooks'], allow: ['hooks', 'services', 'core'] },
          { from: ['components'], allow: ['components', 'core'] },
          { from: ['screens'], allow: ['screens', 'hooks', 'components', 'core'] },
        ],
      },
    ],
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add typescript/layouts/rn-app.js
git commit -m "layouts: add rn-app (React Native, modeled on mtm)"
```

---

## Task 4: Implement `react-spa` layout

**Files:**
- Create: `typescript/layouts/react-spa.js`

- [ ] **Step 1: Write the file**

```javascript
// ASP205/206 boundary layout for React/Vite single-page apps.
//
// Elements:
//   shared/     — pure utilities, types, hooks-without-IO.
//   services/   — API clients, storage adapters, I/O boundary.
//   components/ — pure render of props.
//   pages/      — compose components + services. Top-level shell.

import boundaries from 'eslint-plugin-boundaries';

export default {
  files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
  plugins: { boundaries },
  settings: {
    'boundaries/elements': [
      { type: 'shared', pattern: '**/shared/**' },
      { type: 'services', pattern: '**/services/**' },
      { type: 'components', pattern: '**/components/**' },
      { type: 'pages', pattern: '**/pages/**' },
    ],
    'boundaries/include': ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    'boundaries/ignore': ['**/*.test.*', '**/*.spec.*', '**/__tests__/**'],
  },
  rules: {
    'boundaries/element-types': [
      'warn',
      {
        default: 'disallow',
        rules: [
          { from: ['shared'], allow: ['shared'] },
          { from: ['services'], allow: ['services', 'shared'] },
          { from: ['components'], allow: ['components', 'shared'] },
          { from: ['pages'], allow: ['pages', 'components', 'services', 'shared'] },
        ],
      },
    ],
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add typescript/layouts/react-spa.js
git commit -m "layouts: add react-spa (React/Vite SPA)"
```

---

## Task 5: Implement `fullstack-monorepo` layout

**Files:**
- Create: `typescript/layouts/fullstack-monorepo.js`

This is the largest layout — 9 element types covering the server/client split. Patterns assume the conventional `server/` and `client/` top-level dirs (matches TrashScan-Explorer).

- [ ] **Step 1: Write the file**

```javascript
// ASP205/206 boundary layout for full-stack TypeScript monorepos with
// server/ and client/ subtrees plus a top-level shared/.
//
// Server elements:
//   server/core/     — pure logic
//   server/db/       — data access
//   server/services/ — I/O wrappers (DB, external APIs)
//   server/routes/   — HTTP shell
//
// Client elements:
//   client/shared/     — client-only pure utilities
//   client/services/   — API clients, storage adapters
//   client/components/ — pure render
//   client/pages/      — page-level shell composing components + services
//
// Top-level:
//   shared/ — types/utils shared between server and client (pure only)

import boundaries from 'eslint-plugin-boundaries';

export default {
  files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
  plugins: { boundaries },
  settings: {
    'boundaries/elements': [
      { type: 'shared', pattern: '**/shared/**' },
      { type: 'server-core', pattern: '**/server/core/**' },
      { type: 'server-db', pattern: '**/server/db/**' },
      { type: 'server-services', pattern: '**/server/services/**' },
      { type: 'server-routes', pattern: '**/server/routes/**' },
      { type: 'client-shared', pattern: '**/client/shared/**' },
      { type: 'client-services', pattern: '**/client/services/**' },
      { type: 'client-components', pattern: '**/client/components/**' },
      { type: 'client-pages', pattern: '**/client/pages/**' },
    ],
    'boundaries/include': ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    'boundaries/ignore': ['**/*.test.*', '**/*.spec.*', '**/__tests__/**'],
  },
  rules: {
    'boundaries/element-types': [
      'warn',
      {
        default: 'disallow',
        rules: [
          { from: ['shared'], allow: ['shared'] },
          { from: ['server-core'], allow: ['server-core', 'shared'] },
          { from: ['server-db'], allow: ['server-db', 'shared'] },
          { from: ['server-services'], allow: ['server-services', 'server-db', 'server-core', 'shared'] },
          { from: ['server-routes'], allow: ['server-routes', 'server-services', 'server-core', 'shared'] },
          { from: ['client-shared'], allow: ['client-shared', 'shared'] },
          { from: ['client-services'], allow: ['client-services', 'client-shared', 'shared'] },
          { from: ['client-components'], allow: ['client-components', 'client-shared', 'shared'] },
          { from: ['client-pages'], allow: ['client-pages', 'client-components', 'client-services', 'client-shared', 'shared'] },
        ],
      },
    ],
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add typescript/layouts/fullstack-monorepo.js
git commit -m "layouts: add fullstack-monorepo (server + client + shared)"
```

---

## Task 6: Implement `generic-3-layer` layout

**Files:**
- Create: `typescript/layouts/generic-3-layer.js`

- [ ] **Step 1: Write the file**

```javascript
// ASP205/206 boundary layout — minimal viable FC/IS. Use when no other
// preset fits. Consumers can refine later by switching to a more
// specific layout or by appending an override block.
//
// Elements:
//   core/  — pure logic
//   infra/ — I/O boundary (DB, HTTP, fs, etc.)
//   app/   — imperative shell composing core + infra

import boundaries from 'eslint-plugin-boundaries';

export default {
  files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
  plugins: { boundaries },
  settings: {
    'boundaries/elements': [
      { type: 'core', pattern: '**/core/**' },
      { type: 'infra', pattern: '**/infra/**' },
      { type: 'app', pattern: '**/app/**' },
    ],
    'boundaries/include': ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    'boundaries/ignore': ['**/*.test.*', '**/*.spec.*', '**/__tests__/**'],
  },
  rules: {
    'boundaries/element-types': [
      'warn',
      {
        default: 'disallow',
        rules: [
          { from: ['core'], allow: ['core'] },
          { from: ['infra'], allow: ['infra', 'core'] },
          { from: ['app'], allow: ['app', 'infra', 'core'] },
        ],
      },
    ],
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add typescript/layouts/generic-3-layer.js
git commit -m "layouts: add generic-3-layer (minimal FC/IS fallback)"
```

---

## Task 7: Update package.json (version, exports, files, peerDependenciesMeta)

**Files:**
- Modify: `package.json`
- Modify: `package-lock.json`

- [ ] **Step 1: Bump version**

```json
"version": "0.1.0-rc.3",
```

- [ ] **Step 2: Add the `./layouts/*` subpath export**

Add to the `exports` map (alphabetical):

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

- [ ] **Step 3: Update `files` glob**

Add `typescript/layouts/**` and EXCLUDE `typescript/layouts/index.js` (internal barrel only):

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

(Reasoning for excluding `index.js`: it's only used by aspergillus's own CLI/tests; consumers import named layouts via the subpath export, never the barrel.)

- [ ] **Step 4: Declare `eslint-plugin-boundaries` as optional peer dep**

`peerDependenciesMeta` lets us mark a peer dep as optional — npm won't warn consumers who don't install it (e.g., those using `--layout=none`). Add:

```json
"peerDependenciesMeta": {
  "eslint-plugin-boundaries": { "optional": true }
}
```

Note: this is the FIRST `peerDependenciesMeta` entry in this package. The full `peerDependencies` decision (declare all 9 peers vs continue documenting in README) is deferred to its own dedicated PR per the L2 plan's roadmap. This entry is justified because aspergillus actively imports the package from its own source files (the layouts), unlike the other peers which are imported from the consumer's wrapped config.

- [ ] **Step 5: Regenerate lockfile**

```bash
npm install --no-audit --no-fund
```

- [ ] **Step 6: Verify pack contents**

```bash
npm pack --dry-run 2>&1 | grep 'layouts'
```

Expected:
- `typescript/layouts/node-service.js` — present
- `typescript/layouts/rn-app.js` — present
- `typescript/layouts/react-spa.js` — present
- `typescript/layouts/fullstack-monorepo.js` — present
- `typescript/layouts/generic-3-layer.js` — present
- `typescript/layouts/index.js` — **absent** (excluded by negation pattern)

- [ ] **Step 7: Commit**

```bash
git add package.json package-lock.json
git commit -m "package: bump 0.1.0-rc.3; export ./layouts/*; ship layouts/"
```

---

## Task 8: Add `--layout` flag to CLI args parsing

**Files:**
- Modify: `typescript/cli/src/index.ts`
- Modify: `typescript/cli/src/init.ts`
- Create: `typescript/cli/src/layouts.ts`

- [ ] **Step 1: Create `typescript/cli/src/layouts.ts`**

CLI-side mirror of `LAYOUT_NAMES` plus prompt logic. Lives TS-side because the CLI is TS.

```typescript
// CLI-side layout name list. Mirrors typescript/layouts/index.js.
// Tasks adding a layout must update both lists.

import { createInterface } from 'node:readline';

export const LAYOUT_NAMES = [
  'node-service',
  'rn-app',
  'react-spa',
  'fullstack-monorepo',
  'generic-3-layer',
] as const;

export type LayoutName = (typeof LAYOUT_NAMES)[number] | 'none';

export const ALL_LAYOUT_CHOICES: readonly LayoutName[] = [...LAYOUT_NAMES, 'none'];

export function isValidLayout(s: string): s is LayoutName {
  return (ALL_LAYOUT_CHOICES as readonly string[]).includes(s);
}

const LAYOUT_DESCRIPTIONS: Record<LayoutName, string> = {
  'node-service': 'Express/Fastify backend with DB (core/db/services/routes)',
  'rn-app': 'React Native app (core/services/hooks/components/screens)',
  'react-spa': 'React/Vite SPA (shared/services/components/pages)',
  'fullstack-monorepo': 'Top-level server/, client/, shared/ dirs (no src/ nesting)',
  'generic-3-layer': 'Minimal FC/IS fallback (core/infra/app)',
  none: 'Skip — declare elements yourself in eslint.config.js',
};

export function describeLayout(name: LayoutName): string {
  return LAYOUT_DESCRIPTIONS[name];
}

/**
 * Prompt the user to pick a layout. Default is 'none'. Returns 'none' if
 * stdin is not a TTY (so non-interactive callers like CI silently get the
 * documented default).
 */
export async function promptForLayout(): Promise<LayoutName> {
  if (!process.stdin.isTTY) return 'none';

  process.stdout.write('\nPick an ASP205/206 boundary layout (you can change later):\n');
  ALL_LAYOUT_CHOICES.forEach((name, i) => {
    process.stdout.write(`  ${i + 1}) ${name.padEnd(20)} ${describeLayout(name)}\n`);
  });
  process.stdout.write(`Choice [${ALL_LAYOUT_CHOICES.indexOf('none') + 1}]: `);

  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const answer: string = await new Promise((resolve) => rl.question('', (a) => resolve(a)));
  rl.close();

  const trimmed = answer.trim();
  if (trimmed === '') return 'none';
  const n = Number.parseInt(trimmed, 10);
  if (Number.isFinite(n) && n >= 1 && n <= ALL_LAYOUT_CHOICES.length) {
    return ALL_LAYOUT_CHOICES[n - 1] as LayoutName;
  }
  if (isValidLayout(trimmed)) return trimmed;
  process.stdout.write(`Invalid choice "${trimmed}". Defaulting to "none".\n`);
  return 'none';
}
```

- [ ] **Step 2: Update `typescript/cli/src/index.ts`**

Extend `Args` and `parseArgs` to accept `--layout=<name>`; pass to `init`. Update `USAGE`.

```typescript
#!/usr/bin/env node
// Aspergillus TypeScript CLI.
// Commands: init, check. See typescript/README.md for adoption workflow.

import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { check } from './check.js';
import { init } from './init.js';
import { ALL_LAYOUT_CHOICES, isValidLayout, type LayoutName } from './layouts.js';

const USAGE = `aspergillus-ts <command> [flags]

Commands:
  init [--target <dir>] [--layout <name>]
                             Copy reference configs into target dir.
                             --layout selects an ASP205/206 boundary
                             layout. If omitted, prompts (or 'none' on
                             non-TTY). Valid: ${ALL_LAYOUT_CHOICES.join(', ')}.
  check [--target <dir>]     Diff consumer config vs reference; exit 1 on drift

Flags:
  --target <dir>             Consumer repo root (default: cwd)
  --layout <name>            ASP205/206 layout (init only)
  -h, --help                 Show this message
`;

type Args = {
  command: string | undefined;
  target: string;
  layout: LayoutName | undefined;
  help: boolean;
};

export function parseArgs(argv: readonly string[]): Args {
  const rest = argv.slice(2);
  let target = process.cwd();
  let layout: LayoutName | undefined;
  let help = false;
  let command: string | undefined;
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a === '-h' || a === '--help') help = true;
    else if (a === '--target') target = rest[++i] ?? target;
    else if (a === '--layout') {
      const v = rest[++i];
      if (v !== undefined && isValidLayout(v)) layout = v;
      else if (v !== undefined) {
        process.stderr.write(
          `unknown layout: ${v} (valid: ${ALL_LAYOUT_CHOICES.join(', ')})\n`,
        );
      }
    } else if (!command) command = a;
  }
  return { command, target, layout, help };
}

export async function main(argv: readonly string[]): Promise<number> {
  const { command, target, layout, help } = parseArgs(argv);
  if (help || !command) {
    process.stdout.write(USAGE);
    return help ? 0 : 1;
  }
  switch (command) {
    case 'init':
      return init({ target, layout });
    case 'check':
      return check({ target });
    default:
      process.stderr.write(`unknown command: ${command}\n\n${USAGE}`);
      return 1;
  }
}

function isMainEntry(): boolean {
  try {
    const modulePath = realpathSync(fileURLToPath(import.meta.url));
    const argv1 = process.argv[1];
    return argv1 !== undefined && realpathSync(argv1) === modulePath;
  } catch {
    return false;
  }
}

if (isMainEntry()) {
  void main(process.argv).then((code) => process.exit(code));
}
```

- [ ] **Step 3: Compile and quick smoke**

```bash
npm run prepare
node typescript/cli/lib/index.js --help 2>&1 | head -20
```

Expected: usage text mentions `--layout`.

- [ ] **Step 4: Commit**

```bash
git add typescript/cli/src/layouts.ts typescript/cli/src/index.ts typescript/cli/lib/
git commit -m "cli: add --layout flag and layout name registry"
```

---

## Task 9: Wire layout into init wrapper template + DEV_DEPS filter

**Files:**
- Modify: `typescript/cli/src/init.ts`

- [ ] **Step 1: Update `InitOpts` and `init`/`runInit` signatures**

Add `layout?: LayoutName` to `InitOpts`. Import `promptForLayout` and `type LayoutName` from `./layouts.js`.

- [ ] **Step 2: Resolve the layout at init start**

Add at the top of `runInit`, before `mkdirSync`:

```typescript
const layout: LayoutName = opts.layout ?? (await promptForLayout());
```

(Pass `opts` through from `init` to `runInit`.)

- [ ] **Step 3: Extend `eslintWrapper` template**

Replace the existing `eslintWrapper` constant. The new wrapper conditionally includes the layout import + override-comment block:

```typescript
const layoutImport =
  layout === 'none'
    ? ''
    : `import layout from '${PACKAGE_SPECIFIERS.eslintBase.replace('eslint-config', `layouts/${layout}`)}';\n`;
const layoutSpread = layout === 'none' ? '' : '  layout,\n';
const layoutComments =
  layout === 'none'
    ? `// To enable ASP205/206 layered-import enforcement, declare
// settings['boundaries/elements'] in this config (or re-run
// 'aspergillus-ts init --layout=<name>' to import a preset).
`
    : `// To switch layouts: change the import above to one of:
//   '@afdudley/aspergillus/layouts/node-service'
//   '@afdudley/aspergillus/layouts/rn-app'
//   '@afdudley/aspergillus/layouts/react-spa'
//   '@afdudley/aspergillus/layouts/fullstack-monorepo'
//   '@afdudley/aspergillus/layouts/generic-3-layer'
//
// To customize WITHOUT switching layouts, append your overrides AFTER
// 'layout' above. Settings merge deeply; the last block wins for any
// 'boundaries/elements' or rule options you redefine. Example:
//   {
//     settings: { 'boundaries/elements': [
//       { type: 'core', pattern: 'src/lib/**' },
//     ] },
//   },
`;

const eslintWrapper = `// Aspergillus wrapper. Spreads the package reference; add repo-specific
// overrides after the spread.
import base from '${PACKAGE_SPECIFIERS.eslint}';
${layoutImport}
export default [
  ...base,
${layoutSpread}];

${layoutComments}`;
```

(Note: this assumes `PACKAGE_SPECIFIERS` exposes both `eslint` for the base config path and a way to derive layout paths. If the existing `PACKAGE_SPECIFIERS.eslint` is `@afdudley/aspergillus/eslint-config`, derive the layout specifier as `@afdudley/aspergillus/layouts/<name>`. Add a helper or new constant to `wrappers.ts` if cleaner.)

- [ ] **Step 4: Filter `eslint-plugin-boundaries` from DEV_DEPS for `--layout=none`**

Replace the existing `DEV_DEPS` constant + helper:

```typescript
const BASE_DEV_DEPS = [
  '@afdudley/aspergillus',
  '@eslint/js',
  'typescript-eslint',
  'eslint-plugin-functional',
  'eslint-plugin-import',
  'eslint-plugin-unused-imports',
  'eslint-config-prettier',
  'eslint',
  'prettier',
  'typescript',
] as const;

const LAYOUT_DEV_DEPS = ['eslint-plugin-boundaries'] as const;

function depsForLayout(layout: LayoutName): readonly string[] {
  return layout === 'none' ? BASE_DEV_DEPS : [...BASE_DEV_DEPS, ...LAYOUT_DEV_DEPS];
}
```

Update `devDepCommand` to take a `layout` argument and use `depsForLayout(layout).join(' ')`.

- [ ] **Step 5: Print the layout choice in init's output**

Add after `printBackupSummary`:

```typescript
if (layout !== 'none') {
  process.stdout.write(`\nASP205/206 layout: ${layout}\n`);
} else {
  process.stdout.write(`\nASP205/206 layout: none (skipped — see eslint.config.js comments)\n`);
}
```

- [ ] **Step 6: Compile and manual smoke**

```bash
npm run prepare
mkdir -p /tmp/init-smoke && cd /tmp/init-smoke
node /home/dev/git_puller/repos/aspergillus/typescript/cli/lib/index.js init --target . --layout=node-service
cat eslint.config.js
```

Expected: the wrapper includes `import layout from '@afdudley/aspergillus/layouts/node-service';` and `layout` is spread into the array. Override comments are present.

Re-run with `--layout=none`:
```bash
rm -rf /tmp/init-smoke && mkdir -p /tmp/init-smoke && cd /tmp/init-smoke
node /home/dev/git_puller/repos/aspergillus/typescript/cli/lib/index.js init --target . --layout=none
cat eslint.config.js
```

Expected: no layout import. Comment block explaining how to enable.

Cleanup: `rm -rf /tmp/init-smoke`.

- [ ] **Step 7: Commit**

```bash
git add typescript/cli/src/init.ts typescript/cli/lib/
git commit -m "cli(init): wire layout choice into wrapper + DEV_DEPS filter"
```

---

## Task 10: Update CLI tests

**Files:**
- Modify: `typescript/cli/src/init.test.ts`

- [ ] **Step 1: Read existing tests to find conventions**

Run: `cat typescript/cli/src/init.test.ts | head -40`. Note how the existing tests construct a temp dir and invoke `init`.

- [ ] **Step 2: Add a test per layout name**

For each name in `LAYOUT_NAMES.concat('none')`, add a test that:
1. Creates a fresh temp target dir.
2. Calls `init({ target, layout: name })`.
3. Reads the resulting `eslint.config.js`.
4. For `name !== 'none'`: asserts the file contains the substring `import layout from '@afdudley/aspergillus/layouts/<name>'` and `layout,` in the array.
5. For `name === 'none'`: asserts the file does NOT contain `layout,` and DOES contain the "To enable ASP205/206" comment.

Skeleton:

```typescript
import { describe, test, expect, beforeEach, afterEach } from 'bun:test';
import { mkdtempSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { init } from './init.js';
import { LAYOUT_NAMES } from './layouts.js';

describe('init --layout', () => {
  let target: string;
  beforeEach(() => {
    target = mkdtempSync(join(tmpdir(), 'asp-init-'));
  });
  afterEach(() => {
    rmSync(target, { recursive: true, force: true });
  });

  for (const name of LAYOUT_NAMES) {
    test(`writes layout import for --layout=${name}`, async () => {
      await init({ target, layout: name });
      const cfg = readFileSync(join(target, 'eslint.config.js'), 'utf8');
      expect(cfg).toContain(`@afdudley/aspergillus/layouts/${name}`);
      expect(cfg).toContain('layout,');
    });
  }

  test(`writes no layout import for --layout=none`, async () => {
    await init({ target, layout: 'none' });
    const cfg = readFileSync(join(target, 'eslint.config.js'), 'utf8');
    expect(cfg).not.toContain('@afdudley/aspergillus/layouts/');
    expect(cfg).toContain('To enable ASP205/206');
  });
});
```

- [ ] **Step 3: Run tests**

```bash
cd typescript/cli && PATH="$HOME/.bun/bin:$PATH" bun test
```

Expected: all prior tests still pass; 6 new tests (5 layouts + 1 none) added and pass.

- [ ] **Step 4: Commit**

```bash
git add typescript/cli/src/init.test.ts
git commit -m "cli(init): test --layout flag for each layout name + none"
```

---

## Task 11: Update typescript/README.md

**Files:**
- Modify: `typescript/README.md`

- [ ] **Step 1: Add a "Layouts (ASP205/206)" section**

Insert AFTER the "Adoption" section, BEFORE "Severity-flip workflow":

```markdown
## Layouts (ASP205/206)

ASP205 (no impure functions outside I/O boundary) and ASP206 (functional
core / imperative shell) are enforced via `eslint-plugin-boundaries`.
Aspergillus ships several preset layouts covering common project shapes.
You pick one at `aspergillus-ts init` time:

| Layout | Project shape | Key elements |
|---|---|---|
| `node-service` | Express/Fastify + DB | `core/`, `db/`, `services/`, `routes/` |
| `rn-app` | React Native | `core/`, `services/`, `hooks/`, `components/`, `screens/` |
| `react-spa` | React/Vite SPA | `shared/`, `services/`, `components/`, `pages/` |
| `fullstack-monorepo` | Server + client + shared | `server/{core,db,services,routes}/`, `client/{shared,services,components,pages}/`, `shared/` |
| `generic-3-layer` | Fallback / minimal | `core/`, `infra/`, `app/` |
| `none` | Skip — declare elements yourself | — |

`aspergillus-ts init --layout=<name>` writes the layout as an import in
your `eslint.config.js`:

```js
import base from '@afdudley/aspergillus/eslint-config';
import layout from '@afdudley/aspergillus/layouts/node-service';

export default [
  ...base,
  layout,
];
```

### Switching layouts

Change the layout import line. Re-running `aspergillus-ts init --layout=<name>`
also works (existing `eslint.config.js` is backed up to `.local.bak`).

### Overriding without switching

ESLint flat config evaluates blocks in order; later blocks override earlier.
Append a flat-config block after the layout import:

```js
import base from '@afdudley/aspergillus/eslint-config';
import layout from '@afdudley/aspergillus/layouts/node-service';

export default [
  ...base,
  layout,
  // Override: add a custom element type.
  {
    settings: {
      'boundaries/elements': [
        { type: 'rpc', pattern: '**/rpc/**' },
      ],
    },
    rules: {
      'boundaries/element-types': [
        'warn',
        {
          default: 'disallow',
          rules: [{ from: ['rpc'], allow: ['rpc', 'core'] }],
        },
      ],
    },
  },
];
```

### Peer dep

`eslint-plugin-boundaries` is required only when a layout is used. `init`
prints the install command including it; for `--layout=none`, the command
omits it. It's declared as an *optional* peer dep in aspergillus's
`package.json` so npm doesn't warn consumers using `--layout=none`.
```

- [ ] **Step 2: Update the install command in step 1 of "Adoption"**

The current command lists peer deps. After the layout work, the install command varies by layout. Replace the example install with a note:

```markdown
1. **Install aspergillus and peer devDependencies.**

   `aspergillus-ts init` (next step) prints the exact `npm install -D …`
   command for your detected package manager and chosen layout. You don't
   need to memorize the list.
```

(Remove or shorten the explicit `npm install -D` block to avoid duplication with what `init` prints.)

- [ ] **Step 3: Update the rule-mapping table**

Update the ASP205/206 rows from "*not yet in config*" to:

```markdown
| 205 | `eslint-plugin-boundaries` (via layouts; see Layouts section) |
| 206 | `eslint-plugin-boundaries` (via layouts) |
```

- [ ] **Step 4: Commit**

```bash
git add typescript/README.md
git commit -m "docs(typescript): document ASP205/206 layouts + override pattern"
```

---

## Task 12: End-to-end smoke test

**Files:** none modified.

This task does not commit. It packs the local repo, installs into a temporary consumer, runs `aspergillus-ts init --layout=node-service`, and verifies ESLint reports a layered-import violation on a fixture.

- [ ] **Step 1: Pack and set up smoke fixture**

```bash
cd /home/dev/git_puller/repos/aspergillus
SMOKE=/tmp/aspergillus-asp205-smoke
rm -rf "$SMOKE" && mkdir -p "$SMOKE"
npm pack --pack-destination "$SMOKE"
cd "$SMOKE"
mv afdudley-aspergillus-*.tgz aspergillus.tgz
cat > package.json <<'EOF'
{ "name": "smoke205", "version": "1.0.0", "type": "module", "private": true }
EOF
npm install --no-audit --no-fund \
  ./aspergillus.tgz \
  @eslint/js typescript-eslint eslint-plugin-import \
  eslint-plugin-unused-imports eslint-plugin-functional \
  eslint-plugin-boundaries \
  eslint-config-prettier eslint prettier typescript
```

- [ ] **Step 2: Run init with a layout**

```bash
node node_modules/@afdudley/aspergillus/typescript/cli/lib/index.js \
  init --target . --layout=node-service
```

Expected: eslint.config.js created with the layout import.

- [ ] **Step 3: Create a violating fixture**

```bash
mkdir -p src/core src/db src/routes
cat > src/core/util.ts <<'EOF'
export const add = (a: number, b: number) => a + b;
EOF
cat > src/db/users.ts <<'EOF'
export const findUser = (id: number) => ({ id, name: 'fake' });
EOF
cat > src/routes/users.ts <<'EOF'
// VIOLATION: routes element imports from db (must go through services).
import { findUser } from '../db/users.js';
import { add } from '../core/util.js';
export const handler = (id: number) => ({ user: findUser(id), x: add(1, 2) });
EOF
cat > tsconfig.json <<'EOF'
{
  "extends": "@afdudley/aspergillus/tsconfig",
  "include": ["src/**/*"],
  "compilerOptions": { "noEmit": true, "allowImportingTsExtensions": true }
}
EOF
```

- [ ] **Step 4: Run ESLint and capture output**

```bash
npx eslint src/ 2>&1 | tee /tmp/asp205-smoke.log | tail -20
```

Expected output includes a `boundaries/element-types` warning on `src/routes/users.ts` for importing `db`.

- [ ] **Step 5: Cleanup**

```bash
rm -rf "$SMOKE" /tmp/asp205-smoke.log
```

If Step 4 didn't surface the expected warning: report BLOCKED with the captured log.

---

## Verification summary (after all tasks)

- [ ] `npm test` clean (rules tests + new init tests)
- [ ] `npm run prepare` clean (CLI builds)
- [ ] `npm pack --dry-run` lists all 5 layout files; excludes `index.js`
- [ ] `aspergillus-ts init --help` shows the `--layout` flag and valid names
- [ ] `aspergillus-ts init --target /tmp/x --layout=node-service` produces a wrapper with the import + override comments
- [ ] E2E smoke test (Task 12) flags the layered-import violation
- [ ] `docs/design.md` ASP205/206 row matches `eslint-plugin-boundaries + layout templates from aspergillus-ts init` (already landed in prior commit)
- [ ] No push (per standing instruction); branch handed to user for review and push

## Out-of-scope (track separately)

- Custom layout for project shapes not covered by the five presets — consumers add overrides in their own config.
- An `aspergillus-ts add-layout <name>` subcommand — `init --layout=<name>` already supports re-init with backup.
- Auto-detection of project shape (e.g., infer `rn-app` from `react-native` in `package.json`) — explicit selection is more honest.
- Migrating TrashScan-Explorer / mtm to use a layout — separate consumer-side PRs.
- Custom `aspergillus/asp205-purity-boundary` rule using a Python-style I/O blocklist — explicitly rejected; layered imports are the right TS approach.
