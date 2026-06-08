// Aspergillus reference ESLint flat config — Level 1 + Level 2 + Level 3
// (universal rules).
//
// Consumers import and spread this from their repo's eslint.config.js:
//
//   import base from '../vendor/aspergillus/typescript/configs/eslint.config.js';
//   export default [...base, /* repo-specific overrides */];
//
// Level 2 rules (ASP201–204) and Level 3 rules (ASP301–302) land at
// warn per the severity-flip workflow. The layer-stratified L3 rule
// (`functional/no-throw-statements`) is shipped via the layouts in
// `typescript/layouts/` — see docs/design-decisions/2026-05-08-l3-
// error-handling-mechanism.md.
//
// Required peer devDependencies (install in the consumer repo). These are
// the same list `aspergillus-ts init` prints after it runs:
//   eslint prettier typescript
//   @eslint/js typescript-eslint eslint-plugin-import
//   eslint-plugin-unused-imports eslint-plugin-functional
//   @okee-tech/eslint-plugin-neverthrow
//   eslint-config-prettier
//
// Adoption workflow: every new rule lands at "warn", flips to "error"
// in a dedicated PR once violations reach zero. See typescript/README.md.

import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import importPlugin from 'eslint-plugin-import';
import functional from 'eslint-plugin-functional';
import neverthrow from '@okee-tech/eslint-plugin-neverthrow';
import unusedImports from 'eslint-plugin-unused-imports';
import prettierConfig from 'eslint-config-prettier';
import aspergillus from '../rules/index.js';

export default [
  {
    ignores: [
      'dist/**',
      'build/**',
      'node_modules/**',
      'coverage/**',
      '.next/**',
      '.expo/**',
      // Subtree-model: consumers pull aspergillus into vendor/ and should
      // not be linting its internal sources. Also covers generic vendor
      // dirs in any other convention.
      'vendor/**',
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
      // Type-aware linting — required by rules like
      // `@typescript-eslint/no-floating-promises`. `projectService` auto-
      // discovers the nearest tsconfig.json from cwd, so consumers don't
      // need to hard-code a tsconfigRootDir.
      parserOptions: {
        projectService: true,
      },
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

  // Level 2 — lands at warn pending severity-flip. Each rule flips to
  // `error` in a dedicated PR once the consumer has zero violations.
  {
    files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    plugins: {
      aspergillus,
      functional,
    },
    rules: {
      // ASP201 — function too long. NASA Power of 10 #4: ≤60 lines.
      'max-lines-per-function': [
        'warn',
        { max: 60, skipBlankLines: true, skipComments: true, IIFEs: true },
      ],

      // ASP203 — no global mutable state. NASA Power of 10 #6 (narrowed):
      // bans module-level mutable bindings and mutable exports. Local
      // `let` inside functions is intentionally allowed — the rule's
      // intent is global, not lexical, immutability.
      //
      // Lands at `error`: the rule's scope is narrow and the fix is
      // mechanical (wrap state in a const-bound object), so the
      // standard severity-flip warm-up phase isn't needed. To temporarily
      // demote during a cleanup branch, restate the full rule array
      // with `'warn'` — flat-config replaces the whole array, so
      // severity-only overrides clear the selectors and disable the rule.
      'no-restricted-syntax': [
        'error',
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

      // ASP204 — no unbounded loops. NASA Power of 10 #2 calls for a
      // statically-determinable iteration bound. There is no off-the-
      // shelf rule for that exact predicate, so we use the strict
      // approximation `no-loop-statements` (bans all loops). Lands at
      // warn so consumers can audit loops case-by-case; replace with a
      // more precise rule when one exists. See docs/design.md ASP204.
      'functional/no-loop-statements': 'warn',

      // ASP202 — assertion density. Custom rule shipped by aspergillus;
      // see typescript/rules/asp202-min-assertions.js.
      'aspergillus/asp202-min-assertions': 'warn',
    },
  },

  // Level 3 — universal rules. Lands at warn pending severity-flip.
  // The layer-stratified L3 rule (`functional/no-throw-statements`) lives
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
      // `if (result)` ambiguity (truthy on a Result object always,
      // since neverthrow's Result is a non-empty object). Forces
      // explicit `result.isOk()` etc.
      '@typescript-eslint/strict-boolean-expressions': 'warn',
    },
  },

  // Keep Prettier last so it disables conflicting formatting rules.
  prettierConfig,
];
