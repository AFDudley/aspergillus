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
