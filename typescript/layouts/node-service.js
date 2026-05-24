// ASP205/206 boundary layout for Node.js services (Express/Fastify + DB).
//
// Requires (installed automatically by `aspergillus-ts init --layout=node-service`):
//   eslint-plugin-boundaries     — architectural enforcement
//   eslint-import-resolver-typescript — maps .js-extension imports to .ts source files
//
// Elements (matched via path pattern; common synonyms accepted):
//   core      — pure logic. Matches `core/**` or `lib/**` (any nesting).
//   db        — data access. Matches `db/**` or `repositories/**`.
//   services  — I/O wrappers. Matches `services/**`.
//   routes    — HTTP shell. Matches `routes/**`, `controllers/**`, or `handlers/**`.
//
// Patterns use `**/<dir>/**` so they match whether the project nests under
// `src/` or not. Type-only imports are allowed across any boundary because
// they are erased at compile time and don't constitute runtime coupling.
//
// Lands the boundaries/dependencies rule at `warn`. Override or extend
// by appending a later flat-config block in your eslint.config.js.

import boundaries from 'eslint-plugin-boundaries';

const elements = [
  { type: 'core', pattern: ['**/core/**', '**/lib/**'] },
  { type: 'db', pattern: ['**/db/**', '**/repositories/**'] },
  { type: 'services', pattern: '**/services/**' },
  { type: 'routes', pattern: ['**/routes/**', '**/controllers/**', '**/handlers/**'] },
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
            // Type-only imports are allowed everywhere — they're stripped at
            // compile time and don't create runtime coupling.
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

  // Block 2: L3 functional-core — core, lib, db, repositories, services.
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

  // Block 3: L3 imperative-shell — routes/controllers/handlers throw HTTP
  // errors and catch from third-party libs. Layer-correct.
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
