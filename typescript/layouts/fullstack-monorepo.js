// ASP205/206 boundary layout for full-stack TypeScript monorepos with
// server/ and client/ subtrees plus a top-level shared/.
//
// Requires (installed automatically by `aspergillus-ts init --layout=fullstack-monorepo`):
//   eslint-plugin-boundaries     — architectural enforcement
//   eslint-import-resolver-typescript — maps .js-extension imports to .ts source files
//
// Server elements:
//   server/core/     — pure logic
//   server/db/       — data access
//   server/services/ — I/O wrappers (DB, external APIs)
//   server/routes/   — HTTP shell
//
// Client elements:
//   client/shared/     — client-only pure utilities
//   client/services/   — API clients, storage adapters
//   client/components/ — pure render
//   client/pages/      — page-level shell composing components + services
//
// Top-level:
//   shared/ — types/utils shared between server and client (pure only)

import boundaries from 'eslint-plugin-boundaries';

export default {
  files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
  plugins: { boundaries },
  settings: {
    // Order matters for overlapping patterns: eslint-plugin-boundaries v6
    // (@boundaries/elements v2) uses full-path matching when mode:'full' is
    // set, and resolves ties by first-match-wins within the elements array.
    // client-shared and shared both match **/shared/** paths, so client-shared
    // must appear BEFORE shared, and both use mode:'full' to force full-path
    // evaluation rather than incremental path-segment accumulation.
    'boundaries/elements': [
      { type: 'server-core', pattern: '**/server/core/**' },
      { type: 'server-db', pattern: '**/server/db/**' },
      { type: 'server-services', pattern: '**/server/services/**' },
      { type: 'server-routes', pattern: '**/server/routes/**' },
      { type: 'client-shared', pattern: '**/client/shared/**', mode: 'full' },
      { type: 'client-services', pattern: '**/client/services/**' },
      { type: 'client-components', pattern: '**/client/components/**' },
      { type: 'client-pages', pattern: '**/client/pages/**' },
      { type: 'shared', pattern: '**/shared/**', mode: 'full' },
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
          { from: { type: 'server-core' }, allow: { to: { type: ['server-core', 'shared'] } } },
          { from: { type: 'server-db' }, allow: { to: { type: ['server-db', 'shared'] } } },
          { from: { type: 'server-services' }, allow: { to: { type: ['server-services', 'server-db', 'server-core', 'shared'] } } },
          { from: { type: 'server-routes' }, allow: { to: { type: ['server-routes', 'server-services', 'server-core', 'shared'] } } },
          { from: { type: 'client-shared' }, allow: { to: { type: ['client-shared', 'shared'] } } },
          { from: { type: 'client-services' }, allow: { to: { type: ['client-services', 'client-shared', 'shared'] } } },
          { from: { type: 'client-components' }, allow: { to: { type: ['client-components', 'client-shared', 'shared'] } } },
          { from: { type: 'client-pages' }, allow: { to: { type: ['client-pages', 'client-components', 'client-services', 'client-shared', 'shared'] } } },
        ],
      },
    ],
  },
};
