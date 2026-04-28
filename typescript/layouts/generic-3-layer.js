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
