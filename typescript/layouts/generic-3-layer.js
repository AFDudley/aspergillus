// ASP205/206 boundary layout — minimal viable FC/IS. Use when no other
// preset fits. Consumers can refine later by switching to a more
// specific layout or by appending an override block.
//
// Requires (installed automatically by `aspergillus-ts init --layout=generic-3-layer`):
//   eslint-plugin-boundaries     — architectural enforcement
//   eslint-import-resolver-typescript — maps .js-extension imports to .ts source files
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
          { from: { type: 'core' }, allow: { to: { type: 'core' } } },
          { from: { type: 'infra' }, allow: { to: { type: ['infra', 'core'] } } },
          { from: { type: 'app' }, allow: { to: { type: ['app', 'infra', 'core'] } } },
        ],
      },
    ],
  },
};
