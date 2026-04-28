# TypeScript Level 2 rules implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Level 2 (ASP201–204) lint rules to aspergillus's TypeScript reference config, including the project's first custom ESLint rule (`asp202-min-assertions`), and ship as `@afdudley/aspergillus@0.1.0-rc.2`.

**Architecture:** Three of the four rules ride on existing or near-existing ESLint mechanisms (`max-lines-per-function`, `no-restricted-syntax`, `eslint-plugin-functional/no-loop-statements`), with no new code beyond config blocks. ASP202 (assertion density) has no off-the-shelf TS implementation, so aspergillus ships a small custom rule via a new `./eslint-rules` package export. All four rules land at `warn` per the severity-flip workflow. Where this plan diverges from `docs/design.md` and `docs/superpowers/specs/2026-04-24-aspergillus-multilang-design.md` (ASP202 promoted from "Manual" to a custom rule; ASP203 narrowed from `functional/no-let` to module-level only; ASP204 acknowledged as a strict over-approximation pending a custom unbounded-loop rule), `docs/design.md` is updated to reflect the new mapping.

**Tech Stack:** ESLint 9 flat config, `eslint-plugin-functional` (new peer dep), bun:test (for the custom rule's RuleTester suite), `eslint` (new devDep — RuleTester host).

---

## Why this plan diverges from the original spec

The original `docs/superpowers/specs/2026-04-24-aspergillus-multilang-design.md` mapped:
- ASP202 → "Manual (code-review responsibility)"
- ASP203 → `functional/no-let`, `functional/immutable-data`
- ASP204 → `functional/no-loop-statements`

This plan revises:

| Rule | Spec mapping | Plan mapping | Why |
|---|---|---|---|
| ASP202 | Manual | Custom `aspergillus/asp202-min-assertions` rule | Establishes custom-rule infrastructure for ASP302/etc. later; "manual code-review" loses signal in practice. |
| ASP203 | `functional/no-let`, `functional/immutable-data` | `no-restricted-syntax` patterns banning module-level `let`/`var`/mutable named exports | NASA's rule is "no global mutable state" — not "no `let` anywhere". `functional/no-let` bans local `let` in loops/accumulators, which has a high false-positive surface and pushes consumers off the cliff. The narrower selector matches NASA intent. |
| ASP204 | `functional/no-loop-statements` | `functional/no-loop-statements` (kept) — but documented as a strict over-approximation | NASA's actual rule is "loops must have a statically-determinable upper bound" (no `while(true)`). `no-loop-statements` bans all loops. Acceptable at `warn` because (a) it surfaces something useful and (b) it's a placeholder until a custom `aspergillus/asp204-bounded-loops` rule exists. `docs/design.md` gets a "revisit" note. |

The plan also adds `eslint-plugin-functional` as a documented peer dep (needed for ASP204) and `eslint` as a devDep (needed to host RuleTester for the ASP202 tests).

---

## File Structure

**New files:**
- `typescript/rules/asp202-min-assertions.js` — custom ESLint rule, ~110 LOC
- `typescript/rules/index.js` — flat-config plugin export wrapping the rules
- `typescript/rules/asp202-min-assertions.test.js` — RuleTester suite via bun:test
- `typescript/rules/package.json` — minimal package manifest so bun knows where the test lives (no name field needed; just `type: module` + scripts)
- `typescript/rules/tsconfig.json` — bun:test type plumbing only if needed; skip if rule files are plain JS (no TS)

**Modified files:**
- `package.json` — bump version, add `./eslint-rules` export, add `typescript/rules/**` (excluding `*.test.js`) to `files`, add `eslint` devDep, add `test` script that runs both CLI and rules tests
- `typescript/configs/eslint.config.js` — append L2 rule block referencing the new plugin and `eslint-plugin-functional`
- `typescript/README.md` — update rule-mapping table; document new peer dep `eslint-plugin-functional`
- `docs/design.md` — update ASP201/202/203/204 TS columns; add "to revisit" note for ASP204
- `package-lock.json` — regenerated when `eslint` is added as devDep

**Out of scope (deferred to follow-up PRs):**
- ASP301 (no-throw + neverthrow) — Level 3, separate PR
- ASP302 (no-Optional return) — Level 3, separate PR (likely needs custom rule)
- ASP205/206 (FC/IS boundary) — needs `eslint-plugin-boundaries` per-consumer architectural config; design conversation needed first
- Custom `asp204-bounded-loops` rule that replaces `no-loop-statements` — separate design + PR
- Severity-flip PRs in TrashScan-Explorer to address the warnings these rules will surface

---

## Task 1: Scaffold the rules package directory

**Files:**
- Create: `typescript/rules/index.js`
- Create: `typescript/rules/package.json`

This task creates the empty plugin skeleton so subsequent tasks can plug rules in. The plugin is wired into `eslint.config.js` and tested in later tasks.

- [ ] **Step 1: Create `typescript/rules/index.js` with an empty rules map**

```javascript
// Aspergillus ESLint plugin — flat-config compatible.
//
// Hosts custom rules that don't have a sufficient off-the-shelf
// equivalent. Add new rules to the `rules` map here and re-export the
// rule object from a sibling file.

export default {
  meta: {
    name: '@afdudley/aspergillus',
    // Bumped manually alongside the package version. Used by ESLint flat
    // config in error reporting and cache keys.
    version: '0.1.0-rc.2',
  },
  rules: {
    // Populated in Task 3.
  },
};
```

- [ ] **Step 2: Create `typescript/rules/package.json`**

This stays minimal — it exists so bun:test resolves the directory as a package and `type: module` enables ESM imports inside tests. It is not published (the publishable artifact is the root package).

```json
{
  "name": "aspergillus-rules-internal",
  "private": true,
  "type": "module"
}
```

- [ ] **Step 3: Commit the scaffolding**

```bash
git add typescript/rules/index.js typescript/rules/package.json
git commit -m "rules: scaffold @afdudley/aspergillus ESLint plugin (empty)"
```

---

## Task 2: Add `eslint` devDep and a test script (TDD setup)

**Files:**
- Modify: `package.json` — add `eslint` devDep, add `test` script
- Modify: `package-lock.json` — regenerated

ESLint's `RuleTester` is what we use to test the custom rule. Adding it as a devDep here (not as a peer dep) lets aspergillus's own test suite run.

- [ ] **Step 1: Read current `package.json` to confirm devDeps and scripts shape**

Run: `cat package.json | jq '.devDependencies, .scripts'`

Expected output (approximate):
```
{
  "@types/node": ">=18",
  "typescript": ">=5.4"
}
{
  "prepare": "tsc -p typescript/cli/tsconfig.json && node -e \"...\""
}
```

- [ ] **Step 2: Add `eslint` to devDependencies**

Edit `package.json`. Set `devDependencies` to (preserving existing entries):

```json
"devDependencies": {
  "@types/node": ">=18",
  "eslint": "^9.0.0",
  "typescript": ">=5.4"
}
```

- [ ] **Step 3: Add a `test` script that runs the rules suite**

Edit `package.json`. Add to `scripts`:

```json
"scripts": {
  "prepare": "tsc -p typescript/cli/tsconfig.json && node -e \"require('fs').chmodSync('typescript/cli/lib/index.js', 0o755)\"",
  "test": "bun test typescript/rules"
}
```

- [ ] **Step 4: Run `npm install` to regenerate `package-lock.json`**

Run: `npm install --no-audit --no-fund`

Expected: lockfile updated, `node_modules/eslint` exists.

- [ ] **Step 5: Verify ESLint is resolvable**

Run: `node -e "import('eslint').then(m => console.log(typeof m.RuleTester))"`

Expected: `function`

- [ ] **Step 6: Commit**

```bash
git add package.json package-lock.json
git commit -m "deps: add eslint devDep + test script for rules suite"
```

---

## Task 3: Write the failing ASP202 RuleTester suite

**Files:**
- Create: `typescript/rules/asp202-min-assertions.test.js`

This task writes the test before the rule, per TDD. The test imports a not-yet-existing rule module — the suite fails on import. That's the expected failure mode.

- [ ] **Step 1: Write `typescript/rules/asp202-min-assertions.test.js`**

```javascript
// RuleTester suite for asp202-min-assertions. Run via `bun test`.

import { RuleTester } from 'eslint';
import { describe, it } from 'bun:test';

import rule from './asp202-min-assertions.js';

// Wire bun:test into RuleTester. ESLint v9 RuleTester calls
// RuleTester.describe / RuleTester.it directly; assigning bun:test's
// versions makes the suite report through the bun runner.
RuleTester.describe = describe;
RuleTester.it = it;
RuleTester.itOnly = it;

const tester = new RuleTester({
  languageOptions: { ecmaVersion: 2022, sourceType: 'module' },
});

const longBody = `
  // line 1
  // line 2
  // line 3
  // line 4
  // line 5
  // line 6
  // line 7
  // line 8
  // line 9
  return x;
`;

tester.run('asp202-min-assertions', rule, {
  valid: [
    // Trivial function: under default minFunctionLength (10 lines) — exempt.
    { code: 'function add(a, b) { return a + b; }' },

    // Two bare assert() calls.
    {
      code: `function f(x) {
        assert(x > 0);
        assert(x < 100);
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        return x + a + b + c + d + e;
      }`,
    },

    // Namespace methods on a configured assertionName count: assert.ok, assert.equal.
    {
      code: `function f(x) {
        assert.ok(x);
        assert.equal(x, 1);
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        return x + a + b + c + d + e;
      }`,
    },

    // console.assert counts (from default memberPatterns).
    {
      code: `function f(x) {
        console.assert(x !== null);
        console.assert(x !== undefined);
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        return x + a + b + c + d + e;
      }`,
    },

    // Custom assertionNames option recognizes 'check'.
    {
      code: `function f(x) {
        check(x > 0);
        check(x < 100);
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        return x + a + b + c + d + e;
      }`,
      options: [{ assertionNames: ['check'] }],
    },

    // Arrow functions with non-block body are skipped (no body to count).
    { code: 'const f = (x) => x + 1;' },
  ],

  invalid: [
    // Long function with zero assertions.
    {
      code: `function f(x) {${longBody}}`,
      errors: [{ messageId: 'tooFew', data: { count: '0', min: '2' } }],
    },

    // One assertion, default min is 2.
    {
      code: `function f(x) {
        assert(x > 0);
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        const g = 6;
        return x + a + b + c + d + e + g;
      }`,
      errors: [{ messageId: 'tooFew', data: { count: '1', min: '2' } }],
    },

    // Nested function bodies are NOT counted toward the outer function's
    // assertion total — each function is checked independently.
    {
      code: `function outer(x) {
        function inner(y) {
          assert(y > 0);
          assert(y < 100);
          return y;
        }
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        return inner(x) + a + b + c + d;
      }`,
      errors: [
        // outer has 0 assertions, fails.
        // inner has 2 but is only 5 lines — under minFunctionLength, exempt.
        { messageId: 'tooFew', data: { count: '0', min: '2' } },
      ],
    },

    // Custom min option.
    {
      code: `function f(x) {
        assert(x > 0);
        assert(x < 100);
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        return x + a + b + c + d + e;
      }`,
      options: [{ min: 3 }],
      errors: [{ messageId: 'tooFew', data: { count: '2', min: '3' } }],
    },
  ],
});
```

- [ ] **Step 2: Run the test — expect import failure**

Run: `bun test typescript/rules/asp202-min-assertions.test.js`

Expected: FAIL — error like `Cannot find module './asp202-min-assertions.js'` or `Module not found`. This confirms the test will exercise the rule once we write it.

- [ ] **Step 3: Commit the failing test**

```bash
git add typescript/rules/asp202-min-assertions.test.js
git commit -m "rules: add failing RuleTester suite for asp202-min-assertions"
```

---

## Task 4: Implement the ASP202 rule

**Files:**
- Create: `typescript/rules/asp202-min-assertions.js`
- Modify: `typescript/rules/index.js` — wire the rule into the plugin

- [ ] **Step 1: Write `typescript/rules/asp202-min-assertions.js`**

```javascript
// ASP202 — assertion density.
//
// NASA Power of 10 #5: minimum two assertions per function. Reports
// non-trivial functions whose bodies contain fewer than `min` assertion-
// like calls. Defaults skip short functions (< minFunctionLength lines)
// since the rule's intent is non-trivial logic, not 3-line helpers.
//
// Recognized as assertions by default:
//   assert(...)             — node:assert default export, or top-level
//                             helper conventionally named `assert`
//   assert.ok / .equal …    — namespace methods on `assert`
//   invariant(...)          — common helper convention
//   console.assert(...)     — JS host
//
// Consumers extend the lists via `assertionNames` (bare callee name)
// or `memberPatterns` (full `obj.method` form).

const DEFAULT_MIN = 2;
const DEFAULT_MIN_FUNCTION_LENGTH = 10;
const DEFAULT_ASSERTION_NAMES = ['assert', 'invariant'];
const DEFAULT_MEMBER_PATTERNS = ['console.assert'];

function isAssertionCall(node, assertionNames, memberPatterns) {
  if (node.type !== 'CallExpression') return false;
  const callee = node.callee;

  if (callee.type === 'Identifier') {
    return assertionNames.includes(callee.name);
  }

  if (
    callee.type === 'MemberExpression' &&
    !callee.computed &&
    callee.object.type === 'Identifier' &&
    callee.property.type === 'Identifier'
  ) {
    const full = `${callee.object.name}.${callee.property.name}`;
    if (memberPatterns.includes(full)) return true;
    // `assert.ok(...)`, `assert.equal(...)` etc. when `assert` is in
    // assertionNames — namespace methods on a configured name count.
    if (assertionNames.includes(callee.object.name)) return true;
  }

  return false;
}

function countAssertionsIn(rootBody, assertionNames, memberPatterns) {
  let count = 0;
  function walk(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) {
      for (const item of node) walk(item);
      return;
    }
    if (typeof node.type !== 'string') return;
    // Don't recurse into nested function bodies — each function is
    // visited separately by the rule's selectors.
    if (
      node !== rootBody &&
      (node.type === 'FunctionDeclaration' ||
        node.type === 'FunctionExpression' ||
        node.type === 'ArrowFunctionExpression')
    ) {
      return;
    }
    if (isAssertionCall(node, assertionNames, memberPatterns)) {
      count++;
    }
    for (const key of Object.keys(node)) {
      if (key === 'parent' || key === 'loc' || key === 'range') continue;
      walk(node[key]);
    }
  }
  walk(rootBody);
  return count;
}

export default {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        'Require a minimum number of assertion-like calls per non-trivial function (ASP202).',
    },
    schema: [
      {
        type: 'object',
        properties: {
          min: { type: 'number', minimum: 0 },
          minFunctionLength: { type: 'number', minimum: 0 },
          assertionNames: { type: 'array', items: { type: 'string' } },
          memberPatterns: { type: 'array', items: { type: 'string' } },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      tooFew:
        "ASP202: function has {{count}} assertion(s); expected at least {{min}}. Add `assert(...)`, `invariant(...)`, or extend the rule's `assertionNames`/`memberPatterns` if you use a different convention.",
    },
  },
  create(context) {
    const opts = context.options[0] ?? {};
    const min = opts.min ?? DEFAULT_MIN;
    const minLength = opts.minFunctionLength ?? DEFAULT_MIN_FUNCTION_LENGTH;
    const assertionNames = opts.assertionNames ?? DEFAULT_ASSERTION_NAMES;
    const memberPatterns = opts.memberPatterns ?? DEFAULT_MEMBER_PATTERNS;

    function check(node) {
      if (!node.body || node.body.type !== 'BlockStatement') return;
      const length = node.loc.end.line - node.loc.start.line + 1;
      if (length < minLength) return;

      const count = countAssertionsIn(node.body, assertionNames, memberPatterns);
      if (count < min) {
        context.report({
          node,
          messageId: 'tooFew',
          data: { count: String(count), min: String(min) },
        });
      }
    }

    return {
      FunctionDeclaration: check,
      FunctionExpression: check,
      ArrowFunctionExpression: check,
    };
  },
};
```

- [ ] **Step 2: Wire the rule into `typescript/rules/index.js`**

Edit the file. Replace the empty `rules: {}` block:

```javascript
// Aspergillus ESLint plugin — flat-config compatible.
//
// Hosts custom rules that don't have a sufficient off-the-shelf
// equivalent. Add new rules to the `rules` map here and re-export the
// rule object from a sibling file.

import asp202MinAssertions from './asp202-min-assertions.js';

export default {
  meta: {
    name: '@afdudley/aspergillus',
    // Bumped manually alongside the package version. Used by ESLint flat
    // config in error reporting and cache keys.
    version: '0.1.0-rc.2',
  },
  rules: {
    'asp202-min-assertions': asp202MinAssertions,
  },
};
```

- [ ] **Step 3: Run the RuleTester suite — expect PASS**

Run: `bun test typescript/rules/asp202-min-assertions.test.js`

Expected: all valid + invalid cases pass. If any case fails, fix the rule (don't fix the test) until green.

- [ ] **Step 4: Commit**

```bash
git add typescript/rules/asp202-min-assertions.js typescript/rules/index.js
git commit -m "rules: implement asp202-min-assertions custom rule"
```

---

## Task 5: Add ASP201 (`max-lines-per-function`) to the reference config

**Files:**
- Modify: `typescript/configs/eslint.config.js` — add an L2 rule block

This rule is part of ESLint core; no new plugin or peer dep.

- [ ] **Step 1: Read the current eslint.config.js to find the insertion point**

Run: `cat typescript/configs/eslint.config.js`

Note the structure: a single config block at lines ~45–82 holds the rule set. The L2 block goes immediately after that block (so prettier-config still comes last).

- [ ] **Step 2: Append the L2 rule block before the `prettierConfig` entry**

Edit `typescript/configs/eslint.config.js`. Find the line `// Keep Prettier last so it disables conflicting formatting rules.` and insert this block above it:

```javascript
  // Level 2 — lands at warn pending severity-flip. Each rule flips to
  // `error` in a dedicated PR once the consumer has zero violations.
  {
    files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    rules: {
      // ASP201 — function too long. NASA Power of 10 #4: ≤60 lines.
      'max-lines-per-function': [
        'warn',
        { max: 60, skipBlankLines: true, skipComments: true, IIFEs: true },
      ],
    },
  },
```

- [ ] **Step 3: Verify the config still parses**

Run: `node --input-type=module -e "import('./typescript/configs/eslint.config.js').then(m => console.log('blocks:', m.default.length))"`

Expected: prints `blocks: <N>` where N is one greater than before. No syntax errors.

- [ ] **Step 4: Commit**

```bash
git add typescript/configs/eslint.config.js
git commit -m "config: add ASP201 (max-lines-per-function) at warn"
```

---

## Task 6: Add ASP203 (no module-level mutable state)

**Files:**
- Modify: `typescript/configs/eslint.config.js` — extend the L2 block with `no-restricted-syntax` patterns

Narrowed scope vs the original spec: targets module-level `let`/`var` and mutable named exports. Local `let` inside functions remains allowed (matches NASA "no global mutable state" intent).

- [ ] **Step 1: Add `no-restricted-syntax` to the L2 rule block**

Edit `typescript/configs/eslint.config.js`. Inside the Level 2 block created in Task 5, add to `rules`:

```javascript
      // ASP203 — no global mutable state. NASA Power of 10 #6 (narrowed):
      // bans module-level mutable bindings and mutable exports. Local
      // `let` inside functions is intentionally allowed — the rule's
      // intent is global, not lexical, immutability.
      'no-restricted-syntax': [
        'warn',
        {
          selector: 'Program > VariableDeclaration[kind="let"]',
          message:
            'ASP203: module-level `let` is mutable global state. Use `const`, or move state inside a function.',
        },
        {
          selector: 'Program > VariableDeclaration[kind="var"]',
          message:
            'ASP203: module-level `var` is mutable global state. Use `const`, or move state inside a function.',
        },
        {
          selector: 'ExportNamedDeclaration > VariableDeclaration[kind="let"]',
          message:
            'ASP203: `export let` exposes mutable state across modules. Export a `const` or a getter.',
        },
        {
          selector: 'ExportNamedDeclaration > VariableDeclaration[kind="var"]',
          message:
            'ASP203: `export var` exposes mutable state across modules. Export a `const` or a getter.',
        },
      ],
```

- [ ] **Step 2: Sanity-check on a fixture**

Create a temporary fixture at `/tmp/asp203-fixture.js`:

```javascript
let bad = 1;             // should warn — module-level let
var alsoBad = 2;         // should warn — module-level var
export let mutable = 3;  // should warn — export let
const ok = 4;            // should NOT warn

function f() {
  let local = 1;         // should NOT warn — function-local let
  return local + ok;
}
```

Run:
```bash
npx eslint --config typescript/configs/eslint.config.js /tmp/asp203-fixture.js 2>&1 | head -30
```

Expected: 3 warnings (lines 1, 2, 3); no warning on line 4 (`const`) or line 7 (function-local `let`).

- [ ] **Step 3: Clean up the fixture**

Run: `rm /tmp/asp203-fixture.js`

- [ ] **Step 4: Commit**

```bash
git add typescript/configs/eslint.config.js
git commit -m "config: add ASP203 (no module-level mutable state) at warn"
```

---

## Task 7: Add ASP204 (`functional/no-loop-statements`)

**Files:**
- Modify: `typescript/configs/eslint.config.js` — register `eslint-plugin-functional` plugin and enable the rule

This rule comes from `eslint-plugin-functional`, which becomes a new documented peer dep. The README is updated in a later task.

- [ ] **Step 1: Confirm the package is installable in the consumer environment**

This step exists so we know the plugin name and entry point. Run:
```bash
npm view eslint-plugin-functional name version
```

Expected: package exists, name is `eslint-plugin-functional`, recent version (≥6.x at time of writing).

- [ ] **Step 2: Add the plugin import to the top of `typescript/configs/eslint.config.js`**

Edit the imports block:

```javascript
import functional from 'eslint-plugin-functional';
```

Place it alphabetically with the other plugin imports (between `eslint-plugin-import` and `eslint-plugin-unused-imports`).

- [ ] **Step 3: Register the plugin in the L2 block**

Edit the L2 block created in Task 5. Add a `plugins:` field above `rules:`:

```javascript
  {
    files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    plugins: {
      functional,
    },
    rules: {
      // … ASP201, ASP203 from prior tasks …

      // ASP204 — no unbounded loops. NASA Power of 10 #2 calls for a
      // statically-determinable iteration bound. There is no off-the-
      // shelf rule for that exact predicate, so we use the strict
      // approximation `no-loop-statements` (bans all loops). Lands at
      // warn so consumers can audit loops case-by-case; replace with a
      // more precise rule when one exists. See docs/design.md ASP204.
      'functional/no-loop-statements': 'warn',
    },
  },
```

- [ ] **Step 4: Verify config still parses**

Run: `node --input-type=module -e "import('./typescript/configs/eslint.config.js').then(m => console.log('blocks:', m.default.length))"`

Expected: prints `blocks: <N>` (no errors). Note: this will FAIL with a "Cannot find module" error because `eslint-plugin-functional` is not installed in aspergillus's own node_modules. That's acceptable — aspergillus's config is consumer-installed; consumers will have the plugin. To make the smoke check pass:

Run: `npm install --no-save --no-audit --no-fund eslint-plugin-functional`

Then re-run the parse check above. Expected: `blocks: <N>` printed cleanly.

- [ ] **Step 5: Commit**

```bash
git add typescript/configs/eslint.config.js
git commit -m "config: add ASP204 (functional/no-loop-statements) at warn"
```

Do **not** commit the `node_modules` change from `--no-save`; the install was transient.

---

## Task 8: Update aspergillus's own ESLint plugin registration in the L2 block

**Files:**
- Modify: `typescript/configs/eslint.config.js` — register the aspergillus plugin and turn on `aspergillus/asp202-min-assertions`

- [ ] **Step 1: Add the import**

Edit `typescript/configs/eslint.config.js`. Add to the imports block:

```javascript
import aspergillus from '../rules/index.js';
```

Place it after `import prettierConfig from 'eslint-config-prettier';` (last existing import).

- [ ] **Step 2: Register the plugin and enable the rule in the L2 block**

Edit the L2 block to include `aspergillus` in `plugins:` and add the rule:

```javascript
  {
    files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    plugins: {
      aspergillus,
      functional,
    },
    rules: {
      // ASP201 (Task 5) …
      // ASP203 (Task 6) …
      // ASP204 (Task 7) …

      // ASP202 — assertion density. Custom rule shipped by aspergillus;
      // see typescript/rules/asp202-min-assertions.js.
      'aspergillus/asp202-min-assertions': 'warn',
    },
  },
```

- [ ] **Step 3: Verify the plugin resolves and the config parses**

Run: `node --input-type=module -e "import('./typescript/configs/eslint.config.js').then(m => console.log('rules:', Object.keys(m.default.find(b => b.rules?.['aspergillus/asp202-min-assertions']).rules)))"`

Expected: prints an array containing `aspergillus/asp202-min-assertions` along with the other L2 rule names.

- [ ] **Step 4: Commit**

```bash
git add typescript/configs/eslint.config.js
git commit -m "config: register aspergillus plugin, enable ASP202 at warn"
```

---

## Task 9: Update package.json (version, exports, files, regenerate lockfile)

**Files:**
- Modify: `package.json` — version, exports, files
- Modify: `package-lock.json` — regenerated

- [ ] **Step 1: Bump the version**

Edit `package.json`:

```json
"version": "0.1.0-rc.2",
```

- [ ] **Step 2: Add the `./eslint-rules` export**

Add to the `exports` map:

```json
"exports": {
  "./eslint-config": "./typescript/configs/eslint.config.js",
  "./eslint-rules": "./typescript/rules/index.js",
  "./tsconfig": "./typescript/configs/tsconfig.base.json",
  "./prettier-config": "./typescript/configs/prettier.config.cjs",
  "./pre-commit": "./typescript/configs/pre-commit-config.yaml"
},
```

- [ ] **Step 3: Add the rules directory to `files`, excluding tests**

Edit the `files` array:

```json
"files": [
  "typescript/configs/**",
  "typescript/cli/lib/**",
  "typescript/cli/package.json",
  "typescript/rules/**",
  "!typescript/rules/**/*.test.js",
  "!typescript/rules/package.json",
  "README.md",
  "LICENSE"
],
```

The two negation patterns drop the test files and the directory's internal `package.json` (which is bun-test-only and shouldn't ship).

- [ ] **Step 4: Regenerate the lockfile**

Run: `npm install --no-audit --no-fund`

- [ ] **Step 5: Verify the package still builds**

Run: `npm run prepare`

Expected: tsc emits `typescript/cli/lib/index.js` cleanly; chmod sets exec bit. No errors.

- [ ] **Step 6: Verify the file list is what we'll publish**

Run: `npm pack --dry-run 2>&1 | grep -E '^npm notice [0-9]'`

Expected output includes lines for:
- `package.json`
- `typescript/configs/eslint.config.js`
- `typescript/configs/tsconfig.base.json`
- `typescript/configs/prettier.config.cjs`
- `typescript/configs/pre-commit-config.yaml`
- `typescript/cli/lib/index.js`
- `typescript/cli/package.json`
- `typescript/rules/index.js`
- `typescript/rules/asp202-min-assertions.js`
- `README.md`
- `LICENSE`

And does NOT include:
- `typescript/rules/asp202-min-assertions.test.js`
- `typescript/rules/package.json`

- [ ] **Step 7: Commit**

```bash
git add package.json package-lock.json
git commit -m "package: bump to 0.1.0-rc.2; export ./eslint-rules; ship rules/"
```

---

## Task 10: Run the full test + build check

**Files:** none (verification step)

- [ ] **Step 1: Run the rules test suite**

Run: `npm test`

Expected: all RuleTester cases from Task 3 pass (now that the rule is implemented).

- [ ] **Step 2: Run the CLI tests too (regression check)**

Run: `cd typescript/cli && bun test && cd -`

Expected: existing CLI tests still pass.

- [ ] **Step 3: Run the build**

Run: `npm run prepare`

Expected: clean tsc emit.

If anything fails: fix the underlying issue, re-run, and amend the relevant commit (it's local-only).

---

## Task 11: Update `typescript/README.md` rule-mapping table

**Files:**
- Modify: `typescript/README.md` — update rule mapping; document new peer dep

- [ ] **Step 1: Update the install command to include `eslint-plugin-functional`**

Edit `typescript/README.md`. Find the install command block (around line 22–27) and add the new peer dep:

```bash
npm install -D github:AFDudley/aspergillus#main @eslint/js typescript-eslint \
  eslint-plugin-import eslint-plugin-unused-imports eslint-plugin-functional \
  eslint-config-prettier eslint prettier typescript
```

(Adjust to keep the line wrapping readable.)

- [ ] **Step 2: Update the rule-mapping table**

Find the "Rule mapping (summary)" section. Replace the existing rows with:

```markdown
| ASP | Tooling                                                            |
|-----|--------------------------------------------------------------------|
| 201 | `max-lines-per-function` — ESLint core                             |
| 202 | `aspergillus/asp202-min-assertions` — custom rule, this package    |
| 203 | `no-restricted-syntax` — bans module-level `let`/`var`/`export let`/`export var` |
| 204 | `functional/no-loop-statements` — strict over-approximation; see design.md |
| 205 | `eslint-plugin-boundaries` (architecture enforcement) — *not yet in config*  |
| 206 | `eslint-plugin-boundaries` + project layering — *not yet in config*          |
| 301 | `functional/no-throw-statements`, `@okee-tech/neverthrow/must-consume-result` — *not yet in config* |
| 302 | `strictNullChecks` in tsconfig + neverthrow-typed returns — *not yet in config* |
```

- [ ] **Step 3: Add a "Severity-flip backlog" subsection under "Severity-flip workflow"**

Insert after the existing severity-flip-workflow paragraph:

```markdown
### Currently at `warn`

The following rules currently land at `warn` in this package's reference config. Consumers should adopt them, fix violations on their own schedule, and contribute severity-flip PRs back to aspergillus once the rule reaches zero violations across consumers.

- `max-lines-per-function` (ASP201)
- `aspergillus/asp202-min-assertions` (ASP202)
- `no-restricted-syntax` (ASP203)
- `functional/no-loop-statements` (ASP204)
- `@typescript-eslint/no-explicit-any` (Level 1 promotion candidate)
- `no-console` (Level 1 promotion candidate)
```

- [ ] **Step 4: Commit**

```bash
git add typescript/README.md
git commit -m "docs(typescript): document L2 rules + severity-flip backlog"
```

---

## Task 12: Update `docs/design.md` ASP rule rows

**Files:**
- Modify: `docs/design.md` — update Level 2 rule table

- [ ] **Step 1: Update the Level 2 table**

Find the Level 2 table in `docs/design.md` (the rows for ASP201–ASP206). Replace the TypeScript column entries:

```markdown
### Level 2 — Blocking

| Rule   | Description                              | Python (Fixit)                   | TypeScript                                                | Rust |
|--------|------------------------------------------|----------------------------------|-----------------------------------------------------------|------|
| ASP201 | Function ≤ 60 lines                      | `FunctionTooLong`                | `max-lines-per-function`                                  | `clippy::too_many_lines` |
| ASP202 | Assertion density ≥ 2 per function       | `LowAssertionDensity`            | `aspergillus/asp202-min-assertions` (custom)              | Manual (planned dylint rule) |
| ASP203 | No global mutable state                  | `GlobalMutableState`             | `no-restricted-syntax` (module-level `let`/`var`/`export let`) | Language (no safe `static mut`) |
| ASP204 | No unbounded loops                       | `UnboundedLoop`                  | `functional/no-loop-statements` (strict; revisit)         | Manual (prefer iterators) |
| ASP205 | No impure functions outside I/O boundary | `ImpureFunction`                 | `eslint-plugin-boundaries` *(planned)*                    | Module structure (pure core) |
| ASP206 | Functional core / imperative shell       | `MixedIOAndLogic`                | `eslint-plugin-boundaries` *(planned)*                    | Module structure |
```

- [ ] **Step 2: Add a "TypeScript Level 2 — design notes" subsection**

Insert after the Level 2 table, before the Level 3 table:

```markdown
#### TypeScript Level 2 — design notes

- **ASP202 (assertion density):** Originally specified as "manual code review" because no off-the-shelf TS rule exists. Aspergillus 0.1.0-rc.2 ships its own `asp202-min-assertions` rule via the `./eslint-rules` plugin export. Default behavior: skip functions under 10 lines; require ≥2 assertion-like calls (`assert`, `invariant`, `console.assert`, `assert.X`); configurable via rule options.

- **ASP203 (no global mutable state):** Implemented via `no-restricted-syntax` patterns banning module-level `let`/`var` and `export let`/`export var`. This is narrower than the original `functional/no-let` mapping — local `let` inside functions remains allowed, matching NASA's actual "global mutable state" intent rather than a blanket ban on `let`.

- **ASP204 (no unbounded loops):** NASA's rule requires loops to have a statically-determinable iteration bound (no `while(true)`). There is no off-the-shelf ESLint rule for that predicate, so the current implementation uses `functional/no-loop-statements` — which bans **all** loops, including bounded `for(let i=0; i<N; i++)`. This is a strict over-approximation chosen because it lands at `warn` and surfaces something useful. **To revisit:** replace with a custom `aspergillus/asp204-bounded-loops` rule that detects only unbounded loop patterns (`while(true)`, `for(;;)`, `while(condition)` where condition isn't statically bounded). Tracked under the next aspergillus TS milestone.
```

- [ ] **Step 3: Commit**

```bash
git add docs/design.md
git commit -m "docs(design): record TS L2 rule mapping; note ASP204 to revisit"
```

---

## Task 13: Final verification

**Files:** none (verification step)

- [ ] **Step 1: Run the full test suite one more time**

Run: `npm test && cd typescript/cli && bun test && cd -`

Expected: all green.

- [ ] **Step 2: Verify `npm pack --dry-run` shows the right files**

Run: `npm pack --dry-run 2>&1 | tail -40`

Expected (per Task 9 step 6): rules dir present, test files absent.

- [ ] **Step 3: Verify the published config actually loads against a consumer-style fixture**

Create `/tmp/aspergillus-smoke/` with a minimal package and config that imports from a tarball pack of the local repo:

```bash
SMOKE=/tmp/aspergillus-smoke
rm -rf "$SMOKE" && mkdir -p "$SMOKE"
npm pack --pack-destination "$SMOKE"
cd "$SMOKE"
mv afdudley-aspergillus-0.1.0-rc.2.tgz aspergillus.tgz
cat > package.json <<'EOF'
{
  "name": "smoke",
  "version": "1.0.0",
  "type": "module",
  "private": true
}
EOF
npm install --no-audit --no-fund \
  ./aspergillus.tgz \
  @eslint/js typescript-eslint eslint-plugin-import \
  eslint-plugin-unused-imports eslint-plugin-functional \
  eslint-config-prettier eslint prettier typescript
cat > eslint.config.js <<'EOF'
import base from '@afdudley/aspergillus/eslint-config';
export default [...base];
EOF
cat > smoke.js <<'EOF'
let bad = 1; // ASP203
function tooLongFn() {
  // ASP201 — over 60 lines if the body is padded; here it's
  // ASP202 — zero assertions in a non-trivial function instead.
  const a = 1;
  const b = 2;
  const c = 3;
  const d = 4;
  const e = 5;
  const f = 6;
  const g = 7;
  return a + b + c + d + e + f + g;
}
for (let i = 0; i < 10; i++) { console.log(i); } // ASP204
EOF
npx eslint smoke.js 2>&1 | tee /tmp/smoke.log
```

Expected: at least one warning each for ASP202, ASP203, and ASP204 in the output.

- [ ] **Step 4: Clean up smoke test**

Run: `rm -rf /tmp/aspergillus-smoke /tmp/smoke.log`

- [ ] **Step 5: Don't push**

Per the user's standing instruction (memory: "Never push. Only commit."), the branch stays local. Hand off to the user for review and push.

---

## Out-of-scope follow-ups (track as separate plans)

1. **ASP205/206 — `eslint-plugin-boundaries` integration.** Needs a per-consumer architectural-element design conversation. Requires consumers to declare what counts as `core/` vs `infra/` vs `app/`. Aspergillus can ship a template config plus documented elements convention.

2. **ASP301 — no-throw + neverthrow.** Adds peer deps `eslint-plugin-functional` already in place, plus `@okee-tech/neverthrow/must-consume-result` (or `eslint-plugin-neverthrow`). Lands at warn.

3. **ASP302 — no Optional/None return.** No off-the-shelf rule exists. Custom rule like `aspergillus/asp302-no-optional-return` that flags function return types containing `| undefined` or `| null` (excluding type guards / explicit nullable APIs). Lands at warn.

4. **Custom `aspergillus/asp204-bounded-loops` rule.** Replaces `functional/no-loop-statements`. Detects `while(true)`, `for(;;)`, and (best-effort) loops whose condition isn't statically bounded.

5. **Consumer severity-flip PRs in TrashScan-Explorer** for each rule landed in this PR, in priority order (already documented in the previous review pass): `no-floating-promises` first, then `import/order`, then `no-param-reassign`, then ASP201–204 cleanup as their counts reach zero.
