// ASP205/206 boundary layout for Node.js services (Express/Fastify + DB).
//
// Elements (matched via path pattern):
//   core/     — pure logic. No I/O imports.
//   db/       — data access. Imports core.
//   services/ — I/O wrappers. Imports db + core.
//   routes/   — HTTP shell. Imports services + core (NOT db directly).
//
// Lands the boundaries/element-types rule at `warn`. Override or extend
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
  },
  rules: {
    'boundaries/element-types': [
      'warn',
      {
        default: 'disallow',
        rules: [
          { from: ['core'], allow: ['core'] },
          { from: ['db'], allow: ['db', 'core'] },
          { from: ['services'], allow: ['services', 'db', 'core'] },
          { from: ['routes'], allow: ['routes', 'services', 'core'] },
        ],
      },
    ],
  },
};
