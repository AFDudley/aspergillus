// ASP205/206 boundary layout for React/Vite single-page apps.
//
// Requires (installed automatically by `aspergillus-ts init --layout=react-spa`):
//   eslint-plugin-boundaries     — architectural enforcement
//   eslint-import-resolver-typescript — maps .js-extension imports to .ts source files
//
// Elements (common synonyms accepted):
//   shared     — pure utilities, types, hooks-without-IO. Matches
//                `lib/**` or `shared/**`.
//   services   — API clients, storage adapters, I/O boundary. Matches
//                `services/**` or `api/**`.
//   hooks      — imperative shell with React state. Calls services.
//   components — pure-ish render of props. May use hooks for state.
//   pages      — top-level shell composing components + services.
//                Matches `pages/**` or `app/**` (Next.js App Router).
//
// Patterns use `**/<dir>/**` so they match whether the project nests under
// `src/` or not. Type-only imports are allowed across any boundary.

import boundaries from 'eslint-plugin-boundaries';

export default {
  files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
  plugins: { boundaries },
  settings: {
    // Order matters: eslint-plugin-boundaries uses first-match-wins. The
    // catch-all shared/lib element must appear LAST so it does not shadow
    // more specific patterns.
    'boundaries/elements': [
      { type: 'services', pattern: ['**/services/**', '**/api/**'] },
      { type: 'hooks', pattern: '**/hooks/**' },
      { type: 'components', pattern: '**/components/**' },
      { type: 'pages', pattern: ['**/pages/**', '**/app/**'] },
      { type: 'shared', pattern: ['**/lib/**', '**/shared/**'] },
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
          { from: { type: 'shared' }, allow: { to: { type: 'shared' } } },
          { from: { type: 'services' }, allow: { to: { type: ['services', 'shared'] } } },
          { from: { type: 'hooks' }, allow: { to: { type: ['hooks', 'services', 'shared'] } } },
          // Components may use hooks for state — idiomatic React.
          { from: { type: 'components' }, allow: { to: { type: ['components', 'hooks', 'shared'] } } },
          { from: { type: 'pages' }, allow: { to: { type: ['pages', 'components', 'hooks', 'services', 'shared'] } } },
        ],
      },
    ],
  },
};
