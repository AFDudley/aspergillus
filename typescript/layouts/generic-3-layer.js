// ASP205/206 boundary layout — minimal viable FC/IS. Use when no other
// preset fits. Consumers can refine later by switching to a more
// specific layout or by appending an override block.
//
// Requires (installed automatically by `aspergillus-ts init --layout=generic-3-layer`):
//   eslint-plugin-boundaries     — architectural enforcement
//   eslint-import-resolver-typescript — maps .js-extension imports to .ts source files
//
// Elements (common synonyms accepted):
//   core   — pure logic. Matches `core/**` or `lib/**`.
//   infra  — I/O boundary (DB, HTTP, fs, etc.). Matches `infra/**` or
//            `services/**`.
//   app    — imperative shell composing core + infra. Matches `app/**`.
//
// Type-only imports are allowed across any boundary.

import boundaries from 'eslint-plugin-boundaries';

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
  // workflow). Universal L3 rules (must-consume-result,
  // strict-boolean-expressions) live in the base config since they apply
  // regardless of layer.
  {
    files: [
      '**/core/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/lib/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/infra/**/*.{ts,tsx,js,jsx,mjs,cjs}',
      '**/services/**/*.{ts,tsx,js,jsx,mjs,cjs}',
    ],
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
