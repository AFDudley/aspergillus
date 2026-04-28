// ASP205/206 boundary layout for React Native apps. Modeled on the
// mtm code-quality.md pattern.
//
// Requires (installed automatically by `aspergillus-ts init --layout=rn-app`):
//   eslint-plugin-boundaries     — architectural enforcement
//   eslint-import-resolver-typescript — maps .js-extension imports to .ts source files
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
          { from: { type: 'services' }, allow: { to: { type: ['services', 'core'] } } },
          { from: { type: 'hooks' }, allow: { to: { type: ['hooks', 'services', 'core'] } } },
          { from: { type: 'components' }, allow: { to: { type: ['components', 'core'] } } },
          { from: { type: 'screens' }, allow: { to: { type: ['screens', 'hooks', 'components', 'core'] } } },
        ],
      },
    ],
  },
};
