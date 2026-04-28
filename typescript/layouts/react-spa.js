// ASP205/206 boundary layout for React/Vite single-page apps.
//
// Requires (installed automatically by `aspergillus-ts init --layout=react-spa`):
//   eslint-plugin-boundaries     — architectural enforcement
//   eslint-import-resolver-typescript — maps .js-extension imports to .ts source files
//
// Elements:
//   shared/     — pure utilities, types, hooks-without-IO.
//   services/   — API clients, storage adapters, I/O boundary.
//   components/ — pure render of props.
//   pages/      — compose components + services. Top-level shell.

import boundaries from 'eslint-plugin-boundaries';

export default {
  files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
  plugins: { boundaries },
  settings: {
    // Order matters: eslint-plugin-boundaries uses first-match-wins. The
    // catch-all shared/ must appear LAST so it does not shadow other patterns.
    'boundaries/elements': [
      { type: 'services', pattern: '**/services/**' },
      { type: 'components', pattern: '**/components/**' },
      { type: 'pages', pattern: '**/pages/**' },
      { type: 'shared', pattern: '**/shared/**' },
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
          { from: { type: 'shared' }, allow: { to: { type: 'shared' } } },
          { from: { type: 'services' }, allow: { to: { type: ['services', 'shared'] } } },
          { from: { type: 'components' }, allow: { to: { type: ['components', 'shared'] } } },
          { from: { type: 'pages' }, allow: { to: { type: ['pages', 'components', 'services', 'shared'] } } },
        ],
      },
    ],
  },
};
