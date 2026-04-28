// ASP205/206 boundary layout for React/Vite single-page apps.
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
    'boundaries/elements': [
      { type: 'shared', pattern: '**/shared/**' },
      { type: 'services', pattern: '**/services/**' },
      { type: 'components', pattern: '**/components/**' },
      { type: 'pages', pattern: '**/pages/**' },
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
          { from: ['services'], allow: ['services', 'shared'] },
          { from: ['components'], allow: ['components', 'shared'] },
          { from: ['pages'], allow: ['pages', 'components', 'services', 'shared'] },
        ],
      },
    ],
  },
};
