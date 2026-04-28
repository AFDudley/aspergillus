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

export default {
  files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
  plugins: { boundaries },
  settings: {
    'boundaries/elements': [
      { type: 'core', pattern: ['**/core/**', '**/lib/**'] },
      { type: 'infra', pattern: ['**/infra/**', '**/services/**'] },
      { type: 'app', pattern: '**/app/**' },
    ],
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
};
