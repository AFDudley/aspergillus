// ASP205/206 boundary layout for full-stack TypeScript monorepos with
// server/ and client/ subtrees plus a top-level shared/.
//
// Requires (installed automatically by `aspergillus-ts init --layout=fullstack-monorepo`):
//   eslint-plugin-boundaries     — architectural enforcement
//   eslint-import-resolver-typescript — maps .js-extension imports to .ts source files
//
// Patterns are deliberately permissive: each element accepts common aliases
// and tolerates `src/` nesting (e.g., `client/src/components/` is matched
// the same as `client/components/`).
//
// Server elements:
//   server-core      — `server/**/core/**` or `server/**/lib/**`. Pure logic.
//   server-db        — `server/**/db/**` or `server/**/repositories/**`.
//   server-services  — `server/**/services/**`.
//   server-routes    — `server/**/{routes,controllers,handlers}/**`.
//
// Client elements:
//   client-shared      — `client/**/{lib,shared}/**`. Pure utilities.
//   client-services    — `client/**/{services,api}/**`. I/O.
//   client-hooks       — `client/**/hooks/**`. Imperative shell with state.
//   client-components  — `client/**/components/**`. Render of props.
//   client-pages       — `client/**/{pages,app}/**`. Top-level shell.
//
// Top-level:
//   shared — `shared/**` (project root only). Types/utils shared between
//            server and client (pure only).
//
// Type-only imports are allowed across any boundary because they're erased
// at compile time and don't create runtime coupling.

import boundaries from 'eslint-plugin-boundaries';

export default {
  files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
  plugins: { boundaries },
  settings: {
    // Order matters: eslint-plugin-boundaries v6 uses first-match-wins for
    // overlapping patterns. The project-root `shared/` element is anchored
    // (no leading `**/`) and uses `mode: 'full'` so it only matches the
    // top-level shared/ directory and never collides with a `client/shared/`
    // or similar nested directory.
    'boundaries/elements': [
      { type: 'server-core', pattern: ['**/server/**/core/**', '**/server/**/lib/**'] },
      { type: 'server-db', pattern: ['**/server/**/db/**', '**/server/**/repositories/**'] },
      { type: 'server-services', pattern: '**/server/**/services/**' },
      { type: 'server-routes', pattern: ['**/server/**/routes/**', '**/server/**/controllers/**', '**/server/**/handlers/**'] },
      { type: 'client-shared', pattern: ['**/client/**/lib/**', '**/client/**/shared/**'] },
      { type: 'client-services', pattern: ['**/client/**/services/**', '**/client/**/api/**'] },
      { type: 'client-hooks', pattern: '**/client/**/hooks/**' },
      { type: 'client-components', pattern: '**/client/**/components/**' },
      { type: 'client-pages', pattern: ['**/client/**/pages/**', '**/client/**/app/**'] },
      { type: 'shared', pattern: 'shared/**', mode: 'full' },
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
          { from: { type: 'server-core' }, allow: { to: { type: ['server-core', 'shared'] } } },
          { from: { type: 'server-db' }, allow: { to: { type: ['server-db', 'server-core', 'shared'] } } },
          { from: { type: 'server-services' }, allow: { to: { type: ['server-services', 'server-db', 'server-core', 'shared'] } } },
          { from: { type: 'server-routes' }, allow: { to: { type: ['server-routes', 'server-services', 'server-core', 'shared'] } } },
          { from: { type: 'client-shared' }, allow: { to: { type: ['client-shared', 'shared'] } } },
          { from: { type: 'client-services' }, allow: { to: { type: ['client-services', 'client-shared', 'shared'] } } },
          { from: { type: 'client-hooks' }, allow: { to: { type: ['client-hooks', 'client-services', 'client-shared', 'shared'] } } },
          // Components may use hooks for state — idiomatic React.
          { from: { type: 'client-components' }, allow: { to: { type: ['client-components', 'client-hooks', 'client-shared', 'shared'] } } },
          { from: { type: 'client-pages' }, allow: { to: { type: ['client-pages', 'client-components', 'client-hooks', 'client-services', 'client-shared', 'shared'] } } },
        ],
      },
    ],
  },
};
