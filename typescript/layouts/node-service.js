// ASP205/206 boundary layout for Node.js services (Express/Fastify + DB).
//
// Requires (installed automatically by `aspergillus-ts init --layout=node-service`):
//   eslint-plugin-boundaries     — architectural enforcement
//   eslint-import-resolver-typescript — maps .js-extension imports to .ts source files
//
// Elements (matched via path pattern):
//   core/     — pure logic. No I/O imports.
//   db/       — data access. Imports core.
//   services/ — I/O wrappers. Imports db + core.
//   routes/   — HTTP shell. Imports services + core (NOT db directly).
//
// Lands the boundaries/dependencies rule at `warn`. Override or extend
// by appending a later flat-config block in your eslint.config.js.

import boundaries from 'eslint-plugin-boundaries';

export default {
  files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
  plugins: { boundaries },
  settings: {
    'boundaries/elements': [
      { type: 'core', pattern: '**/core/**' },
      { type: 'db', pattern: '**/db/**' },
      { type: 'services', pattern: '**/services/**' },
      { type: 'routes', pattern: '**/routes/**' },
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
          { from: { type: 'db' }, allow: { to: { type: ['db', 'core'] } } },
          { from: { type: 'services' }, allow: { to: { type: ['services', 'db', 'core'] } } },
          { from: { type: 'routes' }, allow: { to: { type: ['routes', 'services', 'core'] } } },
        ],
      },
    ],
  },
};
