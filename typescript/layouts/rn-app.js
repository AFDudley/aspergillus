// ASP205/206 boundary layout for React Native apps.
//
// Requires (installed automatically by `aspergillus-ts init --layout=rn-app`):
//   eslint-plugin-boundaries     — architectural enforcement
//   eslint-import-resolver-typescript — maps .js-extension imports to .ts source files
//
// Elements (common synonyms accepted):
//   core       — pure functions. Matches `core/**` or `lib/**`.
//   services   — I/O boundary. Matches `services/**` or `api/**`.
//   hooks      — imperative shell. Calls services, manages React state.
//   components — pure-ish render of props. May use hooks for state.
//   screens    — compose hooks + components. Thin wiring.
//
// Patterns use `**/<dir>/**` so they match whether the project nests under
// `src/` or not. Type-only imports are allowed across any boundary.

import boundaries from 'eslint-plugin-boundaries';

const elements = [
  { type: 'core', pattern: ['**/core/**', '**/lib/**'] },
  { type: 'services', pattern: ['**/services/**', '**/api/**'] },
  { type: 'hooks', pattern: '**/hooks/**' },
  { type: 'components', pattern: '**/components/**' },
  { type: 'screens', pattern: '**/screens/**' },
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
            { from: { type: 'services' }, allow: { to: { type: ['services', 'core'] } } },
            { from: { type: 'hooks' }, allow: { to: { type: ['hooks', 'services', 'core'] } } },
            // Components may use hooks for state — that's idiomatic React.
            { from: { type: 'components' }, allow: { to: { type: ['components', 'hooks', 'core'] } } },
            { from: { type: 'screens' }, allow: { to: { type: ['screens', 'hooks', 'components', 'core'] } } },
          ],
        },
      ],
    },
  },

  // Block 2: L3 functional-core — core, lib, services, api.
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

  // Block 3: L3 imperative-shell — hooks/components/screens.
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
