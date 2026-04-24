// Aspergillus reference ESLint flat config — Level 1 baseline.
//
// Consumers import and spread this from their repo's eslint.config.js:
//
//   import base from '../vendor/aspergillus/typescript/configs/eslint.config.js';
//   export default [...base, /* repo-specific overrides */];
//
// Level 2 and Level 3 rules are appended by follow-up work; this file
// currently enforces only the Level 1 baseline (external-tool tier).
//
// Required peer devDependencies (install in the consumer repo). These are
// the same list `aspergillus-ts init` prints after it runs:
//   eslint prettier typescript
//   @eslint/js typescript-eslint eslint-plugin-import
//   eslint-plugin-unused-imports eslint-config-prettier
//
// Adoption workflow: every new rule lands at "warn", flips to "error"
// in a dedicated PR once violations reach zero. See typescript/README.md.

import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import importPlugin from 'eslint-plugin-import';
import unusedImports from 'eslint-plugin-unused-imports';
import prettierConfig from 'eslint-config-prettier';

export default [
  {
    ignores: [
      'dist/**',
      'build/**',
      'node_modules/**',
      'coverage/**',
      '.next/**',
      '.expo/**',
    ],
  },

  js.configs.recommended,
  ...tseslint.configs.recommended,

  {
    files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    plugins: {
      import: importPlugin,
      'unused-imports': unusedImports,
    },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      // Type-aware linting — required by rules like
      // `@typescript-eslint/no-floating-promises`. `projectService` auto-
      // discovers the nearest tsconfig.json from cwd, so consumers don't
      // need to hard-code a tsconfigRootDir.
      parserOptions: {
        projectService: true,
      },
    },
    rules: {
      // Level 1 baseline — lands at error.
      'no-var': 'error',
      'no-param-reassign': 'error',
      '@typescript-eslint/no-floating-promises': 'error',
      'unused-imports/no-unused-imports': 'error',
      'import/no-cycle': 'error',
      'import/order': [
        'error',
        {
          groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
          'newlines-between': 'always',
          alphabetize: { order: 'asc', caseInsensitive: true },
        },
      ],

      // Level 1 baseline — lands at warn (promotes at Level 2).
      '@typescript-eslint/no-explicit-any': 'warn',
      'no-console': ['warn', { allow: ['warn', 'error'] }],
    },
  },

  // Keep Prettier last so it disables conflicting formatting rules.
  prettierConfig,
];
