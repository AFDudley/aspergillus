// ASP205/206 boundary layout for full-stack TypeScript monorepos with
// server/ and client/ subtrees plus a top-level shared/.
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
    'boundaries/elements': [
      { type: 'shared', pattern: '**/shared/**' },
      { type: 'server-core', pattern: '**/server/core/**' },
      { type: 'server-db', pattern: '**/server/db/**' },
      { type: 'server-services', pattern: '**/server/services/**' },
      { type: 'server-routes', pattern: '**/server/routes/**' },
      { type: 'client-shared', pattern: '**/client/shared/**' },
      { type: 'client-services', pattern: '**/client/services/**' },
      { type: 'client-components', pattern: '**/client/components/**' },
      { type: 'client-pages', pattern: '**/client/pages/**' },
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
          { from: ['shared'], allow: ['shared'] },
          { from: ['server-core'], allow: ['server-core', 'shared'] },
          { from: ['server-db'], allow: ['server-db', 'shared'] },
          { from: ['server-services'], allow: ['server-services', 'server-db', 'server-core', 'shared'] },
          { from: ['server-routes'], allow: ['server-routes', 'server-services', 'server-core', 'shared'] },
          { from: ['client-shared'], allow: ['client-shared', 'shared'] },
          { from: ['client-services'], allow: ['client-services', 'client-shared', 'shared'] },
          { from: ['client-components'], allow: ['client-components', 'client-shared', 'shared'] },
          { from: ['client-pages'], allow: ['client-pages', 'client-components', 'client-services', 'client-shared', 'shared'] },
        ],
      },
    ],
  },
};
